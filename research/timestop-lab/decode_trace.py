"""Decode CBRTS001 observations offline; this module never opens a game process.

Usage: python decode_trace.py trace.bin [--json summary.json] [--csv events.csv]
Exit status: 0 structurally complete, 1 incomplete/ambiguous, 2 invalid format.
"""

from __future__ import annotations

import argparse
import csv
import json
import struct
import sys
from pathlib import Path


MAGIC = b"CBRTS001"
HEADER_SIZE = RECORD_SIZE = 128
EVENTS = {
    1: "preexpiry", 2: "parentremove", 3: "construct", 4: "copy",
    5: "dispatch", 6: "postdispatch", 7: "healsubmission", 8: "workerdestruct",
}
HEADER_FIELDS = {
    "armed": (0, "I"), "capacity": (4, "I"), "writeCount": (8, "I"),
    "overflow": (12, "I"), "targetActorPtr": (16, "Q"), "actorID": (24, "I"),
    "epoch": (28, "I"), "regenVtable": (32, "Q"), "chitinGlobalAddress": (40, "Q"),
    "recordSize": (48, "I"), "schema": (52, "I"),
    "activeRecorders": (56, "I"),
}
RECORD_FIELDS = {
    "kind": (0, "I"), "seq": (4, "I"), "world": (8, "I"),
    "TSremaining": (12, "I"), "TScaster": (16, "i"), "actorID": (20, "i"),
    "actorPtr": (24, "Q"), "parentPtr": (32, "Q"), "workerPtr": (40, "Q"),
    "relatedPtr": (48, "Q"), "timing": (64, "I"), "opcode": (68, "I"),
    "deadline": (72, "I"), "origin": (76, "i"), "counter": (80, "i"),
    "period": (84, "h"), "periodCounter": (86, "h"), "workerDuration": (88, "i"),
    "workerDone": (92, "i"), "workerDeleted": (96, "i"), "HP": (100, "i"),
    "generalState": (104, "I"), "AISpeed": (108, "I"), "immunity": (112, "i"),
    "elapsed": (116, "I"), "flags": (120, "I"), "sharedCounter": (124, "I"),
}


class TraceFormatError(ValueError):
    """The file cannot be interpreted as the supported trace schema."""


def _unpack(data: bytes, fields: dict) -> dict:
    return {name: struct.unpack_from("<" + fmt, data, offset)[0]
            for name, (offset, fmt) in fields.items()}


def decode_trace(data: bytes) -> dict:
    """Return JSON-compatible observations, issues, and generation-scoped lineage."""
    if not data.startswith(MAGIC):
        raise TraceFormatError("Expected CBRTS001 magic.")
    if len(data) < len(MAGIC) + HEADER_SIZE:
        raise TraceFormatError("Truncated 128-byte buffer header.")
    header = _unpack(data[8:136], HEADER_FIELDS)
    if header["schema"] != 1 or header["recordSize"] != RECORD_SIZE:
        raise TraceFormatError("Only schema 1 with 128-byte records is supported.")
    if not header["capacity"]:
        raise TraceFormatError("Record capacity must be positive.")

    issues: list[dict] = []

    def issue(code: str, message: str, event: dict | None = None, **extra) -> None:
        item = {"code": code, "message": message, **extra}
        if event is not None:
            item.update(seq=event["seq"], slot=event["slot"])
        issues.append(item)

    payload = data[136:]
    available, trailing = divmod(len(payload), RECORD_SIZE)
    expected = min(header["writeCount"], header["capacity"])
    if header["activeRecorders"]:
        issue("active_recorders", "Snapshot was taken with native recorders active; consistency is unproven.",
              activeRecorders=header["activeRecorders"])
    if header["overflow"] or header["writeCount"] > header["capacity"]:
        issue("overflow", "Capture exceeded its buffer; omitted events are unknown.")
    if available < expected:
        issue("truncated_records", "Dump lacks reserved record slots.",
              expected=expected, available=available)
    if trailing:
        issue("partial_record", "Dump ends with a partial record.", bytes=trailing)
    if available > header["capacity"]:
        issue("extra_records", "Dump contains slots beyond declared capacity.")

    records: list[dict] = []
    for slot in range(min(available, header["capacity"])):
        raw = payload[slot * RECORD_SIZE:(slot + 1) * RECORD_SIZE]
        kind = struct.unpack_from("<I", raw)[0]
        if slot >= expected:
            if kind:
                issue("commit_outside_count", "Committed slot is beyond writeCount.", slot=slot)
            continue
        if not kind:
            issue("incomplete_commit", "Reserved slot has no committed event.", slot=slot)
            continue
        event = _unpack(raw, RECORD_FIELDS)
        event.update(slot=slot, event=EVENTS.get(kind, "unknown"),
                     sourceRes=raw[56:64].rstrip(b"\0").decode("ascii", errors="backslashreplace"),
                     attribution="unattributed", parentGeneration=None, workerGeneration=None)
        records.append(event)
        if event["seq"] != slot:
            issue("sequence_gap", "Sequence does not match its reserved slot; order is ambiguous.", event,
                  expectedSequence=slot)
        if kind not in EVENTS:
            issue("unknown_event", "Unrecognized committed event kind.", event)

    parents: list[dict] = []
    workers: list[dict] = []
    active_parents: dict[int, dict] = {}
    active_workers: dict[int, dict] = {}
    pending: dict[int, dict] = {}
    dispatches: list[dict] = []
    time_stop: list[dict] = []
    unknown_lifecycle = 0

    def parent_for(event: dict) -> dict | None:
        ptr = event["parentPtr"]
        if not ptr:
            issue("missing_parent_pointer", "Fixture event has no parent identity.", event)
            return None
        parent = active_parents.get(ptr)
        identity = (event["sourceRes"].upper(), event["opcode"])
        if parent and (parent["sourceRes"].upper(), parent["opcode"]) != identity:
            issue("parent_reused_without_removal", "Parent pointer changed identity without observed removal.", event)
            parent["retiredSeq"] = event["seq"]
            parent["retirement"] = "identity_changed"
            parent = None
        if parent is None:
            parent = {"generation": len(parents) + 1, "pointer": ptr,
                      "sourceRes": event["sourceRes"], "opcode": event["opcode"],
                      "firstSeq": event["seq"], "retiredSeq": None}
            parents.append(parent)
            active_parents[ptr] = parent
        event["parentGeneration"] = parent["generation"]
        return parent

    def new_worker(event: dict, ptr: int, parent_gen: int | None,
                   copied_from: int | None = None) -> dict | None:
        if not ptr:
            if parent_gen is not None:
                issue("missing_worker_pointer", "Selected worker has no pointer.", event)
            return None
        previous = active_workers.get(ptr)
        if previous:
            if previous["parentGeneration"] is not None or parent_gen is not None:
                issue("worker_reused_without_retirement", "Worker pointer reused without observed destruction.", event)
            previous["retiredSeq"] = event["seq"]
            previous["retirement"] = "pointer_reused"
        worker = {"generation": len(workers) + 1, "pointer": ptr,
                  "parentGeneration": parent_gen, "createdSeq": event["seq"],
                  "copiedFrom": copied_from, "retiredSeq": None}
        workers.append(worker)
        active_workers[ptr] = worker
        return worker

    def attribute(event: dict, worker: dict) -> None:
        event["workerGeneration"] = worker["generation"]
        event["parentGeneration"] = worker["parentGeneration"]
        if worker["parentGeneration"] is not None:
            event["attribution"] = "fixture"

    def close_pending(worker: dict, event: dict) -> None:
        if worker["generation"] in pending:
            issue("worker_retired_during_dispatch", "Worker lifetime ended before observed dispatch return.", event)

    for event in records:
        kind = event["kind"]
        if kind not in EVENTS:
            continue
        if kind in (4, 8):
            worker = active_workers.get(event["workerPtr"])
            if worker:
                attribute(event, worker)
            if event["attribution"] != "fixture":
                unknown_lifecycle += 1
            if kind == 4:
                copy = new_worker(event, event["relatedPtr"],
                                  worker["parentGeneration"] if worker else None,
                                  worker["generation"] if worker else None)
                event["relatedWorkerGeneration"] = copy["generation"] if copy else None
            elif worker:
                close_pending(worker, event)
                worker.update(retiredSeq=event["seq"], retirement="destruct")
                del active_workers[event["workerPtr"]]
            continue

        if (event["actorPtr"] != header["targetActorPtr"] or
                (event["actorID"] & 0xFFFFFFFF) != header["actorID"] or not event["actorPtr"]):
            issue("target_mismatch", "Actor-context record does not match the selected actor.", event)
            continue
        ts = {name: event[name] for name in ("world", "TSremaining", "TScaster")}
        if not time_stop or any(time_stop[-1][name] != value for name, value in ts.items()):
            time_stop.append({"seq": event["seq"], **ts})

        if kind in (1, 2, 3):
            expected_opcode = {"CBRTBUF": 0, "CBRTREG": 98}.get(event["sourceRes"].upper())
            if expected_opcode is None or event["opcode"] != expected_opcode or (kind == 3 and expected_opcode != 98):
                issue("fixture_mismatch", "Parent record is not the selected AC/regeneration fixture.", event)
                continue
            event["attribution"] = "fixture"
            parent = parent_for(event)
            if parent is None:
                continue
            if kind == 2:
                parent.update(retiredSeq=event["seq"], retirement="parentremove")
                del active_parents[event["parentPtr"]]
            elif kind == 3:
                worker = new_worker(event, event["workerPtr"], parent["generation"])
                if worker:
                    attribute(event, worker)
            continue

        worker = active_workers.get(event["workerPtr"])
        if worker is None or worker["parentGeneration"] is None:
            if worker:
                attribute(event, worker)
            issue("unmatched_selected_worker", "Selected-actor event lacks a known live fixture worker lineage.", event)
            continue
        attribute(event, worker)
        generation = worker["generation"]
        if kind == 5:
            if generation in pending:
                issue("overlapping_dispatch", "Worker dispatched again before its observed return.", event)
            pending[generation] = {"before": event, "heals": []}
        elif kind == 7:
            if generation not in pending:
                issue("heal_outside_dispatch", "Healing submission has no matching observed dispatch.", event)
            else:
                pending[generation]["heals"].append(event["seq"])
        elif kind == 6:
            pair = pending.pop(generation, None)
            if pair is None:
                issue("unmatched_postdispatch", "Worker return has no observed dispatch entry.", event)
            else:
                before = pair["before"]
                dispatches.append({"workerGeneration": generation,
                                   "parentGeneration": worker["parentGeneration"],
                                   "beforeSeq": before["seq"], "afterSeq": event["seq"],
                                   "worldBefore": before["world"], "worldAfter": event["world"],
                                   "HPBefore": before["HP"], "HPAfter": event["HP"],
                                   "HPDelta": event["HP"] - before["HP"],
                                   "healSubmissionSeqs": pair["heals"]})

    for pair in pending.values():
        issue("unmatched_dispatch", "Capture has no matching dispatch return.", pair["before"])

    return {
        "format": MAGIC.decode("ascii"), "header": header,
        "status": "incomplete" if issues else "complete",
        "acceptance": "Offline trace analysis only; no live acceptance inferred.",
        "counts": {"reservedSlots": expected, "committedRecords": len(records),
                   "fixtureEvents": sum(e["attribution"] == "fixture" for e in records),
                   "unattributedLifecycleEvents": unknown_lifecycle,
                   "unattributedEvents": sum(e["attribution"] != "fixture" for e in records),
                   "pairedDispatches": len(dispatches)},
        "issues": issues, "parents": parents, "workers": workers,
        "dispatches": dispatches, "timeStopObservations": time_stop, "records": records,
        "limitations": [
            "Complete means structurally complete within this capture, not complete gameplay coverage.",
            "Time Stop entries are sampled observations; missing edges and full intervals are not reconstructed.",
            "Healing submissions are native effect attempts; HPDelta is the observed change during a paired dispatch.",
            "Pointers identify generations only within this epoch; unobserved removal paths can hide pointer reuse.",
            "Unattributed global copy/destruction events can belong to other actors and are not fixture evidence.",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("trace", type=Path)
    parser.add_argument("--json", type=Path, dest="json_path", help="JSON destination; otherwise stdout")
    parser.add_argument("--csv", type=Path, dest="csv_path", help="Optional committed-event CSV")
    args = parser.parse_args(argv)
    try:
        result = decode_trace(args.trace.read_bytes())
        encoded = json.dumps(result, indent=2) + "\n"
        if args.json_path:
            args.json_path.write_text(encoded, encoding="utf-8")
        else:
            sys.stdout.write(encoded)
        if args.csv_path:
            fields = ["slot", "event", "attribution", "parentGeneration", "workerGeneration",
                      "relatedWorkerGeneration", *RECORD_FIELDS, "sourceRes"]
            with args.csv_path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=fields)
                writer.writeheader()
                writer.writerows(result["records"])
    except (OSError, TraceFormatError) as exc:
        print(f"Trace decode failed: {exc}", file=sys.stderr)
        return 2
    return 1 if result["issues"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
