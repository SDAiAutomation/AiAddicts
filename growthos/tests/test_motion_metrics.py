import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
import motion_metrics as mm


class RunTest(unittest.TestCase):
    def test_longest_run(self):
        self.assertEqual(mm.longest_run(np.array([1, 1, 0, 1, 1, 1, 0])), 3)
        self.assertEqual(mm.longest_run(np.array([0, 0])), 0)
