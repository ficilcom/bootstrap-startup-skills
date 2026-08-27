import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = (
    Path(__file__).resolve().parents[3]
    / "skills/sales/founder-led-sales-review/scripts/analyze_pipeline.py"
)
SPEC = importlib.util.spec_from_file_location("analyze_pipeline", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def sample_input():
    return {
        "as_of_date": "2026-08-22",
        "cohort": {"start": "2026-05-01", "end": "2026-06-30", "minimum_observation_days": 30},
        "stage_order": ["qualified", "discovery", "evaluation", "proposal", "closed_won"],
        "stale_after_days": {"discovery": 14, "evaluation": 21, "proposal": 14},
        "opportunities": [
            {"id": "a", "created_at": "2026-05-01", "initial_stage": "qualified", "current_stage": "proposal", "entered_current_stage_at": "2026-05-21"},
            {"id": "b", "created_at": "2026-05-10", "initial_stage": "qualified", "current_stage": "discovery", "entered_current_stage_at": "2026-05-10"},
            {"id": "c", "created_at": "2026-06-25", "initial_stage": "qualified", "current_stage": "evaluation", "entered_current_stage_at": "2026-07-02"},
        ],
        "transitions": [
            {"opportunity_id": "a", "from_stage": "qualified", "to_stage": "discovery", "occurred_at": "2026-05-03"},
            {"opportunity_id": "a", "from_stage": "discovery", "to_stage": "evaluation", "occurred_at": "2026-05-10"},
            {"opportunity_id": "a", "from_stage": "evaluation", "to_stage": "proposal", "occurred_at": "2026-05-21"},
            {"opportunity_id": "c", "from_stage": "qualified", "to_stage": "discovery", "occurred_at": "2026-06-28"},
            {"opportunity_id": "c", "from_stage": "discovery", "to_stage": "evaluation", "occurred_at": "2026-07-02"},
        ],
        "losses": [
            {"opportunity_id": "a", "lost_at": "2026-06-01", "reason": "budget", "evidence": "customer_stated"},
            {"opportunity_id": "b", "lost_at": "2026-06-15", "reason": "", "evidence": "unknown"},
        ],
    }


class AnalyzePipelineTests(unittest.TestCase):
    def test_reports_mature_cohort_conversion_velocity_ageing_and_losses(self):
        result = MODULE.summarize(sample_input())

        self.assertEqual(result["stage_metrics"][0]["eligible_cohort_entries"], 3)
        self.assertEqual(result["stage_metrics"][0]["converted_to_next_stage"], 2)
        self.assertEqual(result["stage_metrics"][0]["conversion_rate"], 0.666667)
        self.assertEqual(result["stage_metrics"][0]["median_days_to_next_stage"], 2.5)
        self.assertEqual(result["stage_metrics"][1]["eligible_cohort_entries"], 2)
        self.assertEqual(result["stage_metrics"][1]["median_days_to_next_stage"], 5.5)
        self.assertEqual(result["open_pipeline_summary"], {"count": 1, "stale_count": 1})
        self.assertEqual(result["loss_reasons"]["known"], [{"reason": "budget", "count": 1}])
        self.assertEqual(result["loss_reasons"]["unknown_count"], 1)

    def test_rejects_non_adjacent_transition(self):
        data = sample_input()
        data["transitions"][0]["to_stage"] = "evaluation"

        with self.assertRaisesRegex(ValueError, "next stage"):
            MODULE.summarize(data)

    def test_excludes_immature_stage_entries(self):
        data = sample_input()
        data["cohort"]["end"] = "2026-08-22"
        data["cohort"]["minimum_observation_days"] = 60

        result = MODULE.summarize(data)

        self.assertEqual(result["stage_metrics"][1]["eligible_cohort_entries"], 1)

    def test_rejects_reversed_or_future_cohort_dates(self):
        cases = [
            ("reversed", "2026-07-01", "2026-06-30"),
            ("future", "2026-05-01", "2026-08-23"),
        ]

        for name, start, end in cases:
            with self.subTest(name=name):
                data = sample_input()
                data["cohort"].update({"start": start, "end": end})
                with self.assertRaisesRegex(ValueError, "start <= end <= as_of_date"):
                    MODULE.summarize(data)

    def test_rejects_duplicate_stages_unknown_stages_and_duplicate_ids(self):
        cases = []
        duplicate_stages = sample_input()
        duplicate_stages["stage_order"][1] = "qualified"
        cases.append(("duplicate stages", duplicate_stages, "duplicate stage"))

        unknown_opportunity_stage = sample_input()
        unknown_opportunity_stage["opportunities"][0]["current_stage"] = "contracting"
        cases.append(("unknown opportunity stage", unknown_opportunity_stage, "unknown stage"))

        unknown_transition_stage = sample_input()
        unknown_transition_stage["transitions"][0]["to_stage"] = "contracting"
        cases.append(("unknown transition stage", unknown_transition_stage, "stage_order"))

        duplicate_id = sample_input()
        duplicate_id["opportunities"].append(dict(duplicate_id["opportunities"][0]))
        cases.append(("duplicate opportunity id", duplicate_id, "unique non-empty id"))

        for name, data, message in cases:
            with self.subTest(name=name):
                with self.assertRaisesRegex(ValueError, message):
                    MODULE.summarize(data)

    def test_rejects_inconsistent_or_out_of_order_transition_history(self):
        current_stage_mismatch = sample_input()
        current_stage_mismatch["opportunities"][0]["current_stage"] = "evaluation"

        chronological_reversal = sample_input()
        chronological_reversal["transitions"][1]["occurred_at"] = "2026-05-02"

        unknown_opportunity = sample_input()
        unknown_opportunity["transitions"][0]["opportunity_id"] = "missing"

        cases = [
            ("current stage mismatch", current_stage_mismatch, "current_stage does not match"),
            ("chronological reversal", chronological_reversal, "out of sequence"),
            ("unknown opportunity", unknown_opportunity, "reference an opportunity"),
        ]
        for name, data, message in cases:
            with self.subTest(name=name):
                with self.assertRaisesRegex(ValueError, message):
                    MODULE.summarize(data)

    def test_rejects_inconsistent_loss_history(self):
        before_creation = sample_input()
        before_creation["losses"][0]["lost_at"] = "2026-04-30"

        duplicate_loss = sample_input()
        duplicate_loss["losses"].append(
            {"opportunity_id": "a", "lost_at": "2026-06-02", "reason": "timing"}
        )

        future_loss = sample_input()
        future_loss["losses"][0]["lost_at"] = "2026-08-23"

        cases = [
            ("loss before creation", before_creation, "cannot precede"),
            ("duplicate loss", duplicate_loss, "at most one loss"),
            ("future loss", future_loss, "cannot be after"),
        ]
        for name, data, message in cases:
            with self.subTest(name=name):
                with self.assertRaisesRegex(ValueError, message):
                    MODULE.summarize(data)

    def test_reports_zero_denominator_unknown_reason_and_missing_stale_threshold(self):
        data = {
            "as_of_date": "2026-08-22",
            "cohort": {"start": "2026-05-01", "end": "2026-05-31", "minimum_observation_days": 0},
            "stage_order": ["qualified", "discovery", "evaluation", "closed_won"],
            "opportunities": [
                {"id": "only", "created_at": "2026-05-10", "initial_stage": "qualified", "current_stage": "qualified", "entered_current_stage_at": "2026-05-10"},
                {"id": "open", "created_at": "2026-05-11", "initial_stage": "qualified", "current_stage": "qualified", "entered_current_stage_at": "2026-05-11"}
            ],
            "transitions": [],
            "losses": [{"opportunity_id": "only", "lost_at": "2026-05-12", "reason": "  "}],
        }

        result = MODULE.summarize(data)

        self.assertIsNone(result["stage_metrics"][1]["conversion_rate"])
        self.assertIsNone(result["stage_metrics"][1]["median_days_to_next_stage"])
        self.assertEqual(result["loss_reasons"], {"known": [], "unknown_count": 1, "total": 1})
        self.assertEqual(result["open_pipeline"], [{
            "opportunity_id": "open",
            "current_stage": "qualified",
            "age_days": 103,
            "stale_after_days": None,
            "is_stale": None,
        }])

    def test_cli_returns_json_for_valid_input_and_error_for_invalid_input(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary_path = Path(temporary_directory)
            valid_path = temporary_path / "valid.json"
            invalid_path = temporary_path / "invalid.json"
            invalid_contract_path = temporary_path / "invalid-contract.json"
            valid_path.write_text(json.dumps(sample_input()), encoding="utf-8")
            invalid_path.write_text("{", encoding="utf-8")
            invalid_contract_path.write_text("[]", encoding="utf-8")

            valid = subprocess.run(
                [sys.executable, str(SCRIPT), str(valid_path)],
                check=False,
                capture_output=True,
                text=True,
            )
            malformed = subprocess.run(
                [sys.executable, str(SCRIPT), str(invalid_path)],
                check=False,
                capture_output=True,
                text=True,
            )
            invalid_contract = subprocess.run(
                [sys.executable, str(SCRIPT), str(invalid_contract_path)],
                check=False,
                capture_output=True,
                text=True,
            )

        self.assertEqual(valid.returncode, 0)
        self.assertEqual(json.loads(valid.stdout)["as_of_date"], "2026-08-22")
        self.assertEqual(valid.stderr, "")
        self.assertEqual(malformed.returncode, 2)
        self.assertEqual(malformed.stdout, "")
        self.assertIn("input error:", malformed.stderr)
        self.assertEqual(invalid_contract.returncode, 2)
        self.assertIn("input must be an object", invalid_contract.stderr)


if __name__ == "__main__":
    unittest.main()
