"""MLflow adapter retaining the fitted preprocessing and positive-class mapping."""

import mlflow.pyfunc
import pandas as pd


class FraudProbabilityModel(mlflow.pyfunc.PythonModel):
    def __init__(self, pipeline):
        self.pipeline = pipeline

    def predict(self, context, model_input, params=None):
        positive_index = list(self.pipeline.classes_).index(1)
        probabilities = self.pipeline.predict_proba(model_input)[:, positive_index]
        return pd.DataFrame({"fraud_probability": probabilities}, index=model_input.index)
