import asyncio
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi import HTTPException

from fraud_detection.serving import model_loader


def test_get_predictor_ready():
    predictor = Mock()
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(predictor=predictor)))
    assert model_loader.get_predictor(request) is predictor


def test_get_predictor_not_ready():
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(predictor=None)))
    with pytest.raises(HTTPException) as error:
        model_loader.get_predictor(request)
    assert error.value.status_code == 503
    assert error.value.detail == 'Model not ready'


def test_get_predictor_missing_state_attribute():
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace()))
    with pytest.raises(HTTPException) as error:
        model_loader.get_predictor(request)
    assert error.value.status_code == 503


def test_lifespan_initializes_and_cleans_up(monkeypatch):
    predictor = Mock()
    predictor.model_name = 'fraud-detection'
    predictor.model_version = '1'
    constructor = Mock(return_value=predictor)
    monkeypatch.setattr(model_loader, 'FraudPredictor', constructor)
    app = SimpleNamespace(state=SimpleNamespace())

    async def check():
        async with model_loader.lifespan(app):
            assert app.state.predictor is predictor
        assert app.state.predictor is None

    asyncio.run(check())
    constructor.assert_called_once_with()


def test_lifespan_propagates_loading_failure(monkeypatch):
    monkeypatch.setattr(model_loader, 'FraudPredictor', Mock(side_effect=RuntimeError('load failed')))
    app = SimpleNamespace(state=SimpleNamespace())

    async def check():
        async with model_loader.lifespan(app):
            pass

    with pytest.raises(RuntimeError, match='load failed'):
        asyncio.run(check())
    assert app.state.predictor is None
