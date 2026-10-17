"""Read-only compiler for a deliberately narrow potion-admission prototype.

Accepts explicit ITM bytes or a loose directory; prints JSON to stdout only.
No game discovery, KEY access, installation, resource patching or save access.
Only direct finite self effects with reviewed bonus semantics become owned.
Unsupported potential bonuses fail with a diagnostic before a manifest exists.
"""
from __future__ import annotations

import argparse
from collections import Counter
from collections.abc import Mapping
import hashlib
import json
from pathlib import Path
import re
import struct
import sys

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(0, str(SCRIPTS))
import audit_potion_payloads as audit


class ManifestError(ValueError):
    def __init__(self, code: str, context: str, detail: str):
        self.code, self.context = code, context
        super().__init__(f"{code}: {context}: {detail}")


PRESENTATION = {7, 50, 51, 132, 139, 142, 155, 174, 215}
HP_COSMETIC = {7, 142}
HARMFUL = {12, 24, 25, 38, 39, 40, 45, 74, 76, 80}
NATIVE_UNIQUE = {16, 48}
# Native constructors use no dice for these opcodes. The reviewed finite
# additive Apply paths modify only derived accumulators, keeping the original
# effect's matching fields intact. probe_native_potion_stats.py replays them
# through the old and refreshed deadlines; this is not live acceptance.
ADDITIVE_BONUSES = {6, 10, 15, 21, 22, 27, 28, 29, 30, 31, 33, 34, 35, 36, 37,
                    44, 49, 59, 73}
SKILL_BONUSES = {90, 91, 92, 275, 276, 277}
STAT_SETTERS = {6, 10, 15, 44, 49}
ANCHOR = re.compile(r"POTN\d\d\Z")
SCS_COPY = re.compile(r"DW#PTN(\d\d)\Z")


def canonical(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _signed16(value: int) -> int:
    """Classify the native operand without changing the raw fingerprint."""
    return (value + 0x8000) % 0x10000 - 0x8000


def _decoded_dword20(raw: bytes) -> int:
    # Shared DecodeEffect1DE3E7–1DE3F6 normalizes this exact V1 sentinel
    # before any opcode constructor. Direct CItem::GetAbilityEffect calls it
    # at1FB4B8. Predict runtime fields without modifying resource bytes.
    value = audit.u32(raw, 0x20)
    return 0 if value == 0xFFFFFFFF else value


def _name(name: str) -> str:
    if not isinstance(name, str) or not name.upper().endswith(".ITM"):
        raise ManifestError("INPUT", str(name), "explicit input must be an ITM resource name")
    stem = name[:-4]
    if (not 1 <= len(stem) <= 8 or not stem.isascii()
            or any(ord(c) < 33 or ord(c) > 126 or c in "\\/:." for c in stem)):
        raise ManifestError("INPUT", name, "invalid eight-byte resource identity")
    return stem.upper()


def _owned(effect: dict, context: str, *, hp_family: bool = False, validate_target: bool = True) -> bool:
    op, mode, amount = effect["opcode"], effect["parameter2"], effect["parameter1"]
    if validate_target and effect["target"] != 1:
        raise ManifestError("TARGET_CAPABILITY", context,
                            "transport prototype requires target 1 for every original effect")
    if op in audit.LINKS:
        raise ManifestError("LINK_CAPABILITY", context,
                            f"opcode {op} delivers a linked payload; direct-only compiler cannot classify/own it")
    if op >= 400:
        raise ManifestError("OPCODE_CAPABILITY", context, f"extension opcode {op} is not reviewed")
    timing, duration = effect["timing"], effect["duration"]
    if (op in PRESENTATION and not (op in HP_COSMETIC and hp_family)) or op in HARMFUL or op in {11, 17}:
        return False
    if op == 23 and effect["special"] == 0:
        # Apply1BA440 rewrites amount/mode to10/1 and sets Done before
        # setting base morale (unless panic). Preserve this native cure;
        # its stored finite/delayed timing does not make it a timed bonus.
        return False
    # Permanent/instant stat operations remain native and reusable.
    if timing in {1, 2, 4, 7, 8, 9} or (timing in {0, 10} and duration == 0):
        return False
    if timing not in {0, 10}:
        raise ManifestError("TIMING_CAPABILITY", context, f"timing {timing} needs a lifetime adapter")
    if op in HP_COSMETIC:
        return True  # Finite HP companion; never itself prolongs HP blocking.
    if op == 98:
        # Apply1BECC3 dispatches LOW16(mode). Mode2 copies LOW16(amount)
        # into the cache's heal WORD and sets interval1 (1BED12..1BED5A);
        # mode3 copies it into the interval WORD and heals1 (1BECFC..1BED10).
        # AIUpdate1A5E61 sign-extends heal amount; phase division/comparison
        # requires a positive signed16 interval. Keep both raw DWORD operands
        # in the descriptor/key: classification must not normalize resources.
        effective_mode, effective = mode % 65536, _signed16(amount)
        if effective_mode not in {2, 3}:
            raise ManifestError("OPCODE_CAPABILITY", context,
                                f"opcode 98 mode {mode} lacks the reviewed mode2/3 cache adapter")
        if effect["special"] != 0:
            raise ManifestError("SPECIAL_CAPABILITY", context,
                                "regeneration Special takes an additional native path outside the reviewed cache adapter")
        if effective_mode == 2 and effective <= 0:
            return False  # Native Heal17 receives zero/a negative amount; no healing bonus.
        if effective_mode == 3 and effective <= 0:
            raise ManifestError("AMOUNT_CAPABILITY", context,
                                "regeneration interval must be positive signed16 for the reviewed native phase/recovery arithmetic")
        if timing == 10 and duration > 0x7FFFFFFF:
            raise ManifestError("DURATION_CAPABILITY", context,
                                "regeneration cache countdown must fit positive signed32 ticks")
        # No immediate HP grant: regeneration alone uses safe refresh policy.
        # A containing HP/CON family retains its existing ignore-repeat policy.
        # Constructor1A16C0 UsesDice=false; ordinary _fields level guards apply.
        return True
    if op == 20:
        if mode == 0:
            # OnAddSpecific is a no-op in mode0; Apply and its native visual
            # message only set invisibility flags. Mode1 delivers another
            # effect from OnAddSpecific and requires separate provenance.
            return hp_family
        raise ManifestError("MODE_CAPABILITY", context,
                            "invisibility mode may copy/deliver a distinct effect; only ordinary mode0 is reviewed")
    if op == 23:
        raise ManifestError("MORALE_CAPABILITY", context,
                            "Special-nonzero morale can repeatedly change base morale; no stable timed-bonus policy")
    if op == 63:
        return hp_family  # Infravision is one derived bit; no first-use write.
    if op == 83:
        # Apply1B6DE0 appends raw mode; projectile consumers query unsigned16
        # IDs with non-consuming CObList::Find4076F0. Duplicate membership
        # cannot add protection capacity. Larger raw IDs never match.
        return hp_family and mode <= 65535
    if op in {86, 87, 88, 89}:
        if mode != 0:
            raise ManifestError("MODE_CAPABILITY", context,
                                "physical resistance setter/percentage requires separate polarity review")
        effective = _signed16(amount)
        # Finite ADD (86:1C1B38, 87:1C0F98, 88:1C1988, 89:1C17D8)
        # writes WORD before signed cap100. From any finite
        # native accumulator[-32768,100], 1..32767-100 is monotone and cannot
        # wrap. Larger positives can wrap at100; negatives can underflow at
        # -32768 and become a bonus. Do not silently label either harmless.
        if effective < 0 or effective > 32667:
            raise ManifestError("AMOUNT_CAPABILITY", context,
                                "native physical-resistance WORD addition can wrap and reverse benefit/harm polarity")
        return effective > 0
    if op == 106:
        if mode == 1:
            return hp_family  # Stable native [0,20] setter, skipped under panic.
        raise ManifestError("MODE_CAPABILITY", context,
                            "morale-break mode needs additive/percentage polarity review")
    if op == 120:
        # Apply1B6420 creates a weapon predicate; OnList1F9040 returns a
        # boolean without consuming entries. Even modes outside0..11 append
        # a zero descriptor (enchantment0), not a no-op. Preserve all native
        # operands; no potency/charge accumulation is caused by duplicates.
        if hp_family:
            raise ManifestError("HP_COMPANION_CAPABILITY", context,
                                "weapon immunity HP companion still needs complete package lifetime treatment")
        return False
    if op == 126:
        if mode in {1, 2}:
            if hp_family:
                raise ManifestError("HP_COMPANION_CAPABILITY", context,
                                    "movement setter HP ownership needs baseline/wrapping polarity policy")
            return False  # Fixed low8 speed or default-derived low16 percentage.
        if mode in {0, 5}:
            raise ManifestError("MODE_CAPABILITY", context,
                                "movement mode changes current speed cumulatively; no reviewed repeat adapter")
        return False  # Native switch only implements0/1/2/5.
    if op == 233:
        index = mode % 65536
        if not 89 <= index <= 134:
            return False  # Neither setter nor additive table has this slot.
        if mode >= 65536:
            raise ManifestError("MODE_CAPABILITY", context,
                                "additive proficiency consumes first-call state and derives parameter3; no stable adapter")
        return hp_family  # Stable raw32 derived proficiency-state setter.
    if op == 282:
        # A fixed derived scripting-state value, not an increment. Package
        # ownership does not assert that arbitrary states are positive alone.
        return hp_family and mode < 45
    if op == 102:
        if amount < 0:
            raise ManifestError("LEVEL_CAPABILITY", context,
                                "native spell-level immunity indexes before its table for negative amounts")
        return hp_family and amount <= 9
    if op in {101, 169, 267, 296}:
        if hp_family:
            raise ManifestError("HP_COMPANION_CAPABILITY", context,
                                "boolean immunity companion still needs HP expiry/rebuild and removal review")
        return False  # Native immunity lookup is boolean, with no consumed count.
    if op == 166:
        if mode == 0:
            # Apply1C1B70 adds signed32 amount to any signed16 MR baseline.
            # INT_MIN-(-32768) <= amount <= INT_MAX-32767 prevents wrap before
            # native [-128,127] clamping. This is an arithmetic capability
            # bound, not a requirement that modded MR use reference values.
            if not -2147450880 <= amount <= 2147450880:
                raise ManifestError("AMOUNT_CAPABILITY", context,
                                    "native signed32 addition can overflow with a signed16 MR baseline")
            return amount > 0
        if mode == 1:
            return hp_family and amount > 0  # Stable native setter clamps [-128,127].
        raise ManifestError("MODE_CAPABILITY", context, "MR mode is outside the reviewed additive/setter forms")
    if op in {0, 1}:
        # These native classes consume signed LOW16(parameter1), not its raw
        # dword sign. Keep raw fields in the fingerprint; this is classification
        # only. Source aliases with different raw encodings still need proof.
        effective = _signed16(amount)
        if op == 0:
            if mode in {0, 1, 2, 4, 8}:
                return effective > 0  # Native SUB from the AC accumulator.
            if mode == 16:
                return hp_family  # Native min(current signed AC, effective).
        elif mode == 0:
            # Native ShortToFloat: 1..5 whole APR, 6..10 half-step encodings;
            # negative encodings penalize, zero and magnitudes>10 add nothing.
            return 1 <= effective <= 10
        raise ManifestError("MODE_CAPABILITY", context,
                            f"opcode {op} mode {mode} lacks reviewed stable bonus semantics")
    if op in NATIVE_UNIQUE:
        if hp_family:
            raise ManifestError("HP_COMPANION_CAPABILITY", context,
                                f"finite native-unique opcode {op} still needs ownership in an HP-sensitive package")
        return False
    if op == 328:
        if effect["special"] != 0:
            # Native SetSpellState checks unsigned id<256, then sets one bit;
            # higher ids are no-ops. This is package companion ownership, not
            # an assertion that every state has a positive meaning in isolation.
            return hp_family and mode < 256
        raise ManifestError("STATE_CAPABILITY", context,
                            "spell/scripting-state semantics need a reviewed companion classification")
    if op in ADDITIVE_BONUSES:
        if mode == 0:
            return _signed16(amount) > 0
        if op == 30 and mode == 1:
            # Finite fire setter1C120D consumes signed LOW16 then clamps
            # [-128,127]. Keep its raw fingerprint and native adverse forms.
            return hp_family and _signed16(amount) > 0
        if op in STAT_SETTERS and mode in {1, 2}:
            return hp_family and (_signed16(amount) > 100 if mode == 2 else amount > 0)
        if op in {33, 34, 35, 36, 37} and mode == 3:
            return _signed16(amount) > 0
        raise ManifestError("MODE_CAPABILITY", context,
                            f"opcode {op} mode {mode} lacks reviewed stable bonus semantics")
    if op == 19 or op in SKILL_BONUSES:
        if mode == 0:
            # 275/276/277 sign-extend LOW16 into DWORD skill accumulators.
            # Classify nominal bonuses; uniqueness suppresses repeated gains,
            # not engine overflow in an aggregate assembled by other effects.
            return _signed16(amount) > 0
        if mode == 1:  # Native flat sets do not accumulate additively.
            return hp_family and (amount % 256 > 0 if op in {275, 276, 277} else amount > 0)
        if mode == 2:
            # Find Traps91 scales already-derived skill, unlike the other
            # reviewed base-derived percentages. Its repeats do accumulate.
            if op in {90, 91}:
                if not hp_family and op == 90:
                    return False  # Base-derived native setter, no repeat accumulation.
                # Finite90 multiplies signed32 by a base U8; finite91 by the
                # current derived I16. Guard the product before native /100.
                low, high = (-8421504, 8421504) if op == 90 else (-65535, 65536)
                if not low <= amount <= high:
                    raise ManifestError("AMOUNT_CAPABILITY", context,
                                        f"opcode {op} native signed32 percentage product can overflow")
                effective = amount
            else:
                effective = _signed16(amount)
            return effective > 100 and (hp_family or op == 91)
        raise ManifestError("MODE_CAPABILITY", context, f"opcode {op} mode {mode} is not a reviewed additive bonus")
    if op == 18:
        if mode not in {0, 2}:
            raise ManifestError("HP_MODE_CAPABILITY", context, f"HP mode {mode} is not reviewed")
        positive = amount > (100 if mode == 2 else 0)
        raw = bytes.fromhex(effect["raw_hex"])
        if positive and (audit.i32(raw, 0x1C) or _decoded_dword20(raw)):
            raise ManifestError("HP_DICE_CAPABILITY", context,
                                "opcode 18 mutates its amount when dice are used; no stable native fingerprint")
        return positive
    if op == 54:
        if mode == 0:
            return _signed16(amount) > 0
        if mode == 2:
            effective = _signed16(amount)
            if hp_family and effective < 0:
                raise ManifestError("BASELINE_CAPABILITY", context,
                                    "negative THAC0 percentage helps nonnegative base THAC0 but harms negative base THAC0")
            # Native signed8 base, signed16 multiplier, then [0,25] clamp.
            # [0,100] never exceeds the native100%-clamped control, including
            # negative baselines; that does not imply it improves raw THAC0<0.
            return 0 <= effective <= 100 if hp_family else 0 < effective < 100
        if mode == 1:
            return hp_family  # Every signed16 setter is native-clamped [0,25].
        raise ManifestError("MODE_CAPABILITY", context, f"THAC0 mode {mode} is not reviewed")
    raise ManifestError("OPCODE_CAPABILITY", context,
                        f"finite opcode {op} may supply an unreviewed cumulative bonus; no prototype adapter")


def _fields(effect: dict, ability: bytes, *, strict_resource: bool) -> dict:
    raw = bytes.fromhex(effect["raw_hex"])
    uses_dice = effect["opcode"] == 18
    if strict_resource and raw[0xD] & ~3:
        raise ManifestError("FLAGS_CAPABILITY", "effect flags",
                            "bits beyond dispel/resistance become native timing bits; no timing adapter")
    decoded_size = _decoded_dword20(raw)
    min_level = 0 if uses_dice else decoded_size
    max_level = 0 if uses_dice else audit.u32(raw, 0x1C)
    if strict_resource and min_level > 65535:
        raise ManifestError("LEVEL_CAPABILITY", "effect minimum level",
                            "native admission normalizes values over 65535; no fingerprint adapter")
    try:
        resource = raw[0x14:0x1C].split(b"\0", 1)[0].decode("ascii").upper()
    except UnicodeDecodeError as error:
        if strict_resource:
            raise ManifestError("FINGERPRINT_CAPABILITY", "effect resource",
                                "non-ASCII native operand cannot be represented by this bridge") from error
        resource = raw[0x14:0x1C].hex()  # preserved, unrelated native data only
    return dict(opcode=effect["opcode"], target=effect["target"], power=effect["power"],
                amount=effect["parameter1"], mode=effect["parameter2"], resource=resource,
                diceCount=audit.i32(raw, 0x1C) if uses_dice else 0,
                diceSize=(decoded_size + 2**31) % 2**32 - 2**31 if uses_dice else 0,
                minLevel=min_level, maxLevel=max_level,
                saveType=audit.u32(raw, 0x24), saveBonus=audit.i32(raw, 0x28),
                special=effect["special"], flags=raw[0xD],
                school=ability[0x17], secondary=ability[0x19],
                sourceFlags=audit.u32(ability, 0x26), probUpper=effect["probability1"],
                probLower=effect["probability2"], timing=effect["timing"], duration=effect["duration"])


def _stable(fields: dict) -> dict:
    """Only engine-derived bits may vary when identifying an active record."""
    stable = {key: value for key, value in fields.items()
              if key not in {"timing", "duration", "nativeSources"}}
    stable["flags"] &= ~8  # self-delivery ORs this bit; identification supplies bit31
    if stable["opcode"] == 18:
        stable["special"] &= ~1  # first-application marker changes in ApplyEffect
    return stable


def _transport_target(effect, ability, context):
    if effect["target"] == 1:
        return
    if effect["target"] == 2 and ability[0xC] == 5 and audit.u16(ability, 0x2A) == 1:
        # Pinned projectile1 uses base CProjectile and transfers the original
        # pointer. Runtime still MUST check actual vtable (EEex may replace the
        # class), and source/target equality. No generic projectile acceptance.
        return
    raise ManifestError("TARGET_CAPABILITY", context,
                        "needs direct target1 or target2 with self ability5/projectile1; other delivery routes are unreviewed")


def _unowned_link(effect, context, read_resource, *, hp_family, ancestors=(), nodes=None):
    """Prove a bounded branch has no policy-owned finite bonus; never rewrite it.

    A 177 child inherits the carrier's timing/duration. Other cast edges retain
    their native child's lifetime. Conditions are not assumed false: every
    potential branch is examined. Shared unowned resources need no dose identity.
    """
    if read_resource is None:
        raise ManifestError("LINK_CAPABILITY", context, "linked payload requires an explicit read-only resource resolver")
    if nodes is None:
        nodes = set()
    child = effect["resource"] + "." + audit.LINKS[effect["opcode"]]
    if not effect["resource"]:
        raise ManifestError("LINK_CAPABILITY", context, "implicit/empty child cannot be proven unowned")
    if child in ancestors:
        raise ManifestError("LINK_CYCLE", context, " -> ".join(ancestors + (child,)))
    if len(ancestors) >= 16 or (child not in nodes and len(nodes) >= 256):
        raise ManifestError("LINK_BOUNDS", context, "linked proof exceeds depth16 or node256 bound")
    nodes.add(child)
    try:
        node = audit.parse_resource(child, read_resource(child))
    except (OSError, ValueError, KeyError) as exc:
        raise ManifestError("LINK_RESOURCE", context, f"cannot inspect {child}: {exc}") from exc
    removals = []
    for part in node["slices"]:
        if effect["opcode"] == 146 and effect["parameter2"] == 1 and part["kind"] == "casting":
            continue  # This proven native mode1 route omits both casting-effect passes.
        for ordinal, original in enumerate(part["effects"]):
            candidate = dict(original)
            if effect["opcode"] == 177:
                candidate.update(timing=effect["timing"], duration=effect["duration"])
            where = f"{context} -> {child} {part['kind']} effect {ordinal}"
            if candidate["opcode"] in audit.LINKS:
                removals.extend(_unowned_link(candidate, where, read_resource, hp_family=hp_family,
                                              ancestors=ancestors + (child,), nodes=nodes))
            elif (candidate["opcode"] == 318 and candidate["timing"] in {0, 10}
                  and candidate["duration"] > 0 and candidate["resource"]):
                if hp_family:
                    raise ManifestError("HP_COMPANION_CAPABILITY", where,
                                        "conditional resource immunity has no HP package ownership policy")
                # Neither predicate outcome adds capacity: success registers
                # boolean resource immunity, failure sets Done. Preserve the
                # native predicate/table meaning and the entire original graph.
                # The family check below must still reject a guard that would
                # block the owned source's later refresh before admission.
            elif _owned(candidate, where, hp_family=hp_family or candidate["opcode"] in {10, 18},
                        validate_target=False):
                raise ManifestError("LINK_OWNED_CAPABILITY", where,
                                    "finite child bonus needs native parent/child dose provenance and source matching")
            if candidate["opcode"] == 321 and candidate["resource"]:
                removals.append({"source": candidate["resource"], "context": where})
            if candidate["opcode"] == 318 and candidate["resource"]:
                removals.append({"source": candidate["resource"], "context": where,
                                 "kind": "resource_guard"})
    return removals


def _register(result, effect, fields, context):
    """Register one owned descriptor; SPL resource names are provenance variants.

    Native source type remains in the logical signature, so item and spell
    originals never collide. Identical children through two declared SPLs can
    share a policy key without discarding either native source identity.
    """
    stable = _stable(fields)
    lifetime = {"timing": fields["timing"], "duration": fields["duration"]}
    key = hashlib.sha256(canonical(dict(fields=stable, lifetime=lifetime)).encode("ascii")).hexdigest()
    old = result["records"].get(key)
    if old and "nativeSources" in fields:
        old["nativeSources"].update(fields["nativeSources"])
    else:
        result["records"][key] = fields
    result["keys"][key] = True
    result["owned_ops"].add(effect["opcode"])
    if effect["opcode"] in HP_COSMETIC:
        result["non_blocking_keys"][key] = True
    result["entries"].append(dict(base=canonical(stable), fields=stable,
        lifetime=canonical(lifetime), special=effect["special"],
        flags=bytes.fromhex(effect["raw_hex"])[0xD], context=context))
    return key


def _add_quota(quotas, key, count, context):
    """Keep every intermediate count within Core's unsigned32 quota domain."""
    maximum = 0xFFFFFFFF
    previous = quotas.get(key, 0)
    if (type(count) is not int or not 1 <= count <= maximum
            or type(previous) is not int or not 0 <= previous <= maximum
            or count > maximum - previous):
        raise ManifestError("QUOTA_CAPABILITY", context,
                            "expanded effect quota exceeds the exact unsigned32 Core capacity")
    # Each original route is merged separately. Even a u16-sized route list
    # therefore never accumulates an oversized intermediate or Lua rounding.
    quotas[key] = previous + count


def _add_quotas(quotas, incoming, context):
    for key, count in incoming.items():
        _add_quota(quotas, key, count, context)


def _call_graph(effect, context, read_resource, result, *, hp_family, ancestors=()):
    """Compile the proven original146/mode1 route; globals are native-undelivered.

    Header selection stays native. The registry records every header's actual
    ordinal map, and reserves the maximum quota for each possible child key.
    Existing resolvability checks still diagnose lifetime-only ambiguities;
    varying cumulative potency needs a separate policy, not a guessed match.
    """
    if effect["opcode"] != 146 or effect["parameter2"] != 1:
        raise ManifestError("LINK_OWNED_CAPABILITY", context,
                            "owned child requires original opcode146 mode1 transport")
    # Resolve1E8516–1E8649 defers raw3/4/5 and absolute6/7/8. Their later
    # Apply can run after the original AddEffect message frame has retired;
    # Lineage.parentQueued cannot recover that dose from messages.top(parent).
    # Other raw-byte timings fall through Apply immediately;146 marks Done.
    if 3 <= effect["timing"] <= 8:
        raise ManifestError("LINK_TIMING_CAPABILITY", context,
                            "delayed owned carrier can cast after its original dose delivery frame is gone")
    name = effect["resource"]
    if not name or name in ancestors:
        raise ManifestError("LINK_CYCLE", context, "empty or cyclic owned spell route")
    if len(ancestors) >= 16 or (name not in result["calls"] and len(result["calls"]) >= 256):
        raise ManifestError("LINK_BOUNDS", context, "owned spell graph exceeds depth16/node256 inspection bound")
    if name in result["calls"]:
        return name
    try:
        data = read_resource(name + ".SPL")
        node = audit.parse_resource(name + ".SPL", data)
    except (OSError, ValueError, KeyError) as exc:
        raise ManifestError("LINK_RESOURCE", context, f"cannot inspect {name}.SPL: {exc}") from exc
    call = dict(resource=name, abilities={}, quotas={}, semantic=[], baseSemantic=[])
    # Publish only within this not-yet-returned compilation. Ancestor checks
    # still reject a recursive reference before the cache can conceal it.
    result["calls"][name] = call
    for part in node["slices"]:
        if not part["kind"].startswith("ability:"):
            continue
        header = bytes.fromhex(part["raw_ability_hex"])
        ability_index = part["kind"].split(":", 1)[1]
        children, carriers, quotas, signatures, base_signatures = {}, {}, Counter(), [], []
        for ordinal, candidate in enumerate(part["effects"]):
            where = f"{context} -> {name}.SPL {part['kind']} effect {ordinal}"
            linked = None
            if candidate["opcode"] in audit.LINKS:
                try:
                    result["removals"].extend(_unowned_link(candidate, where, read_resource, hp_family=hp_family))
                    owned = False
                except ManifestError as exc:
                    if exc.code != "LINK_OWNED_CAPABILITY":
                        raise
                    linked = _call_graph(candidate, where, read_resource, result,
                                         hp_family=hp_family, ancestors=ancestors + (name,))
                    owned = False
            else:
                owned = _owned(candidate, where, hp_family=hp_family, validate_target=False)
            fields = _fields(candidate, bytes(56), strict_resource=owned or linked is not None)
            fields.update(school=data[0x25], secondary=data[0x27], sourceFlags=audit.u32(data, 0x18),
                          nativeSourceType=1, nativeSources={name: True})
            if (owned or linked) and candidate["target"] not in {1, 2}:
                raise ManifestError("TARGET_CAPABILITY", where,
                                    "owned mode1 child requires target1/2 and runtime drinker identity validation")
            if owned and candidate["timing"] == 0 and candidate["duration"] > 0x08888888:
                raise ManifestError("DURATION_CAPABILITY", where, "seconds duration exceeds native conversion clamp")
            if candidate["opcode"] in {10, 18}:
                result["hp"] |= _owned(candidate, where, hp_family=True, validate_target=False)
            if candidate["opcode"] == 321 and fields["resource"]:
                result["removals"].append({"source": fields["resource"], "context": where})
            stable = _stable(fields)
            descriptor = dict(fields=stable, lifetime={"timing": fields["timing"], "duration": fields["duration"]})
            base_descriptor = dict(fields=stable)
            if linked:
                descriptor["fields"] = dict(stable, resource="")
                descriptor["linked"] = result["calls"][linked]["semantic"]
                base_descriptor = dict(fields=dict(stable, resource=""),
                                       linked=result["calls"][linked]["baseSemantic"])
                carriers[str(ordinal)] = dict(call=linked, fields=fields)
                _add_quotas(quotas, result["calls"][linked]["quotas"], where)
            if candidate["opcode"] not in PRESENTATION:
                signatures.append(canonical(descriptor))
                base_signatures.append(canonical(base_descriptor))
            if owned:
                key = _register(result, candidate, fields, where)
                children[str(ordinal)] = key
                _add_quota(quotas, key, 1, where)
            else:
                children[str(ordinal)] = False
                result["other_native_buff"] |= candidate["opcode"] in NATIVE_UNIQUE
        call["abilities"][ability_index] = dict(count=len(part["effects"]), effects=children,
            carriers=carriers, quotas=dict(sorted(quotas.items())), minimumLevel=audit.u16(header, 0x10))
        # These are cast-graph semantics, not extra CGameEffect fields. SPL
        # type selects native caster/duration rules. GetCasterLevel's mage
        # branch reads the LOW16 spell level through CSpell::GetSpellLevel.
        metadata = dict(spellType=audit.u16(data, 0x1C), spellLevel=audit.u16(data, 0x34),
                        minimumLevel=audit.u16(header, 0x10))
        call["semantic"].append(dict(metadata, effects=sorted(signatures)))
        call["baseSemantic"].append(dict(metadata, effects=sorted(base_signatures)))
        for key, count in quotas.items():
            call["quotas"][key] = max(call["quotas"].get(key, 0), count)
    # Different selected headers must not grant an additional cumulative
    # descriptor while an earlier header's potency is still present. Matching
    # duplicate counts/order are valid; selecting different potency is not yet
    # a proven refresh operation on existing native originals.
    owned_sets = {tuple(sorted(header["quotas"])) for header in call["abilities"].values()}
    if len(owned_sets) > 1:
        raise ManifestError("LINK_VARIANT_CAPABILITY", context,
                            "selected headers have different owned bonus descriptors; refresh potency policy is unresolved")
    return name


def _parse(name: str, data: bytes, *, hp_family: bool = False, read_resource=None) -> dict | None:
    try:
        audit.checked(data, 0, 0x1E, "item category")
        if audit.u16(data, 0x1C) != 9:
            return None
        node = audit.parse_resource(name + ".ITM", data)
    except (ValueError, struct.error) as error:
        raise ManifestError("FORMAT", name, str(error)) from error
    result = dict(name=name, keys={}, non_blocking_keys={}, records={}, abilities={}, calls={}, signatures=[], base_signatures=[],
                  entries=[], hp=False, owned_ops=set(), other_native_buff=False, removals=[])
    for part in node["slices"]:
        context = f"{name} {part['kind']}"
        ability = bytes.fromhex(part.get("raw_ability_hex", "00" * 56))
        emitted, carriers, quotas, signature, base_signature = {}, {}, Counter(), [], []
        for ordinal, effect in enumerate(part["effects"]):
            where = f"{context} effect {ordinal}"
            linked = None
            if effect["opcode"] in audit.LINKS:
                try:
                    result["removals"].extend(_unowned_link(effect, where, read_resource, hp_family=hp_family))
                except ManifestError as exc:
                    if exc.code != "LINK_OWNED_CAPABILITY":
                        raise
                    linked = _call_graph(effect, where, read_resource, result, hp_family=hp_family)
                owned = False
            else:
                owned = _owned(effect, where, hp_family=hp_family, validate_target=False)
            if owned or linked:
                _transport_target(effect, ability, where)
            if owned and effect["timing"] == 0 and effect["duration"] > 0x08888888:
                raise ManifestError("DURATION_CAPABILITY", where,
                                    "seconds duration exceeds native conversion clamp")
            if part["kind"] == "equipped" and (owned or linked):
                raise ManifestError("EQUIPPED_CAPABILITY", where,
                                    "equipped bonus has no item-use dose boundary")
            # CON can trigger current/max-HP adjustments in CheckStatsChange;
            # its family follows the same no-refresh repeat policy as HP18.
            result["hp"] |= (effect["opcode"] in {10, 18} and
                             _owned(effect, where, hp_family=True, validate_target=False))
            fields = _fields(effect, ability, strict_resource=owned or linked is not None)
            if effect["opcode"] == 321 and fields["resource"]:
                result["removals"].append({"source": fields["resource"], "context": where})
            stable = _stable(fields)
            lifetime = {"timing": effect["timing"], "duration": effect["duration"]}
            descriptor = dict(fields=stable, lifetime=lifetime)
            base_descriptor = dict(fields=stable)
            if linked:
                descriptor["fields"] = dict(stable, resource="")
                descriptor["linked"] = result["calls"][linked]["semantic"]
                base_descriptor = dict(fields=dict(stable, resource=""),
                                       linked=result["calls"][linked]["baseSemantic"])
                carriers[str(ordinal)] = dict(call=linked, fields=fields)
                _add_quotas(quotas, result["calls"][linked]["quotas"], where)
            if effect["opcode"] not in PRESENTATION:
                signature.append(canonical(descriptor))
                base_signature.append(canonical(base_descriptor))
            if not owned:
                emitted[str(ordinal)] = False
                result["other_native_buff"] |= effect["opcode"] in NATIVE_UNIQUE
                continue
            key = _register(result, effect, fields, where)
            emitted[str(ordinal)] = key
            _add_quota(quotas, key, 1, where)
        if part["kind"] != "equipped":
            index = part["kind"].split(":", 1)[1]
            result["abilities"][index] = dict(quotas=dict(sorted(quotas.items())), effects=emitted,
                                               count=len(part["effects"]))
            if carriers:
                result["abilities"][index]["carriers"] = carriers
            result["signatures"].append(tuple(sorted(signature)))
            result["base_signatures"].append(tuple(sorted(base_signature)))
    # Equivalent/reordered alternative abilities do not create another type.
    result["signature"] = tuple(sorted(set(result.pop("signatures"))))
    result["base_signature"] = tuple(sorted(set(result.pop("base_signatures"))))
    return result


def _check_resolvable(items: list[dict], label: str) -> None:
    seen, variants = {}, {}
    for item in items:
        for entry in item["entries"]:
            old = seen.get(entry["base"])
            if old and old["lifetime"] != entry["lifetime"]:
                raise ManifestError("DURATION_AMBIGUITY", label,
                                    f"{old['context']} and {entry['context']} differ only in original lifetime; "
                                    "active native effects do not retain that descriptor")
            if old and old["special"] != entry["special"]:
                raise ManifestError("SPECIAL_AMBIGUITY", label,
                                    f"{old['context']} and {entry['context']} collide after opcode18 special-bit0 normalization")
            if old and old["flags"] != entry["flags"]:
                raise ManifestError("FLAGS_AMBIGUITY", label,
                                    f"{old['context']} and {entry['context']} collide after native self flag normalization")
            seen[entry["base"]] = entry
            fields = entry["fields"]
            bonuses = {fields["saveBonus"]}
            if fields["school"]:
                bonuses.add((fields["saveBonus"] - 2 + 2**31) % 2**32 - 2**31)
            for bonus in bonuses:
                variant = canonical(dict(fields, saveBonus=bonus))
                previous = variants.get(variant)
                if previous and previous["base"] != entry["base"]:
                    raise ManifestError("SPECIALIST_AMBIGUITY", label,
                                        f"{previous['context']} and {entry['context']} overlap under specialist save-bonus adjustment")
                variants[variant] = entry


def build_manifest(inputs: Mapping[str, bytes], policy: str = "unique", *, read_resource=None) -> dict:
    """Compile explicit inputs without mutating them; errors return no partial manifest."""
    if policy not in {"unique", "except_genius"}:
        raise ManifestError("POLICY", str(policy), "expected unique or except_genius")
    if not isinstance(inputs, Mapping):
        raise ManifestError("INPUT", "resources", "expected name-to-bytes mapping")
    items, identities, originals = {}, set(), {}
    for filename, value in sorted(inputs.items()):
        name = _name(filename)
        if name in identities:
            raise ManifestError("INPUT", name, "duplicate case-insensitive resource identity")
        identities.add(name)
        if not isinstance(value, (bytes, bytearray, memoryview)):
            raise ManifestError("INPUT", name, "resource content must be bytes")
        item = _parse(name, bytes(value), read_resource=read_resource)
        if item:
            _check_resolvable([item], name)
            items[name] = item
            originals[name] = bytes(value)
    family_of = {name: name for name in items}
    anchors = {name: item for name, item in items.items() if ANCHOR.fullmatch(name)}
    for name, item in items.items():
        scs = SCS_COPY.fullmatch(name)
        if scs:
            anchor = "POTN" + scs.group(1)
            if anchor not in items:
                raise ManifestError("PROVENANCE", name, f"canonical {anchor} input is required to resolve this SCS family")
            candidate = items[anchor]
            if not set(item["keys"]).issubset(candidate["keys"]):
                raise ManifestError("PROVENANCE", name,
                                    f"owned payload is not a subset of {anchor}; the filename alone cannot prove family")
            if not candidate["hp"] and set(item["keys"]) != set(candidate["keys"]):
                raise ManifestError("PAYLOAD_CAPABILITY", name,
                                    "partial safe-family payload needs a policy for unmatched active bonuses")
            family_of[name] = anchor
        elif name not in anchors and (item["keys"] or item["hp"]):
            matches = [a for a, candidate in anchors.items() if candidate["signature"] == item["signature"]]
            if len(matches) > 1:
                raise ManifestError("IDENTITY_AMBIGUITY", name, "matches distinct canonical potion types: " + ", ".join(matches))
            if matches:
                family_of[name] = matches[0]
            else:
                possible = [a for a, candidate in anchors.items()
                            if candidate["base_signature"] == item["base_signature"]]
                if possible:
                    raise ManifestError("DURATION_AMBIGUITY", name,
                                        "otherwise identical to " + ", ".join(possible) + " but original lifetimes differ")
    unknown = [item for name, item in items.items()
               if (item["keys"] or item["hp"]) and family_of[name] == name and name not in anchors]
    for index, item in enumerate(unknown):
        for other in unknown[:index]:
            if item["base_signature"] == other["base_signature"]:
                code = "IDENTITY_AMBIGUITY" if item["signature"] == other["signature"] else "DURATION_AMBIGUITY"
                raise ManifestError(code, item["name"] + ", " + other["name"],
                                    "copy-versus-distinct-type identity has no canonical/provenance anchor")
    groups = {}
    for name, family in family_of.items():
        groups.setdefault(family, []).append(items[name])
    families, sources = {}, {}
    for family, members in sorted(groups.items()):
        hp_family = any(item["hp"] for item in members)
        if hp_family:
            # Identity/provenance is resolved before final ownership. An alias
            # without HP18/CON10 still inherits the canonical package's policy.
            members = [_parse(item["name"], originals[item["name"]], hp_family=True,
                              read_resource=read_resource) for item in members]
            canonical_member = next((item for item in members if item["name"] == family), None)
            if canonical_member:
                for member in members:
                    gameplay_keys = set(member["keys"]) - set(member["non_blocking_keys"])
                    if SCS_COPY.fullmatch(member["name"]) and not gameplay_keys.issubset(canonical_member["keys"]):
                        raise ManifestError("PROVENANCE", member["name"],
                                            "HP-package companion differs from the canonical payload after ownership resolution")
        _check_resolvable(members, family)
        if any(item["keys"] for item in members):
            member_names = {item["name"] for item in members}
            for member in members:
                for record in member["records"].values():
                    member_names.update(record.get("nativeSources", {}))
            for item in members:
                for removal in item["removals"]:
                    if removal["source"] in member_names:
                        if removal.get("kind") == "resource_guard":
                            raise ManifestError("RESOURCE_GUARD_CAPABILITY", removal["context"],
                                                "native resource immunity can reject this family's repeat before refresh admission; "
                                                "guard policy must be explicit")
                        raise ManifestError("REMOVAL_CAPABILITY", removal["context"],
                                            "native source removal can destroy this family's active bonuses before admission; "
                                            "cross-alias removal policy needs an adapter")
        anchor = items.get(family)
        genius = bool(family == "POTN29" and anchor and anchor["owned_ops"] == {19}
                      and not anchor["other_native_buff"] and not anchor["hp"])
        families[family] = dict(hp=hp_family, genius=genius)
        for item in members:
            sources[item["name"]] = dict(family=family, keys=dict(sorted(item["keys"].items())),
                                         nonBlockingKeys=dict(sorted(item["non_blocking_keys"].items())),
                                         records=dict(sorted(item["records"].items())), abilities=item["abilities"])
            if item["calls"]:
                sources[item["name"]]["calls"] = {name: {key: call[key] for key in ("resource", "abilities", "quotas")}
                                                   for name, call in sorted(item["calls"].items())}
    return dict(policy=policy, families=families, sources=dict(sorted(sources.items())))


def read_loose(directory: Path) -> dict[str, bytes]:
    """Read only direct ITM children of the explicitly supplied directory."""
    directory = Path(directory)
    if not directory.is_dir():
        raise ManifestError("INPUT", str(directory), "loose resource directory does not exist")
    resources = {}
    for path in sorted(directory.iterdir()):
        if path.is_file() and path.suffix.upper() == ".ITM":
            name = path.name.upper()
            if name in resources:
                raise ManifestError("INPUT", name, "duplicate case-insensitive loose resource")
            resources[name] = path.read_bytes()
    return resources


def lua_manifest(value) -> str:
    """Serialize only the compiler's JSON-shaped schema, with Lua-safe strings."""
    def encode(item):
        if isinstance(item, bool):
            return "true" if item else "false"
        if isinstance(item, str):
            escaped = []
            for byte in item.encode("utf-8"):
                if byte == 34:
                    escaped.append('\\"')
                elif byte == 92:
                    escaped.append("\\\\")
                elif 32 <= byte <= 126:
                    escaped.append(chr(byte))
                else:
                    escaped.append(f"\\{byte:03d}")
            return '"' + "".join(escaped) + '"'
        if isinstance(item, int):
            return str(item)
        if isinstance(item, dict):
            return "{" + ",".join("[" + encode(key) + "]=" + encode(val)
                                    for key, val in sorted(item.items())) + "}"
        raise TypeError(f"unsupported manifest value {type(item).__name__}")
    return "return " + encode(value) + "\n"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--resources", type=Path, required=True)
    parser.add_argument("--policy", choices=("unique", "except_genius"), default="unique")
    parser.add_argument("--format", choices=("json", "lua"), default="json")
    args = parser.parse_args(argv)
    try:
        store = audit.ResourceStore(args.resources, game=False)
        result = build_manifest(read_loose(args.resources), args.policy, read_resource=store.read)
    except (ManifestError, OSError) as error:
        print(str(error), file=sys.stderr)
        return 2
    print(lua_manifest(result) if args.format == "lua" else json.dumps(result, indent=2, sort_keys=True), end="\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
