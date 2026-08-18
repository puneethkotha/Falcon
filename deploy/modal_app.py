"""Modal scale-to-zero GPU deployment of the vLLM engine for Falcon.

Near-$0 hosting path: the engine idles at zero cost and cold-starts on demand; billing
is per-second only while a request is in flight. New Modal accounts get $30/month in
credits, which comfortably covers a portfolio demo's sporadic traffic. Falcon's workers
point VLLM_BASE_URL at this endpoint's /v1 URL; the always-free CPU/mock backstop keeps
the demo from ever showing a broken state during a cold start.

Deploy:
  pip install modal
  modal deploy deploy/modal_app.py
  # -> https://<workspace>--falcon-vllm-serve.modal.run  (use <url>/v1 as VLLM_BASE_URL)

Alternatives with the same scale-to-zero property: RunPod serverless (sub-200ms
FlashBoot cold starts) and HF Inference Endpoints (pause = no charge). Fly.io GPU
machines were deprecated and are not an option.

This file is deployment scaffolding; it requires a Modal account and is not exercised
in the build environment.
"""
import os

import modal

MODEL_ID = os.environ.get("MODEL_ID", "Qwen/Qwen3-1.7B")
GPU = os.environ.get("MODAL_GPU", "L4")  # 24GB; ample for a 1.7B model
VLLM_PORT = 8000

# Pin vllm; bake HF cache into the image so cold starts do not re-download weights.
image = (
    modal.Image.debian_slim()
    .pip_install("vllm==0.6.3", "huggingface_hub[hf_transfer]")
    .env({"HF_HUB_ENABLE_HF_TRANSFER": "1"})
)

app = modal.App("falcon-vllm")


@app.function(
    image=image,
    gpu=GPU,
    # Scale to zero: no container is kept warm; billing is per-second while serving.
    scaledown_window=60,      # seconds of idle before the container is released
    timeout=600,
    allow_concurrent_inputs=64,  # let continuous batching pack concurrent requests
)
@modal.web_server(port=VLLM_PORT, startup_timeout=300)
def serve():
    import subprocess

    cmd = [
        "vllm", "serve", MODEL_ID,
        "--host", "0.0.0.0",
        "--port", str(VLLM_PORT),
        "--max-model-len", "4096",
        "--enable-prefix-caching",     # kept ON (see docs/SERVING_LEVERS.md)
        "--enable-chunked-prefill",    # kept ON
        # Speculative decoding intentionally OFF by default; enable per the batch-size rule.
    ]
    subprocess.Popen(" ".join(cmd), shell=True)
