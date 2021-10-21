#!/usr/bin/python3
"""Installer for stream-proxy, only really here for development, as the .deb file is the only supported install method."""

import setuptools
setuptools.setup(
    name='stream_proxy',
    version='1.0',
    packages=['stream_proxy', 'stream_proxy.http_resources'],
    package_data={'stream_proxy.http_resources': ['*.html',
                                                  '*.css',
                                                  '*.js',
                                                  '*.svg',
                                                  'favicon.ico',
                                                  ]},
    entry_points={
        'console_scripts': [
            'stream-proxy=stream_proxy:__main__',
        ]
    }
)
