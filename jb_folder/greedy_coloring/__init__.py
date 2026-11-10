"""Copies of four networkx greedy coloring strategies."""
from . import welsh_powell, dsatur, smallest_last, independent_set

ALGORITHMS = {
    "welsh_powell": welsh_powell.color,
    "dsatur": dsatur.color,
    "smallest_last": smallest_last.color,
    "independent_set": independent_set.color,
}

# Name of the matching strategy in networkx.greedy_color(G, strategy=...)
NX_STRATEGY_NAMES = {
    "welsh_powell": "largest_first",
    "dsatur": "DSATUR",
    "smallest_last": "smallest_last",
    "independent_set": "independent_set",
}
