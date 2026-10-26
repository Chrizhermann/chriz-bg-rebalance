"""Decode a cloud record of CBRTCld.lua (cbr-timestop-output/NAME.jsonl) offline: when the cloud
arrived, exploded and vanished, what the sampled creatures' hit points did, and whether any of it
changed while a Time Stop ran. This module never opens a game process.

Usage: python decode_cloud.py record.jsonl [--json summary.json]
Exit status: 0 complete, 1 incomplete (samples lost, errors caught in the game, or no cloud
followed from its arrival to its end), 2 invalid format.

A sample is kept at a sampled creature's update whenever something but the world time changed.
A change between two samples that both show a running stop happened inside the stop. One between
a sample without a running stop and one with it happened at the stop's start, one in the reverse
order at its end: there the order of updates within the tick decides whether the cloud still ran.
Once arrived, the cloud changes its countdown at every update it runs (one step, or the reload at
an explosion check), so its own updates are counted from those changes: the ticks it skipped are
its lifetime minus its updates, and an explosion's gap in updates is the count between two.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.dont_write_bytecode = True

SAMPLE_KEYS = ("t", "by", "stop", "caster", "cloud", "left", "arrived", "interval", "countdown", "hp")
CLOUD_FIELDS = ("cloud", "left", "arrived", "interval", "countdown")
CLOUD_STATES = frozenset(("none", "pending", "live", "gone", "lost"))


class RecordFormatError(ValueError):
    pass


def read_record(text: str) -> tuple[dict, list[dict]]:
    lines = text.splitlines()
    if not lines:
        raise RecordFormatError("empty record")
    header = json.loads(lines[0])
    if not isinstance(header, dict) or header.get("schema") != 1 or not isinstance(header.get("watch"), list) \
            or not isinstance(header.get("cloud"), dict):
        raise RecordFormatError("not a schema 1 CBRTCld record")
    samples = []
    for number, line in enumerate(lines[1:], start=2):
        if not line.strip():
            continue
        sample = json.loads(line)
        if not isinstance(sample, dict) or tuple(sample) != SAMPLE_KEYS:
            raise RecordFormatError(f"line {number}: not a sample")
        if sample["cloud"] not in CLOUD_STATES or len(sample["hp"]) != len(header["watch"]):
            raise RecordFormatError(f"line {number}: unknown cloud state or hit point count")
        samples.append(sample)
    if len(samples) != header.get("samples"):
        raise RecordFormatError(f"{len(samples)} samples, header says {header.get('samples')}")
    return header, samples


def _window(samples: list[dict], first: int, last: int) -> dict:
    start, end = samples[first], samples[last]
    return {"first": start["t"], "last": end["t"], "ticks": end["t"] - start["t"] + 1,
            "caster": start["caster"], "longest": max(s["stop"] for s in samples[first:last + 1]),
            "left": [start["left"], end["left"]], "countdown": [start["countdown"], end["countdown"]],
            "cloud_inside": [], "hp_inside": [], "at_start": None, "at_end": None}


def _changes(before: dict, after: dict, watch: list) -> tuple[list, list]:
    cloud = [{"field": key, "from": before[key], "to": after[key]}
             for key in CLOUD_FIELDS if before[key] != after[key]]
    hp = [{"id": ident, "from": old, "to": new}
          for ident, old, new in zip(watch, before["hp"], after["hp"]) if old != new]
    return cloud, hp


def decode_record(header: dict, samples: list[dict]) -> dict:
    watch = header["watch"]
    issues = []
    if header.get("overflow"):
        issues.append("samples overflowed; the record stopped early")
    if header.get("errors"):
        issues.append(f"{header['errors']} errors caught in the game, first: {header.get('first_error')}")

    # Each stop window by the index of every sample it holds.
    stops, of, open_at = [], {}, None
    for index, sample in enumerate(samples + [{"stop": 0}]):
        if sample["stop"] > 0 and open_at is None:
            open_at = index
        if sample["stop"] == 0 and open_at is not None:
            if index == len(samples):
                issues.append("the record ends inside a stop")
            stops.append(_window(samples, open_at, index - 1))
            of.update((i, stops[-1]) for i in range(open_at, index))
            open_at = None

    explosions, checks, hp = [], [], {ident: {"drops": [], "rises": []} for ident in watch}
    for index, (before, after) in enumerate(zip(samples, samples[1:])):
        cloud, changed_hp = _changes(before, after, watch)
        if cloud or changed_hp:
            entry = {"t": after["t"], "by": after["by"], "cloud": cloud, "hp": changed_hp}
            if before["stop"] > 0 and after["stop"] > 0:
                of[index]["cloud_inside"] += [dict(c, t=after["t"]) for c in cloud]
                of[index]["hp_inside"] += [dict(h, t=after["t"]) for h in changed_hp]
            elif after["stop"] > 0:
                of[index + 1]["at_start"] = entry
            elif before["stop"] > 0:
                of[index]["at_end"] = entry
        if before["cloud"] == after["cloud"] == "live":
            if after["left"] < before["left"]:
                explosions.append({"t": after["t"], "left": after["left"]})
            if after["countdown"] > before["countdown"]:
                checks.append(after["t"])
        for change in changed_hp:
            kind = "drops" if change["to"] is not None and change["from"] is not None \
                and change["to"] < change["from"] else "rises"
            hp[change["id"]][kind].append({"t": after["t"], "from": change["from"], "to": change["to"]})
    for ident, first, last in zip(watch, samples[0]["hp"] if samples else [None] * len(watch),
                                  samples[-1]["hp"] if samples else [None] * len(watch)):
        hp[ident].update(start=first, end=last)

    live = [s for s in samples if s["cloud"] == "live"]
    arrived = next((s["t"] for s in live if s["arrived"]), None)
    gone = next((s["t"] for s in samples if s["cloud"] == "gone"), None)
    # The cloud's own updates after its arrival: each changed its countdown, the last destroyed it.
    updates = [after["t"] for before, after in zip(samples, samples[1:])
               if before["cloud"] == "live" and before["arrived"] and
               (after["cloud"] == "gone" or (after["cloud"] == "live" and after["countdown"] != before["countdown"]))]
    count = len(explosions)
    if gone is not None and live and live[-1]["left"] == 1:
        # The check that leaves none destroys the cloud in the same update.
        explosions.append({"t": gone, "left": 0, "seen": "gone"})
        count += 1
    previous = arrived
    for explosion in explosions:
        if previous is not None:
            explosion["world_gap"] = explosion["t"] - previous
            explosion["active_gap"] = sum(1 for t in updates if previous < t <= explosion["t"])
        previous = explosion["t"]
    cloud = {"state": header["cloud"].get("state"), "id": header["cloud"].get("id"),
             "decoded": header["cloud"].get("decoded"), "resolved": header["cloud"].get("resolved"),
             "arrived": arrived, "gone": gone, "initial_left": live[0]["left"] if live else None,
             "interval": live[0]["interval"] if live else None, "explosions": explosions,
             "explosion_count": count, "checks": checks}
    if arrived is not None and gone is not None:
        cloud["lifetime"] = gone - arrived
        cloud["updates"] = len(updates)
        cloud["skipped_ticks"] = cloud["lifetime"] - cloud["updates"]
        cloud["stop_ticks"] = sum(max(0, min(gone, s["last"]) - max(arrived + 1, s["first"]) + 1) for s in stops)
        cloud["lifetime_outside_stops"] = cloud["lifetime"] - cloud["stop_ticks"]
    else:
        issues.append(f"no cloud followed from its arrival to its end (state {cloud['state']})")
    inside_cloud = sum(len(s["cloud_inside"]) for s in stops)
    inside_hits = sum(1 for s in stops for h in s["hp_inside"]
                      if h["from"] is not None and h["to"] is not None and h["to"] < h["from"])
    return {"name": header.get("name"), "caster": header.get("caster"), "watch": watch, "samples": len(samples),
            "cloud": cloud, "stops": stops, "hp": {str(k): v for k, v in hp.items()},
            "verdict": {"stops": len(stops), "cloud_changes_in_stop": inside_cloud, "hits_in_stop": inside_hits,
                        "frozen": bool(stops) and inside_cloud == 0},
            "issues": issues}


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
