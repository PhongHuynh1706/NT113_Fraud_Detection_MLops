
import argparse
import json
import os

import mlflow
import yaml

from fraud_detection.training.preprocess import (
    TARGET,
    FEATURE_COLUMNS,
    load_dataset,
    split_dataset,
    fit_preprocessing,
    transform_features,
)
from fraud_detection.training.evaluate import evaluate_model
from fraud_detection.training.threshold_analysis import (
    analyze_thresholds,
)
from fraud_detection.training.model_trainer import train_model
from fraud_detection.training.mlflow_logger import (
    log_training_info,
    log_threshold_analysis,
    log_evaluation,
    log_inference_artifacts,
    log_model,
)


def train(config_path, threshold_override=None):
    # ==========================================
    # 1. LOAD CONFIGURATION
    # ==========================================
    with open(config_path, encoding="utf-8") as f:
        config = yaml.safe_load(f)

    data_config = config["data"]
    model_section = config["model"]
    evaluation_config = config["evaluation"]
    mlflow_config = config["mlflow"]

    algorithm = model_section["algorithm"].lower()

    supported_algorithms = (
        "catboost",
        "lightgbm",
        "xgboost",
    )

    if algorithm not in supported_algorithms:
        raise ValueError(
            f"Unsupported algorithm: {algorithm}. "
            f"Supported: {supported_algorithms}"
        )

    model_config = model_section[algorithm].copy()

    custom_threshold = (
        evaluation_config.get("custom_threshold", 0.80)
        if threshold_override is None
        else threshold_override
    )

    if not 0.0 <= custom_threshold <= 1.0:
        raise ValueError(
            "Threshold must be between 0 and 1"
        )

    # ==========================================
    # 2. CONFIGURE MLFLOW
    # ==========================================
    tracking_uri = os.getenv(
        "MLFLOW_TRACKING_URI",
        mlflow_config["tracking_uri"],
    )

    mlflow.set_tracking_uri(tracking_uri)
    mlflow.set_experiment(
        mlflow_config["experiment_name"]
    )

    # ==========================================
    # 3. LOAD AND SPLIT DATASET
    # ==========================================
    df = load_dataset(data_config["path"])

    train_df, val_df, test_df = split_dataset(
        df,
        train_ratio=data_config["train_ratio"],
        validation_ratio=data_config["validation_ratio"],
    )

    # ==========================================
    # 4. SHARED PREPROCESSING
    # ==========================================
    preprocessing = fit_preprocessing(train_df)

    X_train = transform_features(
        train_df,
        preprocessing,
    )
    X_val = transform_features(
        val_df,
        preprocessing,
    )
    X_test = transform_features(
        test_df,
        preprocessing,
    )

    y_train = train_df[TARGET]
    y_val = val_df[TARGET]
    y_test = test_df[TARGET]

    # ==========================================
    # 5. START MLFLOW RUN
    # ==========================================
    with mlflow.start_run(
        run_name=f"{algorithm}-training"
    ) as run:

        log_training_info(
            model_config={
                "algorithm": algorithm,
                **model_config,
            },
            train_samples=len(train_df),
            val_samples=len(val_df),
            test_samples=len(test_df),
            feature_count=len(FEATURE_COLUMNS),
        )

        mlflow.log_params({
            "train_ratio": data_config["train_ratio"],
            "validation_ratio": data_config["validation_ratio"],
            "test_ratio": data_config["test_ratio"],
            "random_seed": data_config["random_seed"],
        })

        # ======================================
        # 6. TRAIN SELECTED MODEL
        # ======================================
        model = train_model(
            algorithm=algorithm,
            X_train=X_train,
            y_train=y_train,
            X_val=X_val,
            y_val=y_val,
            model_config=model_config,
            random_seed=data_config["random_seed"],
        )

        # ======================================
        # 7. VALIDATION THRESHOLD ANALYSIS
        # ======================================
        val_probabilities = model.predict_proba(
            X_val
        )[:, 1]

        threshold, comparison, custom_metrics = (
            analyze_thresholds(
                y_val,
                val_probabilities,
                custom_threshold=custom_threshold,
            )
        )

        log_threshold_analysis(
            custom_threshold,
            comparison,
            custom_metrics,
        )

        # ======================================
        # 8. MODEL EVALUATION
        # ======================================
        test_probabilities = model.predict_proba(
            X_test
        )[:, 1]

        val_metrics = evaluate_model(
            y_val,
            val_probabilities,
            threshold,
        )

        test_metrics = evaluate_model(
            y_test,
            test_probabilities,
            threshold,
        )

        log_evaluation(
            threshold,
            val_metrics,
            test_metrics,
        )

        # ======================================
        # 9. LOG INFERENCE ARTIFACTS
        # ======================================
        log_inference_artifacts(
            preprocessing,
            threshold,
        )

        # ======================================
        # 10. LOG MODEL TO MLFLOW
        # ======================================
        model_info = log_model(
            model=model,
            algorithm=algorithm,
            input_example=X_train.head(5),
        )

        # ======================================
        # 11. TRAINING RESULT
        # ======================================
        result = {
            "algorithm": algorithm,
            "run_id": run.info.run_id,
            "model_uri": model_info.model_uri,
            "threshold": threshold,
            "validation": val_metrics,
            "test": test_metrics,
        }

        print(
            json.dumps(
                result,
                indent=2,
            )
        )

        return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Fraud Detection Model Training"
    )

    parser.add_argument(
        "--config",
        type=str,
        default="configs/training.yml",
        help="Path to training configuration",
    )

    parser.add_argument(
        "--threshold",
        type=float,
        default=None,
        help="Custom threshold for validation comparison",
    )

    args = parser.parse_args()

    train(
        config_path=args.config,
        threshold_override=args.threshold,
    )
