from __future__ import annotations

import os
import random
import signal
import subprocess
import threading
from pathlib import Path
from typing import Any

from .models import ExperimentRequest
from .storage import atomic_json, environment_snapshot, read_json, safe_id, utc_now, write_checksums

class ExperimentBusy(RuntimeError): pass
class ExperimentNotFound(RuntimeError): pass

class Orchestrator:
    def __init__(self, results_dir: Path, runner_jar: Path, analysis_script: Path):
        self.results_dir=results_dir; self.runner_jar=runner_jar; self.analysis_script=analysis_script
        self.results_dir.mkdir(parents=True, exist_ok=True)
        self._lock=threading.RLock(); self._thread=None; self._current_id=None; self._process=None; self._stop=threading.Event()

    def current(self):
        with self._lock:
            return None if not self._current_id else self.get(self._current_id)

    def start(self, request: ExperimentRequest) -> str:
        with self._lock:
            if self._thread and self._thread.is_alive(): raise ExperimentBusy("another experiment is already running")
            experiment_id=safe_id(request.name); directory=self.results_dir/experiment_id; directory.mkdir(parents=True,exist_ok=False); plan=self._plan(request)
            atomic_json(directory/"manifest.json", {"schemaVersion":1,"id":experiment_id,"createdAt":utc_now(),"request":request.model_dump(),"environment":environment_snapshot(),"plan":plan,"note":"Each repetition is a fresh JVM process. WebSocket/STOMP is outside the scheduler benchmark hot path."})
            atomic_json(directory/"status.json", {"status":"queued","completedRuns":0,"totalRuns":len(plan),"currentRun":None})
            self._stop.clear(); self._current_id=experiment_id; self._thread=threading.Thread(target=self._run,args=(experiment_id,request,plan),daemon=True); self._thread.start(); return experiment_id

    def stop(self, experiment_id: str) -> None:
        with self._lock:
            if experiment_id != self._current_id: raise ExperimentNotFound("experiment is not active")
            self._stop.set(); process=self._process
        if process and process.poll() is None:
            try: process.send_signal(signal.SIGTERM); process.wait(timeout=5)
            except Exception: process.kill()

    def get(self, experiment_id: str) -> dict[str, Any]:
        directory=self.results_dir/experiment_id; manifest=read_json(directory/"manifest.json")
        if manifest is None: raise ExperimentNotFound(experiment_id)
        return {"manifest":manifest,"status":read_json(directory/"status.json",{}),"analysis":read_json(directory/"analysis.json")}

    def _plan(self, request: ExperimentRequest):
        items=[]; ordinal=0
        for runtime in request.runtimes:
            for sessions in request.session_levels:
                for repetition in range(1,request.repetitions+1):
                    ordinal+=1; items.append({"planOrdinal":ordinal,"runtime":runtime,"sessions":sessions,"repetition":repetition})
        if request.randomize_order: random.Random(request.order_seed).shuffle(items)
        for execution_order,item in enumerate(items,1): item["executionOrder"]=execution_order
        return items

    def _run(self, experiment_id: str, request: ExperimentRequest, plan):
        directory=self.results_dir/experiment_id; completed=0; failed=0
        try:
            for item in plan:
                if self._stop.is_set(): break
                run_name=f"run-{item['executionOrder']:03d}-{item['runtime']}-s{item['sessions']}-r{item['repetition']:02d}"; run_dir=directory/"runs"/run_name; run_dir.mkdir(parents=True,exist_ok=False)
                run_config={"runtime":item["runtime"],"sessions":item["sessions"],"actionRate":request.action_rate,"tickRate":request.tick_rate,"publicationRate":request.publication_rate,"workers":request.workers,"capacity":request.capacity,"budget":request.budget,"warmupSeconds":request.warmup_seconds,"measurementSeconds":request.measurement_seconds,"producerThreads":request.producer_threads,"sampleIntervalMs":request.sample_interval_ms,"outputDir":str(run_dir)}
                atomic_json(run_dir/"run-config.json",run_config)
                atomic_json(directory/"status.json",{"status":"running","completedRuns":completed,"failedRuns":failed,"totalRuns":len(plan),"currentRun":{**item,"name":run_name},"updatedAt":utc_now()})
                rc=self._run_child(run_dir)
                if rc != 0 and not (run_dir / "summary.json").exists():
                    atomic_json(run_dir / "summary.json", {
                        "status": "failed",
                        "runtime": item["runtime"],
                        "config": run_config,
                        "error": f"child JVM exited with code {rc} before writing summary"
                    })
                completed += 1 if rc == 0 else 0
                failed += 1 if rc != 0 else 0
                write_checksums(run_dir)
            final_status="stopped" if self._stop.is_set() else ("completed_with_failures" if failed else "completed")
            atomic_json(directory/"status.json",{"status":final_status,"completedRuns":completed,"failedRuns":failed,"totalRuns":len(plan),"currentRun":None,"updatedAt":utc_now()})
            if completed: subprocess.run(["python3",str(self.analysis_script),str(directory)],check=False,timeout=120)
            write_checksums(directory)
        except Exception as exc:
            atomic_json(directory/"status.json",{"status":"failed","completedRuns":completed,"failedRuns":failed+1,"totalRuns":len(plan),"currentRun":None,"updatedAt":utc_now(),"error":f"{type(exc).__name__}: {exc}"}); write_checksums(directory)
        finally:
            with self._lock: self._process=None; self._current_id=None

    def _run_child(self, run_dir: Path) -> int:
        config_path=run_dir/"run-config.json"; log_path=run_dir/"runner.log"; java_opts=os.getenv("BENCHMARK_JAVA_OPTS","-Xms4g -Xmx4g -XX:+UseG1GC").split(); cmd=["java",*java_opts,"-jar",str(self.runner_jar),"--config",str(config_path)]
        env=os.environ.copy(); env["BENCHMARK_RUN_ID"]=run_dir.name
        with log_path.open("w",encoding="utf-8",buffering=1) as log:
            log.write(f"[{utc_now()}] command: {' '.join(cmd)}\n")
            with self._lock: self._process=subprocess.Popen(cmd,stdout=log,stderr=subprocess.STDOUT,text=True,env=env); process=self._process
            while process.poll() is None:
                if self._stop.wait(0.5):
                    process.terminate()
                    try: process.wait(timeout=5)
                    except subprocess.TimeoutExpired: process.kill()
                    break
            rc=process.wait(); log.write(f"[{utc_now()}] exit={rc}\n")
            with self._lock: self._process=None
            return rc
