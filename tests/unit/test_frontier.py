"""Tests for the frontier analysis helpers (pure functions, no plotting)."""
import importlib.util
import os

_spec = importlib.util.spec_from_file_location(
    "plot_frontier",
    os.path.join(os.path.dirname(__file__), "..", "..", "benchmarks", "plot_frontier.py"),
)
pf = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pf)


def test_cost_per_1m_output():
    # 100 tok/s at $3.60/hr => $0.001/s => $1e-5/token => $10 per 1M tokens.
    assert abs(pf.cost_per_1m_output(100, 3.60) - 10.0) < 1e-6


def test_cost_zero_throughput_is_nan():
    import math

    assert math.isnan(pf.cost_per_1m_output(0, 1.0))


def test_max_rate_at_slo_picks_highest_throughput_within_slo():
    pts = [
        {"throughput_tok_s": 100, "ttft_p95_ms": 200, "tpot_p95_ms": 20},
        {"throughput_tok_s": 200, "ttft_p95_ms": 400, "tpot_p95_ms": 40},
        {"throughput_tok_s": 300, "ttft_p95_ms": 900, "tpot_p95_ms": 60},  # violates SLO
    ]
    op = pf.max_rate_at_slo(pts, ttft_slo_ms=500, tpot_slo_ms=50)
    assert op["throughput_tok_s"] == 200


def test_max_rate_at_slo_none_when_all_violate():
    pts = [{"throughput_tok_s": 100, "ttft_p95_ms": 800, "tpot_p95_ms": 80}]
    assert pf.max_rate_at_slo(pts, 500, 50) is None


def test_find_knee_returns_interior_point():
    pts = pf._synthetic_points()
    knee = pf.find_knee(pts)
    assert knee is not None
    assert pts[0]["throughput_tok_s"] < knee["throughput_tok_s"] < pts[-1]["throughput_tok_s"]
