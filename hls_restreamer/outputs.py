import pathlib
import subprocess
import urllib.parse

def hls(input_pipe, output_dir: pathlib.Path):
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
            '-master_pl_name', 'master.m3u8',
            '-hls_segment_filename', str(output_dir / '%v_data%02d.ts'),
            str(output_dir / '%v_playlist.m3u8'),
        ], stdin=input_pipe)

    return ffmpeg_proc

def multicast(input_pipe, output_address):
    raise NotImplementedError("Multicat output hasn't been implemented yet")
    # Multicat doesn't support long-options, so here's the descriptions for the short-options used:
    # -t <ttl>      TTL of the packets send by multicat
    # NOTE: multicat did not accept '-' or '/dev/stdout' as valid, so I'm assuming the same for input
    multicat_proc = subprocess.Popen(['multicat',
            '-t', '2',
            '/dev/fd/0',
            output_address,
        ])

    return multicat_proc
