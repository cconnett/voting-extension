import contextlib
import itertools
import json
import os.path
import random
import secrets
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
    salt = secrets.randbits(64)
    channel_id = flask.request.form["channel_id"]
    title = flask.request.form["title"]
    candidates = flask.request.form["candidates"]
    with db_connection() as conn:
        conn.execute(
            "INSERT INTO polls (id, salt, channel_id, title, candidates) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                str(new_id),
                salt,
                channel_id,
                title,
                candidates,
            ),
        )
    return str(new_id)


# @app.route("/open/<uuid:poll_id>", methods=["POST"])
def open(poll_id):
    with db_connection() as conn:
        # FIXME: AUTHENTICATE THE STREAMER
        conn.execute("UPDATE polls SET open=1 WHERE poll_id=?", (str(poll_id),))


@app.route("/close/<uuid:poll_id>", methods=["POST"])
def close(poll_id):
    with db_connection() as conn:
        # FIXME: AUTHENTICATE THE STREAMER
        conn.execute("UPDATE polls SET open=0 WHERE poll_id=?", (str(poll_id),))


def tablulate_results(poll_id):
    import mam

    with db_connection() as conn:
        cur = conn.cursor()
        cur.arraysize = 16
        cur.execute(
            "SELECT candidates, salt, open FROM polls WHERE id=?", (str(poll_id),)
        )
        candidate_string, salt, is_open = cur.fetchone()
        cur = conn.execute(
            "SELECT ranking FROM ballots WHERE poll_id=?", (str(poll_id),)
        )
        ranking_rows = cur.fetchall()
    candidates = json.loads(candidate_string)
    ballots = []
    for row in ranking_rows:
        ranking_dict = json.loads(row[0])
        ballots.append(
            (candidate,)
            for candidate, unused_rank in sorted(
                ranking_dict.items(), key=lambda pair: pair[1]
            )
        )
    return (
        mam.MaximizeAffirmedMajorities(
            ballots,
            tiebreaker=mam.Tiebreaker.NONE if is_open else mam.Tiebreaker.LINEAR,
            seed=salt,
        ),
        is_open,
    )


def render_matrix(matrix, ordering):
    def gen():
        width = max(len(str(elt)) for row in matrix.values() for elt in row.values())
        width = max(width, max(len(cand) for cand in ordering))
        yield " " * (width + 1)
        for col_key in ordering:
            yield f"{col_key:{width}} "
        yield "\n"
        for row_key in ordering:
            yield f"{row_key:{width}} "
            for col_key in ordering:
                if row_key == col_key:
                    cell = ""
                else:
                    cell = matrix[row_key].get(col_key, 0)
                yield f"{cell!s:{width}} "
            yield "\n"

    return "".join(gen())


@app.route("/results/<uuid:poll_id>", methods=["GET"])
def results(poll_id):
    (ordering, matrix), is_open = tablulate_results(poll_id)
    ret = f"Poll is {'open' if is_open else 'closed'}.<br>{ordering}<br>"
    for winner, loser in itertools.pairwise(ordering):
        if isinstance(winner, tuple):
            exemplar_winner = winner[0]
        else:
            exemplar_winner = winner
        if isinstance(loser, tuple):
            exemplar_loser = loser[0]
        else:
            exemplar_loser = loser
        affirmed = matrix[exemplar_winner][exemplar_loser]
        disaffirmed = matrix[exemplar_loser][exemplar_winner]
        ret += (
            f"{affirmed/(affirmed + disaffirmed):.0%} prefer {winner} to {loser}.<br>"
        )
    winner = ordering[0]
    if not isinstance(winner, tuple):
        if all(matrix[winner][x] > matrix[x][winner] or x == winner for x in ordering):
            ret += f"{winner} is a Condorcet winner.<br>"
    ret += f"<pre>{render_matrix(matrix, ordering)}</pre>"
    return ret


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
            "SELECT title, candidates FROM polls WHERE id=?", (str(poll_id),)
        )
        row = cur.fetchone()
        if not row:
            abort(404)
        cur = conn.execute(
            "SELECT ranking FROM ballots WHERE poll_id=? AND opaque_user_id=?",
            (
                str(poll_id),
                user_id,
            ),
        )
        ranking = cur.fetchone()
    title, candidates_string = row
    candidates = json.loads(candidates_string)
    random.shuffle(candidates)
    if ranking:
        ranking = json.loads(ranking)
        for candidate in ranking:
            candidates.remove(candidate)
    else:
        ranking = []

    return flask.render_template(
        "ballot.html",
        title=title,
        candidates=candidates,
        ranking=ranking,
    )


@app.route("/cast_vote/<uuid:poll_id>", methods=["POST"])
def cast_vote(poll_id):
    token = flask.request.form["token"]  # FIXME
    ranking = flask.request.form["ranking"]
    with db_connection() as conn:
        cur = conn.execute("SELECT open FROM polls WHERE id=?", (str(poll_id),))
        is_open = cur.fetchone()[0]
        if not is_open:
            abort(409)
        conn.execute(
            "INSERT OR REPLACE INTO ballots (poll_id, opaque_user_id, ranking) "
            "VALUES (?, ?, ?)",
            (
                str(poll_id),
                token,
                ranking,
            ),
        )
    return "OK"
