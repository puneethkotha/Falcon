# Online quality observability

"200 OK" is not "the output was correct." Falcon samples a fraction of completions and
scores them off the hot path so that success/latency and output quality are separate
signals. Implemented in `app/services/quality_service.py`.

## How it works

1. **Async sampler.** 5-10% of completions (`QUALITY_SAMPLE_RATE`, default 0.1) are
   enqueued into a bounded `asyncio.Queue`. A full queue drops samples (counted by
   `falcon_quality_dropped_total`) rather than blocking the request path. Scoring never
   happens synchronously -- a judge on the critical path would double latency and cost.
2. **Deterministic checks first** (free, catch most regressions):
   - generate path: refusal-phrase detection, empty output, truncation (`finish_reason=length`).
   - classify path: label in the allowed set, confidence in `[0,1]`.
   Failures increment `falcon_quality_check_failed_total{check}`; refusals also increment
   `falcon_refusal_total`.
3. **LLM-as-judge second** (optional, `QUALITY_JUDGE_ENABLED`, off by default because it
   needs a budget). A rubric prompt returns a 0-1 score recorded in `falcon_judge_score`.
   Treat it as a noisy estimator: calibrate against 50-100 human labels and trend it.
4. **Storage.** Scores are written to the `quality_scores` Postgres table alongside the
   request log (best-effort, off the critical path).

## Dashboards and alerts

- Grafana: **Falcon Quality Observability** (`grafana/dashboards/falcon-quality.json`) --
  judge-score trend, refusal rate, check-failure rate by check, sampling throughput/drops,
  and a reliability success-rate panel to show the decoupling.
- Alerts (`prometheus/alerts/quality_alerts.yml`): refusal-rate spike, judge-score drop,
  high check-failure rate.

## Calibrating the judge

```bash
# labels.json: [{"human": 1, "judge": 0.9}, {"human": 0, "judge": 0.2}, ...]
python benchmarks/calibrate_judge.py labels.json --threshold 0.5
# reports raw agreement and Cohen's Kappa; target Kappa > 0.6
```

## Demonstrating the decoupling

The acceptance criterion is that a deliberately degraded model shows a quality drop while
reliability stays green. Reproduce locally against `tools/mock_vllm_server.py`:

```bash
# Send prompts containing TRIGGER_REFUSAL so the mock returns a refusal; with
# QUALITY_SAMPLE_RATE=1.0 every one is scored.
curl -sN -X POST http://localhost:8001/generate -H 'Content-Type: application/json' \
  -d '{"prompt":"TRIGGER_REFUSAL please help","max_tokens":16}' >/dev/null
# falcon_refusal_total rises and check-failure rate climbs, while
# inference_requests_total{status="success"} stays green and TTFT is unaffected.
```

A live capture of exactly this (refusal metric rising while success rate stays 100%) is
in the PR evidence.
