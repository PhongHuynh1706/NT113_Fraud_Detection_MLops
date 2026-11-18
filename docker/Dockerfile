FROM python:3.11-slim
RUN apt-get update \
    && apt-get upgrade --yes \
    && rm -rf /var/lib/apt/lists/*
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 HOME=/tmp MLFLOW_TRACKING_URI=http://mlflow:5000
WORKDIR /app
COPY pyproject.toml ./
COPY src ./src
# setuptools is needed to build the project, not to serve the installed model.
# Remove it too: its vendored jaraco.context/wheel copies are separate packages
# from any top-level upgrades and would otherwise remain visible to Trivy.
RUN python -m pip install . \
    && python -m pip uninstall --yes setuptools wheel jaraco.context \
    && python -m pip check \
    && python -c "import mlflow.pyfunc; import sklearn; import fraud_detection.api" \
    && useradd --uid 10001 --create-home app
USER 10001:10001
EXPOSE 8000
CMD ["uvicorn", "fraud_detection.api:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
