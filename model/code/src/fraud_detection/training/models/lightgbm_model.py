
import pandas as pd
from lightgbm import LGBMClassifier

from fraud_detection.training.models.base import BaseFraudModel
from fraud_detection.training.preprocess import CATEGORICAL_FEATURES


class LightGBMFraudModel(BaseFraudModel):
    def __init__(self, config, random_seed=42):
        self.config = config
        self.random_seed = random_seed
        self.model = None
        self.categories = {}

    def _transform(self, X, fit=False):
        X = X.copy()

        for column in CATEGORICAL_FEATURES:
            values = X[column].astype(str)

            if fit:
                self.categories[column] = sorted(
                    values.unique().tolist()
                )

            X[column] = pd.Categorical(
                values,
                categories=self.categories[column],
            )

        return X

    def fit(self, X_train, y_train, X_val, y_val):
        X_train = self._transform(X_train, fit=True)
        X_val = self._transform(X_val)

        params = {
            k: v for k, v in self.config.items()
            if k != "algorithm"
        }

        params.setdefault("random_state", self.random_seed)
        params.setdefault("verbosity", -1)

        self.model = LGBMClassifier(**params)
        self.model.fit(
            X_train,
            y_train,
            categorical_feature=CATEGORICAL_FEATURES,
            eval_set=[(X_val, y_val)],
        )

        return self

    def predict_proba(self, X):
        return self.model.predict_proba(
            self._transform(X)
        )

    def get_model(self):
        return self.model
