#!/usr/bin/env python3
"""Plot the throughput-vs-latency frontier from a guidellm sweep report.

x-axis  = system output tokens/sec
y-axes  = TTFT p95 (left) and TPOT p95 (right)
markers = the knee (max curvature) and the max-sustainable-rate at the chosen SLO
footer  = cost per 1M output tokens at the operating point

HONESTY: this script only draws numbers it is given. It never invents measurements.
Use --self-test to verify the tooling runs end-to-end; that mode draws obviously
SYNTHETIC data with a watermark and must never be presented as a real result.

Usage:
  python benchmarks/plot_frontier.py docs/frontier/Qwen-Qwen3-1.7B-sweep.json \\
      --gpu-price-per-hour 0.80 --ttft-slo-ms 500 --tpot-slo-ms 50 \\
      --out docs/frontier/frontier.png
  python benchmarks/plot_frontier.py --self-test --out docs/frontier/EXAMPLE_synthetic_frontier.png
"""
import argparse
import json
import sys
from typing import Dict, List, Optional


def _first(d: dict, *keys, default=None):
    for k in keys:
        if k in d and d[k] is not None:
            return d[k]
    return default


def load_guidellm(path: str) -> List[Dict]:
    """Parse a guidellm JSON report into comparable per-rate points.

    guidellm's schema has shifted across versions, so this reads defensively: it
    walks the list of benchmark runs and pulls TTFT p95 (ms), TPOT/ITL p95 (ms),
    and output tokens/sec from whichever field names are present.
    """
    with open(path) as f:
        report = json.load(f)

    runs = report.get("benchmarks") or report.get("results") or report
    if isinstance(runs, dict):
        runs = runs.get("benchmarks", [])

    points: List[Dict] = []
    for run in runs:
        metrics = run.get("metrics", run)
        ttft = _first(metrics, "time_to_first_token_ms", "ttft_ms", "ttft_p95_ms")
        tpot = _first(metrics, "inter_token_latency_ms", "tpot_ms", "itl_ms", "tpot_p95_ms")
        thr = _first(metrics, "output_tokens_per_second", "tokens_per_second", "throughput_tok_s")
        # Percentile sub-objects are common: prefer p95 when present.
        ttft = _p95(ttft)
        tpot = _p95(tpot)
        thr = _mean_or_value(thr)
        if ttft is None or tpot is None or thr is None:
            continue
        points.append(
            {
                "rate": _first(run, "request_rate", "rate", default=len(points) + 1),
                "throughput_tok_s": float(thr),
                "ttft_p95_ms": float(ttft),
                "tpot_p95_ms": float(tpot),
            }
        )
    points.sort(key=lambda p: p["throughput_tok_s"])
    return points


def _p95(v):
    if isinstance(v, dict):
        return _first(v, "p95", "percentiles_95", "95", default=_first(v, "median", "mean"))
    return v


def _mean_or_value(v):
    if isinstance(v, dict):
        return _first(v, "mean", "value", "median")
    return v


def max_rate_at_slo(points: List[Dict], ttft_slo_ms: float, tpot_slo_ms: float) -> Optional[Dict]:
    """Highest-throughput point that still satisfies both SLOs (the operating point)."""
    ok = [p for p in points if p["ttft_p95_ms"] <= ttft_slo_ms and p["tpot_p95_ms"] <= tpot_slo_ms]
    return max(ok, key=lambda p: p["throughput_tok_s"]) if ok else None


def find_knee(points: List[Dict]) -> Optional[Dict]:
    """Kneedle-style knee: point of maximum distance from the chord joining the
    endpoints of the throughput-vs-TTFT curve (past which latency degrades without
    throughput gain)."""
    if len(points) < 3:
        return None
    x0, y0 = points[0]["throughput_tok_s"], points[0]["ttft_p95_ms"]
    x1, y1 = points[-1]["throughput_tok_s"], points[-1]["ttft_p95_ms"]
    dx, dy = x1 - x0, y1 - y0
    denom = (dx * dx + dy * dy) ** 0.5 or 1.0
    best, best_d = None, -1.0
    for p in points[1:-1]:
        d = abs(dy * p["throughput_tok_s"] - dx * p["ttft_p95_ms"] + x1 * y0 - y1 * x0) / denom
        if d > best_d:
            best, best_d = p, d
    return best


def cost_per_1m_output(tokens_per_second: float, gpu_price_per_hour: float) -> float:
    """Cost per 1M output tokens at a given system throughput.

    At throughput T tok/s the host produces T tokens per second for price
    (price_per_hour / 3600) per second, so cost/token = price_per_second / T.
    """
    if tokens_per_second <= 0:
        return float("nan")
    price_per_second = gpu_price_per_hour / 3600.0
    return price_per_second / tokens_per_second * 1_000_000.0


def _synthetic_points() -> List[Dict]:
    # Obviously fake, monotone example just to exercise the plotting code path.
    pts = []
    for i in range(1, 11):
        thr = 40 * i
        ttft = 120 + (i ** 2) * 9          # rises faster past the knee
        tpot = 18 + i * 3
        pts.append({"rate": i, "throughput_tok_s": thr, "ttft_p95_ms": ttft, "tpot_p95_ms": tpot})
    return pts


def plot(points, out, ttft_slo_ms, tpot_slo_ms, gpu_price_per_hour, title, synthetic=False):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    xs = [p["throughput_tok_s"] for p in points]
    ttft = [p["ttft_p95_ms"] for p in points]
    tpot = [p["tpot_p95_ms"] for p in points]

    fig, ax1 = plt.subplots(figsize=(9, 5.5))
    fig.patch.set_facecolor("#0B0D10")
    ax1.set_facecolor("#14171C")
    ax1.plot(xs, ttft, "-o", color="#E8A33D", label="TTFT p95 (ms)")
    ax1.set_xlabel("output tokens/sec (system)", color="#E6E8EB")
    ax1.set_ylabel("TTFT p95 (ms)", color="#E8A33D")
    ax1.tick_params(colors="#8A9099")
    ax1.axhline(ttft_slo_ms, color="#E5484D", ls="--", lw=1, alpha=0.7)

    ax2 = ax1.twinx()
    ax2.plot(xs, tpot, "-s", color="#5B8DEF", label="TPOT p95 (ms)")
    ax2.set_ylabel("TPOT p95 (ms)", color="#5B8DEF")
    ax2.tick_params(colors="#8A9099")

    op = max_rate_at_slo(points, ttft_slo_ms, tpot_slo_ms)
    knee = find_knee(points)
    footer = []
    if knee:
        ax1.annotate("knee", (knee["throughput_tok_s"], knee["ttft_p95_ms"]),
                     color="#E6E8EB", xytext=(0, 18), textcoords="offset points",
                     arrowprops=dict(arrowstyle="->", color="#E6E8EB"))
    if op:
        ax1.scatter([op["throughput_tok_s"]], [op["ttft_p95_ms"]], s=120,
                    facecolors="none", edgecolors="#E8A33D", linewidths=2, zorder=5)
        cost = cost_per_1m_output(op["throughput_tok_s"], gpu_price_per_hour)
        footer.append(
            f"operating point: {op['throughput_tok_s']:.0f} tok/s at "
            f"TTFT p95 {op['ttft_p95_ms']:.0f}ms, TPOT p95 {op['tpot_p95_ms']:.0f}ms"
        )
        footer.append(
            f"cost/1M output tokens = ${cost:.3f} at ${gpu_price_per_hour:.2f}/GPU-hr "
            f"(idle = $0 on scale-to-zero)"
        )
    else:
        footer.append(f"no point met SLO (TTFT<{ttft_slo_ms}ms, TPOT<{tpot_slo_ms}ms)")

    ax1.set_title(title, color="#E6E8EB")
    fig.text(0.5, 0.01, "  |  ".join(footer), ha="center", color="#8A9099", fontsize=9)

    if synthetic:
        fig.text(0.5, 0.5, "SYNTHETIC EXAMPLE\nNOT A MEASUREMENT", ha="center", va="center",
                 color="#E5484D", fontsize=30, alpha=0.30, rotation=25, weight="bold")

    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(lines1 + lines2, labels1 + labels2, loc="upper left", facecolor="#14171C",
               edgecolor="#232830", labelcolor="#E6E8EB")

    fig.tight_layout(rect=[0, 0.04, 1, 1])
    fig.savefig(out, dpi=130, facecolor=fig.get_facecolor())
    print(f"wrote {out}")
    if op:
        print(f"operating point: {op['throughput_tok_s']:.0f} tok/s, "
              f"cost/1M = ${cost_per_1m_output(op['throughput_tok_s'], gpu_price_per_hour):.3f}")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("report", nargs="?", help="guidellm JSON report path")
    ap.add_argument("--out", default="docs/frontier/frontier.png")
    ap.add_argument("--ttft-slo-ms", type=float, default=500)
    ap.add_argument("--tpot-slo-ms", type=float, default=50)
    ap.add_argument("--gpu-price-per-hour", type=float, default=0.80,
                    help="e.g. Modal L4 ~ $0.80/hr; used only for cost annotation")
    ap.add_argument("--self-test", action="store_true", help="render a SYNTHETIC example (no real data)")
    args = ap.parse_args(argv)

    if args.self_test:
        pts = _synthetic_points()
        plot(pts, args.out, args.ttft_slo_ms, args.tpot_slo_ms, args.gpu_price_per_hour,
             "Falcon frontier (SYNTHETIC self-test)", synthetic=True)
        return 0

    if not args.report:
        ap.error("provide a guidellm report path, or use --self-test")
    pts = load_guidellm(args.report)
    if not pts:
        print("no usable points parsed from report", file=sys.stderr)
        return 1
    plot(pts, args.out, args.ttft_slo_ms, args.tpot_slo_ms, args.gpu_price_per_hour,
         "Falcon throughput-vs-latency frontier")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
