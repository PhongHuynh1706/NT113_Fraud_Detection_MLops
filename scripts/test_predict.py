
import json
import os

os.environ["OPENBLAS_NUM_THREADS"] = "1"
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"
os.environ["NUMEXPR_NUM_THREADS"] = "1"

import pandas as pd
import requests
import yaml

from fraud_detection.training.preprocess import (
    FEATURE_COLUMNS,
    TARGET,
    load_dataset,
    split_dataset,
)


def main():
    # 1. Đọc config giống train.py
    with open(
        "configs/training.yml",
        encoding="utf-8",
    ) as f:
        config = yaml.safe_load(f)

    # 2. Load dataset gốc
    df = load_dataset(
        config["data"]["path"]
    )

    # 3. Chia dataset giống training
    _, _, test_df = split_dataset(
        df,
        train_ratio=config["data"]["train_ratio"],
        validation_ratio=config["data"]["validation_ratio"],
    )

    # 4. Lấy giao dịch đầu tiên của test set
    transaction = test_df.iloc[0]

    payload = {}

    for column in FEATURE_COLUMNS:
        value = transaction[column]

        if pd.isna(value):
            payload[column] = None
        elif hasattr(value, "item"):
            payload[column] = value.item()
        else:
            payload[column] = value

    # 5. Gửi request tới FastAPI
    response = requests.post(
        "http://127.0.0.1:8000/predict",
        json=payload,
        timeout=30,
    )

    response.raise_for_status()
    result = response.json()

    # 6. In kết quả
    print("\n=== FRAUD PREDICTION ===")

    print(json.dumps(
        result,
        indent=2,
    ))

    print("\n=== GROUND TRUTH ===")
    print("Actual label:", int(transaction[TARGET]))
    print("Predicted label:", result["prediction"])

    print(
        "Correct:",
        int(transaction[TARGET]) == result["prediction"]
    )


if __name__ == "__main__":
    main()
