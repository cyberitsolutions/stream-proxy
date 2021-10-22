Helpful dev testing snippets
============================

Install the Python library, and *temporarily* install & start the systemd unit::

    sudo pip3 install .
    sudo cp stream-proxy.service /run/systemd/transient/stream-proxy.service
    sudo systemctl daemon-reload && sudo systemctl restart stream-proxy.service

Clean all ^ that up::

    sudo systemctl stop stream-proxy.service
    sudo rm /run/systemd/transient/stream-proxy.service
    sudo systemctl daemon-reload
    sudo pip3 uninstall stream-proxy
