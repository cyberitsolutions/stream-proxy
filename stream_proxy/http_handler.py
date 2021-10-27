import base64
import functools
import http
import http.server
import importlib.resources
import os.path
import pathlib
import shutil
import sys
import time
import urllib.parse

import systemd

from . import inputs
from . import outputs
from . import http_resources


# FIXME: Is this really the best way to do this?
INCLUDED_HTTP_RESOURCES = [r for r in importlib.resources.contents(http_resources)]
INCLUDED_HTTP_RESOURCES.remove('__init__.py')
INCLUDED_HTTP_RESOURCES.remove('__pycache__')

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

    def translate_path(self, path):
        """Wrap parent translate_path to get a couple of always-available resources from the root of the working directory."""
        # NOTE: I have confirmed that translated currently doesn't allow 'http://localhost/foo/../../../../etc/passwd".
        #       I did put a small amount of effort into rewriting super().translate_path to better use urllib and pathlib,
        #       but in doing so I realised there was a risk of introducing that kind of security bug, so left it alone.
        translated = super().translate_path(path)
        filename = translated.rpartition('/')[2]

        if not filename:
            # Default to index.html if trying to browse a directory
            filename = 'index.html'
            path = os.path.join(path, 'index.html')

        if filename in INCLUDED_HTTP_RESOURCES:
            # NOTE: This depends on filename not starting with a '/',
            #       otherwise it will leave off the directory.
            translated = os.path.join(self.directory, filename)

        if filename == 'index.html':
            stream_id = path[:-len('index.html')].strip('/')
            # NOTE: Even though *I* passed directory as a pathlib.Path object to __init__,
            #       http.server replaced it with os.fspath(directory).
            if not _maybe_tune_stream(stream_id, pathlib.Path(self.directory) / stream_id):
                self.send_error(http.HTTPStatus.FORBIDDEN, "That stream has not been enabled")

        return translated

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


def setup_working_directory(working_directory):
    """Copy useful package files into the working directory because http.server can't easily support with importlib.resources..."""
    # FIXME: Should this just raise an exception instead?
    if not working_directory.is_dir():
        working_directory.mkdir()

    # NOTE: I could do both with/as in a single line,
    #       but then the line is really long and there's no good way to wrap them.
    for filename in INCLUDED_HTTP_RESOURCES:
        with importlib.resources.open_binary(http_resources, filename) as resource_file:
            with (working_directory / filename).open('wb') as working_file:
                shutil.copyfileobj(resource_file, working_file)


def start_server(bind_address, working_directory):
    """Start the actual HTTP server. Blocks forever."""
    try:
        with http.server.ThreadingHTTPServer(
                bind_address, functools.partial(RequestHandler, directory=working_directory)) as httpd:
            systemd.daemon.notify('READY=1')
            httpd.serve_forever()
    finally:
        systemd.daemon.notify('STOPPING=1')
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
