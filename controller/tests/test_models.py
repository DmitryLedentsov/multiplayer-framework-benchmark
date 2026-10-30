import unittest
from controller.models import ExperimentRequest, PRESETS
class ModelTests(unittest.TestCase):
    def test_full_preset_has_scientific_repetitions(self):
        self.assertEqual(10, PRESETS["full"]["repetitions"]); self.assertTrue(PRESETS["full"]["randomize_order"])
    def test_unknown_runtime_rejected(self):
        with self.assertRaises(ValueError): ExperimentRequest(runtimes=["unknown"])
if __name__ == "__main__": unittest.main()
