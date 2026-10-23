"""Summarize a Time Clocks lab sampler file (<capture>.samples.jsonl): what happened at which
world tick, relative to the capture's Time Stop.

Usage: python -B research/timestop-lab/tc_report.py SAMPLES.jsonl [--json OUT]

Read only. Times are world ticks (15 per second). For each tracked creature: HP changes, AI
speed changes and each tracked effect (source/opcode) with its deadline when first seen,
every deadline move and its removal. For each projectile: its decode, the tick it got an ID,
the ticks it moved, its area counters (arrival, remaining explosions, pulse countdown) when
they changed, and its end. Stops: the ticks the counter at game +0x9690 was set, and the caster.
Marks: the labels script actions recorded. A record is kept only when something changed, so
a tick without a record repeats the one before it.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


def load(path: Path) -> tuple[dict, list[dict]]:
    lines = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not lines or lines[0].get("k") != "header":
        raise ValueError(f"{path}: not a sampler file (no header)")
    return lines[0], lines[1:]


def effects(text: str) -> dict[str, tuple[int, int]]:
    """'SRC/op/timing/deadline,...' -> {'SRC/op': (timing, deadline)}; a second copy gets '#2'."""
    out: dict[str, tuple[int, int]] = {}
    for item in filter(None, (text or "").split(",")):
        source, opcode, timing, deadline = item.split("/")
        key, n = f"{source}/{opcode}", 1
        while key in out:
            n += 1
            key = f"{source}/{opcode}#{n}"
        out[key] = (int(timing), int(deadline))
    return out


def stops(samples: list[dict]) -> list[dict]:
    """Each run of samples with the stop counter set: first and last tick, the tick it ended."""
    out, current = [], None
    for record in samples:
        if record.get("ts", 0) > 0:
            if current is None:
                current = {"start": record["w"], "counter": record["ts"], "caster": record.get("tc"), "last": record["w"]}
                out.append(current)
            current["last"] = record["w"]
        elif current is not None:
            current["end"] = record["w"]
            current = None
    return out


def summarize(header: dict, records: list[dict]) -> dict:
    samples = [r for r in records if r.get("k") == "s"]
    marks = [{"label": r["label"], "w": r["w"], "actor": r.get("actor")} for r in records if r.get("k") == "mark"]
    actors: dict[int, dict] = {}
    previous: dict[int, dict] = {}
    for record in samples:
        for state in record.get("a", []):
            ident = state["id"]
            entry = actors.setdefault(ident, {"hp": [], "speed": [], "effects": {}, "gone": None})
            last = previous.get(ident)
            if state.get("gone"):
                if entry["gone"] is None:
                    entry["gone"] = record["w"]
                continue
            if last is None or last.get("hp") != state["hp"]:
                entry["hp"].append([record["w"], state["hp"]])
            if last is None or last.get("sp") != state["sp"]:
                entry["speed"].append([record["w"], state["sp"]])
            now, before = effects(state.get("fx", "")), effects((last or {}).get("fx", ""))
            for key, (timing, deadline) in now.items():
                item = entry["effects"].setdefault(key, {"seen": record["w"], "timing": timing, "deadline": deadline,
                                                         "moves": [], "removed": None})
                if key in before and before[key][1] != deadline:
                    item["moves"].append([record["w"], before[key][1], deadline])
                if key not in before and item["removed"] is not None:
                    # Removed, then applied again (a cloud's next pulse): [removed, again, deadline].
                    item.setdefault("again", []).append([item["removed"], record["w"], deadline])
                    item["removed"] = None
            for key in before:
                if key not in now and key in entry["effects"]:
                    entry["effects"][key]["removed"] = record["w"]
            previous[ident] = state
    projectiles: dict[int, dict] = {}
    decodes = []
    for record in records:
        kind = record.get("k")
        if kind == "decode":
            decodes.append({key: record.get(key) for key in ("w", "ty", "source", "by", "pro")})
        elif kind == "fired":
            projectiles[record["id"]] = {"type": record.get("ty"), "decoded": record.get("decoded"),
                                         "fired": record["w"], "moved": [], "area": [], "gone": None}
        elif kind == "gone" and record.get("id") in projectiles:
            projectiles[record["id"]]["gone"] = record["w"]
        elif kind == "unresolved":
            decodes.append({"w": record["w"], "ty": record.get("ty"), "unresolved": True})
    last_state: dict[int, dict] = {}
    for record in samples:
        for state in record.get("pj", []):
            entry = projectiles.get(state["id"])
            if entry is None:
                continue
            last = last_state.get(state["id"])
            if last and (last["x"], last["y"]) != (state["x"], state["y"]):
                entry["moved"].append(record["w"])
            counters = [state.get(key) for key in ("ar", "rm", "cd")]
            if "ar" in state and (last is None or [last.get(key) for key in ("ar", "rm", "cd")] != counters):
                entry["area"].append([record["w"], *counters])
            if last is None:
                entry["first"] = [record["w"], state["x"], state["y"]]
            entry["last"] = [record["w"], state["x"], state["y"]]
            last_state[state["id"]] = state
    for entry in projectiles.values():
        moves = entry.pop("moved")
        entry["moved"] = {"count": len(moves), "first": moves[0] if moves else None, "last": moves[-1] if moves else None,
                          "ticks": sorted(set(moves))}
    return {"lab": header.get("lab"), "mod": header.get("mod"), "records": header.get("records"),
            "overflow": header.get("overflow"), "errors": header.get("errors"),
            "world": [samples[0]["w"], samples[-1]["w"]] if samples else None, "stops": stops(samples),
            "marks": marks, "actors": {str(k): v for k, v in actors.items()}, "decodes": decodes,
            "projectiles": {str(k): v for k, v in projectiles.items()}}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("samples", type=Path)
    parser.add_argument("--json", type=Path)
    args = parser.parse_args(argv)
    try:
        summary = summarize(*load(args.samples))
    except (OSError, ValueError, KeyError) as error:
        print(f"TC_REPORT_ERROR: {error}", file=sys.stderr)
        return 2
    text = json.dumps(summary, indent=1)
    if args.json:
        with args.json.open("x", encoding="utf-8") as handle:
            handle.write(text + "\n")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
