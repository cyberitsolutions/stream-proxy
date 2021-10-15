#!/usr/bin/python3
import argparse
import base64
import os
import pathlib
import shutil
import sys

from . import http_handler
from . import inputs
from . import outputs

# Argument handling
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--hls-working-directory', metavar='PATH',
                    type=pathlib.Path, default=None,
                    help=f"Where to store the temporary files for HLS output. (default: $XDG_RUNTIME_DIR/{__package__})")
parser.add_argument('--input-address', metavar='URL',
                    help="Only accept this input address instead of letting the HLS client decide.")
parser.add_argument('--multicast-output-address', metavar='IP:PORT',
                    help="Uses multicast output instead of starting the HLS web listener. "
                         "Requires --input-address")

parser.add_argument('--http-listening-port',
                    type=int, default=80,
                    help="For running as non-root during development (default: 80)")

args = parser.parse_args()

if args.multicast_output_address and not args.input_address:
    # FIXME: Is it ok to use argparse's exceptions like this?
    raise argparse.ArgumentError(args.multicast_output_address,
                                 "Can't specify a multicast output without including an input address")

if not args.hls_working_directory:
    # $XDG_RUNTIME_DIR, or $TMPDIR, or /tmp
    # Then add the package name to the end
    args.hls_working_directory = pathlib.Path(os.environ.get('XDG_RUNTIME_DIR',
                                              os.environ.get('TMPDIR',
                                                             '/tmp'))
                                              ) / __package__
    # If it's the default directory we control it entirely and should delete it before we start
    shutil.rmtree(args.hls_working_directory)

if args.multicast_output_address:
    # Multicast mode, easiest control mode there is
    input_pipe = inputs.autoselect(args.input_address)
    output_proc = outputs.multicast(input_pipe, args.multicast_output_address)

    output_proc.wait()

else:
    # HLS mode, this is where things get trickier
    if not args.input_address:
        raise NotImplementedError("Can't auto detect input address yet")

    http_handler.setup_working_directory(args.hls_working_directory)

    # When using running multiple HLS streams we'll need to tell them apart.
    # I tried using urllib.parse.quote() but that was painful to find the right URL for the browser given the nested quoting.
    # Base64 is a bit annoying since it expects bytes not strings, but was the easiest to make work.
    b64_input_address = base64.urlsafe_b64encode(args.input_address.encode()).decode()

    input_pipe = inputs.autoselect(args.input_address)
    output_proc = outputs.hls(input_pipe, (args.hls_working_directory / b64_input_address))

    # This try except is only meant to clean up the ytdl & ffmpeg processes when Ctrl-C is pressed
    try:
        http_handler.start_server(bind_address=('0.0.0.0', args.http_listening_port), working_directory=args.hls_working_directory)
    finally:
        print("Wait a sec while I kill off the ffmpeg processes", file=sys.stderr)
        # Youtube-dl exits when it can't write to the output anymore
        # Ffmpeg exits when it finishes reading from the input
        # So closing the input pipe is enough to make them clean themselves up

        # FIXME: Properly kill all processes, don't just rely on things cleaning up politely
        input_pipe.close()
        output_proc.wait()
