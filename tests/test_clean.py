import importlib
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
TEXT = "set an alarm for seven thirty am tomorrow"
GOOD = '{"intent": "alarm_set", "date": "tomorrow", "time": "seven thirty am", "place": null}'


def load_clean():
    """Import worker/clean.py without needing boto3 (it only builds an S3 client at import)."""
    stubs = {"boto3": mock.MagicMock(), "botocore": mock.MagicMock(), "botocore.config": mock.MagicMock()}
    with mock.patch.dict(sys.modules, stubs):
        sys.path.insert(0, str(ROOT / "worker"))
        try:
            sys.modules.pop("clean", None)
            return importlib.import_module("clean")
        finally:
            sys.path.pop(0)


clean = load_clean()


def rec(raw, text=TEXT):
    return {"text": text, "teacher_raw": raw}


class CleanTests(unittest.TestCase):
    def test_valid_reply_is_kept(self):
        self.assertIsNone(clean.classify(rec(GOOD)))

    def test_reply_with_surrounding_whitespace_is_kept(self):
        self.assertIsNone(clean.classify(rec("  " + GOOD + "\n")))

    def test_reply_with_explanatory_note_is_rejected_as_invalid_json(self):
        self.assertEqual(clean.classify(rec(GOOD + "\n\n(Note: the date was implied.)")), "a")

    def test_missing_key_is_rejected(self):
        self.assertEqual(clean.classify(rec('{"intent": "alarm_set", "date": null, "time": null}')), "b")

    def test_unknown_intent_is_rejected(self):
        raw = '{"intent": "set_alarm", "date": null, "time": null, "place": null}'
        self.assertEqual(clean.classify(rec(raw)), "c")

    def test_slot_not_copied_from_command_is_rejected(self):
        raw = '{"intent": "alarm_set", "date": "next friday", "time": null, "place": null}'
        self.assertEqual(clean.classify(rec(raw)), "d")


if __name__ == "__main__":
    unittest.main()
