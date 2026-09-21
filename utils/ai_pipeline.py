# -*- coding: utf-8 -*-
"""Estado del pipeline IA diario y cores AIS11."""
import json
import os
from datetime import datetime

AIS11_CORE_SCRIPTS = (
    "models/precalculate_timesfm.py",
    "models/finetune_tspulse.py",
    "models/train_minirocket_gpu.py",
)

GPU_SKIP_SCRIPTS = (
    "models/precalculate_timesfm.py",
    "models/finetune_tspulse.py",
    "models/finetune_tspulse_multi.py",
    "models/train_minirocket_gpu.py",
)

STATUS_PATH = os.path.join(
    os.path.abspath(os.path.join(os.path.dirname(__file__), "..")),
    "data",
    "ai_pipeline_status.json",
)


def cuda_available():
    try:
        import torch
        return bool(torch.cuda.is_available())
    except Exception:
        return False


def should_skip_gpu_script(script, has_cuda=None):
    if has_cuda is None:
        has_cuda = cuda_available()
    return (not has_cuda) and script in GPU_SKIP_SCRIPTS


def evaluate_ais11_cores(step_results):
    """
    step_results: dict script -> 'ok' | 'failed' | 'skipped'
    Escribe timestamp solo si los 3 cores AIS11 corrieron OK.
    """
    cores = {s: step_results.get(s, "missing") for s in AIS11_CORE_SCRIPTS}
    if all(v == "ok" for v in cores.values()):
        return True, "cores AIS11 OK"
    if any(v == "failed" for v in cores.values()):
        failed = [s for s, v in cores.items() if v == "failed"]
        return False, "falló: " + ", ".join(failed)
    skipped = [s for s, v in cores.items() if v == "skipped"]
    return False, "GPU ausente, cores no regenerados: " + ", ".join(skipped)


def save_pipeline_status(payload):
    os.makedirs(os.path.dirname(STATUS_PATH), exist_ok=True)
    payload = dict(payload)
    payload["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(STATUS_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)


def fetch_ai_dataset():
    """Carga OHLC+indicadores según AI_TICKERS (lab 18 / live_us 5y)."""
    from utils.tickers_universe import resolve_ai_fetch_args
    from backtester import fetch_data, TICKERS
    tickers, start = resolve_ai_fetch_args()
    data = fetch_data(tickers=tickers, start_date=start)
    loop = list(tickers) if tickers is not None else list(TICKERS)
    return data, loop


def load_pipeline_status():
    if not os.path.exists(STATUS_PATH):
        return {}
    try:
        with open(STATUS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}
