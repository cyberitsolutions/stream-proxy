"""
Use yt-dlp and multicat (more in future?) to proxy HLS and RTP streams.

HLS output will use base64 to automatically determine the source to proxy from the path being browsed.
Do this to find the base64ed version a given URL: base64.urlsafe_b64encode(b"URL").decode()
"""

__author__ = "Mike Abrahall"
__version__ = "0.1.0"

import pathlib
import argparse


# Argument handling
# FIXME: Probably shouldn't use RawDescriptionHelpFormatter because it won't do any word wrapping,
#        but I wanted my lines separated out into paragraphs how I wrote them.
argparser = argparse.ArgumentParser(prog="stream-proxy", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
argparser.add_argument('input_urls', nargs='*', default=[], metavar='INPUT_URL',
                       help="Only accept these input URLs for proxying")
argparser.add_argument('--hls-working-directory', metavar='PATH',
                       type=pathlib.Path,
                       help="Where to store the temporary files for HLS output. (default: RUNTIME_DIR/{})".format(__package__))
argparser.add_argument('--multicast-output-address', metavar='IPPORT',
                       help="Uses multicast output instead of starting the HLS web listener. "
                       "Requires exactly 1 INPUT_URL")
argparser.add_argument('--http-listening-port',
                       type=int, default=80,
                       help="For running as non-root during development (default: 80)")

argparser.add_argument('--ytdl-arg',
                       type=str, default=[], nargs='*',
                       help="Argument to add to the yt-dlp call if yt-dlp is used. Repeat to specify multiple args")
argparser.add_argument('--ffmpeg-arg',
                       type=str, default=[], nargs='*',
                       help="Argument to add to the ffmpeg call if ffmpeg is used. Repeat to specify multiple args")
argparser.add_argument('--multicat-arg',
                       type=str, default=[], nargs='*',
                       help="Argument to add to the multicat call if multicat is used. Repeat to specify multiple args")
