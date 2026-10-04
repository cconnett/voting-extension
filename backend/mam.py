import collections
import enum
import itertools
import logging
import random
from typing import List, Set

import networkx

logging.basicConfig(level=logging.DEBUG)


class Tiebreaker(enum.Enum):
    NONE = 0
    # Random Voter Hierarchy: Break ties with the preferences of a random
    # ballot, cascading to additional ballots when the tie remains
    # unresolved. Ties are still possible if no voter expresses any preference
    # between two candidates. Return a list of (potentially singleton) sets of
    # tied candidates.
    RVH = 1
    # As RVH, but break any remaining ties with a random total ordering. Return
    # a list of singleton sets of candidates.
    LINEAR = 2


def MaximizeAffirmedMajorities(
    ballots, /, candidates=(), tiebreaker=Tiebreaker.NONE, seed=None
) -> List[Set[str]]:
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
    matrix = collections.defaultdict(collections.Counter)

    # Make a tiebreak ordering that will ideally be a total linear ordering
    # after processing all ballots. If it is not, some candidates may be tied
    # in the final ranking.
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
                    matrix[a][b] += 1

    if tiebreaker == Tiebreaker.LINEAR:
        # Apply a final random total ordering to the tiebreak ordering. This
        # guarantees.
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

    # We are now ready to construct the final order.
    final_graph = networkx.DiGraph()
    final_graph.add_nodes_from(candidates)

    pairwise_defeats = []
    for a, b in itertools.product(candidates, candidates):
        if a != b and matrix[a][b] > matrix[b][a]:
            pairwise_defeats.append(
                (
                    (a, b),
                    (
                        matrix[a][b],
                        -matrix[b][a],
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
        propose = []
        for (a, b), metric in group:
            if networkx.has_path(final_graph, a, b):
                # This edge is already implied by transitivity, so apply it
                # immediately.
                logging.debug(f"Applied {a} > {b} : {metric} by transitivity")
                final_graph.add_edge(a, b, metric=metric)
            elif networkx.has_path(final_graph, b, a):
                # This edge creates a loop contrary to stronger defeats. Reject
                # it immediately.
                logging.debug(f"Rejected {a} > {b} : {metric}")
            else:
                # Putative edges will be checked all at once in the next step.
                propose.append(((a, b), metric))
        if len(propose) == 1:
            (a, b), metric = propose[0]
            final_graph.add_edge(a, b, metric=metric)
            logging.debug(f"Applied {a} > {b} : {metric}")
        elif len(propose) > 1:
            logging.debug("Probing tied group")
            # Apply the entire `propose` group. Any edge that has a path
            # reversing it must be rejected. Keep the others.
            keepable = []
            probe = final_graph.copy()
            for (a, b), metric in propose:
                probe.add_edge(a, b)
            for (a, b), metric in propose:
                if networkx.has_path(probe, b, a):
                    logging.debug(f"Cannot apply {a} > {b} : {metric} (creates loop)")
                else:
                    keepable.append((a, b, metric))
                    logging.debug(f"Applied {a} > {b} : {metric} (keepable from tie)")
            logging.debug("End of probe")
            for a, b, metric in keepable:
                final_graph.add_edge(a, b, metric=metric)

    if tiebreaker != Tiebreaker.NONE:
        logging.debug(f"Applying final tiebreaker. Ranks: {tiebreak_ranks}")
        # Finally, apply the tiebreak ordering to resolve any other unresolved loops.
        for a, b in itertools.product(candidates, candidates):
            if (
                not final_graph.has_edge(a, b)
                and tiebreak_ranks[a] < tiebreak_ranks[b]
                and not networkx.has_path(final_graph, b, a)
            ):

                final_graph.add_edge(a, b, metric=(0, 0, 0, 0))
    generations = list(networkx.topological_generations(final_graph))
    final_ordering = [set(generation) for generation in generations]
    return (final_ordering, matrix, final_graph)
