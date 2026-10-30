from __future__ import annotations

import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()

def safe_id(name: str) -> str:
    clean = "".join(c.lower() if c.isalnum() else "-" for c in name).strip("-")
    clean = "-".join(filter(None, clean.split("-")))[:48] or "experiment"
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{stamp}-{clean}"

def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)

def read_json(path: Path, default: Any = None) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default

def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def write_checksums(directory: Path) -> None:
    files = sorted(p for p in directory.rglob("*") if p.is_file() and p.name != "checksums.sha256")
    lines = [f"{sha256(path)}  {path.relative_to(directory).as_posix()}" for path in files]
    (directory / "checksums.sha256").write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")

def environment_snapshot() -> dict[str, Any]:
    result: dict[str, Any] = {"capturedAt": utc_now(), "platform": platform.platform(), "python": sys.version, "cpuCount": os.cpu_count(), "hostname": platform.node(), "machine": platform.machine(), "benchmarkSourceCommit": os.getenv("BENCHMARK_SOURCE_COMMIT", "unknown"), "frameworkCoordinate": os.getenv("MF_COORDINATE", "com.mf:mf-game-service-starter:0.5.0-SNAPSHOT")}
    meminfo = Path("/proc/meminfo")
    if meminfo.exists():
        for line in meminfo.read_text(encoding="utf-8").splitlines():
            if line.startswith("MemTotal:"):
                result["hostMemTotalKb"] = int(line.split()[1]); break
    try:
        result["java"] = subprocess.check_output(["java", "-version"], stderr=subprocess.STDOUT, text=True, timeout=5).strip()
    except Exception as exc:
        result["java"] = f"unavailable: {type(exc).__name__}"
    return result

def list_experiments(results_dir: Path) -> list[dict[str, Any]]:
    items=[]
    if not results_dir.exists(): return items
    for directory in sorted((p for p in results_dir.iterdir() if p.is_dir()), reverse=True):
        manifest=read_json(directory/"manifest.json",{}); status=read_json(directory/"status.json",{})
        if manifest:
            items.append({"id":directory.name,"name":manifest.get("request",{}).get("name",directory.name),"createdAt":manifest.get("createdAt"),"status":status.get("status","unknown"),"completedRuns":status.get("completedRuns",0),"totalRuns":status.get("totalRuns",0)})
    return items

def remove_tree(path: Path) -> None:
    if path.exists(): shutil.rmtree(path)
