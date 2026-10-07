"""The serial numbers of the office's manifests: a counter, so that a run gives the same
numbers every time."""
import itertools

_numbers = itertools.count(1)


def next_serial() -> str:
    return f"M-{next(_numbers):04d}"
