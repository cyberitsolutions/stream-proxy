#!/usr/bin/python3
import argparse
import base64
import os
import pathlib
import shutil
import sys

import systemd.daemon

from . import argparser
from . import http_handler
from . import inputs
from . import outputs

# $RUNTIME_DIRECTORY, $XDG_RUNTIME_DIR, $TMPDIR, or /tmp
# Then add the package name to the end
DEFAULT_WORKING_DIR = pathlib.Path(os.environ.get('RUNTIME_DIRECTORY',
                                                  os.environ.get('XDG_RUNTIME_DIR',
                                                                 os.environ.get('TMPDIR',
                                                                                '/tmp'))
                                                  )) / __package__

argparser.set_defaults(hls_working_directory=DEFAULT_WORKING_DIR)
args = argparser.parse_args()

os.chdir(str(args.hls_working_directory.parent))

inputs.ytdl_extra_args = args.ytdl_arg
inputs.multicat_extra_args = args.multicat_arg
outputs.ffmpeg_extra_args = args.ffmpeg_arg
outputs.multicat_extra_args = args.multicat_arg

if args.multicast_output_address and not len(args.input_urls) == 1:
    # FIXME: Is it ok to use argparse's exceptions like this?
    raise argparse.ArgumentError(None,  # Expects an argument object, not a string.
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
    print('Test URLs:', file=sys.stderr, flush=True)
    for url in http_handler.acceptable_input_addresses:
        print('* http://localhost:', args.http_listening_port, '/', base64.urlsafe_b64encode(url.encode()).decode(), '/',
              sep='', file=sys.stderr, flush=True)

    # This blocks forever even after streams have ended,
    # http_handler will notify systemd on both start & stopping, so we don't handle that here.
    http_handler.start_server(bind_address=('', args.http_listening_port), working_directory=args.hls_working_directory)
