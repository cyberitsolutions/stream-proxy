#!/usr/bin/python3
import argparse
import os
import pathlib
import shutil

import systemd.daemon

from . import http_handler
from . import inputs
from . import outputs

# $RUNTIME_DIRECTORY, $XDG_RUNTIME_DIR, or $TMPDIR, or /tmp
# Then add the package name to the end
DEFAULT_WORKING_DIR = pathlib.Path(os.environ.get('RUNTIME_DIRECTORY',
                                                  os.environ.get('XDG_RUNTIME_DIR',
                                                                 os.environ.get('TMPDIR',
                                                                                '/tmp'))
                                                  )) / __package__

# Argument handling
# FIXME: Probably shouldn't use RawDescriptionHelpFormatter because it won't do any word wrapping,
#        but I wanted my lines separated out into paragraphs how I wrote them.
parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
parser.add_argument('input_urls', nargs='*', default=[], metavar='INPUT_URL',
                    help="Only accept these input URLs for proxying")
parser.add_argument('--hls-working-directory', metavar='PATH',
                    type=pathlib.Path, default=DEFAULT_WORKING_DIR,
                    help="Where to store the temporary files for HLS output. (default: $XDG_RUNTIME_DIR/{})".format(__package__))
# Setting a variable here because this one is used to raise my own exception below,
multicast_arg = parser.add_argument('--multicast-output-address', metavar='IP:PORT',
                                    help="Uses multicast output instead of starting the HLS web listener. "
                                    "Requires exactly 1 INPUT_URL")

parser.add_argument('--http-listening-port',
                    type=int, default=80,
                    help="For running as non-root during development (default: 80)")

args = parser.parse_args()

if args.multicast_output_address and not len(args.input_urls) == 1:
    # FIXME: Is it ok to use argparse's exceptions like this?
    raise argparse.ArgumentError(multicast_arg,
                                 "Can't specify a multicast output without exactly 1 INPUT_URL")

if args.hls_working_directory == DEFAULT_WORKING_DIR:
    # If it's the default directory we control it entirely and should delete it before we start
    if args.hls_working_directory.is_dir():
        shutil.rmtree(args.hls_working_directory)
    else:
        args.hls_working_directory.mkdir()

if args.multicast_output_address:
    # Multicast mode, easiest control mode there is
    input_proc = inputs.autoselect(*args.input_urls)
    output_proc = outputs.multicast(input_proc.stdout, args.multicast_output_address)

    systemd.daemon.notify('READY=1')
    output_proc.wait()

else:
    # HLS mode, so we need a smart HTTP server.

    http_handler.acceptable_input_addresses = args.input_urls

    http_handler.setup_working_directory(args.hls_working_directory)

    # This blocks forever even after streams have ended,
    # http_handler will notify systemd on both start & stopping, so we don't handle that here.
    http_handler.start_server(bind_address=('', args.http_listening_port), working_directory=args.hls_working_directory)
