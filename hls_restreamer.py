#!/usr/bin/python3
import http.server
import pathlib
import shutil
import subprocess
import sys
import time

STREAM_URL = sys.argv[1]
WORKING_DIR = pathlib.Path.cwd() / 'html_dir'

# FIXME: Risky
if (WORKING_DIR / 'stream').is_dir():
    shutil.rmtree(WORKING_DIR / 'stream')
(WORKING_DIR / 'stream').mkdir()

class RequestHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, directory=None):
        if not directory:
            directory = WORKING_DIR

        super().__init__(*args, directory=str(directory))

    def send_head(self):
        # Both do_GET and do_HEAD run this first, so this is the best spot to delay if file doesn't exist yet
        path = pathlib.Path(self.translate_path(self.path))
        if not path.exists():
            # Just wait a couple seconds, it'll appear soon... hopefully
            # FIXME: This should be done in the JS as a retry attempt,
            # but I don't understand JS enough to get that deep in HLS.js yet
            time.sleep(3)

        return super().send_head()


ytdl_proc = subprocess.Popen(['youtube-dl',
        # Stop running once the stream ends
        # FIXME: May stop running when there's a short-term transient issue?
        '--abort-on-unavailable-fragment',
        # Output a file that can be played while still being downloaded
        '--hls-use-mpegts',
        # Use the best mp4 available, mp4 theoretically reduces the re-encoding and re-muxing effort required
        '--format=best[ext=mp4]',
        # Send output to stdout
        '--output','-',
        # Grab from given stream URL
        '--', STREAM_URL,
    ], stdout=subprocess.PIPE)
ffmpeg_proc = subprocess.Popen(['ffmpeg',
        # Take input from stdin
        '-i', '-',
        # Output to HLS for browser playback with HLS.js
        '-f', 'hls',
        # This instructs the browser to treat it as a "live" HLS stream and keep checking back on the playlist file.
        '-hls_playlist_type', 'event',

        # FINDME: Change these values for less live delay
        # This is *supposed* to only keep the latest 6 .ts files in the playlist,
        # and delete old .ts files whenever there's more than 9 in the filesystem
        '-hls_list_size', '6', '-hls_delete_threshold', '3', '-hls_flags', 'delete_segments',
        # But that doesn't seem to have any effect at all, while this long deprecated option still works.
        # FIXME: WHY?!?!?
        '-hls_wrap', '12',

        # This is where all the output files go.
        # The HTML only needs to reference the master_pl_name, HLS standards take care of the rest.
        # NOTE: master_pl_name is somehow relative to one of the other args
        '-hls_segment_filename', str(WORKING_DIR / 'stream' / '%v_data%02d.ts'),
        '-master_pl_name', 'master.m3u8',
        str(WORKING_DIR / 'stream' / '%v_playlist.m3u8'),
    ], stdin=ytdl_proc.stdout)

# This blocks forever
http.server.test(HandlerClass=RequestHandler, port=8000)

# FIXME: Wait for *any* 1 process to die, then kill everything.
