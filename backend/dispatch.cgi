#!/home/cconnett/.venvs/polls/bin/python3
# -*- coding: utf-8 -*-
# -*- mode: python -*-

import os
import sys
from wsgiref import handlers

import flask_app

# Add your app to the path
sys.path.insert(0, "/home/cconnett/alphachannel.gg/polls")

# Activate a virtualenv if you're using one
# activate = "/home/cconnett/.venvs/polls/bin/activate_this.py"
# exec(open(activate).read(), {"__file__": activate})


if __name__ == "__main__":
    handlers.CGIHandler().run(flask_app.app)
