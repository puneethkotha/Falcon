"""Tests for generation request schema and cache-key helpers."""
import pytest
from pydantic import ValidationError

from app.models.schemas import GenerationRequest


def test_prompt_wraps_as_user_message():
    req = GenerationRequest(prompt="hello", max_tokens=10)
    assert req.as_messages() == [{"role": "user", "content": "hello"}]
    assert req.sampling_params()["max_tokens"] == 10


def test_messages_pass_through():
    req = GenerationRequest(messages=[{"role": "system", "content": "s"}, {"role": "user", "content": "u"}])
    assert req.as_messages() == [{"role": "system", "content": "s"}, {"role": "user", "content": "u"}]


def test_requires_prompt_or_messages():
    with pytest.raises(ValidationError):
        GenerationRequest(max_tokens=5)


def test_cache_key_depends_on_model_and_text():
    from app.api.routes import _classify_cache_key
    from app.core import config

    k1 = _classify_cache_key("same text")
    k2 = _classify_cache_key("same text")
    k3 = _classify_cache_key("different text")
    assert k1 == k2
    assert k1 != k3

    original = config.settings.model_id
    try:
        config.settings.model_id = "another/model"
        assert _classify_cache_key("same text") != k1
    finally:
        config.settings.model_id = original
