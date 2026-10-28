
from prometheus_client import Counter, Histogram


PREDICTION_REQUESTS = Counter(
    "fraud_prediction_requests_total",
    "Total prediction requests",
    ["status"],
)

PREDICTION_LATENCY = Histogram(
    "fraud_prediction_duration_seconds",
    "Prediction request latency in seconds",
)

FRAUD_PREDICTIONS = Counter(
    "fraud_prediction_positive_total",
    "Transactions predicted as fraud",
)
