"""Verify the actual HTTP service, optionally with a supplied model manifest."""

import argparse
import json
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def request(url, payload=None):
    data = None if payload is None else json.dumps(payload).encode()
    req = Request(url, data=data, headers={"Content-Type": "application/json"})
    try:
        with urlopen(req, timeout=5) as response:
            return response.status, response.read().decode()
    except HTTPError as error:
        return error.code, error.read().decode()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:18000")
    parser.add_argument("--manifest", type=Path)
    args = parser.parse_args()
    base = args.url.rstrip("/")
    for _ in range(30):
        try:
            live, _ = request(base + "/health/live")
            ready, _ = request(base + "/health/ready")
            if live == 200 and ready == (200 if args.manifest else 503):
                break
        except (URLError, TimeoutError, ConnectionError):
            pass
        time.sleep(1)
    else:
        raise RuntimeError("Container did not reach the expected health/readiness state")
    if args.manifest:
        manifest = json.loads(args.manifest.read_text(encoding="utf-8-sig"))
        payload = {"instances": [{name: 0.0 for name in manifest["features"]}]}
        status, body = request(base + "/predict", payload)
        if status != 200:
            raise RuntimeError(f"Prediction returned HTTP {status}")
        result = json.loads(body)
        assert result["model_version"] == manifest["model_version"]
        assert len(result["predictions"]) == 1
        assert 0 <= result["predictions"][0]["fraud_probability"] <= 1
        print("Model prediction passed:", json.dumps(result))
    status, body = request(base + "/metrics")
    assert status == 200 and "fraud_model_ready" in body
    print("Container HTTP health, readiness and metrics passed")


if __name__ == "__main__":
    main()
