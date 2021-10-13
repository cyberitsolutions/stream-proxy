#!/usr/bin/python3
import argparse
import pathlib

from . import http_handler
from . import inputs
from . import outputs

# Argument handling
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--hls-working-directory', metavar='PATH',
                    type=pathlib.Path, default=pathlib.Path.cwd() / 'hls_dir',
                    help="Where to store the temporary files for HLS output.")
parser.add_argument('--input-address', metavar='URL',
                    help="Only accept this input address instead of letting the HLS client decide.")
parser.add_argument('--multicast-output-address', metavar='IP:PORT',
                    help="Uses multicast output instead of starting the HLS web listener."
                         "Requires --input-address")

parser.add_argument('--http-listening-port',
                    type=int, default=80,
                    help="For running as non-root during development")

args = parser.parse_args()

if args.multicast_output_address and not args.input_address:
    # FIXME: Is it ok to use argparse's exceptions like this?
    raise argparse.ArgumentError(args.multicast_output_address, "Can't specify a multicast output with including an input address")


if args.multicast_output_address:
    # Multicast mode, easiest control mode there is
    input_pipe = inputs.autoselect(args.input_address)
    output_proc = outputs.multicast(input_pipe, args.multicast_output_address)

    output_proc.wait()

else:
    # HLS mode, this is where things get trickier
    if not args.input_address:
        raise NotImplementedError("Can't auto detect input address yet")

    # Make the working directory if it doesn't already exist
    # FIXME: Should this just raise an exception instead?
    if not args.hls_working_directory.is_dir():
        args.hls_working_directory.mkdir()

    input_pipe = inputs.autoselect(args.input_address)
    output_proc = outputs.hls(input_pipe, (args.hls_working_directory / 'stream'))

    # This try except is only meant to clean up the ytdl & ffmpeg processes when Ctrl-C is pressed
    try:
        http_handler.start_server(bind_address=('0.0.0.0', args.http_listening_port), working_directory=args.hls_working_directory)
    finally:
        # Youtube-dl exits when it can't write to the output anymore
        # Ffmpeg exits when it finishes reading from the input
        # So closing the input pipe is enough to make them clean themselves up

        # FIXME: Properly kill all processes, don't just rely on things cleaning up politely
        input_pipe.close()
        output_proc.wait()
