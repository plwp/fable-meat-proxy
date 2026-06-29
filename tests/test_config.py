import pytest

from fable_meat_proxy import Config
from fable_meat_proxy.config import (
    DEFAULT_FABLE_MODELS,
    MIN_POLL_INTERVAL_SECONDS,
    fable_models_from_env,
)
from fable_meat_proxy.errors import FableConfigError


def test_config_from_env_defaults(monkeypatch):
    monkeypatch.setenv("FABLE_FRIEND_EMAIL", "hank@example.com")
    monkeypatch.delenv("FABLE_REPLY_TIMEOUT_SECONDS", raising=False)
    monkeypatch.delenv("FABLE_REPLY_TIMEOUT_BUSINESS_DAYS", raising=False)
    monkeypatch.delenv("FABLE_POLL_INTERVAL", raising=False)
    cfg = Config.from_env()
    assert cfg.friend_email == "hank@example.com"
    assert cfg.reply_timeout_business_days == 7.0
    assert cfg.reply_timeout_seconds is None
    assert cfg.poll_interval == 120.0


def test_config_from_env_business_days_override(monkeypatch):
    monkeypatch.setenv("FABLE_FRIEND_EMAIL", "hank@example.com")
    monkeypatch.setenv("FABLE_REPLY_TIMEOUT_BUSINESS_DAYS", "3")
    assert Config.from_env().reply_timeout_business_days == 3.0


def test_config_from_env_seconds_override(monkeypatch):
    monkeypatch.setenv("FABLE_FRIEND_EMAIL", "hank@example.com")
    monkeypatch.setenv("FABLE_REPLY_TIMEOUT_SECONDS", "30")
    assert Config.from_env().reply_timeout_seconds == 30.0


def test_config_missing_friend_raises(monkeypatch):
    monkeypatch.delenv("FABLE_FRIEND_EMAIL", raising=False)
    with pytest.raises(FableConfigError):
        Config.from_env()


def test_config_invalid_email_raises():
    with pytest.raises(FableConfigError):
        Config(friend_email="not-an-email")


def test_config_invalid_number_raises(monkeypatch):
    monkeypatch.setenv("FABLE_FRIEND_EMAIL", "hank@example.com")
    monkeypatch.setenv("FABLE_POLL_INTERVAL", "soon")
    with pytest.raises(FableConfigError):
        Config.from_env()


def test_config_from_env_clamps_tiny_poll_interval(monkeypatch):
    monkeypatch.setenv("FABLE_FRIEND_EMAIL", "hank@example.com")
    monkeypatch.setenv("FABLE_POLL_INTERVAL", "0")
    assert Config.from_env().poll_interval == MIN_POLL_INTERVAL_SECONDS


def test_config_from_env_default_fable_models(monkeypatch):
    monkeypatch.setenv("FABLE_FRIEND_EMAIL", "hank@example.com")
    monkeypatch.delenv("FABLE_MODELS", raising=False)
    assert Config.from_env().fable_models == DEFAULT_FABLE_MODELS


def test_fable_models_from_env_parses_csv(monkeypatch):
    monkeypatch.setenv("FABLE_MODELS", "Foo-Model, bar-model ,")
    assert fable_models_from_env() == frozenset({"foo-model", "bar-model"})


def test_fable_models_from_env_blank_falls_back(monkeypatch):
    monkeypatch.setenv("FABLE_MODELS", "   ")
    assert fable_models_from_env() == DEFAULT_FABLE_MODELS
