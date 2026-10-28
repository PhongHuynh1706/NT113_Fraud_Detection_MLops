
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request

from fraud_detection.serving.predictor import FraudPredictor


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: load model từ MLflow
    app.state.predictor = None

    predictor = FraudPredictor()
    app.state.predictor = predictor

    print(
        f"Model ready: {predictor.model_name} "
        f"v{predictor.model_version}"
    )

    try:
        yield
    finally:
        # Shutdown: giải phóng reference
        app.state.predictor = None


def get_predictor(request: Request) -> FraudPredictor:
    predictor = getattr(
        request.app.state,
        "predictor",
        None,
    )

    if predictor is None:
        raise HTTPException(
            status_code=503,
            detail="Model not ready",
        )

    return predictor
