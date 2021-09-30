#!/bin/bash
stream_url="$1"

test -d html_dir/stream || mkdir html_dir/stream

youtubedl_args=(
    # Stop running once the stream ends
    # FIXME: May stop running when there's a short-term transient issue?
    --abort-on-unavailable-fragment
    # Output a file that can be played while still being downloaded
    --hls-use-mpegts

    --format 'best[ext=mp4]'
)
ffmpeg_args=(
    # Output to HLS for browser playback with HLS.js
    -f hls
    # This instructs the browser to treat it as a "live" HLS stream and keep checking back on the playlist file.
    -hls_playlist_type event

    # FINDME: Change these values for less live delay
    # This is *supposed* to only keep the latest 6 .ts files in the playlist,
    # and delete old .ts files whenever there's more than 9 in the filesystem
    -hls_list_size 6 -hls_delete_threshold 3 -hls_flags delete_segments \
    # But that doesn't seem to have any effect at all, while this long deprecated option still works.
    # FIXME: WHY?!?!?
    -hls_wrap 12 \

    # This is where all the output files go.
    # The HTML only needs to reference the master_pl_name, HLS standards take care of the rest.
    -hls_segment_filename html_dir/stream/%v_data%02d.ts -master_pl_name master.m3u8 html_dir/stream/%v_playlist.m3u8
)
youtube-dl "${youtubedl_args[@]}" --output - -- "$stream_url" | ffmpeg -i - "${ffmpeg_args[@]}"

# TODO: Clean up ffmpeg output when finished, but wait a minute or 3 to let the browser download them all first.
