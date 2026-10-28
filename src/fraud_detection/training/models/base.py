
from abc import ABC, abstractmethod


class BaseFraudModel(ABC):
    @abstractmethod
    def fit(self, X_train, y_train, X_val, y_val):
        pass

    @abstractmethod
    def predict_proba(self, X):
        pass

    @abstractmethod
    def get_model(self):
        pass
