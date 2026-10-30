#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
import math
import random
import statistics
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

THRESHOLDS = {
    "stepP99Ms": 10.0,
    "actionP99Ms": 30.0,
    "maxRejectionRate": 0.001,
    "minTickFraction": 0.98,
    "maxBacklogGrowthActionsPerSecond": 1.0,
    "minOfferedLoadFraction": 0.99,
}


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def median_ci(values: list[float], seed: int, rounds: int = 4000) -> tuple[float, float]:
    if not values:
        return (0.0, 0.0)
    if len(values) == 1:
        return (values[0], values[0])

    rng = random.Random(seed)
    medians: list[float] = []
    n = len(values)
    for _ in range(rounds):
        sample = [values[rng.randrange(n)] for _ in range(n)]
        medians.append(statistics.median(sample))
    medians.sort()
    return (
        medians[int(0.025 * (rounds - 1))],
        medians[int(0.975 * (rounds - 1))],
    )


def read_samples(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def sample_median(rows: list[dict[str, str]], name: str, fallback: float) -> float:
    values = [float(row[name]) for row in rows if row.get(name) not in (None, "")]
    return statistics.median(values) if values else fallback


def backlog_slope(path: Path, last_n: int = 30) -> float:
    rows = read_samples(path)[-last_n:]
    if len(rows) < 2:
        return 0.0

    xs = [float(row["elapsed_s"]) for row in rows]
    ys = [float(row["backlog"]) for row in rows]
    x_bar = statistics.mean(xs)
    y_bar = statistics.mean(ys)
    denominator = sum((x - x_bar) ** 2 for x in xs)
    if denominator == 0:
        return 0.0
    return sum((x - x_bar) * (y - y_bar) for x, y in zip(xs, ys)) / denominator


def run_key(runtime: str, sessions: int) -> tuple[str, int]:
    return runtime, sessions


def load_runs(root: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    completed: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []

    for summary_path in sorted((root / "runs").glob("*/summary.json")):
        summary = read_json(summary_path)
        config = summary.get("config", {})
        runtime = str(summary.get("runtime", config.get("runtime", "unknown")))
        sessions = int(config.get("sessions", 0))
        try:
            repetition = int(summary_path.parent.name.rsplit("-r", 1)[-1])
        except ValueError:
            repetition = -1

        if summary.get("status") != "completed":
            failed.append(
                {
                    "runtime": runtime,
                    "sessions": sessions,
                    "repetition": repetition,
                    "run": summary_path.parent.name,
                    "error": summary.get("error", "unknown failure"),
                }
            )
            continue

        metrics = summary["metrics"]
        samples_path = summary_path.parent / "samples.csv"
        samples = read_samples(samples_path)
        slope = backlog_slope(samples_path)
        process_cpu = sample_median(samples, "cpu_percent", float(metrics["processCpuPercent"]))
        generator_cpu = sample_median(
            samples,
            "generator_cpu_percent",
            float(summary.get("generatorCpuPercent", -1.0)),
        )
        offered = int(metrics["offeredActions"])
        rejected = int(metrics["rejectedActions"])
        rejection_rate = rejected / offered if offered else 0.0

        expected_steps = sessions * int(config["tickRate"])
        tick_fraction = float(metrics["stepsPerSecond"]) / expected_steps if expected_steps else 1.0

        expected_offered = int(config["actionRate"]) * int(config["measurementSeconds"])
        offered_fraction = offered / expected_offered if expected_offered else 1.0

        sustained = (
            float(metrics["stepP99Ms"]) < THRESHOLDS["stepP99Ms"]
            and float(metrics["actionP99Ms"]) < THRESHOLDS["actionP99Ms"]
            and rejection_rate <= THRESHOLDS["maxRejectionRate"]
            and tick_fraction >= THRESHOLDS["minTickFraction"]
            and slope <= THRESHOLDS["maxBacklogGrowthActionsPerSecond"]
            and offered_fraction >= THRESHOLDS["minOfferedLoadFraction"]
        )

        completed.append(
            {
                "runtime": runtime,
                "sessions": sessions,
                "repetition": repetition,
                "actionP99Ms": float(metrics["actionP99Ms"]),
                "stepP99Ms": float(metrics["stepP99Ms"]),
                "cpuPercent": process_cpu,
                "generatorCpuPercent": generator_cpu,
                "actionsPerSecond": float(metrics["actionsPerSecond"]),
                "rejectionRate": rejection_rate,
                "tickFraction": tick_fraction,
                "offeredLoadFraction": offered_fraction,
                "backlogSlope": slope,
                "sustained": sustained,
            }
        )

    return completed, failed


def expected_counts(manifest: dict[str, Any]) -> dict[tuple[str, int], int]:
    counts: dict[tuple[str, int], int] = defaultdict(int)
    for item in manifest.get("plan", []):
        counts[run_key(str(item["runtime"]), int(item["sessions"]))] += 1
    return counts


def nullable_stats(values: list[float], seed: int) -> dict[str, Any]:
    if not values:
        return {"median": None, "min": None, "max": None, "ci95": None}
    return {
        "median": statistics.median(values),
        "min": min(values),
        "max": max(values),
        "ci95": median_ci(values, seed),
    }


def group_runs(
    runs: list[dict[str, Any]],
    failures: list[dict[str, Any]],
    manifest: dict[str, Any],
    seed: int,
) -> list[dict[str, Any]]:
    by_key: dict[tuple[str, int], list[dict[str, Any]]] = defaultdict(list)
    failed_by_key: dict[tuple[str, int], list[dict[str, Any]]] = defaultdict(list)
    for row in runs:
        by_key[run_key(row["runtime"], row["sessions"])].append(row)
    for row in failures:
        failed_by_key[run_key(row["runtime"], row["sessions"])].append(row)

    expected = expected_counts(manifest)
    keys = sorted(set(expected) | set(by_key) | set(failed_by_key))
    output: list[dict[str, Any]] = []

    for index, key in enumerate(keys):
        runtime, sessions = key
        rows = by_key.get(key, [])
        failed_rows = failed_by_key.get(key, [])
        planned = expected.get(key, len(rows) + len(failed_rows))

        def values(name: str) -> list[float]:
            return [float(row[name]) for row in rows]

        action = nullable_stats(values("actionP99Ms"), seed + index * 31 + 1)
        step = nullable_stats(values("stepP99Ms"), seed + index * 31 + 2)
        cpu = nullable_stats(values("cpuPercent"), seed + index * 31 + 3)
        throughput = nullable_stats(values("actionsPerSecond"), seed + index * 31 + 4)
        generator_cpu = nullable_stats(values("generatorCpuPercent"), seed + index * 31 + 5)

        if rows:
            rejection_median = statistics.median(values("rejectionRate"))
            tick_fraction_median = statistics.median(values("tickFraction"))
            offered_fraction_median = statistics.median(values("offeredLoadFraction"))
            backlog_slope_median = statistics.median(values("backlogSlope"))
            sustained_run_count = sum(bool(row["sustained"]) for row in rows)
        else:
            rejection_median = None
            tick_fraction_median = None
            offered_fraction_median = None
            backlog_slope_median = None
            sustained_run_count = 0

        complete_plan = len(rows) == planned and not failed_rows
        median_passes = bool(
            rows
            and step["median"] < THRESHOLDS["stepP99Ms"]
            and action["median"] < THRESHOLDS["actionP99Ms"]
            and rejection_median <= THRESHOLDS["maxRejectionRate"]
            and tick_fraction_median >= THRESHOLDS["minTickFraction"]
            and offered_fraction_median >= THRESHOLDS["minOfferedLoadFraction"]
            and backlog_slope_median <= THRESHOLDS["maxBacklogGrowthActionsPerSecond"]
        )

        output.append(
            {
                "runtime": runtime,
                "sessions": sessions,
                "plannedRuns": planned,
                "n": len(rows),
                "failedRuns": len(failed_rows),
                "sustainedRuns": sustained_run_count,
                "sustained": complete_plan and median_passes,
                "actionP99Median": action["median"],
                "actionP99Min": action["min"],
                "actionP99Max": action["max"],
                "actionP99Ci95": action["ci95"],
                "stepP99Median": step["median"],
                "stepP99Min": step["min"],
                "stepP99Max": step["max"],
                "stepP99Ci95": step["ci95"],
                "cpuMedian": cpu["median"],
                "cpuMin": cpu["min"],
                "cpuMax": cpu["max"],
                "cpuCi95": cpu["ci95"],
                "generatorCpuMedian": generator_cpu["median"],
                "actionsPerSecondMedian": throughput["median"],
                "actionsPerSecondMin": throughput["min"],
                "actionsPerSecondMax": throughput["max"],
                "actionsPerSecondCi95": throughput["ci95"],
                "rejectionRateMedian": rejection_median,
                "tickFractionMedian": tick_fraction_median,
                "offeredLoadFractionMedian": offered_fraction_median,
                "backlogSlopeMedian": backlog_slope_median,
            }
        )

    return output


def operating_envelope(groups: list[dict[str, Any]]) -> dict[str, int | None]:
    output: dict[str, int | None] = {}
    runtimes = sorted({str(group["runtime"]) for group in groups})
    for runtime in runtimes:
        sustained = [
            int(group["sessions"])
            for group in groups
            if group["runtime"] == runtime and group["sustained"]
        ]
        output[runtime] = max(sustained) if sustained else None
    return output


def write_csv(path: Path, groups: list[dict[str, Any]]) -> None:
    fields = [
        "runtime", "sessions", "plannedRuns", "n", "failedRuns", "sustainedRuns", "sustained",
        "actionP99Median", "actionP99Min", "actionP99Max",
        "stepP99Median", "stepP99Min", "stepP99Max",
        "cpuMedian", "cpuMin", "cpuMax", "generatorCpuMedian",
        "actionsPerSecondMedian", "actionsPerSecondMin", "actionsPerSecondMax",
        "rejectionRateMedian", "tickFractionMedian", "offeredLoadFractionMedian", "backlogSlopeMedian",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for group in groups:
            writer.writerow({field: group.get(field) for field in fields})


def permutation_p(values: list[float], seed: int, rounds: int = 10_000) -> float | None:
    if len(values) < 4:
        return None
    split = len(values) // 2
    first = values[:split]
    second = values[split:]
    observed = abs(statistics.median(first) - statistics.median(second))
    pooled = values[:]
    rng = random.Random(seed)
    extreme = 0
    for _ in range(rounds):
        rng.shuffle(pooled)
        if abs(statistics.median(pooled[:split]) - statistics.median(pooled[split:])) >= observed:
            extreme += 1
    return (extreme + 1) / (rounds + 1)


def aa_analysis(runs: list[dict[str, Any]], failures: list[dict[str, Any]], seed: int) -> dict[str, Any] | None:
    if failures or len({run_key(row["runtime"], row["sessions"]) for row in runs}) != 1 or len(runs) < 5:
        return None
    ordered = sorted(runs, key=lambda row: row["repetition"])
    return {
        "method": "split repetitions into two halves; two-sided permutation test of median difference",
        "stepP99PermutationP": permutation_p([row["stepP99Ms"] for row in ordered], seed),
        "actionP99PermutationP": permutation_p([row["actionP99Ms"] for row in ordered], seed + 1),
        "cpuPermutationP": permutation_p([row["cpuPercent"] for row in ordered], seed + 2),
    }


def svg_plot(
    path: Path,
    groups: list[dict[str, Any]],
    metric: str,
    title: str,
    y_label: str,
    threshold: float | None = None,
) -> None:
    rows = [group for group in groups if group.get(metric) is not None]
    if not rows:
        return

    width, height = 900, 500
    left, right, top, bottom = 80, 30, 45, 65
    xs = sorted({int(row["sessions"]) for row in rows})
    max_y = max(float(row[metric]) for row in rows)
    if threshold is not None:
        max_y = max(max_y, threshold)
    max_y = max(1.0, max_y * 1.12)
    min_x, max_x = min(xs), max(xs)
    if min_x == max_x:
        max_x += 1

    def px(x: float) -> float:
        return left + (x - min_x) / (max_x - min_x) * (width - left - right)

    def py(y: float) -> float:
        return top + (1.0 - y / max_y) * (height - top - bottom)

    palette = ["#2563eb", "#dc2626", "#16a34a", "#7c3aed", "#ea580c"]
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="white"/>',
        f'<text x="{width/2}" y="26" text-anchor="middle" font-family="sans-serif" font-size="18">{title}</text>',
    ]

    for i in range(6):
        value = max_y * i / 5
        y = py(value)
        parts.append(f'<line x1="{left}" y1="{y:.2f}" x2="{width-right}" y2="{y:.2f}" stroke="#e5e7eb"/>')
        parts.append(f'<text x="{left-10}" y="{y+4:.2f}" text-anchor="end" font-family="sans-serif" font-size="11">{value:.1f}</text>')

    for x in xs:
        x_pos = px(x)
        parts.append(f'<text x="{x_pos:.2f}" y="{height-bottom+22}" text-anchor="middle" font-family="sans-serif" font-size="11">{x}</text>')

    parts.append(f'<line x1="{left}" y1="{top}" x2="{left}" y2="{height-bottom}" stroke="#111827"/>')
    parts.append(f'<line x1="{left}" y1="{height-bottom}" x2="{width-right}" y2="{height-bottom}" stroke="#111827"/>')
    parts.append(f'<text x="{width/2}" y="{height-18}" text-anchor="middle" font-family="sans-serif" font-size="12">Active sessions</text>')
    parts.append(f'<text x="18" y="{height/2}" transform="rotate(-90 18 {height/2})" text-anchor="middle" font-family="sans-serif" font-size="12">{y_label}</text>')

    if threshold is not None:
        y = py(threshold)
        parts.append(f'<line x1="{left}" y1="{y:.2f}" x2="{width-right}" y2="{y:.2f}" stroke="#111827" stroke-dasharray="6 5"/>')
        parts.append(f'<text x="{width-right-4}" y="{y-6:.2f}" text-anchor="end" font-family="sans-serif" font-size="11">threshold {threshold:g}</text>')

    for index, runtime in enumerate(sorted({str(row["runtime"]) for row in rows})):
        color = palette[index % len(palette)]
        runtime_rows = sorted((row for row in rows if row["runtime"] == runtime), key=lambda row: int(row["sessions"]))
        points = " ".join(f'{px(int(row["sessions"])):.2f},{py(float(row[metric])):.2f}' for row in runtime_rows)
        parts.append(f'<polyline points="{points}" fill="none" stroke="{color}" stroke-width="2.5"/>')
        for row in runtime_rows:
            parts.append(f'<circle cx="{px(int(row["sessions"])):.2f}" cy="{py(float(row[metric])):.2f}" r="4" fill="{color}"/>')
        legend_x = left + index * 160
        parts.append(f'<line x1="{legend_x}" y1="{height-42}" x2="{legend_x+24}" y2="{height-42}" stroke="{color}" stroke-width="3"/>')
        parts.append(f'<text x="{legend_x+30}" y="{height-38}" font-family="sans-serif" font-size="11">{runtime}</text>')

    parts.append("</svg>")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(parts), encoding="utf-8")


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: analyze.py <experiment-dir>", file=sys.stderr)
        return 2

    root = Path(sys.argv[1])
    manifest = read_json(root / "manifest.json")
    seed = int(manifest.get("request", {}).get("order_seed", 20261105))
    runs, failures = load_runs(root)
    groups = group_runs(runs, failures, manifest, seed)

    analysis = {
        "schemaVersion": 2,
        "sustainThresholds": THRESHOLDS,
        "unitOfAnalysis": "one independently restarted JVM run",
        "aggregation": "median with min-max and deterministic bootstrap 95% CI",
        "runs": runs,
        "failedRuns": failures,
        "groups": groups,
        "operatingEnvelopeSessions": operating_envelope(groups),
        "aa": aa_analysis(runs, failures, seed),
    }

    (root / "analysis.json").write_text(
        json.dumps(analysis, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    write_csv(root / "analysis.csv", groups)
    svg_plot(
        root / "plots" / "step-p99-vs-sessions.svg",
        groups,
        "stepP99Median",
        "p99 simulation-step lateness vs active sessions",
        "p99 step lateness, ms",
        THRESHOLDS["stepP99Ms"],
    )
    svg_plot(
        root / "plots" / "action-p99-vs-sessions.svg",
        groups,
        "actionP99Median",
        "p99 Action latency vs active sessions",
        "p99 Action latency, ms",
        THRESHOLDS["actionP99Ms"],
    )
    svg_plot(
        root / "plots" / "cpu-vs-sessions.svg",
        groups,
        "cpuMedian",
        "Benchmark JVM CPU vs active sessions",
        "process CPU, % host budget",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
