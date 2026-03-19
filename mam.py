import collections
import enum
import itertools
import logging
import random

import networkx


class Tiebreaker(enum.Enum):
    RVH = 1
    LINEAR = 2


def MaximizeAffirmedMajorities(ballots, tiebreaker=Tiebreaker.LINEAR):
    # Normalize ballots by wrapping naked entries in a singleton tuple.
    ballots = [
        [(rank,) if not isinstance(rank, tuple) else rank for rank in ballot]
        for ballot in ballots
    ]

    # Any value mentioned on any ballot is a candidate. Collect them all.
    candidates = set()
    for ballot in ballots:
        for rank in ballot:
            candidates |= set(rank)

    # Table of count of the pairwise preferences.
    preferences = collections.defaultdict(collections.Counter)

    # Shuffle the ballots to later create a tiebreak ordering using random voter
    # hierarchy.
    random.shuffle(ballots)

    # Make a tiebreak ordering that will be a total linear ordering after processing all
    # ballots.
    tiebreak_ordering = networkx.DiGraph()
    tiebreak_ordering.add_nodes_from(candidates)

    # Two things happen in the main counting loop.
    for ballot in ballots:
        for i, higher_rank in enumerate(ballot):
            for lower_rank in ballot[i + 1 :]:
                for a, b in itertools.product(higher_rank, lower_rank):
                    # 1. Add each of this ballot's strict preferences to the tiebreak
                    # ordering.
                    if not networkx.has_path(tiebreak_ordering, b, a):
                        tiebreak_ordering.add_edge(a, b)
                    # 2. Add the strict preference in the preference table.
                    preferences[a][b] += 1
    logging.debug(preferences)

    # In pathological cases, the tiebreak ordering might be incomplete. Complete the
    # tiebreak ordering with a random order.
    final_breaker = list(candidates)
    random.shuffle(final_breaker)
    for a, b in zip(final_breaker, final_breaker[1:]):
        if not networkx.has_path(tiebreak_ordering, b, a):
            tiebreak_ordering.add_edge(a, b)
    tiebreak_ordering = list(networkx.topological_sort(tiebreak_ordering))

    # We are now ready to construct the final order.
    final_order = networkx.DiGraph()
    final_order.add_nodes_from(candidates)

    pairwise_defeats = []
    for a, b in itertools.product(candidates, candidates):
        if a != b:
            pairwise_defeats.append(
                (
                    (a, b),
                    (preferences[a][b] - preferences[b][a], preferences[a][b]),
                )
            )
    # Sort the pairwise defeats first by majority minus minority, then majority.
    pairwise_defeats.sort(key=lambda e: e[1], reverse=True)
    # Apply each pairwise defeat to the final order. Groups of pairwise defeats tie may
    # tie, so group by the metric value.
    for _, group in itertools.groupby(pairwise_defeats, key=lambda e: e[1]):
        group = list(group)
        # The group tie is broken by (1) which pair's defeated candidate is the lowest
        # on the tiebreak order; then (2) which pair's winning candidate is highest in
        # the tiebreak order.
        group.sort(
            key=lambda e: (
                -tiebreak_ordering.index(e[0][1]),
                tiebreak_ordering.index(e[0][0]),
            )
        )
        # Apply the pairwise defeat.
        for (a, b), metric in group:
            if not networkx.has_path(final_order, b, a):
                logging.debug(f'Applying {a} > {b} : {metric}')
                final_order.add_edge(a, b)
            else:
                logging.debug(f'Cannot apply {a} > {b} : {metric}')

    # Finally, apply the tiebreak ordering to resolve any other unresolved loops.
    for a, b in zip(tiebreak_ordering, tiebreak_ordering[1:]):
        if not networkx.has_path(final_order, b, a):
            final_order.add_edge(a, b)
    return list(networkx.topological_sort(final_order))
