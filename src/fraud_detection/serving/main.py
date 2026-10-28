
from time import perf_counter
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import Response

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    generate_latest,
)

from fraud_detection.serving.model_loader import (
    lifespan,
    get_predictor,
)
from fraud_detection.serving.predictor import FraudPredictor
from fraud_detection.serving.schemas import (
    TransactionRequest,
    PredictionResponse,
)
from fraud_detection.serving.metrics import (
    PREDICTION_REQUESTS,
    PREDICTION_LATENCY,
    FRAUD_PREDICTIONS,
)


app = FastAPI(
    title="Fraud Detection API",
    version="1.0.0",
    lifespan=lifespan,
)


PredictorDependency = Annotated[
    FraudPredictor,
    Depends(get_predictor),
]


@app.get("/health/live")
def liveness():
    return {"status": "alive"}


@app.get("/health/ready")
def readiness(
    predictor: PredictorDependency,
):
    return {
        "status": "ready",
        "model_name": predictor.model_name,
        "model_version": predictor.model_version,
    }


@app.post(
    "/predict",
    response_model=PredictionResponse,
)
def predict(
    transaction: TransactionRequest,
    predictor: PredictorDependency,
):
    start = perf_counter()
    status = "success"

    try:
        result = predictor.predict(
            transaction.model_dump()
        )

        if result["prediction"] == 1:
            FRAUD_PREDICTIONS.inc()

        return result

    except HTTPException:
        status = "error"
        raise

    except Exception as exc:
        status = "error"
        raise HTTPException(
            status_code=500,
            detail="Prediction failed",
        ) from exc

    finally:
        PREDICTION_REQUESTS.labels(
            status=status
        ).inc()

        PREDICTION_LATENCY.observe(
            perf_counter() - start
        )


@app.get("/metrics")
def metrics():
    return Response(
        content=generate_latest(),
        media_type=CONTENT_TYPE_LATEST,
    )
