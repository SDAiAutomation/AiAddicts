import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from engine.metrics import append_row, ensure_csv, read_rows


class TestMetrics(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.path = str(Path(self.tmp_dir.name) / "suivi.csv")

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_ensure_csv_creates_header_once(self):
        ensure_csv(self.path)
        header_1 = Path(self.path).read_text(encoding="utf-8")
        ensure_csv(self.path)
        header_2 = Path(self.path).read_text(encoding="utf-8")
        self.assertEqual(header_1, header_2)

    def test_append_and_read_row(self):
        append_row(self.path, {
            "date": "2026-09-08", "compte": "test-account-01",
            "video_id": "erreur-n1", "publications_semaine": "5",
            "vues_moyennes": "1200", "leads": "3",
        })
        rows = read_rows(self.path)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["compte"], "test-account-01")
        self.assertEqual(rows[0]["leads"], "3")
        self.assertEqual(rows[0]["notes"], "")  # unset fields default to empty

    def test_unknown_field_raises(self):
        with self.assertRaises(ValueError):
            append_row(self.path, {"date": "2026-09-08", "budget_pub": "50"})


if __name__ == "__main__":
    unittest.main()
