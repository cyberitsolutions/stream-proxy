import pathlib
import subprocess

ffmpeg_extra_args = []
multicat_extra_args = []


def hls(input_pipe, output_dir: pathlib.Path):
    if not output_dir.is_dir():
        output_dir.mkdir()

    ffmpeg_proc = subprocess.Popen([
        'ffmpeg',
        '-loglevel', '24',

        # Take input from stdin
        '-i', '-',
        # Output to HLS for browser playback with HLS.js
        '-f', 'hls',
        # This instructs the browser to treat it as a "live" HLS stream and keep checking back on the playlist file.
        '-hls_playlist_type', 'event',

        # FINDME: Change these values for less live delay
        # This is *supposed* to only keep the latest 6 .ts files in the playlist,
        # and delete old .ts files whenever there's more than 9 in the filesystem
        '-hls_list_size', '6', '-hls_flags', 'delete_segments',  # '-hls_delete_threshold', '3',
        # But that doesn't seem to have any effect at all, while this long deprecated option still works.
        # FIXME: WHY?!?!?
        '-hls_wrap', '12',

        # This is where all the output files go.
        # The HTML only needs to reference the master_pl_name, HLS standards take care of the rest.
        # NOTE: master_pl_name is somehow relative to one of the other args
        # '-master_pl_name', 'master.m3u8',
        '-hls_segment_filename', str(output_dir / 'data%02d.ts'),
        str(output_dir / 'master.m3u8'),
    ] + ffmpeg_extra_args, stdin=input_pipe)

    return ffmpeg_proc


def multicast(input_pipe, output_address):
    # Multicat doesn't support long-options, so here's the descriptions for the short-options used:
    # -t <ttl>      TTL of the packets send by multicat
    multicat_proc = subprocess.Popen([
        'multicat',
        '-t', '2',
        '/dev/stdin',
        output_address,
    ] + multicat_extra_args, stdin=input_pipe)

    return multicat_proc
