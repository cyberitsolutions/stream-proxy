import base64
import functools
import http
import http.server
import os.path
import pathlib
import sys
import time
import urllib.parse

import systemd

from . import inputs
from . import outputs
from . import http_resources


_tuned_streams = {}
acceptable_input_addresses = []  # default is accept all


def _maybe_tune_stream(b64_input_address, output_directory):
    """Tune in to stream if not already tuned in."""
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

        # FIXME: Use a named tuple or something more self-documented than relying on the order of the tuple?
        _tuned_streams[b64_input_address] = (input_proc, output_proc, output_directory)
    else:
        pass

    return True


# NOTE: There is a new instance of this class for every single request
class RequestHandler(http.server.SimpleHTTPRequestHandler):
    """Handle the stream proxying for a single HTTP connection."""

    def __init__(self, *args, working_directory: pathlib.Path, **kwargs):
        # NOTE: Py3.9 has a self.directory variable which gets recast as a str,
        #       This was causing me problems as I couldn't stop the super().__init__ function from recasting it.
        #       So I renamed my own version of it, it's only used in translate_path anyway (which I also rewrote).
        #       I'm making sure to set it properly anyway, just in case.
        assert working_directory.is_absolute()
        super().__init__(*args, directory=str(working_directory), **kwargs)

    def translate_path(self, path):
        """Wrap translate_path to get some always-available resources from the root of the working directory."""

        # pathlib.Path will lose the trailing slash and is_dir() only works if the path actually exists on the fs.
        # So there's this slightly messy process to add 'index.html' onlny if the original path string ended with '/'
        path_str = super().translate_path(path)
        path = pathlib.Path(path)
        if path_str.endswith('/'):
            path = path.joinpath('index.html')

        # FIXME: Should we just drop this try/except and trust that the upstream http.server code handles this properly?
        try:
            if self.directory / pathlib.Path(path).relative_to(self.directory) != path:
                # This shouldn't actually happen because it happening at all should trigger the exception below
                print("Someone *might* be trying to browse outside of the working directory:", str(path), file=sys.stderr)
                self.send_error(http.HTTPStatus.FORBIDDEN, "That looks naughty")
        except ValueError as e:
            # ValueError: '...' is not in the subpath of '...' OR one path is relative and the other is absolute.
            print('ValueError:', e, file=sys.stderr)
            self.send_error(http.HTTPStatus.FORBIDDEN, "That was very naughty")

        if path.name == 'index.html':
            stream_id = str(path.parent.relative_to(self.working_directory))
            try:
                if not _maybe_tune_stream(stream_id, self.working_directory / stream_id):
                    self.send_error(http.HTTPStatus.FORBIDDEN, "That stream has not been enabled")
            except NotImplementedError:
                self.send_error(http.HTTPStatus.INTERNAL_SERVER_ERROR, "That stream is not currently supported")
            except:  # noqa: E722
                self.send_error(http.HTTPStatus.INTERNAL_SERVER_ERROR, "There was a problem tuning to that stream")

        if path.name in http_resources.resources_list:
            path = self.working_directory.joinpath(path.name)

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
        else:
            return super().send_head()


def start_server(bind_address, working_directory: pathlib.Path):
    """Start the actual HTTP server. Blocks forever."""
    http_resources.install_resources_to(working_directory)

    # FIXME: Should we even bother with this check? It'll fail pretty quickly if we ignore it anyway
    if sys.version_info < 3 or (sys.version_info == 3 and sys.version_info < 9):
        raise RuntimeError("This requires at least Python 3.9 to work correctly")

    server = http.server.ThreadingHTTPServer

    try:
        with server(bind_address, functools.partial(RequestHandler, directory=working_directory)) as httpd:
            httpd = server(bind_address, functools.partial(RequestHandler, working_directory=working_directory))
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
