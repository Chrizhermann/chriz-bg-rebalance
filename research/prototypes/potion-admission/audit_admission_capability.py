"""Read-only captured-resource capability audit for the ORIGINAL-effect prototype.

This compiles current bytes, inventories bounded linked graphs and replays
canonical/SCS orders through the current Lua core. It does not install anything,
run a game, execute generated hooks, or claim live/native transport acceptance.
No proprietary resource bytes are emitted. Output is JSON on stdout only.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import sys

import build_manifest as compiler

audit = compiler.audit
ROOT = Path(__file__).resolve().parent


def error(error):
    return {"code": getattr(error, "code", type(error).__name__), "detail": str(error)}


def replay_order(manifest, first, second, ability_a="0", ability_b="0"):
    """Actual Lua core; assumes native admission succeeded for each owned record.

    Never treats this as CheckAdd/reader/transport evidence. A missing Lupa is
    an explicit unavailable result, not a passing or skipped acceptance case.
    """
    if any(manifest["sources"][name].get("calls") for name in (first, second)):
        return {"status": "not_replayed", "code": "LINKED_REPLAY_CAPABILITY",
                "detail": "this direct-record core harness does not execute the linked call registry"}
    try:
        from lupa import LuaRuntime
    except ImportError as exc:
        return {"status": "unavailable", "detail": str(exc)}
    lua = LuaRuntime(unpack_returned_tuples=True)
    core = lua.execute((ROOT / "CBRPQCore.lua").read_text(encoding="utf-8"))
    m = lua.execute(compiler.lua_manifest(manifest))
    run = lua.eval("""function(core, manifest, first, second, a, b)
        local active, events = {}, {}
        for dose, sourceName in ipairs({first,second}) do
            local source = assert(manifest.sources[sourceName])
            local ability = assert(source.abilities[dose==1 and a or b])
            local state = core.newDose({}, source.family, ability.quotas)
            local now = dose==1 and 1000 or 1100
            for ordinal=0,ability.count-1 do
                local key = ability.effects[tostring(ordinal)]
                if key ~= false then
                    local expected = source.records[key]
                    local object = {m_duration=expected.duration}
                    local incoming = {object=object,sourceType=2,source=sourceName,
                        key=key,timing=expected.timing,expiry=expected.duration,done=false}
                    for _,r in ipairs(active) do r.expiry=r.object.m_duration end
                    local plan=core.plan(incoming,active,manifest,now,state)
                    local allow
                    allow,state=core.commit(plan)
                    events[#events+1]={dose=dose,source=sourceName,opcode=expected.opcode,
                        ordinal=ordinal,allow=allow,reason=plan.reason,writes=#plan.refresh}
                    if allow then
                        object.m_duration=now+expected.duration*(expected.timing==0 and 15 or 1)
                        active[#active+1]={object=object,sourceType=2,source=sourceName,
                            key=key,timing=4096,expiry=object.m_duration,done=false}
                    end
                end
            end
        end
        return events,#active
    end""")
    try:
        events, count = run(core, m, first, second, ability_a, ability_b)
        return {"status": "passed" if len(events) else "native_only", "active_record_count": count,
                "events": [{key: value for key, value in event.items()} for event in events.values()]}
    except Exception as exc:
        return {"status": "failed", "detail": str(exc)}


def inventory(names, read, *, max_depth=16, max_nodes=256, replay=True):
    graph = audit.audit(names, read, max_depth=max_depth, max_nodes=max_nodes)
    rows, inputs, compilable = [], {}, {}
    graph_consumers = defaultdict(set)
    for item in graph["potions"]:
        inputs[item["resource"]] = read(item["resource"])
        for name in item["nodes"]:
            if name != item["resource"]:
                graph_consumers[name].add(item["resource"])
    for item in graph["potions"]:
        name = item["resource"]
        source = name[:-4]
        row = {"resource": name, "sha256": hashlib.sha256(inputs[name]).hexdigest(),
               "graph_incomplete": item["incomplete"], "graph_diagnostics": item["diagnostics"],
               "links": item["edges"], "nodes": {n: v["sha256"] for n, v in item["nodes"].items()},
               "direct_diagnostics": [], "ordered_abilities": []}
        node = item["nodes"].get(name)
        if node:
            for part in node["slices"]:
                ability = bytes.fromhex(part.get("raw_ability_hex", "00" * 56))
                records = []
                for ordinal, effect in enumerate(part["effects"]):
                    owned = False
                    try:
                        context = f"{name} {part['kind']} effect {ordinal}"
                        if effect["opcode"] in audit.LINKS:
                            compiler._unowned_link(effect, context, read, hp_family=False)
                        else:
                            owned = compiler._owned(effect, context, validate_target=False)
                        if owned:
                            compiler._transport_target(effect, ability, context)
                            compiler._fields(effect, ability, strict_resource=True)
                    except compiler.ManifestError as exc:
                        row["direct_diagnostics"].append(dict(error(exc), slice=part["kind"],
                                                                ordinal=ordinal, opcode=effect["opcode"]))
                    records.append({k: effect[k] for k in ("opcode", "target", "parameter1", "parameter2",
                                                           "timing", "duration", "special", "resource")})
                row["ordered_abilities"].append({"slice": part["kind"], "effects": records,
                                                 "ability_type": ability[0], "ability_target": ability[0xC],
                                                 "projectile": audit.u16(ability, 0x2A)})
        subset = {name: inputs[name]}
        scs = compiler.SCS_COPY.fullmatch(source)
        if scs and "POTN" + scs.group(1) + ".ITM" in inputs:
            anchor = "POTN" + scs.group(1) + ".ITM"
            subset[anchor] = inputs[anchor]
        try:
            manifest = compiler.build_manifest(subset, read_resource=read)
            entry = manifest["sources"][source]
            row["owned_transport"] = sorted({"linked" if record.get("nativeSourceType") == 1 else "direct"
                                             for record in entry["records"].values()})
            row["status"] = ("linked_owned" if "linked" in row["owned_transport"] else
                             "direct_owned" if entry["keys"] else "native_only")
            row["owned_keys"] = len(entry["keys"])
            row["family"] = entry["family"]
            row["family_policy"] = manifest["families"][entry["family"]]
            compilable[name] = inputs[name]
        except (compiler.ManifestError, KeyError) as exc:
            row["status"], row["compiler_error"] = "unsupported", error(exc)
        rows.append(row)
    status_counts = dict(Counter(row["status"] for row in rows))
    # The legacy unowned-link probe can reject a branch the complete compiler
    # now proves and registers. Do not count that as missing capability when
    # the authoritative full source compilation succeeds.
    missing = Counter((d["code"], d["opcode"]) for row in rows if row["status"] == "unsupported"
                      for d in row["direct_diagnostics"])
    global_checks = {}
    for label, subset in (("whole_profile", inputs), ("locally_compilable_subset", compilable)):
        try:
            manifest = compiler.build_manifest(subset, read_resource=read)
            global_checks[label] = {"status": "passed", "sources": len(manifest["sources"])}
        except compiler.ManifestError as exc:
            global_checks[label] = dict(status="unsupported", **error(exc))
    orders = []
    for name in sorted(inputs):
        scs = compiler.SCS_COPY.fullmatch(name[:-4])
        if not scs:
            continue
        anchor = "POTN" + scs.group(1) + ".ITM"
        if anchor not in inputs:
            continue
        pair = {anchor: inputs[anchor], name: inputs[name]}
        try:
            manifest = compiler.build_manifest(pair, read_resource=read)
        except compiler.ManifestError as exc:
            orders.append({"canonical": anchor, "alias": name, "status": "unsupported", **error(exc)})
            continue
        for policy in ("unique", "except_genius"):
            manifest["policy"] = policy
            for first, second in ((anchor[:-4], name[:-4]), (name[:-4], anchor[:-4])):
                for a in manifest["sources"][first]["abilities"]:
                    for b in manifest["sources"][second]["abilities"]:
                        result = replay_order(manifest, first, second, a, b) if replay else {"status": "not_requested"}
                        orders.append({"policy": policy, "first": first, "second": second,
                                       "first_ability": a, "second_ability": b, **result})
    return {"scope": "current compiler plus direct-only Lua core replay; linked registry is compile evidence only",
            "compiler_sha256": hashlib.sha256((ROOT / "build_manifest.py").read_bytes()).hexdigest(),
            "core_sha256": hashlib.sha256((ROOT / "CBRPQCore.lua").read_bytes()).hexdigest(),
            "counts": status_counts, "category9_count": len(rows), "global_checks": global_checks,
            "missing_direct_adapters": [{"code": code, "opcode": op, "records": count}
                                        for (code, op), count in sorted(missing.items())],
            "shared_linked_resources": {name: sorted(owners) for name, owners in sorted(graph_consumers.items())
                                        if len(owners) > 1},
            "canonical_scs_orders": orders, "potions": rows,
            "graph_diagnostics": graph["diagnostics"],
            "limitations": ["All candidate effects in core replays are assumed natively accepted.",
                            "Local compile success does not prove profile-wide identity or live transport acceptance.",
                            "Linked ownership is a compiler registry result; linked sources are explicitly not replayed by this direct-record harness.",
                            "This direct-only replay tool does not exercise the separate connected Runtime/Lab or establish linked player coverage.",
                            "Shared consumers outside potion graphs are not enumerated.",
                            "No game, installer, resource writes, saves, or generated assembly execution."]}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--game-root", type=Path)
    group.add_argument("--resources", type=Path)
    parser.add_argument("--no-replay", action="store_true")
    parser.add_argument("--max-depth", type=int, default=16)
    parser.add_argument("--max-nodes", type=int, default=256)
    args = parser.parse_args(argv)
    store = audit.ResourceStore(args.game_root or args.resources, game=args.game_root is not None)
    result = inventory(store.names(), store.read, max_depth=args.max_depth, max_nodes=args.max_nodes,
                       replay=not args.no_replay)
    result["input"] = str(args.game_root or args.resources)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
