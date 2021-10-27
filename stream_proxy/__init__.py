"""
Use youtube-dl and multicat (more in future?) to proxy HLS and RTP streams.

HLS output will use base64 to automatically determine the source to proxy from the path being browsed.
Do this to find the base64ed version a given URL: base64.urlsafe_b64encode(b"URL").decode()
"""

__author__ = "Mike Abrahall"
__version__ = "0.1.0"
