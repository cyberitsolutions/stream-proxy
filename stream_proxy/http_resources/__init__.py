"""Common resources for the stream_proxy HLS output output."""

import shutil
try:
    import importlib.resources
    open_resource = importlib.resources.open_binary
    list_resources = importlib.resources.contents
except ImportError:
    import pkg_resources
    open_resource = pkg_resources.resource_stream
    # pkg_resources syntax is slightly different from importlib.resources
    # NOTE: They also return differently (list vs. iterator) but I don't care
    list_resources = lambda p: pkg_resources.resource_listdir(p, '')

## FIXME: Is this really the best way to do this?
resources_list = [r for r in list_resources(__package__)]
resources_list.remove('__init__.py')
resources_list.remove('__pycache__')


def install_resources_to(working_directory):
    """Copy useful package files into the working directory because http.server can't easily support with importlib.resources..."""
    # FIXME: Should this just raise an exception instead?
    if not working_directory.is_dir():
        working_directory.mkdir()

    # NOTE: I could do both with/as in a single line,
    #       but then the line is really long and there's no good way to wrap them.
    for filename in resources_list:
        with open_resource(__package__, filename) as resource_file:
            with (working_directory / filename).open('wb') as working_file:
                shutil.copyfileobj(resource_file, working_file)
