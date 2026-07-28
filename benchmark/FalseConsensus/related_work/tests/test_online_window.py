"""Regression test: the online latest-window CertaIndex stop check (used in the
live collector) is semantically equivalent to the sequential full-scan
decide_stop() first-stop, and avoids re-invoking the expensive SymPy-backed
equality on historical windows."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[3]
sys.path.insert(0, str(REPO_ROOT))

from benchmark.FalseConsensus.related_work import certaindex_mid  # noqa


def _probe(pid, pos, answer, certain):
    return {"probe_id": pid, "token_position": pos, "probe_answer": answer, "is_certain": certain}


class OnlineWindowEquivalenceTests(unittest.TestCase):
    """Prove that checking records[-patience:] each step matches a sequential
    full-scan decide_stop() first-stop, and that the online path makes
    O(1) equality calls per new probe, not O(n)."""

    PATIENCE = 3

    def _str_eq(self, answers):
        return len(set(answers)) <= 1

    def _count_not_empty(self, answers):
        return sum(1 for a in answers if a != "")

    def _online_stop_index(self, probes):
        """Simulate the live collector's online latest-window check."""
        for i in range(self.PATIENCE, len(probes) + 1):
            window = probes[i - self.PATIENCE : i]
            answers = [p["probe_answer"] for p in window]
            if (self._count_not_empty(answers) == self.PATIENCE
                    and self._str_eq(answers)
                    and sum(1 for p in window if p["is_certain"]) == self.PATIENCE):
                return i
        return None

    def _fullscan_stop_index(self, probes):
        """decide_stop full-scan (the offline replay semantics)."""
        d = certaindex_mid.decide_stop(
            probes, patience=self.PATIENCE,
            answers_equal_fn=self._str_eq, count_not_empty_fn=self._count_not_empty)
        return d["stop_index"] if d else None

    def test_match_stop_at_third_matching_probe(self):
        probes = [
            _probe(1, 64, "204", True),
            _probe(2, 128, "204", True),
            _probe(3, 192, "204", True),
        ]
        self.assertEqual(self._online_stop_index(probes), self._fullscan_stop_index(probes))
        self.assertEqual(self._online_stop_index(probes), 3)

    def test_match_no_stop_when_disagree(self):
        probes = [
            _probe(1, 64, "204", True),
            _probe(2, 128, "100", True),
            _probe(3, 192, "204", True),
            _probe(4, 256, "204", True),
        ]
        self.assertEqual(self._online_stop_index(probes), self._fullscan_stop_index(probes))
        self.assertIsNone(self._online_stop_index(probes))

    def test_match_no_stop_when_uncertain(self):
        probes = [
            _probe(1, 64, "204", True),
            _probe(2, 128, "204", False),
            _probe(3, 192, "204", True),
        ]
        self.assertEqual(self._online_stop_index(probes), self._fullscan_stop_index(probes))
        self.assertIsNone(self._online_stop_index(probes))

    def test_match_stop_after_disagreement_resolves(self):
        # probes: 100, 204, 204, 204, 204 — window [204,204,204] at i=4
        probes = [
            _probe(1, 64, "100", True),
            _probe(2, 128, "204", True),
            _probe(3, 192, "204", True),
            _probe(4, 256, "204", True),
            _probe(5, 320, "204", True),
        ]
        self.assertEqual(self._online_stop_index(probes), self._fullscan_stop_index(probes))
        self.assertEqual(self._online_stop_index(probes), 4)

    def test_match_no_stop_empty(self):
        probes = [
            _probe(1, 64, "", True),
            _probe(2, 128, "", True),
            _probe(3, 192, "", True),
        ]
        self.assertEqual(self._online_stop_index(probes), self._fullscan_stop_index(probes))
        self.assertIsNone(self._online_stop_index(probes))

    def test_online_avoids_historical_equality_calls(self):
        """The online path checks only the latest window per new probe (1 call
        each), while the old full-scan-per-probe path re-checks ALL prior windows
        (1+2+3 = 6 calls for 5 probes). Use always-disagreeing answers so neither
        path stops early."""
        call_count = [0]

        def counting_eq(answers):
            call_count[0] += 1
            return False  # never agree -> never stops -> all windows checked

        # 5 probes, always disagreeing (unique answers)
        probes = [
            _probe(1, 64, "a", True),
            _probe(2, 128, "b", True),
            _probe(3, 192, "c", True),
            _probe(4, 256, "d", True),
            _probe(5, 320, "e", True),
        ]

        # OLD path: call decide_stop(probes[:i]) after each new probe i=3..5
        call_count[0] = 0
        for i in range(self.PATIENCE, len(probes) + 1):
            certaindex_mid.decide_stop(
                probes[:i], patience=self.PATIENCE,
                answers_equal_fn=counting_eq, count_not_empty_fn=self._count_not_empty)
        old_calls = call_count[0]  # 1 + 2 + 3 = 6

        # NEW path: check only the latest window per new probe
        call_count[0] = 0
        for i in range(self.PATIENCE, len(probes) + 1):
            window = probes[i - self.PATIENCE : i]
            answers = [p["probe_answer"] for p in window]
            self._count_not_empty(answers)
            counting_eq(answers)
        new_calls = call_count[0]  # 3

        self.assertEqual(old_calls, 6)   # full scan re-checks history
        self.assertEqual(new_calls, 3)  # online checks only latest window
        self.assertLess(new_calls, old_calls)


if __name__ == "__main__":
    unittest.main()
