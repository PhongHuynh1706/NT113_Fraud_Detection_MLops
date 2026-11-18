"""Explicit offline improvement gate; production promotion is a separate action."""


def improves_reference(candidate, reference, minimum_precision=0.6):
    return (
        candidate["precision"] > minimum_precision
        and candidate["accuracy"] > 0.6
        and candidate["f1"] > reference["f1"]
        and candidate["recall"] >= reference["recall"]
    )
