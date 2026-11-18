from fraud_detection.selection import improves_reference


def test_improvement_requires_f1_gain_without_recall_regression():
    reference = {"f1": 0.79, "recall": 0.75}
    candidate = {"accuracy": 0.99, "precision": 0.85, "recall": 0.8, "f1": 0.82}
    assert improves_reference(candidate, reference)
    assert not improves_reference({**candidate, "f1": 0.79}, reference)
    assert not improves_reference({**candidate, "recall": 0.74}, reference)
    assert not improves_reference({**candidate, "precision": 0.6}, reference)
    assert not improves_reference({**candidate, "accuracy": 0.6}, reference)
