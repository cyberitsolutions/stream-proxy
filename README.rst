Stream proxy
============

Use youtube-dl, ffmpeg, and multicat (more in future?) to proxy HLS and RTP live streams.

Run with --help for usage instructions

Running behind a HTTP(S) proxy
------------------------------
Easiest answer is just adding it to the environment that systemd sets::

    printf '%s\n' '[Service]' 'Environment="http_proxy=http://user:pass@proxy:3128/"' >/etc/systemd/system/python3-stream-proxy.service.d/override.conf

Alternatively it can be passed as an argument to be given to youtube-dl::

    --ytdl-arg="--proxy='http://user:pass@proxy:3128/'"

Running on Debian Stretch
-------------------------
Systemd behaves a bit differently in frustrating ways, here's a workaround::

    printf '%s\n' '[Service]' '"RUNTIME_DIRECTORY=/run/%N" "PYTHONUSERBASE=/run/$N" "HOME=/run/%N"' >/etc/systemd/system/python3-stream-proxy.service.d/override.conf

TODO/NOTES
==========

Squid config fun
----------------

I was able to make Squid force a redirect on YouTube URLs using this config::

    acl streaming_services dstdomain www.youtube.com
    # "https://www.youtube.com/embed/abcdef?playlist=foobar&loop=1&autoplay=1&mute=1&controls=00" -> "http://stream-proxy.lan/redirect/https%3A%2F%2Fwww.youtube.com%2Fembed%2Fabcdef%3Fplaylist%3Dfoobar%26amp%3Bloop%3D1%26amp%3Bautoplay%3D1%26amp%3Bmute%3D1%26amp%3Bcontrols%3D00"
    deny_info 301:http://stream-proxy.lan/redirect/%U streaming_services
    # # "https://www.youtube.com/embed/abcdef?playlist=foobar&loop=1&autoplay=1&mute=1&controls=00" -> "http://stream-proxy.lan/redirect/www.youtube.com/embed/abcdef?playlist=foobar&amp;loop=1&amp;autoplay=1&amp;mute=1&amp;controls=00"
    # deny_info 301:http://restreaming-proxy.lan/redirect/%H%R streaming_services
    # NOTE: The CONNECT request results in an empty '%R' so if we redirect at this point won't send enough info to the stream-proxy code.
    #       Since we're alredy using SSL bump for all requests anyway, this is fine.
    # FIXME: Don't do this redirect for staff users?
    http_access deny !CONNECT streaming_services

This could then be used to whitelist embedded streams near-seamlessly.
The only thing the end-user would notice "wrong" would be the lack of YouTube styled control buttons,
and maybe some extra metadata like subtitles/etc.
