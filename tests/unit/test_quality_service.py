"""Tests for the online quality-observability sidecar's deterministic checks."""
from app.services.quality_service import QualityService, QualitySample


def _svc():
    return QualityService()


def test_clean_generation_passes():
    svc = _svc()
    r = svc.run_checks(
        QualitySample(request_id="r1", path="generate", prompt="hi", output="Hello there, friend.")
    )
    assert r["check_passed"] is True
    assert r["failed_checks"] == []
    assert r["refusal"] is False
    assert r["output_length"] > 0


def test_refusal_detected():
    svc = _svc()
    r = svc.run_checks(
        QualitySample(request_id="r2", path="generate", prompt="do X", output="I cannot help with that.")
    )
    assert r["refusal"] is True
    assert "refusal" in r["failed_checks"]
    assert r["check_passed"] is False


def test_empty_output_flagged():
    svc = _svc()
    r = svc.run_checks(QualitySample(request_id="r3", path="generate", prompt="hi", output="   "))
    assert "empty_output" in r["failed_checks"]


def test_truncation_flagged():
    svc = _svc()
    r = svc.run_checks(
        QualitySample(
            request_id="r4", path="generate", prompt="hi", output="a long answer", finish_reason="length"
        )
    )
    assert "truncated" in r["failed_checks"]


def test_classify_label_out_of_set():
    svc = _svc()
    r = svc.run_checks(
        QualitySample(
            request_id="r5",
            path="classify",
            prompt="great product",
            output="banana",
            label="banana",
            confidence=0.9,
            allowed_labels=["negative", "neutral", "positive"],
        )
    )
    assert "label_out_of_set" in r["failed_checks"]


def test_classify_confidence_out_of_range():
    svc = _svc()
    r = svc.run_checks(
        QualitySample(
            request_id="r6",
            path="classify",
            prompt="ok",
            output="positive",
            label="positive",
            confidence=1.5,
            allowed_labels=["negative", "neutral", "positive"],
        )
    )
    assert "confidence_out_of_range" in r["failed_checks"]


def test_classify_valid_passes():
    svc = _svc()
    r = svc.run_checks(
        QualitySample(
            request_id="r7",
            path="classify",
            prompt="great",
            output="positive",
            label="positive",
            confidence=0.95,
            allowed_labels=["negative", "neutral", "positive"],
        )
    )
    assert r["check_passed"] is True


def test_should_sample_rate_bounds(monkeypatch):
    from app.core import config

    svc = _svc()
    monkeypatch.setattr(config.settings, "quality_sampling_enabled", True)
    monkeypatch.setattr(config.settings, "quality_sample_rate", 1.0)
    assert svc.should_sample() is True
    monkeypatch.setattr(config.settings, "quality_sample_rate", 0.0)
    assert svc.should_sample() is False
