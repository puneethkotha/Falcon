#!/usr/bin/env python3
"""Calibrate the LLM-as-judge against human labels with Cohen's Kappa.

The judge is a noisy estimator. Before trusting its trend, calibrate it against a small
human-labeled set (50-100 items) and report Cohen's Kappa (target > 0.6). Trend the
score; never gate on a single verdict.

Input: a JSON list of {"human": 0|1, "judge": 0.0-1.0} items. The judge score is
binarized at --threshold to compare against binary human labels ("acceptable" vs not).

Usage:
  python benchmarks/calibrate_judge.py labels.json --threshold 0.5
  python benchmarks/calibrate_judge.py --self-test
"""
import argparse
import json
import sys
from typing import List, Tuple


def cohens_kappa(pairs: List[Tuple[int, int]]) -> float:
    """Cohen's Kappa for two binary raters."""
    n = len(pairs)
    if n == 0:
        return float("nan")
    a = b = c = d = 0  # confusion cells for (human, judge)
    for h, j in pairs:
        if h == 1 and j == 1:
            a += 1
        elif h == 1 and j == 0:
            b += 1
        elif h == 0 and j == 1:
            c += 1
        else:
            d += 1
    po = (a + d) / n
    p_yes = ((a + b) / n) * ((a + c) / n)
    p_no = ((c + d) / n) * ((b + d) / n)
    pe = p_yes + p_no
    if pe == 1.0:
        return 1.0 if po == 1.0 else 0.0
    return (po - pe) / (1 - pe)


def load_pairs(path: str, threshold: float) -> List[Tuple[int, int]]:
    with open(path) as f:
        items = json.load(f)
    pairs = []
    for it in items:
        human = int(it["human"])
        judge = 1 if float(it["judge"]) >= threshold else 0
        pairs.append((human, judge))
    return pairs


def _self_test_pairs() -> List[Tuple[int, int]]:
    # Mostly-agreeing synthetic set (kappa clearly > 0.6).
    pairs = [(1, 1)] * 40 + [(0, 0)] * 40 + [(1, 0)] * 5 + [(0, 1)] * 5
    return pairs


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("labels", nargs="?", help="JSON list of {human:0|1, judge:0.0-1.0}")
    ap.add_argument("--threshold", type=float, default=0.5)
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args(argv)

    if args.self_test:
        pairs = _self_test_pairs()
    else:
        if not args.labels:
            ap.error("provide a labels JSON file, or use --self-test")
        pairs = load_pairs(args.labels, args.threshold)

    kappa = cohens_kappa(pairs)
    agree = sum(1 for h, j in pairs if h == j) / len(pairs)
    verdict = "PASS" if kappa > 0.6 else "BELOW TARGET (>0.6)"
    print(f"n={len(pairs)}  raw agreement={agree:.3f}  Cohen's Kappa={kappa:.3f}  [{verdict}]")
    return 0 if kappa > 0.6 else 2


if __name__ == "__main__":
    raise SystemExit(main())
