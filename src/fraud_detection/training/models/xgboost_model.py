
from sklearn.compose import ColumnTransformer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder
from xgboost import XGBClassifier

from fraud_detection.training.models.base import BaseFraudModel
from fraud_detection.training.preprocess import (
    NUMERIC_FEATURES,
    CATEGORICAL_FEATURES,
    BINARY_FEATURES,
)


class XGBoostFraudModel(BaseFraudModel):
    def __init__(self, config, random_seed=42):
        self.config = config
        self.random_seed = random_seed
        self.model = None

    def fit(self, X_train, y_train, X_val, y_val):
        preprocessing = ColumnTransformer([
            (
                "numeric",
                "passthrough",
                NUMERIC_FEATURES + BINARY_FEATURES,
            ),
            (
                "categorical",
                OneHotEncoder(handle_unknown="ignore"),
                CATEGORICAL_FEATURES,
            ),
        ])

        params = {
            k: v for k, v in self.config.items()
            if k != "algorithm"
        }

        params.setdefault("random_state", self.random_seed)
        params.setdefault("eval_metric", "aucpr")
        params.setdefault("tree_method", "hist")

        classifier = XGBClassifier(**params)

        self.model = Pipeline([
            ("preprocessing", preprocessing),
            ("classifier", classifier),
        ])

        self.model.fit(X_train, y_train)
        return self

    def predict_proba(self, X):
        return self.model.predict_proba(X)

    def get_model(self):
        return self.model
