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

    def __init__(self, *args, directory: pathlib.Path, **kwargs):
        self.directory = directory
        assert self.directory.is_absolute()
        return super().__init__(*args, **kwargs)

    def translate_path(self, path):
        """
        Rewrite translate_path with urllib & pathlib to get some always-available resources from the root of the working directory.

        We could get away with just wrapping the parent function in Python 3.9,
        but Python 3.5 doesn't have self.directory and instead assumes current working directory.
        While that may actually be valid in our circumstances I wasn't happy with relying on that.
        """
        # FIXME: Flake8 says this is "too complex", although it's only by a single if/try block
        parsed = urllib.parse.urlparse(self.path)
        path = self.directory
        for part in pathlib.Path(parsed.path).parts:
            # Ignore relative path components as they could be used nefariously.
            # (ie, GET http://localhost/stream/../../../../etc/passwd)
            # FIXME: This is the same way 3.9's translate_path function handles it, it feels kinda messy though
            # FIXME: 3.9's paths can just do .resolve(), but 3.5 can only do that if most of the path dirs actually exist
            if part not in (os.sep, os.curdir, os.pardir):
                path = path.joinpath(part)

        # pathlib.Path will lose the trailing slash and is_dir() only works if the path actually exists on the fs
        if parsed.path.endswith('/'):
            path = path.joinpath('index.html')

        try:
            if self.directory / path.relative_to(self.directory) != path:
                print("Someone *might* be trying to browse outside of the working directory:", str(path), file=sys.stderr)
                self.send_error(http.HTTPStatus.FORBIDDEN, "I don't know what you're doing, but it looks naughty")
        except:  # noqa: E722
            print("Someone tried to browse outside of the working directory:", str(path), file=sys.stderr)
            self.send_error(http.HTTPStatus.FORBIDDEN, "That was very naughty")

        if path.name == 'index.html':
            stream_id = str(path.parent.relative_to(self.directory))
            try:
                if not _maybe_tune_stream(stream_id, self.directory / stream_id):
                    self.send_error(http.HTTPStatus.FORBIDDEN, "That stream has not been enabled")
            except:  # noqa: E722
                self.send_error(http.HTTPStatus.INTERNAL_SERVER_ERROR, "There was a problem tuning to that stream")

        if path.name in http_resources.resources_list:
            path = self.directory.joinpath(path.name)

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


def start_server(bind_address, working_directory):
    """Start the actual HTTP server. Blocks forever."""
    http_resources.install_resources_to(working_directory)

    # ThreadingHTTPServer isn't available until Python 3.7
    # This likely means it can realistically only be used by 1 user at a time on <3.7
    if hasattr(http.server, 'ThreadingHTTPServer'):
        server = http.server.ThreadingHTTPServer
    else:
        server = http.server.HTTPServer

    try:
        # 3.5's http.server also doesn't support with/as. UGH, can I just give up on 3.5 support?
        # I tried manually setting __enter__ & __exit__ to seemingly equivalent lambdas,
        # but that resulted in the whole thing just hanging during __init__ and I don't understand why.
        httpd = server(bind_address, functools.partial(RequestHandler, directory=working_directory))
        systemd.daemon.notify('READY=1')  # Let systemd know we're ready to go
        httpd.serve_forever()
    finally:
        systemd.daemon.notify('STOPPING=1')  # Let systemd know we're cleaning up
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
