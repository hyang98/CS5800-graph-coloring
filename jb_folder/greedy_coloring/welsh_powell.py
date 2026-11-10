"""Copied from networkx 3.7, networkx/algorithms/coloring/greedy_coloring.py (strategy_largest_first).
Self-contained so it can be studied and modified independently.
"""

import itertools


def strategy_largest_first(G, colors):
    """Returns a list of the nodes of ``G`` in decreasing order by
    degree.

    ``G`` is a NetworkX graph. ``colors`` is ignored.

    """
    return sorted(G, key=G.degree, reverse=True)


strategy = strategy_largest_first


def color(G):
    if len(G) == 0:
        return {}
    colors = {}
    nodes = strategy(G, colors)
    for u in nodes:
        # Set to keep track of colors of neighbors
        nbr_colors = {colors[v] for v in G[u] if v in colors}
        # Find the first unused color.
        for color in itertools.count():
            if color not in nbr_colors:
                break
        # Assign the new color to the current node.
        colors[u] = color
    return colors
