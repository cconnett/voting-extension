#!/home/cconnett/.venvs/voting-extension/bin/python3
# -*- coding: utf-8 -*-
# -*- mode: python -*-

import os
import sys

import flup

import flask_app

# Add your app to the path
sys.path.insert(0, "/home/cconnett/voting-extension")

# Activate a virtualenv if you're using one
activate = "/home/cconnett/.venvs/voting-extension/bin/activate_this.py"
exec(open(activate).read(), {"__file__": activate})


if __name__ == "__main__":
    flup.server.fcgi.WSGIServer(flask_app.app).run()
