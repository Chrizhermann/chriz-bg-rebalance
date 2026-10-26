"""Synthetic decoder checks; these do not validate the engine hooks or gameplay."""

import contextlib
import csv
import io
import json
import struct
import tempfile
import unittest
from pathlib import Path

from decode_trace import HEADER_FIELDS, MAGIC, RECORD_FIELDS, TraceFormatError, decode_trace, main


ACTOR = 0x1234567890
PARENT = 0x2345678900
WORKER = 0x3456789000


def record(kind, seq, **values):
    fields = dict(kind=kind, seq=seq, world=100, TScaster=-1, actorID=42,
                  actorPtr=ACTOR, parentPtr=PARENT, workerPtr=WORKER,
                  timing=0x1000, opcode=98, deadline=280, period=2,
                  workerDuration=180, HP=10, AISpeed=1)
    fields.update(values)
    raw = bytearray(128)
    for name, (offset, fmt) in RECORD_FIELDS.items():
        struct.pack_into("<" + fmt, raw, offset, fields.get(name, 0))
    source = fields.get("sourceRes", "CBRTREG").encode("ascii")
    raw[56:64] = source.ljust(8, b"\0")[:8]
    return bytes(raw)


def trace(*records, capacity=None, write_count=None, overflow=0, padding=False, **values):
    capacity = max(1, len(records)) if capacity is None else capacity
    fields = dict(armed=0, capacity=capacity,
                  writeCount=len(records) if write_count is None else write_count,
                  overflow=overflow, targetActorPtr=ACTOR, actorID=42, epoch=3,
                  regenVtable=0x140598B18, chitinGlobalAddress=0x140667548,
                  recordSize=128, schema=1, activeRecorders=0)
    fields.update(values)
    header = bytearray(128)
    for name, (offset, fmt) in HEADER_FIELDS.items():
        struct.pack_into("<" + fmt, header, offset, fields[name])
    body = b"".join(records)
    if padding:
        body += bytes(max(0, capacity - len(records)) * 128)
    return MAGIC + header + body


def codes(result):
    return {issue["code"] for issue in result["issues"]}


class DecodeTraceTests(unittest.TestCase):
    def test_documented_binary_offsets_and_signed_fields(self):
        # Build independently of the decoder's field maps to catch schema drift.
        header = bytearray(128)
        struct.pack_into("<IIIIQIIQQII", header, 0,
                         0, 1, 1, 0, ACTOR, 42, 3, 0x140598B18, 0x140667548, 128, 1)
        raw = bytearray(128)
        struct.pack_into("<IIIIiiQQQQ", raw, 0, 3, 0, 123, 20, -1, 42,
                         ACTOR, PARENT, WORKER, 0)
        raw[56:64] = b"CBRTREG\0"
        struct.pack_into("<IIIiihhiiiiIIiIII", raw, 64,
                         0x1000, 98, 303, -7, -3, 2, -1, 180, 0, 0, -5,
                         0x8000, 0, -1, 1, 0xFEDCBA98, 15)
        result = decode_trace(MAGIC + header + raw)
        event = result["records"][0]
        self.assertEqual(result["status"], "complete")
        self.assertEqual((event["origin"], event["counter"], event["periodCounter"], event["HP"]),
                         (-7, -3, -1, -5))
        self.assertEqual((event["generalState"], event["immunity"], event["flags"], event["sharedCounter"]),
                         (0x8000, -1, 0xFEDCBA98, 15))

    def test_paired_hp_delta_does_not_treat_submission_as_healing(self):
        result = decode_trace(trace(record(3, 0), record(5, 1, HP=10),
                                    record(7, 2, relatedPtr=0x4444), record(6, 3, HP=10)))
        self.assertEqual(result["status"], "complete")
        self.assertEqual(result["dispatches"][0]["HPDelta"], 0)
        self.assertEqual(result["dispatches"][0]["healSubmissionSeqs"], [2])

    def test_copy_inherits_parent_and_destruction_allows_pointer_reuse(self):
        copy = WORKER + 0x100
        result = decode_trace(trace(
            record(3, 0), record(4, 1, actorPtr=0, relatedPtr=copy),
            record(8, 2, actorPtr=0), record(5, 3, workerPtr=copy),
            record(6, 4, workerPtr=copy, HP=12), record(8, 5, actorPtr=0, workerPtr=copy),
            record(2, 6), record(3, 7), record(5, 8), record(6, 9, HP=11),
        ))
        self.assertEqual(result["status"], "complete")
        self.assertEqual([w["generation"] for w in result["workers"]], [1, 2, 3])
        self.assertEqual([w["parentGeneration"] for w in result["workers"]], [1, 1, 2])
        self.assertEqual(result["workers"][1]["copiedFrom"], 1)
        self.assertEqual([d["HPDelta"] for d in result["dispatches"]], [2, 1])

    def test_reuse_without_retirement_is_ambiguous(self):
        result = decode_trace(trace(record(3, 0), record(3, 1)))
        self.assertIn("worker_reused_without_retirement", codes(result))

    def test_global_unknown_lifecycle_is_not_automatically_fixture_evidence(self):
        result = decode_trace(trace(record(4, 0, actorPtr=0, relatedPtr=WORKER + 1),
                                    record(8, 1, actorPtr=0, workerPtr=WORKER + 1)))
        self.assertEqual(result["status"], "complete")
        self.assertEqual(result["counts"]["unattributedLifecycleEvents"], 2)
        self.assertEqual(result["counts"]["fixtureEvents"], 0)

    def test_unknown_copied_worker_later_selected_remains_ambiguous(self):
        result = decode_trace(trace(record(4, 0, actorPtr=0, relatedPtr=WORKER + 1),
                                    record(5, 1, workerPtr=WORKER + 1),
                                    record(7, 2, workerPtr=WORKER + 1)))
        self.assertIn("unmatched_selected_worker", codes(result))
        self.assertEqual(result["counts"]["fixtureEvents"], 0)

    def test_dispatch_after_destruction_does_not_resurrect_lineage(self):
        result = decode_trace(trace(record(3, 0), record(8, 1, actorPtr=0), record(5, 2)))
        self.assertIn("unmatched_selected_worker", codes(result))
        self.assertIsNone(result["records"][-1]["workerGeneration"])

    def test_truncated_reserved_slots_partial_commit_and_sequence_are_reported(self):
        complete = trace(record(3, 0), record(5, 1), record(6, 2))
        result = decode_trace(complete[:-30])
        self.assertTrue({"truncated_records", "partial_record", "unmatched_dispatch"} <= codes(result))
        result = decode_trace(trace(record(3, 4), bytes(128)))
        self.assertTrue({"sequence_gap", "incomplete_commit"} <= codes(result))

    def test_overflow_is_incomplete_even_with_valid_committed_records(self):
        result = decode_trace(trace(record(3, 0), capacity=1, write_count=4, overflow=3))
        self.assertEqual(result["status"], "incomplete")
        self.assertEqual(codes(result), {"overflow"})

    def test_active_recorder_snapshot_is_incomplete_even_when_committed(self):
        data = bytearray(trace(record(3, 0)))
        struct.pack_into("<I", data, 8 + 56, 1)
        result = decode_trace(bytes(data))
        self.assertEqual(result["header"]["activeRecorders"], 1)
        self.assertEqual(result["status"], "incomplete")
        self.assertEqual(codes(result), {"active_recorders"})

    def test_capacity_padding_and_written_prefix_are_both_supported(self):
        for padding in (False, True):
            with self.subTest(padding=padding):
                result = decode_trace(trace(record(3, 0), capacity=10, padding=padding))
                self.assertEqual(result["status"], "complete")
                self.assertEqual(len(result["records"]), 1)
        result = decode_trace(trace(record(3, 0), record(5, 1), write_count=1))
        self.assertIn("commit_outside_count", codes(result))

    def test_target_and_fixture_identity_are_checked(self):
        result = decode_trace(trace(record(3, 0, actorPtr=ACTOR + 1),
                                    record(1, 1, sourceRes="OTHER")))
        self.assertTrue({"target_mismatch", "fixture_mismatch"} <= codes(result))
        self.assertEqual(result["counts"]["fixtureEvents"], 0)

    def test_unsigned_header_actor_id_matches_signed_record_id(self):
        result = decode_trace(trace(record(3, 0, actorID=-1), actorID=0xFFFFFFFF))
        self.assertEqual(result["status"], "complete")

    def test_missing_pairs_and_retirement_during_dispatch_are_incomplete(self):
        result = decode_trace(trace(record(3, 0), record(6, 1), record(7, 2),
                                    record(5, 3), record(8, 4, actorPtr=0)))
        self.assertTrue({"unmatched_postdispatch", "heal_outside_dispatch",
                         "worker_retired_during_dispatch", "unmatched_dispatch"} <= codes(result))

    def test_time_stop_records_are_observations_without_invented_edges(self):
        result = decode_trace(trace(record(1, 0, TSremaining=20, TScaster=7),
                                    record(1, 1, world=120, TSremaining=0)))
        self.assertEqual([row["TSremaining"] for row in result["timeStopObservations"]], [20, 0])
        self.assertNotIn("intervals", result)

    def test_invalid_headers_are_rejected(self):
        for data in (b"wrong", MAGIC + bytes(30), trace(schema=2), trace(recordSize=64)):
            with self.subTest(length=len(data)):
                with self.assertRaises(TraceFormatError):
                    decode_trace(data)

    def test_cli_json_csv_and_incomplete_exit_status(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            source, summary, events = [base / name for name in ("trace.bin", "summary.json", "events.csv")]
            source.write_bytes(trace(record(3, 0), record(5, 1)))
            self.assertEqual(main([str(source), "--json", str(summary), "--csv", str(events)]), 1)
            self.assertEqual(json.loads(summary.read_text())["status"], "incomplete")
            with events.open(newline="", encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[1]["event"], "dispatch")
            source.write_bytes(b"wrong")
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(main([str(source)]), 2)


if __name__ == "__main__":
    unittest.main()
