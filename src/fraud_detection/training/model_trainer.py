
import numpy as np
import pandas as pd

from catboost import CatBoostClassifier
from lightgbm import LGBMClassifier, early_stopping
from xgboost import XGBClassifier

from sklearn.compose import ColumnTransformer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

from fraud_detection.training.preprocess import (
    NUMERIC_FEATURES,
    CATEGORICAL_FEATURES,
    BINARY_FEATURES,
)


class LightGBMFeatureTransformer:
    def __init__(self):
        self.categories = {}

    def fit(self, X):
        for column in CATEGORICAL_FEATURES:
            self.categories[column] = sorted(
                X[column].astype(str).unique().tolist()
            )
        return self

    def transform(self, X):
        X = X.copy()

        for column in CATEGORICAL_FEATURES:
            X[column] = pd.Categorical(
                X[column].astype(str),
                categories=self.categories[column],
            )

        return X


class LightGBMModel:
    def __init__(self, estimator, transformer):
        self.estimator = estimator
        self.transformer = transformer

    def predict_proba(self, X):
        X_transformed = self.transformer.transform(X)
        return self.estimator.predict_proba(X_transformed)


def train_catboost(
    X_train,
    y_train,
    X_val,
    y_val,
    model_config,
    random_seed,
):
    params = model_config.copy()

    model = CatBoostClassifier(
        **params,
        random_seed=random_seed,
        thread_count=-1,
        allow_writing_files=False,
    )

    model.fit(
        X_train,
        y_train,
        cat_features=CATEGORICAL_FEATURES,
        eval_set=(X_val, y_val),
        use_best_model=True,
    )

    return model


def train_lightgbm(
    X_train,
    y_train,
    X_val,
    y_val,
    model_config,
    random_seed,
):
    params = model_config.copy()

    stopping_rounds = params.pop(
        "early_stopping_rounds", None
    )

    transformer = LightGBMFeatureTransformer()
    transformer.fit(X_train)

    X_train_transformed = transformer.transform(X_train)
    X_val_transformed = transformer.transform(X_val)

    model = LGBMClassifier(
        **params,
        random_state=random_seed,
        n_jobs=-1,
    )

    callbacks = []

    if stopping_rounds:
        callbacks.append(
            early_stopping(stopping_rounds, verbose=False)
        )

    model.fit(
        X_train_transformed,
        y_train,
        eval_set=[(X_val_transformed, y_val)],
        eval_metric="average_precision",
        categorical_feature=CATEGORICAL_FEATURES,
        callbacks=callbacks,
    )

    return LightGBMModel(model, transformer)


def train_xgboost(
    X_train,
    y_train,
    X_val,
    y_val,
    model_config,
    random_seed,
):
    params = model_config.copy()

    stopping_rounds = params.pop(
        "early_stopping_rounds", None
    )

    negative_count = int((y_train == 0).sum())
    positive_count = int((y_train == 1).sum())

    if positive_count == 0:
        raise ValueError(
            "Training data contains no fraud samples"
        )

    params.setdefault(
        "scale_pos_weight",
        negative_count / positive_count,
    )

    preprocessor = ColumnTransformer(
        transformers=[
            (
                "numeric",
                "passthrough",
                NUMERIC_FEATURES + BINARY_FEATURES,
            ),
            (
                "categorical",
                OneHotEncoder(
                    handle_unknown="ignore",
                ),
                CATEGORICAL_FEATURES,
            ),
        ]
    )

    X_train_encoded = preprocessor.fit_transform(X_train)
    X_val_encoded = preprocessor.transform(X_val)

    if stopping_rounds is not None:
        params["early_stopping_rounds"] = stopping_rounds
        
    model = XGBClassifier(
        **params,
        random_state=random_seed,
        n_jobs=-1,
        early_stopping_rounds=stopping_rounds,
    )

    model.fit(
        X_train_encoded,
        y_train,
        eval_set=[(X_val_encoded, y_val)],
        verbose=False,
    )

    return Pipeline(
        steps=[
            ("preprocessing", preprocessor),
            ("classifier", model),
        ]
    )


def train_model(
    algorithm,
    X_train,
    y_train,
    X_val,
    y_val,
    model_config,
    random_seed,
):
    algorithm = algorithm.lower()

    trainers = {
        "catboost": train_catboost,
        "lightgbm": train_lightgbm,
        "xgboost": train_xgboost,
    }

    if algorithm not in trainers:
        raise ValueError(
            f"Unsupported algorithm: {algorithm}. "
            f"Supported algorithms: {list(trainers)}"
        )

    return trainers[algorithm](
        X_train=X_train,
        y_train=y_train,
        X_val=X_val,
        y_val=y_val,
        model_config=model_config,
        random_seed=random_seed,
    )
