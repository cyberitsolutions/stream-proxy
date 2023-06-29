"""Handle the http related endpoints."""
import base64
import functools
import http
import http.server
import pathlib
import sys
import urllib.parse
import urllib.request

import yt_dlp
import systemd

from . import http_resources


acceptable_input_addresses = []  # default is accept all

yt = yt_dlp.YoutubeDL()


# NOTE: There is a new instance of this class for every single request
class RequestHandler(http.server.SimpleHTTPRequestHandler):
    """Handle the stream proxying for a single HTTP connection."""

    def get_stream_playback_url(self, b64_input_address: str):
        """Get a direct videoplayback URL for the given stream ID."""
        stream_url = base64.urlsafe_b64decode(b64_input_address).decode()
        if acceptable_input_addresses and stream_url not in acceptable_input_addresses:
            self.send_error(http.HTTPStatus.FORBIDDEN, "That stream has not been enabled")
        stream_info = yt.extract_info(stream_url, download=False)
        # FIXME: I have no idea what this 'https' protocol actually means, the URL mentioned Android, but I think they all do
        # FIXME: HLS/DASH/etc is a better protocol for this kind of thing, I just haven't make sense of their entry in this list
        # FIXME: Don't just grab the highest quality, our users likely only have 720p screens anyway
        format_info = sorted([f for f in stream_info['formats'] if f['protocol'] == 'https'], key=lambda i: i['height'])[-1]
        return format_info['url']

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

        if path.name in http_resources.resources_list:
            path = working_directory.joinpath(path.name)

        # Upstream's http.server does not use pathlib objects,
        # so to reduce any chance of issues I'm just going to avoid returning one.
        # FIXME: This should probably use os.fspath instead of str, but that's not available in py3.5
        return str(path)

    def send_head(self):
        """
        Handle the request headers.

        This gets called by both do_GET and do_HEAD, and probably any similar functions that might be used.
        It's expected to send the headers, then return a file-like object with the response body, or None.

        Here we use it mostly to intercept a couple of specific paths.
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
            proxied_url = self.get_stream_playback_url(str(path.parent.relative_to(self.directory)))
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

    assert working_directory.is_absolute()

    try:
        with http.server.ThreadingHTTPServer(bind_address,
                                             functools.partial(RequestHandler,
                                                               directory=str(working_directory))) as httpd:
            systemd.daemon.notify('READY=1')  # Let systemd know we're ready to go
            httpd.serve_forever()
    finally:
        systemd.daemon.notify('STOPPING=1')  # Let systemd know we're cleaning up
