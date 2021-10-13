import functools
import http.server
import pathlib
import time


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
    def send_head(self):
        # Both do_GET and do_HEAD run this first, so this is the easiest spot to delay if file doesn't exist yet
        path = pathlib.Path(self.translate_path(self.path))
        if not path.exists():
            # Just wait a couple seconds, it'll appear soon... hopefully
            # FIXME: This should be done in the JS as a retry attempt,
            # but I don't understand JS enough to get that deep in HLS.js yet
            time.sleep(3)

        return super().send_head()


def start_server(bind_address, working_directory):
    print(bind_address)
    print(working_directory)
    with http.server.ThreadingHTTPServer(bind_address, functools.partial(RequestHandler, directory=working_directory)) as httpd:
        httpd.serve_forever()
