
from catboost import CatBoostClassifier

from fraud_detection.training.models.base import BaseFraudModel
from fraud_detection.training.preprocess import (
    CATEGORICAL_FEATURES,
)


class CatBoostFraudModel(BaseFraudModel):
    def __init__(self, config, random_seed=42):
        self.config = config.copy()
        self.random_seed = random_seed
        self.model = None

    def fit(self, X_train, y_train, X_val, y_val):
        params = self.config.copy()

        # Backward compatibility with old config
        params.pop("algorithm", None)

        self.model = CatBoostClassifier(
            **params,
            random_seed=self.random_seed,
            thread_count=-1,
            allow_writing_files=False,
        )

        self.model.fit(
            X_train,
            y_train,
            cat_features=CATEGORICAL_FEATURES,
            eval_set=(X_val, y_val),
            use_best_model=True,
        )

        return self

    def predict_proba(self, X):
        if self.model is None:
            raise RuntimeError(
                "CatBoost model has not been trained"
            )

        return self.model.predict_proba(X)

    def get_model(self):
        if self.model is None:
            raise RuntimeError(
                "CatBoost model has not been trained"
            )

        return self.model
