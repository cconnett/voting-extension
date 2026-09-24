import contextlib
import dataclasses
import itertools
import json
import os.path
import random
import secrets
import sqlite3
import uuid
from typing import List

import flask
import jwt

import mam


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
    if salt & 1 << 63:
        # sqlite INTs are 64-bit signed, so wrap the value into the signed regime.
        salt -= 1 << 64
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


@app.route("/open/<uuid:poll_id>", methods=["POST", "GET"])
def open(poll_id):
    with db_connection() as conn:
        # FIXME: AUTHENTICATE THE STREAMER
        conn.execute("UPDATE polls SET open=1 WHERE id=?", (str(poll_id),))
    return f"Poll {poll_id} reopened."


@app.route("/close/<uuid:poll_id>", methods=["GET", "POST"])
def close(poll_id):
    with db_connection() as conn:
        # FIXME: AUTHENTICATE THE STREAMER
        conn.execute("UPDATE polls SET open=0 WHERE id=?", (str(poll_id),))
    return f"Poll {poll_id} closed."


@dataclasses.dataclass
class Candidate:
    seq: int
    text: str


@dataclasses.dataclass
class Group:
    seq: int
    members: Candidate
    # Margin over the next group.
    margin: str
    reversals: List["Reversal"] = dataclasses.field(default_factory=list)


@dataclasses.dataclass
class Reversal:
    seq: int
    # The stronger end of the reversal (lower in the final ranking).
    stronger: Group
    # The weaker end of the reversal (higher in the final ranking).
    weaker: Group
    margin: str


def tabulate_results(poll_id):
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
        rankings = cur.fetchall()
    candidates = json.loads(candidate_string)
    ballots = []
    for row in rankings:
        ranking_dict = json.loads(row[0])
        ballots.append(
            (candidate,)
            for candidate, unused_rank in sorted(
                ranking_dict.items(), key=lambda pair: pair[1]
            )
        )
    ordering, matrix = mam.MaximizeAffirmedMajorities(
        ballots,
        candidates=candidates,
        tiebreaker=mam.Tiebreaker.NONE if is_open else mam.Tiebreaker.LINEAR,
        seed=salt,
    )

    return (
        (ordering, matrix),
        is_open,
        len(rankings),
    )


def render_matrix(matrix, ordering):
    flat_ordering = []
    for rank in ordering:
        flat_ordering.extend(rank)

    def gen():
        labels = sorted(matrix.keys(), key=lambda cand: flat_ordering.index(cand))
        width = max(len(str(elt)) for row in matrix.values() for elt in row.values())
        width = max(width, max(len(cand) for cand in labels))
        yield " " * (width + 1)
        for col_key in labels:
            yield f"{col_key:>{width}} "
        yield "\n"
        for row_key in labels:
            yield f"{row_key:>{width}} "
            for col_key in labels:
                if row_key == col_key:
                    cell = ""
                else:
                    cell = matrix[row_key][col_key]
                yield f"{cell!s:{width}} "
            yield "\n"

    return "".join(gen())


def Exemplar(obj_or_set):
    if isinstance(obj_or_set, set):
        return next(iter(obj_or_set))
    return obj_or_set


@app.route("/old_results/<uuid:poll_id>", methods=["GET"])
def old_results(poll_id):
    (ordering, matrix), is_open, num_ballots = tabulate_results(poll_id)
    ret = f"Poll is {'open' if is_open else 'closed'}.<br>"
    ret += f"{ordering}<br>"
    ret += f"Ballots received: {num_ballots}<br>"
    if num_ballots == 0:
        return ret
    for winner, loser in itertools.pairwise(ordering):
        exemplar_winner = Exemplar(winner)
        exemplar_loser = Exemplar(loser)
        affirmed = matrix[exemplar_winner][exemplar_loser]
        disaffirmed = matrix[exemplar_loser][exemplar_winner]
        ret += (
            f"{affirmed/(affirmed + disaffirmed):.0%} prefer {winner} to {loser}.<br>"
        )
    winner = ordering[0]
    if not isinstance(winner, set):
        if all(matrix[winner][x] > matrix[x][winner] or x == winner for x in ordering):
            ret += f"{winner} is a Condorcet winner.<br>"
    ret += f"<pre>{render_matrix(matrix, ordering)}</pre>"
    return ret


@app.route("/results/<uuid:poll_id>", methods=["GET"])
def results(poll_id):
    (ordering, matrix), is_open, num_ballots = tabulate_results(poll_id)
    groups = []
    reversal_count = itertools.count()
    for i, (group_a, group_b) in enumerate(itertools.pairwise(ordering)):
        a = Exemplar(group_a)
        b = Exemplar(group_b)
        groups.append(
            Group(i, group_a, f"{matrix[a][b]/num_ballots:.0%} ({matrix[a][b]})")
        )
    groups.append(Group(len(groups), group_b, ""))
    for i, group_a in enumerate(groups):
        for j, group_b in enumerate(groups[i:]):
            a = Exemplar(group_a.members)
            b = Exemplar(group_b.members)
            margin = matrix[a][b] - matrix[b][a]
            if margin < 0:
                group_b.reversals.append(
                    Reversal(
                        next(reversal_count),
                        group_b,
                        group_a,
                        f"{matrix[b][a]/num_ballots:.0%} ({matrix[b][a]})",
                    )
                )

    return flask.render_template(
        "ladder.html",
        groups=groups,
        is_open=is_open,
        num_ballots=num_ballots,
    )


@app.route("/results/winner/<uuid:poll_id>", methods=["GET"])
def winner(poll_id):
    ordering, matrix = results(poll_id)
    flask.response.content_type = "text/json"
    return json.dumps(ordering[0])


@app.route("/ballot/<uuid:poll_id>/<user_id>", methods=["GET"])
def ballot(poll_id, user_id):
    # token = flask.request.form["token"]  # FIXME
    with db_connection() as conn:
        cur = conn.execute(
            "SELECT title, candidates FROM polls WHERE id=?", (str(poll_id),)
        )
        row = cur.fetchone()
        if not row:
            abort(404)
        title, candidates_string = row
        cur = conn.execute(
            "SELECT ranking FROM ballots WHERE poll_id=? AND opaque_user_id=?",
            (
                str(poll_id),
                user_id,
            ),
        )
        row = cur.fetchone()
        ranking = row[0] if row else None
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
                "xyz",
                ranking,
            ),
        )
    return "OK"
