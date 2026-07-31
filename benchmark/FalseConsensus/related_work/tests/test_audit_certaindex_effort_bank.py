"""Tests for the CertaIndex effort bank audit/packing utility."""
from __future__ import annotations
import unittest
from benchmark.FalseConsensus.related_work import audit_certaindex_effort_bank as audit


def _probe(pid, pos, source="reused_faithful_mid"):
    return {"probe_id": pid, "token_position": pos, "record_source": source,
            "probe_answer": "5", "is_certain": True, "probe_out_tokens": 10,
            "probe_prompt_tokens": 100, "probe_latency_seconds": 0.1}


def _payload(reused=3, new=2, start_pos=64, interval=64):
    probes = []
    for i in range(reused):
        probes.append(_probe(i + 1, start_pos + i * interval, "reused_faithful_mid"))
    for i in range(new):
        probes.append(_probe(reused + i + 1, start_pos + (reused + i) * interval, "new_mild_extension"))
    return {
        "schema_version": audit.PROBE_SCHEMA,
        "method": audit.METHOD,
        "probes": probes,
        "reused_probe_count": reused,
        "new_probe_count": new,
        "source_mid_file_sha256": "abc123",
    }


class EffortBankAuditTest(unittest.TestCase):
    def test_valid_payload(self):
        m = audit.validate_payload(_payload(reused=3, new=2))
        self.assertEqual(m["probes"], 5)
        self.assertEqual(m["reused"], 3)
        self.assertEqual(m["new"], 2)

    def test_zero_extension(self):
        m = audit.validate_payload(_payload(reused=5, new=0))
        self.assertEqual(m["probes"], 5)
        self.assertEqual(m["new"], 0)
        self.assertEqual(m["problems_with_extensions"], 0)

    def test_wrong_schema_rejected(self):
        p = _payload()
        p["schema_version"] = "wrong"
        with self.assertRaises(ValueError):
            audit.validate_payload(p)

    def test_non_sequential_ids_rejected(self):
        p = _payload(reused=2, new=1)
        p["probes"][1]["probe_id"] = 5
        with self.assertRaises(ValueError):
            audit.validate_payload(p)

    def test_provenance_mismatch_rejected(self):
        p = _payload(reused=3, new=2)
        p["reused_probe_count"] = 2
        with self.assertRaises(ValueError):
            audit.validate_payload(p)

    def test_wrong_record_source_rejected(self):
        p = _payload(reused=2, new=1)
        p["probes"][0]["record_source"] = "new_mild_extension"
        with self.assertRaises(ValueError):
            audit.validate_payload(p)

    def test_error_in_probes_rejected(self):
        p = _payload()
        p["probes"][0]["error"] = "timeout"
        with self.assertRaises(ValueError):
            audit.validate_payload(p)


if __name__ == "__main__":
    unittest.main(verbosity=2)
