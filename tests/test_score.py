import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import score  # noqa: E402

GOLD_PATH = ROOT / "data" / "validation.jsonl"
KEYS = ("intent", "date", "time", "place")


def load_gold():
    return score.read_jsonl(str(GOLD_PATH))


def perfect_predictions(gold):
    return [{"id": g["id"], "prediction": json.dumps({k: g[k] for k in KEYS})} for g in gold]


class ScoreTests(unittest.TestCase):
    def test_perfect_predictions_score_100(self):
        gold = load_gold()
        report = score.score(perfect_predictions(gold), gold)
        self.assertEqual(report["json_validity"], 100.0)
        self.assertEqual(report["full_frame"], 100.0)
        self.assertEqual(report["missing_predictions"], 0)

    def test_text_that_is_not_json_scores_zero_validity(self):
        gold = load_gold()
        preds = [{"id": g["id"], "prediction": "Command: hello"} for g in gold]
        report = score.score(preds, gold)
        self.assertEqual(report["json_validity"], 0.0)
        self.assertEqual(report["full_frame"], 0.0)

    def test_missing_predictions_count_as_wrong(self):
        gold = load_gold()
        preds = perfect_predictions(gold)[: len(gold) // 2]
        report = score.score(preds, gold)
        self.assertLess(report["json_validity"], 100.0)
        self.assertEqual(report["missing_predictions"], len(gold) - len(preds))

    def test_extra_text_after_json_is_invalid(self):
        self.assertIsNone(score.parse_prediction('{"intent": "alarm_set", "date": null, "time": null, "place": null}\n(Note: x)'))

    def test_wrong_keys_are_invalid(self):
        self.assertIsNone(score.parse_prediction('{"intent": "alarm_set", "date": null}'))

    def test_quality_gate_exit_codes(self):
        gold = load_gold()
        with tempfile.TemporaryDirectory() as d:
            good = Path(d) / "good.jsonl"
            bad = Path(d) / "bad.jsonl"
            good.write_text("\n".join(json.dumps(p) for p in perfect_predictions(gold)) + "\n", encoding="utf-8")
            bad.write_text("\n".join(json.dumps({"id": g["id"], "prediction": "x"}) for g in gold) + "\n", encoding="utf-8")
            cmd = [sys.executable, str(ROOT / "tools" / "score.py")]
            ok = subprocess.run(cmd + [str(good), str(GOLD_PATH), "--min-validity", "95"], capture_output=True, text=True)
            fail = subprocess.run(cmd + [str(bad), str(GOLD_PATH), "--min-validity", "95"], capture_output=True, text=True)
        self.assertEqual(ok.returncode, 0)
        self.assertEqual(fail.returncode, 1)
        self.assertIn("QUALITY GATE FAILED", fail.stderr)


if __name__ == "__main__":
    unittest.main()
