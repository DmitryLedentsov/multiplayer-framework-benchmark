import tempfile, unittest
from pathlib import Path
from controller.models import ExperimentRequest
from controller.orchestrator import Orchestrator
class OrchestratorPlanTests(unittest.TestCase):
    def test_plan_expands_and_randomizes_deterministically(self):
        with tempfile.TemporaryDirectory() as tmp:
            orch=Orchestrator(Path(tmp),Path('/tmp/runner.jar'),Path('/tmp/analyze.py')); req=ExperimentRequest(runtimes=['mf','s2'],session_levels=[100,500],repetitions=3,order_seed=42); a=orch._plan(req); b=orch._plan(req)
            self.assertEqual(a,b); self.assertEqual(12,len(a)); self.assertEqual(list(range(1,13)),sorted(x['executionOrder'] for x in a))
if __name__ == "__main__": unittest.main()
