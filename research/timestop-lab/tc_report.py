"""Summarize a Time Clocks lab sampler file (<capture>.samples.jsonl): what happened at which
world tick, relative to the capture's Time Stop.

Usage: python -B research/timestop-lab/tc_report.py SAMPLES.jsonl [--json OUT]

Read only. Times are world ticks (15 per second). For each tracked creature: HP changes, AI
speed changes and each tracked effect (source/opcode) with its deadline when first seen,
every deadline move and its removal. Copies of one effect that a creature has at the same time
(a cloud's next pulse) get rows of their own ('#2', ...), told apart by their deadlines, since
the engine reorders its list when one goes. For each projectile: its decode, the tick it got an ID,
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


def copies(text: str) -> dict[str, list[tuple[int, int]]]:
    """'SRC/op/timing/deadline,...' -> {'SRC/op': [(timing, deadline), ...]} in list order."""
    out: dict[str, list[tuple[int, int]]] = {}
    for item in filter(None, (text or "").split(",")):
        source, opcode, timing, deadline = item.split("/")
        out.setdefault(f"{source}/{opcode}", []).append((int(timing), int(deadline)))
    return out


def match(before: list[int], now: list[int], elapsed: int) -> tuple[list[tuple[int, int]], list[int], list[int]]:
    """Pairs (index before, index now) of the same copies of one effect, then the indexes of the
    copies that went and of those that came. A copy keeps its deadline, or a stop moves it later
    by at most one tick per tick elapsed (plus one: a creature's first frozen pass counts one);
    the engine reorders the list when a copy goes, so the order alone cannot tell them apart."""
    pairs, left, new = [], set(range(len(before))), set(range(len(now)))
    for i in sorted(left):
        j = next((j for j in sorted(new) if now[j] == before[i]), None)
        if j is not None:
            pairs.append((i, j))
            left.discard(i)
            new.discard(j)
    for i, j in sorted(((i, j) for i in left for j in new if 0 < now[j] - before[i] <= elapsed + 1),
                       key=lambda p: (now[p[1]] - before[p[0]], p)):
        if i in left and j in new:
            pairs.append((i, j))
            left.discard(i)
            new.discard(j)
    return pairs, sorted(left), sorted(new)


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
    live: dict[int, dict[str, list[tuple[str, int]]]] = {}  # per actor: effect -> [(row, deadline)]
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
            now, held = copies(state.get("fx", "")), live.setdefault(ident, {})
            elapsed = max(record["w"] - last["w"], 0) if last else 0
            rows = entry["effects"]
            for group in sorted(set(now) | set(held)):
                before, current = held.get(group, []), now.get(group, [])
                pairs, went, came = match([d for _, d in before], [d for _, d in current], elapsed)
                names: list[str | None] = [None] * len(current)
                for i, j in pairs:
                    name, old = before[i]
                    if current[j][1] != old:
                        rows[name]["moves"].append([record["w"], old, current[j][1]])
                    names[j] = name
                for i in went:
                    rows[before[i][0]]["removed"] = record["w"]
                for j in came:
                    timing, deadline = current[j]
                    again = next((name for name, row in rows.items()
                                  if name.split("#")[0] == group and row["removed"] is not None), None)
                    if again:
                        # Removed, then applied again (a cloud's next pulse): [removed, again, deadline].
                        rows[again].setdefault("again", []).append([rows[again]["removed"], record["w"], deadline])
                        rows[again]["removed"] = None
                        names[j] = again
                        continue
                    name, n = group, 1
                    while name in rows:
                        n += 1
                        name = f"{group}#{n}"
                    rows[name] = {"seen": record["w"], "timing": timing, "deadline": deadline, "moves": [],
                                  "removed": None}
                    names[j] = name
                held[group] = [(names[j], current[j][1]) for j in range(len(current))]
                if not current:
                    del held[group]
            previous[ident] = {**state, "w": record["w"]}
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
