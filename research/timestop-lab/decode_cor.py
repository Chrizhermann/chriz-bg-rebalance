"""Decode a CBRTCor lab record (cbr-timestop-output/NAME.jsonl) offline: what each watched
creature's periodic effects did. This module never opens a game process.

Usage: python decode_cor.py record.jsonl [--json summary.json]
Exit status: 0 complete and consistent, 1 events dropped or a replay disagreement, 2 invalid format.

A dispatch event holds the worker as its update will see it. The update is replayed with
periodic_model.worker_step (checked against the pinned executable in test_cor.py), except in a
frozen pass and, for poison, disease and the repeated EFF, while the game waits (WAITING_STATES).
The replay must agree with the worker the next dispatch of the same worker shows; every
disagreement is listed. Units are counted per effect, from the construct that first names its
parent until its worker ends, at world time and, in a corrected record, at the correction's active
time T. A worker built before the record started counts under a parent of null.
"""

from __future__ import annotations

import argparse
from collections import Counter
import json
import sys
from pathlib import Path

sys.dont_write_bytecode = True
from periodic_model import FAMILY_BY_ID, WAITING_STATES, worker_step  # noqa: E402

FIELDS = {
    "F": ("world", "counted"),
    "E": ("world", "elapsed", "list", "check", "hp", "frozen", "mode", "T", "kappa", "frozen_ticks", "state"),
    "D": ("world", "worker", "family", "elapsed", "result", "native", "counter", "period", "phase", "type",
          "amount22", "amount24", "remaining", "done"),
    "C": ("world", "parent", "worker", "family", "origin", "deadline", "timing", "period", "native_phase",
          "phase", "native_remaining", "remaining", "rule", "new"),
}
MODES = {0: "native", 1: "suppress", 2: "restart", 3: "deliver"}
RULES = {0: "native seed", 1: "ahead", 2: "carried", 3: "behind"}


class RecordFormatError(ValueError):
    pass


def read_record(text: str) -> tuple[dict, list[dict]]:
    lines = text.splitlines()
    if not lines:
        raise RecordFormatError("empty record")
    header = json.loads(lines[0])
    if not isinstance(header, dict) or header.get("schema") != 1:
        raise RecordFormatError("not a schema 1 CBRTCor record")
    events = []
    for number, line in enumerate(lines[1:], start=2):
        if not line.strip():
            continue
        event = json.loads(line)
        if not isinstance(event, list) or not event or event[0] not in FIELDS:
            raise RecordFormatError(f"line {number}: unknown event")
        if len(event) != len(FIELDS[event[0]]) + 2:
            raise RecordFormatError(f"line {number}: {event[0]} event with {len(event)} fields")
        events.append({"kind": event[0], "id": event[1], **dict(zip(FIELDS[event[0]], event[2:]))})
    if len(events) != header.get("events"):
        raise RecordFormatError(f"header names {header.get('events')} events, the record holds {len(events)}")
    return header, events


def _intervals(values):
    return [b - a for a, b in zip(values, values[1:])]


def decode_record(header: dict, events: list[dict]) -> dict:
    creatures: dict[int, dict] = {}
    passes: dict[int, dict] = {}  # the current pass (latest entry event) per creature
    workers: dict[int, dict] = {}  # worker address -> {"effect", "expect"}
    effects: dict[tuple[int, int], dict] = {}  # (creature, parent) -> its current effect
    mismatches = []

    def creature(ident):
        if ident not in creatures:
            creatures[ident] = {"id": ident, "passes": 0, "frozen_passes": 0, "frozen_ticks": 0, "first": None,
                                "last": None, "hp": [], "calls": Counter(), "modes": Counter(),
                                "dispatch": Counter(), "effects": []}
        return creatures[ident]

    def new_effect(record, ident, family, parent, origin=None, deadline=None, timing=None, world=None):
        effect = {"family": family, "parent": parent, "origin": origin, "deadline": deadline, "timing": timing,
                  "applied": world, "builds": 0, "rules": Counter(), "units": [], "ended": None,
                  "last_origin": origin, "last_deadline": deadline}
        record["effects"].append(effect)
        if parent is not None:
            effects[(ident, parent)] = effect
        return effect

    for event in events:
        kind, ident = event["kind"], event["id"]
        record = creature(ident)
        if kind == "F":
            record["frozen_passes"] += 1
            record["frozen_ticks"] += event["counted"] or 0
        elif kind == "E":
            passes[ident] = event
            record["passes"] += 1
            record["calls"][event["world"]] += 1
            if record["first"] is None:
                record["first"] = event["world"]
            record["last"] = event["world"]
            if not record["hp"] or record["hp"][-1][1] != event["hp"]:
                record["hp"].append([event["world"], event["hp"]])
            if event["mode"] is not None:
                record["modes"][MODES.get(event["mode"], event["mode"])] += 1
        elif kind == "C":
            family = FAMILY_BY_ID.get(event["family"])
            effect = effects.get((ident, event["parent"]))
            if (effect is None or event["new"] == 1
                    or (event["new"] is None and event["origin"] != effect["last_origin"])):
                effect = new_effect(record, ident, family, event["parent"], event["origin"], event["deadline"],
                                    event["timing"], event["world"])
            effect["builds"] += 1
            effect["ended"] = None  # rebuilt: a worker continues it
            if event["rule"] is not None:
                effect["rules"][RULES.get(event["rule"], event["rule"])] += 1
            effect["last_origin"], effect["last_deadline"] = event["origin"], event["deadline"]
            workers[event["worker"]] = {"effect": effect, "expect": None}
        else:  # "D"
            family = FAMILY_BY_ID.get(event["family"])
            entry = passes.get(ident)
            if family is None or entry is None:
                raise RecordFormatError(f"dispatch without a known family or pass at {event['world']}")
            slot = workers.get(event["worker"])
            if slot is None:
                slot = workers[event["worker"]] = {"effect": new_effect(record, ident, family, None), "expect": None}
            state = {"counter": event["counter"] & 0xFFFFFFFF, "remaining": event["remaining"],
                     "mode": event["type"] & 0xFFFF, "phase": event["phase"] & 0xFFFF,
                     "period": event["period"] & 0xFFFF, "amount22": event["amount22"] & 0xFFFF,
                     "amount24": event["amount24"] & 0xFFFF, "done": event["done"]}
            expect = slot["expect"]
            if expect is not None:
                want = (expect["phase"], expect["remaining"], expect["done"])
                got = (state["phase"], state["remaining"], state["done"])
                if want != got:
                    mismatches.append({"id": ident, "world": event["world"], "worker": event["worker"],
                                       "family": family, "replayed": want, "recorded": got})
            elapsed = event["result"] if event["result"] >= 0 else event["elapsed"]
            after = dict(state)
            units = 0
            if not entry["frozen"] and not (family != "regeneration" and entry["state"] in WAITING_STATES):
                units = worker_step(after, elapsed, family)
            slot["expect"] = after
            effect = slot["effect"]
            if units:
                effect["units"].append([event["world"], entry["T"], units])
            if after["done"]:
                effect["ended"] = event["world"]
            if entry["mode"] is not None:
                exact = event["counter"] == event["native"] and event["result"] in (-1, event["elapsed"])
                record["dispatch"]["native" if exact else "changed"] += 1
    out = []
    for record in creatures.values():
        calls = Counter(record["calls"].values())
        worlds = sorted(record["calls"])
        effects_out = []
        for effect in record["effects"]:
            worlds_units = [unit[0] for unit in effect["units"] for _ in range(unit[2])]
            active = [unit[1] for unit in effect["units"] if unit[1] is not None for _ in range(unit[2])]
            effects_out.append({**{key: effect[key] for key in ("family", "parent", "origin", "deadline", "timing",
                                                                "applied", "builds", "ended", "last_origin",
                                                                "last_deadline")},
                                "rules": dict(effect["rules"]), "unit_count": len(worlds_units),
                                "units": effect["units"], "world_intervals": _intervals(worlds_units),
                                "active_intervals": _intervals(active)})
        out.append({"id": record["id"], "first": record["first"], "last": record["last"],
                    "passes": record["passes"], "frozen_passes": record["frozen_passes"],
                    "frozen_ticks": record["frozen_ticks"],
                    "calls_per_tick": {str(key): value for key, value in sorted(calls.items())},
                    "tick_gaps": {str(key): value for key, value in sorted(Counter(_intervals(worlds)).items())},
                    "modes": dict(record["modes"]), "dispatch": dict(record["dispatch"]), "hp": record["hp"],
                    "effects": effects_out})
    issues = []
    if header.get("dropped"):
        issues.append(f"{header['dropped']} events dropped")
    if mismatches:
        issues.append(f"{len(mismatches)} replay disagreements")
    return {"name": header.get("name"), "observe": header.get("observe"), "events": len(events),
            "watch": header.get("watch"), "stats": header.get("stats"), "creatures": out,
            "mismatch_count": len(mismatches), "mismatches": mismatches[:50], "issues": issues}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("record", type=Path)
    parser.add_argument("--json", type=Path, dest="json_path", help="JSON destination; otherwise stdout")
    args = parser.parse_args(argv)
    try:
        result = decode_record(*read_record(args.record.read_text(encoding="utf-8")))
    except (OSError, ValueError) as exc:
        print(f"Record decode failed: {exc}", file=sys.stderr)
        return 2
    encoded = json.dumps(result, indent=1) + "\n"
    if args.json_path:
        args.json_path.write_text(encoded, encoding="utf-8")
    else:
        sys.stdout.write(encoded)
    return 1 if result["issues"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
