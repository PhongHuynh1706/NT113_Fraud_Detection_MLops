"""FastAPI with explicit model readiness and bounded-cardinality metrics."""

import logging
import os
import time
from collections.abc import Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram, generate_latest
from prometheus_client.exposition import CONTENT_TYPE_LATEST
from pydantic import BaseModel, ConfigDict, Field, StrictFloat, StrictInt

from fraud_detection.model import FeatureMismatch, ModelRuntime

logger = logging.getLogger(__name__)


class PredictionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    instances: list[dict[str, StrictFloat | StrictInt]] = Field(min_length=1, max_length=256)


class Prediction(BaseModel):
    fraud_probability: float
    is_fraud: bool


class PredictionResponse(BaseModel):
    model_version: str
    threshold: float
    predictions: list[Prediction]


def create_app(loader: Callable[[], ModelRuntime] | None = None) -> FastAPI:
    registry = CollectorRegistry()
    requests = Counter(
        "fraud_http_requests_total",
        "HTTP responses",
        ["route", "method", "status"],
        registry=registry,
    )
    latency = Histogram(
        "fraud_http_request_duration_seconds", "HTTP latency", ["route"], registry=registry
    )
    scores = Histogram(
        "fraud_prediction_score",
        "Fraud probability",
        registry=registry,
        buckets=(0.01, 0.1, 0.25, 0.5, 0.75, 0.9, 0.99, 1),
    )
    decisions = Counter("fraud_predictions_total", "Predictions", ["decision"], registry=registry)
    ready = Gauge("fraud_model_ready", "Model loaded", registry=registry)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.runtime = None
        try:
            if loader is not None:
                app.state.runtime = loader()
            elif path := os.getenv("MODEL_MANIFEST"):
                app.state.runtime = ModelRuntime.load(path)
            ready.set(int(app.state.runtime is not None))
        except Exception:
            # Avoid leaking credentials, artifact URIs or data through exceptions.
            logger.error("Model initialization failed; check model configuration and connectivity")
            ready.set(0)
        yield
        app.state.runtime = None
        ready.set(0)

    app = FastAPI(title="Fraud Detection API", version="0.1.0", lifespan=lifespan)

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request: Request, error: RequestValidationError):
        # Do not echo transaction values, including NaN/Infinity, into error responses.
        return JSONResponse(status_code=422, content={"detail": "Invalid prediction payload"})

    @app.middleware("http")
    async def instrument(request: Request, call_next):
        start = time.perf_counter()
        status = 500
        try:
            response = await call_next(request)
            status = response.status_code
            return response
        finally:
            route = request.scope.get("route")
            route_name = route.path if route is not None else "unmatched"
            if route_name not in {"/metrics", "/health/live", "/health/ready"}:
                known_methods = {"GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"}
                method = request.method if request.method in known_methods else "OTHER"
                requests.labels(route_name, method, str(status)).inc()
                latency.labels(route_name).observe(time.perf_counter() - start)

    @app.get("/health/live")
    def live():
        return {"status": "alive"}

    @app.get("/health/ready")
    def readiness(request: Request):
        if request.app.state.runtime is None:
            raise HTTPException(503, "Model is not ready")
        return {"status": "ready"}

    @app.get("/metrics", include_in_schema=False)
    def metrics():
        return Response(generate_latest(registry), headers={"Content-Type": CONTENT_TYPE_LATEST})

    @app.post("/predict", response_model=PredictionResponse)
    def predict(payload: PredictionRequest, request: Request):
        runtime = request.app.state.runtime
        if runtime is None:
            raise HTTPException(503, "Model is not ready")
        try:
            probabilities = runtime.predict(payload.instances)
        except FeatureMismatch as error:
            raise HTTPException(422, "Feature names must match the model manifest") from error
        except Exception as error:
            logger.error("Model prediction failed")
            raise HTTPException(500, "Model prediction failed") from error
        results = []
        for probability in probabilities:
            is_fraud = probability >= runtime.manifest.threshold
            scores.observe(probability)
            decisions.labels("fraud" if is_fraud else "legitimate").inc()
            results.append(Prediction(fraud_probability=probability, is_fraud=is_fraud))
        return PredictionResponse(
            model_version=runtime.manifest.model_version,
            threshold=runtime.manifest.threshold,
            predictions=results,
        )

    return app


app = create_app()
