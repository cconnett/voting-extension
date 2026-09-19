import itertools
import json
import os.path
import random
import secrets
import sqlite3
import uuid
from typing import Dict, List, Tuple

import more_itertools


def generate_ballots(
    candidates, /, lambda_shuffle=1 / 5, lambda_swap=1 / 3, lambda_merge=1 / 2
):
    candidates = list(candidates)
    random.shuffle(candidates)
    while True:
        if random.random() < lambda_shuffle:
            random.shuffle(candidates)
        ballot = list(candidates)
        while True:
            if random.random() < lambda_swap:
                break
            i = random.randrange(len(ballot) - 1)
            ballot[i], ballot[i + 1] = ballot[i + 1], ballot[i]

        ballot = [(cand,) for cand in ballot]
        while random.random() > lambda_merge:
            if len(ballot) <= 1:
                break
            i = random.randrange(len(ballot) - 1)
            ballot[i : i + 2] = (ballot[i] + ballot[i + 1],)
        yield ballot


def ordering_to_ballot(ranking_dict: Dict[str, int]):
    normalized_ranks = {
        original_rank: normalized_rank
        for normalized_rank, original_rank in enumerate(
            sorted(set(ranking_dict.values()))
        )
    }
    ballot = [()] * len(normalized_ranks)
    for candidate, rank in ranking_dict.items():
        ballot[normalized_ranks[rank]] += (candidate,)
    return ballot


def ballot_to_ordering(ballot: List[Tuple[str]]):
    ordering = {}
    for i, rank in enumerate(ballot):
        for candidate in rank:
            ordering[candidate] = i + 1
    return ordering


if __name__ == "__main__":
    try:
        candidates = ["a", "b", "c", "d", "e"]
        new_id = uuid.uuid4()
        salt = secrets.randbits(64)
        if salt & 1 << 63:
            # sqlite INTs are 64-bit signed, so wrap the value into the signed regime.
            salt -= 1 << 64

        with sqlite3.connect(
            os.path.expanduser("~/polls.sqlite3"), autocommit=False
        ) as conn:
            conn.execute("PRAGMA foreign_keys=ON")
            conn.execute(
                "insert into polls (id, salt, channel_id, title, candidates) "
                'values (?, ?, "foo", "bar", ?)',
                (str(new_id), salt, json.dumps(candidates)),
            )

            for user_id, b in enumerate(
                more_itertools.take(97, generate_ballots(["a", "b", "c", "d", "e"]))
            ):
                order = ballot_to_ordering(b)
                round_trip = ordering_to_ballot(order)
                assert b == round_trip
                print(json.dumps(order))
                conn.execute(
                    "insert or replace into ballots (poll_id, opaque_user_id, ranking) "
                    "values (?, ?, ?)",
                    (str(new_id), str(user_id), json.dumps(order)),
                )
        print(f"http://localhost:5000/old_results/{str(new_id)}")
    except Exception as e:
        import pdb

        print(e)
        pdb.post_mortem()
