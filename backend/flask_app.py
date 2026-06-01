import contextlib
import json
import os.path
import sqlite3
import uuid

import flask
import jwt


class ScriptNameFix:
    def __init__(self, app, script_name):
        self.app = app
        self.script_name = script_name

    def __call__(self, environ, start_response):
        environ["SCRIPT_NAME"] = self.script_name
        path = environ.get("PATH_INFO", "")
        if path.startswith(self.script_name):
            environ["PATH_INFO"] = path[len(self.script_name) :]
        return self.app(environ, start_response)


app = flask.Flask(__name__)
# app.config["APPLICATION_ROOT"] = "/polls"
# app.wsgi_app = ScriptNameFix(app.wsgi_app, "/polls")


@contextlib.contextmanager
def db_connection():
    with sqlite3.connect(
        os.path.expanduser("~/polls.sqlite3"), autocommit=False
    ) as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        yield conn


# @app.route("/debug")
def hello():
    r = flask.request
    return f"{r.url=}<br>script name: {r.environ.get('SCRIPT_NAME')}<br>path_info: {r.environ.get('PATH_INFO')}"


@app.route("/create", methods=["POST"])
def create():
    new_id = uuid.uuid4()
    channel_id = flask.request.form["channel_id"]
    title = flask.request.form["title"]
    candidates = flask.request.form["candidates"]
    with db_connection() as conn:
        conn.execute(
            "INSERT INTO polls VALUES (?, ?, ?, ?)",
            new_id.int,
            channel_id,
            title,
            candidates,
        )


# @app.route("/open/<uuid:poll_id>", methods=["POST"])
def open(poll_id):
    with db_connection() as conn:
        # FIXME: AUTHENTICATE THE STREAMER
        conn.execute("UPDATE polls SET open=1 WHERE poll_id=?", poll_id=poll_id.int)


@app.route("/close/<uuid:poll_id>", methods=["POST"])
def close(poll_id):
    with db_connection() as conn:
        # FIXME: AUTHENTICATE THE STREAMER
        conn.execute("UPDATE polls SET open=0 WHERE poll_id=?", poll_id=poll_id.int)


@app.route("/results/<uuid:poll_id>", methods=["GET"])
def results(poll_id):
    pass


@app.route("/ballot/<uuid:poll_id>", methods=["GET"])
def ballot(poll_id):
    with db_connection() as conn:
        cur = conn.execute("SELECT candidates from polls WHERE id=?", poll_id.int)
        row = cur.fetchone()
        candidates = json.loads(row[0])
    return flask.render_template("templates/ballot.html", candidates=candidates)


@app.route("/cast_vote/<uuid:poll_id>", methods=["POST"])
def cast_vote(poll_id):
    token = flask.request.form["token"]  # FIXME
    ranking = flask.request.form["ranking"]
    with db_connection() as conn:
        cur = conn.execute("SELECT open FROM polls WHERE poll_id=?", poll_id.int)
        is_open = cur.fetchone()[0]
        if not is_open:
            abort(409)
        conn.execute(
            "INSERT OR REPLACE INTO ballots VALUES (?, ?, ?)",
            poll_id.int,
            token,
            ranking,
        )
