# Pin the OS image so the distribution cannot change under a floating Python tag.
FROM cgr.dev/chainguard/wolfi-base@sha256:580c9ae79c0229cc381475fbfbed0d91fab5d6606e57cd78732f9836de109e90 AS python-base
RUN apk add --no-cache python-3.11 libstdc++

FROM python-base AS builder
RUN apk add --no-cache py3.11-pip \
    && python3.11 -m venv --without-pip /opt/venv
WORKDIR /build
COPY pyproject.toml ./
COPY src ./src
# Build isolation stays in this stage; do not seed build tools into the runtime venv.
RUN python3.11 -m pip --python /opt/venv/bin/python install --no-cache-dir . \
    && python3.11 -m pip --python /opt/venv/bin/python check \
    && /opt/venv/bin/python -c "import mlflow.pyfunc; import sklearn; import fraud_detection.api"

FROM python-base AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 HOME=/tmp MLFLOW_TRACKING_URI=http://mlflow:5000 \
    PATH=/opt/venv/bin:$PATH
WORKDIR /app
COPY --from=builder /opt/venv /opt/venv
RUN addgroup -g 10001 app && adduser -D -u 10001 -G app -h /home/app app
USER 10001:10001
EXPOSE 8000
CMD ["uvicorn", "fraud_detection.api:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
