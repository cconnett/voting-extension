import contextlib
import json
import os.path
import random
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


@app.route("/new")
def new():
    return flask.render_template(
        "create.html",
    )


@app.route("/create", methods=["POST"])
def create():
    new_id = uuid.uuid4()
    salt = uuid.uuid4()
    channel_id = flask.request.form["channel_id"]
    title = flask.request.form["title"]
    candidates = flask.request.form["candidates"]
    with db_connection() as conn:
        conn.execute(
            "INSERT INTO polls VALUES (?, ?, ?, ?, ?)",
            new_id.int,
            salt.int,
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
    import mam

    with db_connection() as conn:
        cur = conn.cursor()
        cur.arraysize = 16
        cur.execute("SELECT candidates, salt, open FROM polls WHERE id=?", poll_id.int)
        candidate_string, salt, is_open = cur.fetchone()
        cur = conn.execute("SELECT ranking FROM ballots WHERE poll_id=?", poll_id.int)
        ranking_rows = cur.fetchall()
    candidates = json.loads(candidate_string)
    ballots = []
    for row in ranking_rows:
        ranking_dict = json.loads(row[0])
        ballots.append(sorted(ranking_dict.items(), key=lambda pair: pair[1]))
    ordering, defeat_matrix = mam.MaximizeAffirmedMajorities(
        ballots,
        tiebreaker=mam.Tiebreaker.NONE if is_open else mam.Tiebreaker.LINEAR,
        seed=salt,
    )


@app.route("/results/winner/<uuid:poll_id>", methods=["GET"])
def winner(poll_id):
    ordering, matrix = results(poll_id)
    flask.response.content_type = "text/json"
    return json.dumps(ordering[0])


@app.route("/ballot/<uuid:poll_id>", methods=["GET"])
def ballot(poll_id):
    token = flask.request.form["token"]  # FIXME
    with db_connection() as conn:
        cur = conn.execute(
            "SELECT title, candidates FROM polls WHERE id=?", poll_id.int
        )
        row = cur.fetchone()
        if not row:
            abort(404)
        cur = conn.execute(
            "SELECT ranking FROM ballots WHERE poll_id=? AND opaque_user_id=?",
            poll_id.int,
            token,
        )
        ranking = cur.fetchone()
    title, candidates_string = row[0]
    candidates = json.loads(candidates_string)
    random.shuffle(candidates)
    if ranking:
        ranking = json.loads(ranking[0])
        for candidate in ranking:
            candidates.remove(candidate)

    return flask.render_template(
        "templates/ballot.html",
        title=title,
        candidates=candidates,
        ranking=ranking,
    )


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
