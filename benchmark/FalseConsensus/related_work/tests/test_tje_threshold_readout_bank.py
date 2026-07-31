import unittest

from benchmark.FalseConsensus.related_work.tje_threshold_readout_bank import (
    METHOD,
    PROBE_SCHEMA,
    TOP_K_THRESHOLDS,
    copy_readout,
    first_crossing,
    reusable_readout,
    threshold_decisions,
)
from benchmark.FalseConsensus.related_work.audit_tje_threshold_readout_bank import (
    validate_payload,
)


class TJEThresholdReadoutBankTest(unittest.TestCase):
    def setUp(self):
        self.triggers = [
            {
                "trigger_id": 1,
                "token_position": 100,
                "confidence_label": "Likely",
            },
            {
                "trigger_id": 2,
                "token_position": 200,
                "confidence_label": "Highly likely",
            },
            {
                "trigger_id": 3,
                "token_position": 300,
                "confidence_label": "Almost certain",
            },
        ]

    def test_top_k_mapping(self):
        self.assertEqual(TOP_K_THRESHOLDS[1], "Almost certain")
        self.assertEqual(TOP_K_THRESHOLDS[2], "Highly likely")
        self.assertEqual(TOP_K_THRESHOLDS[6], "Less than even")

    def test_first_crossing(self):
        self.assertEqual(
            first_crossing(self.triggers, "Highly likely")["trigger_id"],
            2,
        )
        self.assertEqual(
            first_crossing(self.triggers, "Likely")["trigger_id"], 1
        )

    def test_no_crossing(self):
        rows = [
            {
                "trigger_id": 1,
                "confidence_label": "Highly unlikely",
            }
        ]
        self.assertIsNone(first_crossing(rows, "Almost certain"))

    def test_nested_decisions(self):
        decisions = threshold_decisions(self.triggers)
        self.assertEqual(decisions[1]["trigger_id"], 3)
        self.assertEqual(decisions[2]["trigger_id"], 2)
        self.assertEqual(decisions[3]["trigger_id"], 2)
        self.assertEqual(decisions[4]["trigger_id"], 1)
        self.assertEqual(decisions[5]["trigger_id"], 1)
        self.assertEqual(decisions[6]["trigger_id"], 1)

    def test_reusable_readout(self):
        readout = {
            "at_trigger_id": 3,
            "readout_finish_reason": "stop",
            "readout_answer": "7",
        }
        self.assertTrue(reusable_readout(readout, trigger_id=3))
        self.assertFalse(reusable_readout(readout, trigger_id=2))
        self.assertFalse(
            reusable_readout(
                {**readout, "error": "failed"}, trigger_id=3
            )
        )

    def test_copy_labels_provenance(self):
        copied = copy_readout(
            {
                "at_trigger_id": 3,
                "readout_finish_reason": "length",
                "readout_valid": False,
            }
        )
        self.assertEqual(
            copied["record_source"], "reused_faithful_tje_top1"
        )

    def test_audit_payload(self):
        decisions = {}
        for top_k, label in TOP_K_THRESHOLDS.items():
            trigger_id = 3 if top_k == 1 else 2 if top_k <= 3 else 1
            decisions[str(top_k)] = {
                "threshold_label": label,
                "stop_trigger_id": trigger_id,
                "stop_position": trigger_id * 100,
                "confidence_label": "Almost certain",
            }
        payload = {
            "schema_version": PROBE_SCHEMA,
            "method": METHOD,
            "confidence_queries_generated": 0,
            "confidence_triggers": [],
            "top_k_decisions": decisions,
            "expected_unique_readout_count": 3,
            "reused_readout_count": 1,
            "generated_readout_count": 2,
            "readouts": [
                {
                    "at_trigger_id": trigger_id,
                    "readout_valid": True,
                }
                for trigger_id in (1, 2, 3)
            ],
        }
        metrics = validate_payload(payload)
        self.assertEqual(metrics["readouts"], 3)
        self.assertEqual(metrics["generated"], 2)


if __name__ == "__main__":
    unittest.main()
