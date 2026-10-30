import importlib.util
from pathlib import Path
import unittest

MODULE_PATH = Path(__file__).resolve().parents[2] / "scripts" / "analyze.py"
SPEC = importlib.util.spec_from_file_location("benchmark_analyze", MODULE_PATH)
analyze = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(analyze)


def passing_run():
    return {
        "runtime": "mf",
        "sessions": 500,
        "repetition": 1,
        "actionP99Ms": 15.0,
        "stepP99Ms": 4.0,
        "cpuPercent": 50.0,
        "generatorCpuPercent": 2.0,
        "actionsPerSecond": 9990.0,
        "rejectionRate": 0.0,
        "tickFraction": 0.999,
        "offeredLoadFraction": 1.0,
        "backlogSlope": 0.0,
        "sustained": True,
    }


class AnalysisTests(unittest.TestCase):
    def test_complete_passing_configuration_is_sustained(self):
        manifest = {"plan": [{"runtime": "mf", "sessions": 500, "repetition": 1}]}
        groups = analyze.group_runs([passing_run()], [], manifest, 42)
        self.assertEqual(1, len(groups))
        self.assertTrue(groups[0]["sustained"])
        self.assertEqual(500, analyze.operating_envelope(groups)["mf"])

    def test_failed_repetition_prevents_sustained_classification(self):
        manifest = {
            "plan": [
                {"runtime": "mf", "sessions": 500, "repetition": 1},
                {"runtime": "mf", "sessions": 500, "repetition": 2},
            ]
        }
        failures = [
            {"runtime": "mf", "sessions": 500, "repetition": 2, "run": "run-2", "error": "boom"}
        ]
        groups = analyze.group_runs([passing_run()], failures, manifest, 42)
        self.assertFalse(groups[0]["sustained"])
        self.assertEqual(1, groups[0]["failedRuns"])


if __name__ == "__main__":
    unittest.main()
