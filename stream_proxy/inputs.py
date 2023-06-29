import subprocess
import urllib.parse

ytdl_extra_args = []
multicat_extra_args = []


# FIXME: Can we catch if the process crashes immediately or would that require adding a delay before returning?

def use_ytdl(stream_url):
    ytdl_proc = subprocess.Popen([
        'yt-dlp',
        '--quiet',
        # Stop running once the stream ends
        # FIXME: May stop running when there's a short-term transient issue?
        '--abort-on-unavailable-fragment',
        # Output a file that can be played while still being downloaded
        '--hls-use-mpegts',
        # Use the best mp4 available, mp4 theoretically reduces the re-encoding and re-muxing effort required
        '--format=best[ext=mp4]',
        # Send output to stdout
        '--output', '-',
    ] + ytdl_extra_args + [
        # Grab from given stream URL
        '--', stream_url,
    ], stdout=subprocess.PIPE)

    return ytdl_proc


def use_multicat(stream_url):
    # Multicat doesn't support long-options, so here's the descriptions for the short-options used:
    # -a     Append to existing destination file (risky)
    # -U     Destination has no RTP header
    multicat_proc = subprocess.Popen([
        'multicat',
        stream_url,
        '-a',
        '-U',
        '/dev/stdout',
    ] + multicat_extra_args, stdout=subprocess.PIPE)

    return multicat_proc


def autoselect(stream_url):
    url = urllib.parse.urlparse(stream_url)
    if url.scheme == 'rtp' and url.netloc.startswith('@'):
        return use_multicat(url.netloc)
    elif url.scheme in ('http', 'https'):
        return use_ytdl(stream_url)
    else:
        raise NotImplementedError("Unsupported URL")
