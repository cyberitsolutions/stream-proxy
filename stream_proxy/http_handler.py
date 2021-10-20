import functools
import http.server
import importlib.resources
import os.path
import pathlib
import shutil
import time


INCLUDED_HTTP_RESOURCES = [
    'index.html',
    'press-play.svg',
]


# Currently just adds a delay when the requested file doesn't exist yet.
# More logic is required to:
# * grab the index.html from the Python package:
#   importlib.resources.open_text(__package__, 'index.html')
#   Repeat for press-play.svg
# * programmatically start input streams when requested,
# * find the HLS path for the requested input stream.
#
# NOTE: There is a new instance of this class for every single request
class RequestHandler(http.server.SimpleHTTPRequestHandler):
    def translate_path(self, path):
        """Wraps parent translate_path to get a couple of always-available resources from the root of the working directory."""
        translated = super().translate_path(path)
        filename = translated.rpartition('/')[2]

        if not filename:
            # Default to index.html if trying to browse a directory
            filename = 'index.html'

        if filename in ('index.html', 'press-play.svg'):
            # NOTE: This depends on filename not starting with a '/',
            #       otherwise it will leave off the directory.
            translated = os.path.join(self.directory, filename)

        return translated

        return translated


def setup_working_directory(working_directory):
    # FIXME: Should this just raise an exception instead?
    if not working_directory.is_dir():
        working_directory.mkdir()

    # FIXME: Why is importlib.resources.contents() not showing the resources?
    #        Does it need to be an installed package and won't work from the source tree?
    for filename in INCLUDED_HTTP_RESOURCES:
        with (working_directory / filename).open('wb') as working_file:
            shutil.copyfileobj(importlib.resources.open_binary(__package__, filename), working_file)


def start_server(bind_address, working_directory):
    with http.server.ThreadingHTTPServer(bind_address, functools.partial(RequestHandler, directory=working_directory)) as httpd:
        httpd.serve_forever()
