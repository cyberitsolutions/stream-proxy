import base64
import functools
import http
import http.server
import pathlib
import sys
import time
import urllib.parse
import urllib.request

import yt_dlp
import systemd

from . import inputs
from . import outputs
from . import http_resources


_tuned_streams = {}
acceptable_input_addresses = []  # default is accept all

yt = yt_dlp.YoutubeDL()


def get_stream_playback_url(b64_input_address: str):
    """Get a direct videoplayback URL for the given stream ID."""
    stream_url = base64.urlsafe_b64decode(b64_input_address).decode()
    stream_info = yt.extract_info(stream_url, download=False)
    # FIXME: I have no idea what this 'https' protocol actually means, the URL mentioned Android, but I think they all do
    # FIXME: HLS/DASH/etc is a better protocol for this kind of thing, I just didn't make sense of their entry in this list
    # FIXME: Don't just grab the highest quality, our users likely only have 720p screens anyway
    format_info = sorted([f for f in stream_info['formats'] if f['protocol'] == 'https'], key=lambda i: i['height'])[-1]
    return format_info['url']


def _maybe_tune_stream(b64_input_address: str, output_directory: pathlib.Path):
    """Tune in to stream if not already tuned in."""
    return True  # FIXME: DEV
    if b64_input_address not in _tuned_streams or \
            _tuned_streams[b64_input_address][0].poll() is not None:
        # I tried using urllib.parse.quote() but that was painful to find the right URL for the browser given the nested quoting.
        # Base64 is a bit annoying since it expects bytes not strings, but was the easiest to make work.
        input_address = base64.urlsafe_b64decode(b64_input_address).decode()

        if acceptable_input_addresses and input_address not in acceptable_input_addresses:
            print("Refusing to start unacceptable stream for", input_address)
            return False

        print("Starting streaming processes for", input_address)

        input_proc = inputs.autoselect(input_address)
        output_proc = outputs.hls(input_proc.stdout, output_directory)

        # Wait up to 5s for the master.m3u8 file to appear
        # FIXME: also check both processes for an exit status?
        delay_start = time.monotonic()
        while time.monotonic() < (delay_start + 5) and not (output_directory / 'master.m3u8').exists():
            time.sleep(0.5)

        # FIXME: Use a named tuple or something more self-documented than relying on the order of the tuple?
        _tuned_streams[b64_input_address] = (input_proc, output_proc, output_directory)
    else:
        pass

    return True


# NOTE: There is a new instance of this class for every single request
class RequestHandler(http.server.SimpleHTTPRequestHandler):
    """Handle the stream proxying for a single HTTP connection."""

    def __init__(self, *args, directory: pathlib.Path, **kwargs):
        # NOTE: Py3.9 has a self.directory variable which gets recast as a str,
        #       This was causing me problems as I couldn't stop the super().__init__ function from recasting it.
        #       So I renamed my own version of it, it's only used in translate_path anyway (which I also rewrote).
        #       I'm making sure to set it properly anyway, just in case.
        assert directory.is_absolute()
        super().__init__(*args, directory=str(directory), **kwargs)

    def translate_path(self, path: str):
        """Wrap translate_path to get some always-available resources from the root of the working directory."""
        # pathlib.Path will lose the trailing slash and is_dir() only works if the path actually exists on the fs.
        # So there's this slightly messy process to add 'index.html' onlny if the original path string ended with '/'
        path_str = super().translate_path(path)
        if path_str.endswith('/'):
            path = pathlib.Path(path_str).joinpath('index.html')
        else:
            path = pathlib.Path(path_str)

        working_directory = pathlib.Path(self.directory)

        # FIXME: Should we just drop this try/except and trust that the upstream http.server code handles this properly?
        try:
            if working_directory / pathlib.Path(path).relative_to(working_directory) != path:
                # This shouldn't actually happen because it happening at all should trigger the exception below
                print("Someone *might* be trying to browse outside of the working directory:", str(path), file=sys.stderr)
                self.send_error(http.HTTPStatus.FORBIDDEN, "That looks naughty")
        except ValueError as e:
            # ValueError: '...' is not in the subpath of '...' OR one path is relative and the other is absolute.
            print('ValueError:', e, file=sys.stderr)
            self.send_error(http.HTTPStatus.FORBIDDEN, "That was very naughty")

        if path.name == 'index.html':
            stream_id = str(path.parent.relative_to(working_directory))
            try:
                if not _maybe_tune_stream(stream_id, working_directory / stream_id):
                    self.send_error(http.HTTPStatus.FORBIDDEN, "That stream has not been enabled")
            except NotImplementedError:
                self.send_error(http.HTTPStatus.INTERNAL_SERVER_ERROR, "That stream is not currently supported")
            except:  # noqa: E722
                self.send_error(http.HTTPStatus.INTERNAL_SERVER_ERROR, "There was a problem tuning to that stream")
                raise

        if path.name in http_resources.resources_list:
            path = working_directory.joinpath(path.name)

        # Upstream's http.server does not use pathlib objects,
        # so to reduce any chance of issues I'm just going to avoid returning one.
        # FIXME: This should probably use os.fspath instead of str, but that's not available in py3.5
        return str(path)

    def send_head(self):
        """
        Redirect to the stream playback URL for a given query URL.

        For use with browser registered protocol handlers.
        """
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == '/protocol-handler':
            queries = urllib.parse.parse_qs(parsed.query)
            assert len(queries) == 1 and len(queries['url']) == 1, "Bad query keys provided"

            # Browsers have a predefined list of allowed protocol handlers (and 'rtp' is NOT one of them)
            # but do allow for custom protocols so long as they're prefixed with 'web+'.
            # So just remove 'web+' to allow for the browser to add that to any protocol it wants us to handle.
            if queries['url'][0].startswith('web+'):
                stream_url = queries['url'][0][len('web+'):]
            else:
                stream_url = queries['url'][0]
            redir_path = base64.urlsafe_b64encode(stream_url.encode()).decode()

            # Send the actual redirect
            self.send_response(http.HTTPStatus.MOVED_PERMANENTLY)
            self.send_header("Location", "/{}/".format(redir_path))
            self.end_headers()
            return None
        elif parsed.path.endswith('/videoplayback'):
            path = pathlib.Path(self.translate_path(self.path))
            proxied_url = get_stream_playback_url(str(path.parent.relative_to(self.directory)))
            # FIXME: This is 'format_url' as mentioned in the README which we can query via yt-dlp
            # NOTE: We will either have to whitelist this URL in squid, **live** proxy the request in this web server somehow.
            #       Alternatively, if we used HLS/DASH somehow, we could have this web server pass on 1 segment at a time.
            proxied_request = urllib.request.urlopen(proxied_url)
            self.send_response(proxied_request.code)
            # FIXME: How does this handle duplicated headers?
            for header in proxied_request.headers:
                # FIXME: There's probably other headers we'd want to drop.
                # FIXME: Actually we only want to proxy the content-type and content-length headers.
                if header not in ('Cross-Origin-Resource-Policy', 'Accept-Ranges'):
                    self.send_header(header, proxied_request.headers[header])
            # # Using a temporary redirect because YT at least expired their URLs after a short time.
            # # So rather than letting Chromium cache that expired URL, it should always come back and ask again.
            # self.send_response(http.HTTPStatus.TEMPORARY_REDIRECT)
            self.end_headers()
            # self.do_GET just kinda expects send_head here to handle figuring out what file to grab then return a file object.
            return proxied_request
        else:
            return super().send_head()


def start_server(bind_address, working_directory: pathlib.Path):
    """Start the actual HTTP server. Blocks forever."""
    http_resources.install_resources_to(working_directory)

    # FIXME: Should we even bother with this check? It'll fail pretty quickly if we ignore it anyway
    if sys.version_info.major < 3 or (sys.version_info.major == 3 and sys.version_info.minor < 9):
        raise RuntimeError("This requires at least Python 3.9 to work correctly")

    server = http.server.ThreadingHTTPServer

    try:
        with server(bind_address, functools.partial(RequestHandler, directory=working_directory)) as httpd:
            systemd.daemon.notify('READY=1')  # Let systemd know we're ready to go
            httpd.serve_forever()
    finally:
        systemd.daemon.notify('STOPPING=1')  # Let systemd know we're cleaning up
        if _tuned_streams:
            print("Wait a few seconds while I kill off the streaming processes", file=sys.stderr, flush=True)
            for (input_proc, output_proc, output_dir) in _tuned_streams.values():
                # Youtube-dl exits when it can't write to the output anymore
                # Ffmpeg exits when it finishes reading from the input
                # So closing the input pipe should be enough to make them clean themselves up
                input_proc.stdout.close()
                # But lets send a SIGTERM to be sure
                input_proc.terminate()
                output_proc.terminate()
            time.sleep(3)
            for (input_proc, output_proc, output_dir) in _tuned_streams.values():
                # And lets SIGKILL anything still here, to be really sure
                input_proc.kill()
            output_proc.kill()
