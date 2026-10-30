from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .models import DEFAULTS, PRESETS, ExperimentRequest
from .orchestrator import ExperimentBusy, ExperimentNotFound, Orchestrator
from .storage import list_experiments

BASE_PATH = os.getenv("BENCHMARK_BASE_PATH", "/benchmark").rstrip("/") or "/benchmark"
ROOT = Path(__file__).resolve().parent.parent
STATIC = Path(__file__).resolve().parent / "static"
RESULTS = Path(os.getenv("BENCHMARK_RESULTS_DIR", "/data/results"))
RUNNER = Path(os.getenv("BENCHMARK_RUNNER_JAR", "/app/benchmark-runner.jar"))
ANALYSIS = ROOT / "scripts" / "analyze.py"

app = FastAPI(title="Multiplayer Framework Experimental Stand", docs_url=None, redoc_url=None, openapi_url=None)
app.mount(f"{BASE_PATH}/static", StaticFiles(directory=STATIC), name="static")
orch = Orchestrator(RESULTS, RUNNER, ANALYSIS)

@app.get(BASE_PATH)
@app.get(BASE_PATH + "/")
def index():
    return FileResponse(STATIC / "index.html")

@app.get(BASE_PATH + "/api/health")
def health():
    return {"status": "ok", "runnerJar": RUNNER.exists(), "resultsDir": str(RESULTS)}

@app.get(BASE_PATH + "/api/config")
def config():
    return {"defaults": DEFAULTS.model_dump(), "presets": PRESETS}

@app.get(BASE_PATH + "/api/experiments")
def experiments():
    return {"items": list_experiments(RESULTS), "active": orch.current()}

@app.post(BASE_PATH + "/api/experiments", status_code=202)
def start_experiment(payload: ExperimentRequest):
    try:
        return {"id": orch.start(payload)}
    except ExperimentBusy as exc:
        raise HTTPException(409, str(exc)) from exc

@app.get(BASE_PATH + "/api/experiments/{experiment_id}")
def experiment(experiment_id: str):
    try:
        return orch.get(experiment_id)
    except ExperimentNotFound as exc:
        raise HTTPException(404, "experiment not found") from exc

@app.post(BASE_PATH + "/api/experiments/{experiment_id}/stop")
def stop_experiment(experiment_id: str):
    try:
        orch.stop(experiment_id)
        return {"ok": True}
    except ExperimentNotFound as exc:
        raise HTTPException(404, str(exc)) from exc

@app.get(BASE_PATH + "/api/experiments/{experiment_id}/file/{path:path}")
def result_file(experiment_id: str, path: str):
    root = (RESULTS / experiment_id).resolve()
    target = (root / path).resolve()
    if root not in target.parents and target != root:
        raise HTTPException(400, "invalid path")
    if not target.is_file():
        raise HTTPException(404, "file not found")
    return FileResponse(target)
