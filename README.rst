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
