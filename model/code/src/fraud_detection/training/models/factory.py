
from fraud_detection.training.models.catboost_model import (
    CatBoostFraudModel,
)
from fraud_detection.training.models.lightgbm_model import (
    LightGBMFraudModel,
)
from fraud_detection.training.models.xgboost_model import (
    XGBoostFraudModel,
)


MODEL_REGISTRY = {
    "catboost": CatBoostFraudModel,
    "lightgbm": LightGBMFraudModel,
    "xgboost": XGBoostFraudModel,
}


def create_model(algorithm, config, random_seed=42):
    algorithm = algorithm.lower()

    if algorithm not in MODEL_REGISTRY:
        raise ValueError(
            f"Unsupported algorithm: {algorithm}"
        )

    return MODEL_REGISTRY[algorithm](
        config=config,
        random_seed=random_seed,
    )
    