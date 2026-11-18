FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 HOME=/tmp MLFLOW_TRACKING_URI=http://mlflow:5000
WORKDIR /app
COPY pyproject.toml ./
COPY src ./src
RUN pip install . && useradd --uid 10001 --create-home app
USER 10001:10001
EXPOSE 8000
CMD ["uvicorn", "fraud_detection.api:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
