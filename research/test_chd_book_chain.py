import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from research.budget_chd_study import checkpoint_book, replay_book
from research.chd_book_chain import read_checkpoint


def row(seq, prev=None, event="update", side="bid", price="10", quantity="2"):
    return {"symbol": "AAPLUSDT", "received_time": seq, "event_time": seq,
            "event_type": event, "final_update_id": seq, "prev_final_update_id": prev,
            "side": side, "price": price, "quantity": quantity}


class CheckpointTests(unittest.TestCase):
    def checkpoint(self):
        _, state = replay_book([row(100, event="snapshot"),
                                row(100, event="snapshot", side="ask", price="11")], "AAPLUSDT")
        state["source_sha256"] = "a" * 64
        return state

    def test_delta_continuation_and_identical_boundary_snapshot(self):
        state = self.checkpoint()
        report, output = replay_book([row(105, 100, quantity="3")], "AAPLUSDT", state)
        self.assertEqual(report["imported_state_handover"], "PSEQ_LINKED_HANDOVER")
        self.assertEqual(output["bids"], [["10", "3"]])
        snapshot = [dict(row(100, event="snapshot"), received_time=101),
                    dict(row(100, event="snapshot", side="ask", price="11"), received_time=101)]
        report, output = replay_book(snapshot, "AAPLUSDT", state)
        self.assertEqual(report["imported_state_handover"], "EXACT_SNAPSHOT_HANDOVER")
        self.assertEqual(output["asks"], state["asks"])

    def test_gap_reset_or_changed_snapshot_is_not_continuity(self):
        state = self.checkpoint()
        report, output = replay_book([row(105, 99)], "AAPLUSDT", state)
        self.assertIsNone(output)
        self.assertEqual(report["imported_state_handover"], "UNVERIFIED_GAP")
        report, _ = replay_book([row(105, event="snapshot")], "AAPLUSDT", state)
        self.assertEqual(report["imported_state_handover"], "RESET_WITHOUT_CONTINUITY")
        with self.assertRaisesRegex(ValueError, "backward"):
            replay_book([row(99, 100)], "AAPLUSDT", state)

    def test_checkpoint_schema_symbol_levels_and_provenance(self):
        original = self.checkpoint()
        for changed in (
            {"symbol": "BTCUSDT"}, {"schema": "old"}, {"source_sha256": "bad"},
            {"bids": [["10", "2"], ["10", "3"]]}, {"asks": [["9", "2"]]},
            {"asks": [["11", "0"]]}, {"received_ns": True},
        ):
            state = copy.deepcopy(original)
            state.update(changed)
            with self.subTest(changed=changed), self.assertRaises((ValueError, ArithmeticError)):
                checkpoint_book(state, "AAPLUSDT")

    def test_hash_bound_import(self):
        state = self.checkpoint()
        with tempfile.TemporaryDirectory() as root:
            source = Path(root) / "source"
            source.write_bytes(b"source")
            source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
            state["source_sha256"] = source_hash
            path = Path(root) / "checkpoint"
            path.write_text(json.dumps(state))
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            self.assertEqual(read_checkpoint(path, digest, source, source_hash, "AAPLUSDT"), state)
            with self.assertRaisesRegex(ValueError, "Checkpoint hash"):
                read_checkpoint(path, "0" * 64, source, source_hash, "AAPLUSDT")
            source.write_bytes(b"changed")
            with self.assertRaisesRegex(ValueError, "source hash"):
                read_checkpoint(path, digest, source, source_hash, "AAPLUSDT")


if __name__ == "__main__":
    unittest.main()
