import subprocess
import urllib.parse


# FIXME: Can we catch if the process crashes immediately or would that require adding a delay before returning?
# FIXME: Should we return the process instead of stdout to better deal with killing it later?
#        Does closing stdout deal with that well enough?

def use_ytdl(stream_url):
    ytdl_proc = subprocess.Popen([
        'youtube-dl',
        # Stop running once the stream ends
        # FIXME: May stop running when there's a short-term transient issue?
        '--abort-on-unavailable-fragment',
        # Output a file that can be played while still being downloaded
        '--hls-use-mpegts',
        # Use the best mp4 available, mp4 theoretically reduces the re-encoding and re-muxing effort required
        '--format=best[ext=mp4]',
        # Send output to stdout
        '--output', '-',
        # Grab from given stream URL
        '--', stream_url,
    ], stdout=subprocess.PIPE)

    return ytdl_proc.stdout


def use_multicat(stream_url):
    # Multicat doesn't support long-options, so here's the descriptions for the short-options used:
    # -a     Append to existing destination file (risky)
    # -U     Destination has no RTP header
    # NOTE: multicat did not accept '-' or '/dev/stdout' as valid output
    multicat_proc = subprocess.Popen(['multicat', stream_url, '-a', '-U', '/dev/fd/1'], stdout=subprocess.PIPE)

    return multicat_proc.stdout


def autoselect(stream_url):
    url = urllib.parse.urlparse(stream_url)
    if url.scheme == 'rtp' and url.netloc.startswith('@'):
        return use_multicat(stream_url)
    elif url.scheme in ('http', 'https'):
        return use_ytdl(stream_url)
    else:
        raise NotImplementedError("Unsupported URL")
