import collections
import enum
import itertools
import logging
import random

import networkx


class Tiebreaker(enum.Enum):
    # Return ties as sets within the ordering.
    NONE = 0
    # Random Voter Hierarchy: Break ties with the preferences of a random ballot,
    # cascading to additional ballots when the tie remains unresolved. Ties are still
    # possible if no voter expresses any preference between two candidates; ties are
    # returned as sets.
    RVH = 1
    # As RVH, but break any remaining ties with a random total ordering; returns a total
    # ordering of the candidates.
    LINEAR = 2


def MaximizeAffirmedMajorities(
    ballots, /, candidates=(), tiebreaker=Tiebreaker.NONE, seed=None
):
    """Return the social choice ordering and the matrix of pairwise defeats."""
    # Normalize ballots by wrapping naked entries in a singleton tuple.
    ballots = [
        [(rank,) if not isinstance(rank, (tuple, list)) else rank for rank in ballot]
        for ballot in ballots
    ]

    # Any value mentioned on any ballot is a candidate. Collect them all.
    candidates = set(candidates)
    for ballot in ballots:
        for rank in ballot:
            candidates |= set(rank)

    for ballot in ballots:
        unranked = set(candidates)
        for rank in ballot:
            unranked -= set(rank)
        if unranked:
            ballot.append(tuple(sorted(unranked)))

    seeded_random = random.Random(seed)
    linear_breaker = sorted(candidates)
    random.Random(seeded_random.randbytes(32)).shuffle(linear_breaker)
    ballots = sorted(ballots)
    seeded_random.shuffle(ballots)

    # Table of count of the pairwise preferences.
    preferences = collections.defaultdict(collections.Counter)

    # Make a tiebreak ordering that will ideally be a total linear ordering
    # after processing all ballots. (If it is not, some candidates may be tied
    # in the final ranking, or ties broken by chance.)
    tiebreak_graph = networkx.DiGraph()
    tiebreak_graph.add_nodes_from(candidates)

    # Two things happen in the main counting loop.
    for ballot in ballots:
        for i, higher_rank in enumerate(ballot):
            for lower_rank in ballot[i + 1 :]:
                for a, b in itertools.product(higher_rank, lower_rank):
                    # 1. Add each of this ballot's strict preferences to the tiebreak
                    # ordering.
                    if tiebreaker != Tiebreaker.NONE and not networkx.has_path(
                        tiebreak_graph, b, a
                    ):
                        tiebreak_graph.add_edge(a, b)
                    # 2. Add the strict preference in the preference table.
                    preferences[a][b] += 1

    if tiebreaker == Tiebreaker.LINEAR:
        for a, b in itertools.product(candidates, candidates):
            if linear_breaker.index(a) < linear_breaker.index(
                b
            ) and not networkx.has_path(tiebreak_graph, b, a):
                tiebreak_graph.add_edge(a, b)
    tiebreak_ranks = {}
    for index, generation in enumerate(
        networkx.topological_generations(tiebreak_graph)
    ):
        tiebreak_ranks.update({candidate: index for candidate in generation})
    logging.debug(tiebreak_ranks)

    # We are now ready to construct the final order.
    final_order = networkx.DiGraph()
    final_order.add_nodes_from(candidates)

    pairwise_defeats = []
    for a, b in itertools.product(candidates, candidates):
        if a != b and preferences[a][b] > preferences[b][a]:
            pairwise_defeats.append(
                (
                    (a, b),
                    (
                        preferences[a][b],
                        -preferences[b][a],
                        tiebreak_ranks[b],
                        -tiebreak_ranks[a],
                    ),
                )
            )
    # Sort the pairwise defeats first by majority minus minority, then majority.
    pairwise_defeats.sort(key=lambda e: e[1], reverse=True)
    # Apply each pairwise defeat to the final order. Group by the metric value
    # so tied groups are processed together.
    for metric, group in itertools.groupby(pairwise_defeats, key=lambda e: e[1]):
        group = list(group)
        if metric[0] <= 0:
            # The first metric of this group is negative. We've crossed the
            # midway point and would now be processing inverses of defeats
            # already added. We're done.
            break
        if len(group) > 1:
            logging.debug("Probing application of tied group")
        # Apply the pairwise defeat. If every edge in this group applies
        # cleanly, it is kept. Otherwise, the group is hopelessly tied and must
        # be ignored.
        probe = final_order.copy()
        for (a, b), metric in group:
            if not networkx.has_path(probe, b, a):
                logging.debug(f"Applying {a} > {b} : {metric}")
                probe.add_edge(a, b)
            else:
                logging.debug(f"Cannot apply {a} > {b} : {metric}")
                probe = final_order
                break
        final_order = probe

    logging.debug(tiebreak_ranks)
    if tiebreaker != Tiebreaker.NONE:
        # Finally, apply the tiebreak ordering to resolve any other unresolved loops.
        for a, b in itertools.product(candidates, candidates):
            if tiebreak_ranks[a] < tiebreak_ranks[b] and not networkx.has_path(
                final_order, b, a
            ):
                final_order.add_edge(a, b)
    generations = list(networkx.topological_generations(final_order))
    return (
        [
            generation[0] if len(generation) == 1 else set(generation)
            for generation in generations
        ],
        preferences,
    )
