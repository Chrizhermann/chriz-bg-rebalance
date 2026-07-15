from __future__ import annotations

import dataclasses
import hashlib
import re
import shutil
import struct
import subprocess
import tempfile
import unittest
from pathlib import Path

from tests.ie_formats import (
    EffV2,
    IdsFile,
    SplAbility,
    SplEffect,
    SplFile,
    TwoDA,
    canonical_resource_tree,
    make_spl,
    read_eff_v2,
    read_ids,
    read_spl,
    read_2da,
    spell_resref,
    write_ids,
    write_spl,
    write_2da,
)


ROOT = Path(__file__).resolve().parents[1]
WEIDU = ROOT / "weidu.exe"
HARNESS = ROOT / "tests" / "weidu" / "tempus_holy_power_harness.tp2"
PRODUCTION_TPA = ROOT / "chriz-bg-rebalance" / "lib" / "tempus_holy_power.tpa"
SETUP_TP2 = ROOT / "setup-chriz-bg-rebalance.tp2"
ORIGINALS = ROOT / "research" / "originals"

HOLY_RESREF = "OHTMPS1"
CLAB_NAME = "OHTEMPUS.2DA"
LATE_HOLY_POWER_LEVELS = (26, 31, 36, 41, 46)
SENTINEL_RESOURCE = "CBRSENT"
PRIVATE_STATE_SYMBOLS = (
    "CBR_TEMPUS_IH",
    "CBR_TEMPUS_APR_HALF",
    "CBR_TEMPUS_APR_ONE",
    "CBR_TEMPUS_APR_ONE_HALF",
)
IH_STATE_SYMBOL = PRIVATE_STATE_SYMBOLS[0]
APR_STATE_SYMBOL_BY_KEY = {
    6: PRIVATE_STATE_SYMBOLS[1],
    1: PRIVATE_STATE_SYMBOLS[2],
    7: PRIVATE_STATE_SYMBOLS[3],
}
ACTIVE_SPLSTATE_SEMANTIC = (0x112, -1, 1)
STR_LT_SEMANTIC = (36, -1, 2)
STR_EQ_SEMANTIC = (36, -1, 1)
STR_BONUS_LT_SEMANTIC = (37, -1, 2)
STRENGTH_PULSE_RESREFS = ("CBRSE18", "CBRSE19", "CBRSE20", "CBRSE21")
FOREIGN_PULSE_RESREF = "F272TEST"
FOREIGN_OWNED_OPCODE_RESREFS = (
    "F54TEST",
    "F18TEST",
    "F44TEST",
    "F97TEST",
    "F1TEST",
)
STRENGTH_SETTER_BY_FLOOR = {
    18: "CBRST18",
    19: "CBRST19",
    20: "CBRST20",
    21: "CBRST21",
}
STRENGTH_CHECKER_BY_FLOOR = {
    18: "CBRSC18",
    19: "CBRSC19",
    20: "CBRSC20",
    21: "CBRSC21",
}
STRENGTH_PULSE_BY_FLOOR = {
    18: "CBRSE18",
    19: "CBRSE19",
    20: "CBRSE20",
    21: "CBRSE21",
}
STRENGTH_EXCEPTION_18 = "CBRSX18"
STRENGTH_SETTER_DURATION_TICKS = 31
STRENGTH_HELPER_RESREFS = tuple(
    (*STRENGTH_SETTER_BY_FLOOR.values(),
     *STRENGTH_CHECKER_BY_FLOOR.values(),
     *STRENGTH_PULSE_BY_FLOOR.values(),
     STRENGTH_EXCEPTION_18)
)
APR_HELPER_RESREFS = ("CBRAPR6", "CBRAPR1", "CBRAPR7")
APR_CONDITION_RESREFS = ("CBRAPC6", "CBRAPC1", "CBRAPC7")
RESERVED_PRIVATE_RESREFS = (
    *APR_HELPER_RESREFS,
    *APR_CONDITION_RESREFS,
    *STRENGTH_HELPER_RESREFS,
)
KEY_RESOURCE_TYPE_BY_EXTENSION = {"ITM": 1005, "SPL": 1006, "EFF": 1016}
SCRATCH_COLLISION_SENTINEL = b"FOREIGN-STAGING-SENTINEL"
FIXTURE_STR_LT_ROW = 2
FIXTURE_STR_EQ_ROW = 4
FIXTURE_STR_BONUS_LT_ROW = 5


@dataclasses.dataclass
class Fixture:
    root: Path
    divine_resref: str
    haste_resref: str


@dataclasses.dataclass
class HarnessResult:
    temporary: tempfile.TemporaryDirectory[str]
    fixture: Fixture
    output: Path
    run_dir: Path
    mode: str
    variant: str
    process: subprocess.CompletedProcess[str]
    source_snapshot: dict[str, bytes] | None = None

    @property
    def transcript(self) -> str:
        return f"{self.process.stdout}\n{self.process.stderr}".strip()

    @property
    def succeeded(self) -> bool:
        return (
            self.process.returncode == 0
            and (self.output / "CBR_TEST.OK").is_file()
            and "SUCCESSFULLY INSTALLED" in self.transcript
        )


def _replace_resource(effect: SplEffect, old: str, new: str) -> SplEffect:
    if effect.resource.upper() == old.upper():
        return dataclasses.replace(effect, resource=new)
    return effect


def _sentinel_effect() -> SplEffect:
    return SplEffect(
        opcode=400,
        target=1,
        power=4,
        parameter1=0x13579,
        parameter2=0x24680,
        timing=1,
        resist_dispel=2,
        duration=0,
        probability1=100,
        probability2=0,
        resource=SENTINEL_RESOURCE,
        save_type=0x1020304,
        save_bonus=-7,
        special=0x55667788,
    )


def _foreign_pulse_effect() -> SplEffect:
    return SplEffect(
        opcode=272,
        target=2,
        power=3,
        parameter1=99,
        parameter2=9,
        timing=1,
        resist_dispel=2,
        duration=0,
        probability1=73,
        probability2=19,
        resource=FOREIGN_PULSE_RESREF,
        dice_number=7,
        dice_size=11,
        save_type=0x1020000,
        save_bonus=-4,
        special=0x43425246,
    )


def _foreign_owned_opcode_pack() -> tuple[SplEffect, ...]:
    template = _foreign_pulse_effect()
    return tuple(
        dataclasses.replace(
            template,
            opcode=opcode,
            parameter1=0x5000 + opcode,
            parameter2=0 if opcode == 1 else 9,
            resource=resource,
            special=0x464F0000 + opcode,
        )
        for opcode, resource in zip(
            (54, 18, 44, 97, 1), FOREIGN_OWNED_OPCODE_RESREFS
        )
    )


def _clear_clab_holy_power_grants(raw: bytes, levels: tuple[int, ...]) -> bytes:
    lines = raw.splitlines(keepends=True)
    ability1_count = 0
    for line_index, line in enumerate(lines):
        logical_line = line.rstrip(b"\r\n")
        newline = line[len(logical_line):]
        tokens = list(re.finditer(rb"\S+", logical_line))
        if not tokens or tokens[0].group().upper() != b"ABILITY1":
            continue
        ability1_count += 1
        for level in sorted(levels, reverse=True):
            if not 1 <= level < len(tokens):
                raise ValueError(f"OHTEMPUS ABILITY1 has no level-{level} cell")
            token = tokens[level]
            if token.group().upper() != b"GA_OHTMPS1":
                raise ValueError(
                    f"OHTEMPUS ABILITY1 level {level} is {token.group()!r}, "
                    "not GA_OHTMPS1"
                )
            logical_line = (
                logical_line[:token.start()] + b"****" + logical_line[token.end():]
            )
        lines[line_index] = logical_line + newline
    if ability1_count != 1:
        raise ValueError(f"OHTEMPUS ABILITY1 matched {ability1_count} rows")
    return b"".join(lines)


def _rename_spell_resources(spell: SplFile, old: str, new: str) -> SplFile:
    abilities = []
    for ability in spell.abilities:
        effects = tuple(_replace_resource(effect, old, new) for effect in ability.effects)
        abilities.append(dataclasses.replace(ability, effects=effects))
    casting = tuple(_replace_resource(effect, old, new) for effect in spell.casting_effects)
    return dataclasses.replace(spell, abilities=tuple(abilities), casting_effects=casting)


def _strength_pulse_resref(level: int) -> str:
    if level <= 12:
        return "CBRSE18"
    if level <= 18:
        return "CBRSE19"
    if level <= 24:
        return "CBRSE20"
    return "CBRSE21"


def _strength_floor(level: int) -> int:
    if level <= 12:
        return 18
    if level <= 18:
        return 19
    if level <= 24:
        return 20
    return 21


def _owned_timed_effect(
    opcode: int, parameter1: int, parameter2: int, duration: int
) -> SplEffect:
    """Return the exact canonical timed mechanic owned by this progression."""
    return SplEffect(
        opcode=opcode,
        target=1,
        power=4,
        parameter1=parameter1,
        parameter2=parameter2,
        timing=0,
        resist_dispel=3,
        duration=duration,
        probability1=100,
        probability2=0,
    )


def _make_holy_fixture(divine_resref: str, holy_layout: str = "original") -> SplFile:
    spell = read_spl(ORIGINALS / "OHTMPS1.spl.orig")
    spell = _rename_spell_resources(spell, "SPPR412", divine_resref)
    abilities = list(spell.abilities)
    abilities[9] = dataclasses.replace(
        abilities[9], effects=abilities[9].effects + (_sentinel_effect(),)
    )
    abilities[19] = dataclasses.replace(
        abilities[19],
        effects=abilities[19].effects
        + (_sentinel_effect(), _foreign_pulse_effect(), *_foreign_owned_opcode_pack()),
    )
    if holy_layout.startswith("original_bad_") or holy_layout == "original_duplicate_owned_thac0":
        effects = list(abilities[0].effects)
        if holy_layout == "original_bad_cleanup_order":
            effects[0], effects[1] = effects[1], effects[0]
        elif holy_layout == "original_bad_thac0":
            index = next(i for i, effect in enumerate(effects) if effect.opcode == 54)
            effects[index] = dataclasses.replace(effects[index], parameter1=19)
        elif holy_layout == "original_bad_hp_duration":
            index = next(i for i, effect in enumerate(effects) if effect.opcode == 18)
            effects[index] = dataclasses.replace(effects[index], duration=7)
        elif holy_layout == "original_bad_strength":
            index = next(i for i, effect in enumerate(effects) if effect.opcode == 44)
            effects[index] = dataclasses.replace(effects[index], parameter1=17)
        elif holy_layout == "original_bad_owned_pulse":
            effects.append(
                SplEffect(
                    opcode=272,
                    target=1,
                    power=4,
                    parameter1=1,
                    parameter2=3,
                    timing=0,
                    resist_dispel=3,
                    duration=6,
                    probability1=100,
                    probability2=0,
                    resource=STRENGTH_PULSE_BY_FLOOR[18],
                )
            )
        elif holy_layout == "original_duplicate_owned_thac0":
            effects.append(next(effect for effect in effects if effect.opcode == 54 and not effect.resource))
        else:
            raise ValueError(f"unknown original Holy Power fault: {holy_layout}")
        abilities[0] = dataclasses.replace(abilities[0], effects=tuple(effects))
        return dataclasses.replace(spell, abilities=tuple(abilities))
    pulse_fault_by_layout = {
        "valid_30": None,
        "valid_30_missing_pulse": "missing",
        "valid_30_duplicate_pulse": "duplicate",
        "valid_30_wrong_tier_pulse": "wrong_tier",
        "valid_30_bad_p1": "bad_p1",
        "valid_30_bad_p2": "bad_p2",
        "valid_30_bad_timing": "bad_timing",
        "valid_30_bad_resist_dispel": "bad_resist_dispel",
        "valid_30_bad_duration": "bad_duration",
        "valid_30_bad_target": "bad_target",
        "valid_30_bad_power": "bad_power",
        "valid_30_bad_probability1": "bad_probability1",
        "valid_30_bad_probability2": "bad_probability2",
        "valid_30_bad_dice_number": "bad_dice_number",
        "valid_30_bad_dice_size": "bad_dice_size",
        "valid_30_bad_save_type": "bad_save_type",
        "valid_30_bad_save_bonus": "bad_save_bonus",
        "valid_30_bad_special": "bad_special",
        "valid_30_missing_recast_cleanup": None,
        "valid_30_duplicate_recast_cleanup": None,
        "valid_30_misplaced_recast_cleanup": None,
        "valid_30_missing_expiry_cleanup": None,
        "valid_30_duplicate_expiry_cleanup": None,
        "valid_30_bad_expiry_duration": None,
    }
    recast_fault_by_layout = {
        "valid_30_missing_recast_cleanup": "missing",
        "valid_30_duplicate_recast_cleanup": "duplicate",
        "valid_30_misplaced_recast_cleanup": "misplaced",
    }
    expiry_fault_by_layout = {
        "valid_30_missing_expiry_cleanup": "missing",
        "valid_30_duplicate_expiry_cleanup": "duplicate",
        "valid_30_bad_expiry_duration": "bad_duration",
    }
    if holy_layout == "original":
        return dataclasses.replace(spell, abilities=tuple(abilities))
    if holy_layout != "stale_30" and holy_layout not in pulse_fault_by_layout:
        raise ValueError(f"unknown Holy Power fixture layout: {holy_layout}")

    donor = abilities[-1]
    abilities.extend(
        dataclasses.replace(donor, required_level=level)
        for level in range(21, 31)
    )
    if holy_layout != "stale_30":
        pulse_fault = pulse_fault_by_layout[holy_layout]
        recast_fault = recast_fault_by_layout.get(holy_layout)
        expiry_fault = expiry_fault_by_layout.get(holy_layout)
        normalized = []
        for level, ability in enumerate(abilities, start=1):
            duration = 18 if level <= 6 else 24 if level <= 12 else 30
            thac0 = max(0, 21 - level)
            hp = min(level, 30)
            apr_key = (
                None if level <= 6 else 6 if level <= 12 else 1 if level <= 24 else 7
            )
            source_level = min(level, 20)
            original_duration = source_level * 6
            core_template = next(
                effect
                for effect in ability.effects
                if effect.canonical()
                == _owned_timed_effect(
                    54, max(0, 21 - source_level), 1, original_duration
                ).canonical()
            )
            hp_template = next(
                effect
                for effect in ability.effects
                if effect.canonical()
                == _owned_timed_effect(
                    18, source_level, 0, original_duration
                ).canonical()
            )
            legacy_strength_signatures = {
                _owned_timed_effect(44, 18, 1, original_duration).canonical(),
                _owned_timed_effect(97, 100, 1, original_duration).canonical(),
            }
            legacy_strength = tuple(
                effect
                for effect in ability.effects
                if effect.canonical() in legacy_strength_signatures
            )
            own_cleanup_source = next(
                effect
                for effect in ability.effects
                if effect.opcode == 321 and effect.resource.upper() == HOLY_RESREF
            )
            divine_cleanup_source = next(
                effect
                for effect in ability.effects
                if effect.opcode == 321 and effect.resource.upper() == divine_resref.upper()
            )
            own_cleanup = dataclasses.replace(
                own_cleanup_source, resist_dispel=2
            )
            divine_cleanup = dataclasses.replace(
                divine_cleanup_source, parameter2=2, resist_dispel=2
            )
            effects = []
            for effect in ability.effects:
                if effect is own_cleanup_source or effect is divine_cleanup_source:
                    continue
                if effect is core_template:
                    effects.append(
                        dataclasses.replace(
                            effect,
                            parameter1=thac0,
                            parameter2=1,
                            timing=0,
                            resist_dispel=3,
                            duration=duration,
                        )
                    )
                elif effect is hp_template:
                    effects.append(
                        dataclasses.replace(
                            effect,
                            parameter1=hp,
                            parameter2=0,
                            timing=0,
                            resist_dispel=3,
                            duration=duration,
                        )
                    )
                elif effect in legacy_strength:
                    continue
                else:
                    effects.append(effect)
            if apr_key is not None:
                effects.append(
                    dataclasses.replace(
                        core_template,
                        opcode=1,
                        parameter1=apr_key,
                        parameter2=0,
                        timing=0,
                        resist_dispel=3,
                        duration=duration,
                    )
                )

            floor = _strength_floor(level)
            immediate_effects = [
                dataclasses.replace(
                    core_template,
                    opcode=326,
                    target=1,
                    power=4,
                    parameter1=floor,
                    parameter2=FIXTURE_STR_LT_ROW,
                    timing=1,
                    resist_dispel=2,
                    duration=0,
                    probability1=100,
                    probability2=0,
                    resource=STRENGTH_SETTER_BY_FLOOR[floor],
                    dice_number=0,
                    dice_size=0,
                    save_type=0,
                    save_bonus=0,
                    special=0,
                )
            ]
            if floor == 18:
                immediate_effects.append(
                    dataclasses.replace(
                        core_template,
                        opcode=326,
                        target=1,
                        power=4,
                        parameter1=18,
                        parameter2=FIXTURE_STR_EQ_ROW,
                        timing=1,
                        resist_dispel=2,
                        duration=0,
                        probability1=100,
                        probability2=0,
                        resource=STRENGTH_EXCEPTION_18,
                        dice_number=0,
                        dice_size=0,
                        save_type=0,
                        save_bonus=0,
                        special=0,
                    )
                )
            def strength_cleanup(setter: str, *, timing: int, cleanup_duration: int) -> SplEffect:
                return dataclasses.replace(
                    core_template,
                    opcode=321,
                    target=1,
                    power=4,
                    parameter1=0,
                    parameter2=2,
                    timing=timing,
                    resist_dispel=2,
                    duration=cleanup_duration,
                    probability1=100,
                    probability2=0,
                    resource=setter,
                    dice_number=0,
                    dice_size=0,
                    save_type=0,
                    save_bonus=0,
                    special=0,
                )

            recast_cleanups = [
                strength_cleanup(setter, timing=1, cleanup_duration=0)
                for setter in STRENGTH_SETTER_BY_FLOOR.values()
            ]
            if level == 13 and recast_fault == "missing":
                recast_cleanups.pop(0)
            elif level == 13 and recast_fault == "duplicate":
                recast_cleanups.append(recast_cleanups[0])

            if level == 13 and recast_fault == "misplaced":
                effects = [
                    divine_cleanup,
                    own_cleanup,
                    *immediate_effects,
                    *recast_cleanups,
                    *effects,
                ]
            else:
                effects = [
                    divine_cleanup,
                    own_cleanup,
                    *recast_cleanups,
                    *immediate_effects,
                    *effects,
                ]

            pulse = dataclasses.replace(
                core_template,
                opcode=272,
                parameter1=1,
                parameter2=3,
                timing=0,
                resist_dispel=3,
                duration=duration,
                resource=_strength_pulse_resref(level),
            )
            if level == 13:
                if pulse_fault == "missing":
                    pulse = None
                elif pulse_fault == "wrong_tier":
                    pulse = dataclasses.replace(pulse, resource="CBRSE18")
                elif pulse_fault == "bad_p1":
                    pulse = dataclasses.replace(pulse, parameter1=2)
                elif pulse_fault == "bad_p2":
                    pulse = dataclasses.replace(pulse, parameter2=4)
                elif pulse_fault == "bad_timing":
                    pulse = dataclasses.replace(pulse, timing=1)
                elif pulse_fault == "bad_resist_dispel":
                    pulse = dataclasses.replace(pulse, resist_dispel=2)
                elif pulse_fault == "bad_duration":
                    pulse = dataclasses.replace(pulse, duration=duration + 1)
                elif pulse_fault == "bad_target":
                    pulse = dataclasses.replace(pulse, target=2)
                elif pulse_fault == "bad_power":
                    pulse = dataclasses.replace(pulse, power=3)
                elif pulse_fault == "bad_probability1":
                    pulse = dataclasses.replace(pulse, probability1=99)
                elif pulse_fault == "bad_probability2":
                    pulse = dataclasses.replace(pulse, probability2=1)
                elif pulse_fault == "bad_dice_number":
                    pulse = dataclasses.replace(pulse, dice_number=1)
                elif pulse_fault == "bad_dice_size":
                    pulse = dataclasses.replace(pulse, dice_size=1)
                elif pulse_fault == "bad_save_type":
                    pulse = dataclasses.replace(pulse, save_type=1)
                elif pulse_fault == "bad_save_bonus":
                    pulse = dataclasses.replace(pulse, save_bonus=1)
                elif pulse_fault == "bad_special":
                    pulse = dataclasses.replace(pulse, special=1)
            if pulse is not None:
                effects.append(pulse)
                if level == 13 and pulse_fault == "duplicate":
                    effects.append(pulse)
            expiry_cleanups = [
                strength_cleanup(setter, timing=4, cleanup_duration=duration)
                for setter in STRENGTH_SETTER_BY_FLOOR.values()
            ]
            if level == 13 and expiry_fault == "missing":
                expiry_cleanups.pop(0)
            elif level == 13 and expiry_fault == "duplicate":
                expiry_cleanups.append(expiry_cleanups[0])
            elif level == 13 and expiry_fault == "bad_duration":
                expiry_cleanups[0] = dataclasses.replace(
                    expiry_cleanups[0], duration=duration + 1
                )
            effects.extend(expiry_cleanups)
            normalized.append(dataclasses.replace(ability, effects=tuple(effects)))
        abilities = normalized
    return dataclasses.replace(spell, abilities=tuple(abilities))


def _basic_self_helper(effects: tuple[SplEffect, ...]) -> SplFile:
    raw = bytearray(0x28)
    raw[0x00:0x02] = (1).to_bytes(2, "little")
    raw[0x02:0x04] = (4).to_bytes(2, "little")
    raw[0x0C] = 5
    raw[0x10:0x12] = (1).to_bytes(2, "little")
    raw[0x22:0x24] = (1).to_bytes(2, "little")
    raw[0x24:0x26] = (1).to_bytes(2, "little")
    return make_spl(
        (
            SplAbility(
                required_level=1,
                target=5,
                projectile=0,
                effects=effects,
                raw=bytes(raw),
            ),
        )
    )


def _helper_effect(opcode: int, *, parameter1: int = 0, parameter2: int = 0,
                   timing: int = 1, resist_dispel: int = 2, duration: int = 0,
                   resource: str = "") -> SplEffect:
    return SplEffect(
        opcode=opcode,
        target=1,
        power=4,
        parameter1=parameter1,
        parameter2=parameter2,
        timing=timing,
        resist_dispel=resist_dispel,
        duration=duration,
        probability1=100,
        probability2=0,
        resource=resource,
    )


def _write_strength_helper_fixture(root: Path, layout: str) -> None:
    if layout == "absent":
        return

    helpers: dict[str, SplFile | EffV2] = {}
    for floor, setter in STRENGTH_SETTER_BY_FLOOR.items():
        setter_effects = [
            _helper_effect(321, parameter2=2, resource=setter),
            _helper_effect(
                44,
                parameter1=floor,
                parameter2=1,
                timing=10,
                resist_dispel=3,
                duration=STRENGTH_SETTER_DURATION_TICKS,
            ),
        ]
        if floor == 18:
            setter_effects.append(
                _helper_effect(
                    97,
                    parameter1=100,
                    parameter2=1,
                    timing=10,
                    resist_dispel=3,
                    duration=STRENGTH_SETTER_DURATION_TICKS,
                )
            )
        helpers[setter] = _basic_self_helper(tuple(setter_effects))

        checker_effects = [
            _helper_effect(321, parameter2=2, resource=setter),
            _helper_effect(
                326,
                parameter1=floor,
                parameter2=FIXTURE_STR_LT_ROW,
                resource=setter,
            ),
        ]
        if floor == 18:
            checker_effects.append(
                _helper_effect(
                    326,
                    parameter1=18,
                    parameter2=FIXTURE_STR_EQ_ROW,
                    resource=STRENGTH_EXCEPTION_18,
                )
            )
        helpers[STRENGTH_CHECKER_BY_FLOOR[floor]] = _basic_self_helper(
            tuple(checker_effects)
        )
        helpers[STRENGTH_PULSE_BY_FLOOR[floor]] = EffV2(
            opcode=146,
            target=2,
            power=4,
            parameter1=0,
            parameter2=1,
            timing=1,
            duration=0,
            probability1=100,
            probability2=0,
            resource=STRENGTH_CHECKER_BY_FLOOR[floor],
            flags=2,
        )

    helpers[STRENGTH_EXCEPTION_18] = _basic_self_helper(
        (
            _helper_effect(
                326,
                parameter1=100,
                parameter2=FIXTURE_STR_BONUS_LT_ROW,
                resource=STRENGTH_SETTER_BY_FLOOR[18],
            ),
        )
    )

    if layout == "missing":
        del helpers[STRENGTH_PULSE_BY_FLOOR[20]]
    elif layout == "corrupt":
        checker = helpers[STRENGTH_CHECKER_BY_FLOOR[19]]
        assert isinstance(checker, SplFile)
        ability = checker.abilities[0]
        malformed = dataclasses.replace(ability.effects[1], parameter1=18)
        helpers[STRENGTH_CHECKER_BY_FLOOR[19]] = dataclasses.replace(
            checker,
            abilities=(dataclasses.replace(ability, effects=(ability.effects[0], malformed)),),
        )
    elif layout not in (
        "exact",
        "wrong_extension",
        "cross_extension",
        "timing_high_word",
        "eff_school_corrupt",
        "eff_parent_resource_corrupt",
        "spl_main_header_corrupt",
        "spl_ability_header_corrupt",
    ):
        raise ValueError(f"unknown Strength-helper fixture layout: {layout}")

    for resref, helper in helpers.items():
        suffix = ".eff" if isinstance(helper, EffV2) else ".spl"
        (root / f"{resref}{suffix}").write_bytes(helper.to_bytes())

    if layout == "wrong_extension":
        checker = STRENGTH_CHECKER_BY_FLOOR[20]
        (root / f"{checker}.spl").unlink()
        (root / f"{checker}.eff").write_bytes(
            EffV2(opcode=146, target=2, power=4, parameter2=1,
                  timing=1, resource=checker, flags=2).to_bytes()
        )
    elif layout == "cross_extension":
        setter = STRENGTH_SETTER_BY_FLOOR[18]
        (root / f"{setter}.eff").write_bytes(
            EffV2(opcode=146, target=2, power=4, parameter2=1,
                  timing=1, resource=setter, flags=2).to_bytes()
        )
    elif layout == "timing_high_word":
        pulse_path = root / f"{STRENGTH_PULSE_BY_FLOOR[20]}.eff"
        pulse = bytearray(pulse_path.read_bytes())
        pulse[0x26:0x28] = (1).to_bytes(2, "little")
        pulse_path.write_bytes(pulse)
    elif layout == "eff_school_corrupt":
        pulse_path = root / f"{STRENGTH_PULSE_BY_FLOOR[20]}.eff"
        pulse = bytearray(pulse_path.read_bytes())
        pulse[0x4C] = 1
        pulse_path.write_bytes(pulse)
    elif layout == "eff_parent_resource_corrupt":
        pulse_path = root / f"{STRENGTH_PULSE_BY_FLOOR[20]}.eff"
        pulse = bytearray(pulse_path.read_bytes())
        pulse[0x94:0x9C] = b"FOREIGN\x00"
        pulse_path.write_bytes(pulse)
    elif layout == "spl_main_header_corrupt":
        setter_path = root / f"{STRENGTH_SETTER_BY_FLOOR[19]}.spl"
        setter = bytearray(setter_path.read_bytes())
        setter[0x20] = 1
        setter_path.write_bytes(setter)
    elif layout == "spl_ability_header_corrupt":
        setter_path = root / f"{STRENGTH_SETTER_BY_FLOOR[19]}.spl"
        setter = bytearray(setter_path.read_bytes())
        setter[0x76] = 1
        setter_path.write_bytes(setter)


def _make_divine_fixture(divine_resref: str) -> SplFile:
    spell = read_spl(ORIGINALS / "SPPR412.spl.orig")
    spell = _rename_spell_resources(spell, "SPPR412", divine_resref)
    abilities = list(spell.abilities)
    abilities[3] = dataclasses.replace(
        abilities[3], effects=abilities[3].effects + (_sentinel_effect(),)
    )
    return dataclasses.replace(spell, abilities=tuple(abilities))


def _improved_haste_fixture(
    variant: str, haste_resref: str
) -> tuple[SplFile, dict[str, SplFile]]:
    base = read_spl(ORIGINALS / "SPWI613.spl.orig")
    base = _rename_spell_resources(base, "SPWI613", haste_resref)
    ability = base.abilities[0]
    effects = list(ability.effects)
    additive_index = next(
        i
        for i, effect in enumerate(effects)
        if effect.opcode == 1 and effect.parameter1 == 1 and effect.parameter2 == 0
    )
    additive = effects[additive_index]
    true_haste = dataclasses.replace(additive, opcode=16, parameter1=0, parameter2=1)
    helpers: dict[str, SplFile] = {}

    if variant == "additive":
        pass
    elif variant == "doubling":
        effects[additive_index] = true_haste
    elif variant == "doubling317":
        effects[additive_index] = dataclasses.replace(true_haste, opcode=317)
    elif variant == "mixed":
        effects.insert(additive_index + 1, true_haste)
    elif variant == "duplicate_additive":
        effects.insert(additive_index + 1, additive)
    elif variant == "missing":
        del effects[additive_index]
    elif variant == "probabilistic":
        effects[additive_index] = dataclasses.replace(additive, probability1=50)
    elif variant == "delayed_additive":
        effects[additive_index] = dataclasses.replace(additive, timing=3)
    elif variant == "save_conditioned_additive":
        effects[additive_index] = dataclasses.replace(
            additive, save_type=1, save_bonus=-1
        )
    elif variant == "metadata_additive":
        effects[additive_index] = dataclasses.replace(
            additive,
            resource="FOREIGN",
            dice_number=1,
            dice_size=2,
            special=1,
        )
    elif variant == "mr_resistible_additive":
        effects[additive_index] = dataclasses.replace(additive, resist_dispel=1)
    elif variant == "conditional":
        helper_resref = "CBRIHCON"
        effects[additive_index] = dataclasses.replace(
            additive,
            opcode=326,
            parameter1=9,
            parameter2=0,
            timing=1,
            duration=0,
            resource=helper_resref,
        )
        helpers[helper_resref] = make_spl(
            (
                SplAbility(
                    required_level=1,
                    target=5,
                    projectile=0,
                    effects=(additive,),
                ),
            )
        )
    elif variant == "inconsistent":
        first = dataclasses.replace(ability, effects=tuple(effects), required_level=1)
        second_effects = list(effects)
        second_effects[additive_index] = true_haste
        second = dataclasses.replace(
            ability, effects=tuple(second_effects), required_level=10
        )
        return dataclasses.replace(base, abilities=(first, second)), helpers
    else:
        raise ValueError(f"unknown Improved Haste variant: {variant}")

    headers = []
    for required_level, duration_delta, rotation in ((1, 0, 0), (10, 6, 1), (20, 12, 2)):
        header_effects = [
            dataclasses.replace(effect, duration=effect.duration + duration_delta)
            if (
                (effect.opcode == 1 and effect.parameter1 == 1 and effect.parameter2 == 0)
                or (effect.opcode in (16, 317) and effect.parameter2 == 1)
            )
            else effect
            for effect in effects
        ]
        rotation %= len(header_effects)
        if rotation:
            header_effects = header_effects[rotation:] + header_effects[:rotation]
        headers.append(
            dataclasses.replace(
                ability,
                effects=tuple(header_effects),
                required_level=required_level,
            )
        )
    return dataclasses.replace(base, abilities=tuple(headers)), helpers


def build_fixture(
    root: Path,
    variant: str,
    *,
    divine_id: int = 1499,
    haste_id: int = 2699,
    splstate_layout: str = "free",
    splprot_layout: str = "default",
    holy_layout: str = "original",
    strength_helpers_layout: str | None = None,
    clab_layout: str = "original",
    reserved_itm_resref: str | None = None,
    casting_sentinels: bool = False,
    effect_partition_layout: str = "canonical",
    dangling_apr_owner: str | None = None,
) -> Fixture:
    root.mkdir(parents=True, exist_ok=True)
    ids = IdsFile(
        entries=(
            (divine_id, "CLERIC_HOLY_POWER"),
            (haste_id, "WIZARD_IMPROVED_HASTE"),
            (2998, "WIZARD_FIXTURE_SENTINEL"),
        )
    )
    write_ids(root / "SPELL.IDS", ids)
    divine_resref = spell_resref(divine_id, "CLERIC_HOLY_POWER")
    haste_resref = spell_resref(haste_id, "WIZARD_IMPROVED_HASTE")

    holy_spell = _make_holy_fixture(divine_resref, holy_layout)
    divine_spell = _make_divine_fixture(divine_resref)
    haste, helpers = _improved_haste_fixture(variant, haste_resref)
    if casting_sentinels:
        holy_spell = dataclasses.replace(holy_spell, casting_effects=(_sentinel_effect(),))
        divine_spell = dataclasses.replace(divine_spell, casting_effects=(_sentinel_effect(),))
        haste = dataclasses.replace(haste, casting_effects=(_sentinel_effect(),))
    if dangling_apr_owner == "holy":
        abilities = list(holy_spell.abilities)
        abilities[12] = dataclasses.replace(
            abilities[12],
            effects=abilities[12].effects
            + (_helper_effect(326, resource=APR_HELPER_RESREFS[1]),),
        )
        holy_spell = dataclasses.replace(holy_spell, abilities=tuple(abilities))
    elif dangling_apr_owner == "ih":
        abilities = list(haste.abilities)
        abilities[0] = dataclasses.replace(
            abilities[0],
            effects=abilities[0].effects
            + (_helper_effect(326, resource=APR_HELPER_RESREFS[1]),),
        )
        haste = dataclasses.replace(haste, abilities=tuple(abilities))
    elif dangling_apr_owner is not None:
        raise ValueError(f"unknown dangling APR owner: {dangling_apr_owner}")
    write_spl(root / f"{HOLY_RESREF}.SPL", holy_spell)
    write_spl(root / f"{divine_resref}.SPL", divine_spell)
    write_spl(root / f"{haste_resref}.SPL", haste)
    for resref, helper in helpers.items():
        write_spl(root / f"{resref}.SPL", helper)
    if effect_partition_layout != "canonical":
        haste_path = root / f"{haste_resref}.SPL"
        raw_haste = bytearray(haste_path.read_bytes())
        if effect_partition_layout == "ih_orphan":
            raw_haste.extend(_sentinel_effect().to_bytes())
        elif effect_partition_layout == "ih_overlap":
            ability_offset = int.from_bytes(raw_haste[0x64:0x68], "little")
            first_index = raw_haste[ability_offset + 0x20 : ability_offset + 0x22]
            second_header = ability_offset + 0x28
            raw_haste[second_header + 0x20 : second_header + 0x22] = first_index
        else:
            raise ValueError(f"unknown effect partition layout: {effect_partition_layout}")
        haste_path.write_bytes(raw_haste)

    clab_path = root / CLAB_NAME
    shutil.copyfile(ORIGINALS / "OHTEMPUS.2da.orig", clab_path)
    if clab_layout == "partial":
        clab_path.write_bytes(
            _clear_clab_holy_power_grants(clab_path.read_bytes(), (26,))
        )
    elif clab_layout == "capped":
        clab_path.write_bytes(
            _clear_clab_holy_power_grants(
                clab_path.read_bytes(), LATE_HOLY_POWER_LEVELS
            )
        )
    elif clab_layout == "decoy":
        raw = clab_path.read_bytes()
        lines = raw.splitlines(keepends=True)
        newline = b"\r\n" if b"\r\n" in raw else b"\n"
        lines.insert(3, b"// ABILITY1 decoy must remain byte-identical" + newline)
        clab_path.write_bytes(b"".join(lines))
    elif clab_layout != "original":
        raise ValueError(f"unknown CLAB fixture layout: {clab_layout}")
    base_states = tuple((value, f"FIXTURE_STATE_{value}") for value in range(32)) + (
        (68, "BUFF_ENHANCEMENT"),
        (200, "FOREIGN_200"),
        (254, "FOREIGN_254"),
    )
    splstate_extra = b""
    if splstate_layout == "free":
        state_entries = base_states
    elif splstate_layout == "reuse":
        state_entries = base_states + tuple(
            (240 + index, symbol) for index, symbol in enumerate(PRIVATE_STATE_SYMBOLS)
        )
    elif splstate_layout == "partial_clean":
        state_entries = base_states + (
            (240, PRIVATE_STATE_SYMBOLS[0]),
            (242, PRIVATE_STATE_SYMBOLS[2]),
        )
    elif splstate_layout == "duplicate_private_symbol":
        state_entries = base_states + (
            (240, PRIVATE_STATE_SYMBOLS[0]),
            (241, PRIVATE_STATE_SYMBOLS[0]),
        )
    elif splstate_layout == "shared_private_value":
        state_entries = base_states + (
            (240, PRIVATE_STATE_SYMBOLS[0]),
            (240, "FOREIGN_SHARED_240"),
        )
    elif splstate_layout == "exhausted":
        state_entries = tuple((value, f"FOREIGN_STATE_{value}") for value in range(256))
    elif splstate_layout == "hex_collision":
        state_entries = base_states
        splstate_extra = b"   0xFF FOREIGN_HEX_255\n"
    elif splstate_layout == "hex_reuse":
        state_entries = base_states
        splstate_extra = b"".join(
            f"\t0x{240 + index:X} {symbol}\n".encode("ascii")
            for index, symbol in enumerate(PRIVATE_STATE_SYMBOLS)
        )
    else:
        raise ValueError(f"unknown SPLSTATE fixture layout: {splstate_layout}")
    splstate_path = root / "SPLSTATE.IDS"
    write_ids(splstate_path, IdsFile(entries=state_entries))
    if splstate_extra:
        splstate_path.write_bytes(splstate_path.read_bytes() + splstate_extra)
    if strength_helpers_layout is None:
        strength_helpers_layout = (
            "exact" if holy_layout.startswith("valid_30") else "absent"
        )
    splprot_rows = (
        ("0_KEEP", ("0x10a", "0", "4")),
        ("1_STATE_N", ("0x112", "-1", "1")),
        ("2_STR_LT_N", ("36", "-1", "2")),
        ("3_SENTINEL", ("999", "123", "5")),
    )
    if splprot_layout == "no_active_state":
        splprot_rows = tuple(
            row for row in splprot_rows if row[0] != "1_STATE_N"
        )
    elif splprot_layout == "duplicate_semantics":
        splprot_rows += (
            ("4_ACTIVE_ALIAS", ("0x112", "-1", "1")),
            ("5_STR_EQ_N", ("36", "-1", "1")),
            ("6_STR_EQ_ALIAS", ("36", "-1", "1")),
            ("7_STR_BONUS_LT_N", ("37", "-1", "2")),
        )
    elif splprot_layout == "malformed_numeric":
        splprot_rows += (("4_MALFORMED", ("NOT_A_STAT", "-1", "1")),)
    elif splprot_layout != "default":
        raise ValueError(f"unknown SPLPROT fixture layout: {splprot_layout}")
    if strength_helpers_layout != "absent":
        if splprot_layout != "default":
            raise ValueError("Strength-helper fixtures require the default SPLPROT layout")
        splprot_rows += (
            ("4_STR_EQ_N", ("36", "-1", "1")),
            ("5_STR_BONUS_LT_N", ("37", "-1", "2")),
        )
    write_2da(
        root / "SPLPROT.2DA",
        TwoDA(
            default="0xffff",
            columns=("STAT", "VALUE", "RELATION"),
            rows=splprot_rows,
        ),
    )
    _write_strength_helper_fixture(root, strength_helpers_layout)
    if reserved_itm_resref is not None:
        allowed_itm_resrefs = {
            *RESERVED_PRIVATE_RESREFS,
            HOLY_RESREF,
            divine_resref.upper(),
        }
        if reserved_itm_resref.upper() not in allowed_itm_resrefs:
            raise ValueError(
                f"unknown reserved private resref for ITM collision: {reserved_itm_resref}"
            )
        (root / f"{reserved_itm_resref}.itm").write_bytes(b"ITM V1  collision")
    return Fixture(root=root, divine_resref=divine_resref, haste_resref=haste_resref)


PHASE_COMPONENT = {"full": "1", "classify": "2", "allocate": "3", "progression": "4", "bridge": "5"}


def _write_key_only_resource(game_root: Path, resref: str, extension: str) -> None:
    """Index one resource in a BIFF without placing a loose override copy."""
    extension = extension.upper()
    resource_type = KEY_RESOURCE_TYPE_BY_EXTENSION[extension]
    payload = f"foreign KEY-only {resref}.{extension}".encode("ascii")
    bif_relative = Path("DATA/CBRKEY.BIF")
    bif_path = game_root / bif_relative
    bif_path.parent.mkdir(parents=True, exist_ok=True)
    table_offset = 0x14
    payload_offset = table_offset + 0x10
    bif_path.write_bytes(
        struct.pack("<4s4sIII", b"BIFF", b"V1  ", 1, 0, table_offset)
        + struct.pack("<IIIHH", 0, payload_offset, len(payload), resource_type, 0)
        + payload
    )

    encoded_bif_name = (str(bif_relative).replace("/", "\\") + "\0").encode("ascii")
    bif_table_offset = 0x18
    resource_table_offset = bif_table_offset + 0x0C
    names_offset = resource_table_offset + 0x0E
    game_root.joinpath("chitin.key").write_bytes(
        struct.pack(
            "<4s4sIIII",
            b"KEY ",
            b"V1  ",
            1,
            1,
            bif_table_offset,
            resource_table_offset,
        )
        + struct.pack(
            "<IIHH", bif_path.stat().st_size, names_offset, len(encoded_bif_name), 0
        )
        + struct.pack(
            "<8sHI", resref.upper().encode("ascii").ljust(8, b"\0"), resource_type, 0
        )
        + encoded_bif_name
    )


def _run_key_collision_harness(
    resref: str, extension: str
) -> subprocess.CompletedProcess[str]:
    with tempfile.TemporaryDirectory(prefix="cbr-tempus-key-") as temporary:
        game_root = Path(temporary)
        explicit_resources = game_root / "explicit"
        explicit_resources.mkdir()
        (game_root / "override").mkdir()
        # A zero-string TLK is sufficient for this action-only synthetic game.
        (game_root / "dialog.tlk").write_bytes(
            struct.pack("<8sHII", b"TLK V1  ", 0, 0, 0x12)
        )
        _write_key_only_resource(game_root, resref, extension)
        loose_candidates = (
            explicit_resources / f"{resref}.{extension.lower()}",
            game_root / "override" / f"{resref}.{extension.lower()}",
        )
        if any(path.exists() for path in loose_candidates):
            raise AssertionError("KEY collision fixture unexpectedly contains a loose resource")
        return subprocess.run(
            [
                str(WEIDU),
                str(HARNESS),
                "--game",
                str(game_root),
                "--force-install-list",
                "6",
                "--args",
                str(PRODUCTION_TPA),
                "--args",
                str(explicit_resources),
                "--no-exit-pause",
                "--quick-log",
            ],
            cwd=game_root,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )


def _run_harness(
    variant: str,
    mode: str,
    *,
    alternate_ids: bool = False,
    phase: str = "full",
    splstate_layout: str = "free",
    splprot_layout: str = "default",
    holy_layout: str = "original",
    strength_helpers_layout: str | None = None,
    clab_layout: str = "original",
    relative_output: bool = False,
    absolute_process_override: bool = False,
    reserved_itm_resref: str | None = None,
    scratch_reserved_resref: str | None = None,
    casting_sentinels: bool = False,
    effect_partition_layout: str = "canonical",
    dangling_apr_owner: str | None = None,
) -> HarnessResult:
    temporary = tempfile.TemporaryDirectory(prefix="cbr-tempus-")
    base = Path(temporary.name)
    fixture_root = base / "fixture"
    run_dir = base / "weidu-run"
    run_dir.mkdir()
    if relative_output and absolute_process_override:
        raise ValueError("relative and absolute process override modes are exclusive")
    if relative_output:
        output = run_dir / "override"
        output_argument = "override"
    elif absolute_process_override:
        output = run_dir / "override"
        output_argument = str(output)
    else:
        output = base / "output"
        output_argument = str(output)
    output.mkdir()
    fixture = build_fixture(
        fixture_root,
        variant,
        divine_id=1388 if alternate_ids else 1499,
        haste_id=2788 if alternate_ids else 2699,
        splstate_layout=splstate_layout,
        splprot_layout=splprot_layout,
        holy_layout=holy_layout,
        strength_helpers_layout=strength_helpers_layout,
        clab_layout=clab_layout,
        reserved_itm_resref=reserved_itm_resref,
        casting_sentinels=casting_sentinels,
        effect_partition_layout=effect_partition_layout,
        dangling_apr_owner=dangling_apr_owner,
    )
    if scratch_reserved_resref is not None:
        if scratch_reserved_resref.upper() not in RESERVED_PRIVATE_RESREFS:
            raise ValueError(
                "unknown reserved private resref for scratch collision: "
                f"{scratch_reserved_resref}"
            )
        scratch_override = run_dir / "override"
        scratch_override.mkdir(exist_ok=True)
        (scratch_override / f"{scratch_reserved_resref}.spl").write_bytes(
            SCRATCH_COLLISION_SENTINEL
        )
    command = [
        str(WEIDU),
        str(HARNESS),
        "--nogame",
        "--force-install-list",
        PHASE_COMPONENT[phase],
        "--args",
        str(PRODUCTION_TPA),
        "--args",
        str(fixture.root),
        "--args",
        output_argument,
        "--args",
        mode,
        "--args",
        fixture.divine_resref,
        "--args",
        fixture.haste_resref,
        "--no-exit-pause",
        "--quick-log",
    ]
    process = subprocess.run(
        command,
        cwd=run_dir,
        capture_output=True,
        text=True,
        timeout=45,
        check=False,
    )
    return HarnessResult(
        temporary=temporary,
        fixture=fixture,
        output=output,
        run_dir=run_dir,
        mode=mode,
        variant=variant,
        process=process,
    )


def _rerun_harness(
    previous: HarnessResult,
    *,
    phase: str = "full",
    absolute_process_override: bool = False,
    fixture_mutator=None,
    scratch_sentinel: bool = False,
    scratch_mutator=None,
) -> HarnessResult:
    temporary = tempfile.TemporaryDirectory(prefix="cbr-tempus-second-")
    base = Path(temporary.name)
    fixture_root = base / "fixture"
    run_dir = base / "weidu-run"
    shutil.copytree(previous.output, fixture_root)
    if fixture_mutator is not None:
        fixture_mutator(fixture_root)
    run_dir.mkdir()
    if scratch_sentinel:
        scratch_override = run_dir / "override"
        scratch_override.mkdir(exist_ok=True)
        (scratch_override / "FOREIGN.KEEP").write_bytes(SCRATCH_COLLISION_SENTINEL)
    if scratch_mutator is not None:
        scratch_override = run_dir / "override"
        scratch_override.mkdir(exist_ok=True)
        scratch_mutator(scratch_override)
    if absolute_process_override:
        output = run_dir / "override"
    else:
        output = base / "output"
    output.mkdir()
    fixture = Fixture(
        root=fixture_root,
        divine_resref=previous.fixture.divine_resref,
        haste_resref=previous.fixture.haste_resref,
    )
    source_snapshot = _raw_file_tree(fixture_root)
    command = [
        str(WEIDU), str(HARNESS), "--nogame", "--force-install-list", PHASE_COMPONENT[phase],
        "--args", str(PRODUCTION_TPA), "--args", str(fixture_root), "--args", str(output),
        "--args", previous.mode, "--args", fixture.divine_resref, "--args", fixture.haste_resref,
        "--no-exit-pause", "--quick-log",
    ]
    process = subprocess.run(
        command,
        cwd=run_dir,
        capture_output=True,
        text=True,
        timeout=45,
        check=False,
    )
    return HarnessResult(
        temporary=temporary,
        fixture=fixture,
        output=output,
        run_dir=run_dir,
        mode=previous.mode,
        variant=previous.variant,
        process=process,
        source_snapshot=source_snapshot,
    )


class FixtureFormatTests(unittest.TestCase):
    def test_preserved_spl_and_2da_fixtures_parse(self) -> None:
        holy = read_spl(ORIGINALS / "OHTMPS1.spl.orig")
        divine = read_spl(ORIGINALS / "SPPR412.spl.orig")
        haste = read_spl(ORIGINALS / "SPWI613.spl.orig")
        clab = read_2da(ORIGINALS / "OHTEMPUS.2da.orig")

        self.assertEqual(20, len(holy.abilities))
        self.assertEqual(list(range(1, 21)), [a.required_level for a in holy.abilities])
        self.assertEqual(14, len(divine.abilities))
        self.assertEqual(1, len(haste.abilities))
        self.assertEqual(
            1,
            sum(
                effect.opcode == 1
                and effect.parameter1 == 1
                and effect.parameter2 == 0
                for effect in haste.abilities[0].effects
            ),
        )
        self.assertEqual("GA_OHTMPS1", clab.cell("ABILITY1", "26"))
        self.assertEqual("AP_CDHLYSYM", clab.cell("ABILITY1", "25"))

    def test_semantic_spl_variants_and_eff_v2_round_trip(self) -> None:
        for variant in (
            "additive",
            "doubling",
            "doubling317",
            "mixed",
            "duplicate_additive",
            "missing",
            "probabilistic",
            "conditional",
            "inconsistent",
        ):
            with self.subTest(variant=variant):
                spell, _ = _improved_haste_fixture(variant, "SPWI699")
                self.assertEqual(spell, SplFile.from_bytes(spell.to_bytes()))
                self.assertEqual(
                    2 if variant == "inconsistent" else 3,
                    len(spell.abilities),
                    "fixture must exercise every IH header",
                )
                if variant == "additive":
                    donors = [
                        [
                            (index, effect)
                            for index, effect in enumerate(ability.effects)
                            if effect.opcode == 1
                            and effect.parameter1 == 1
                            and effect.parameter2 == 0
                        ]
                        for ability in spell.abilities
                    ]
                    self.assertTrue(all(len(header) == 1 for header in donors))
                    self.assertEqual(3, len({header[0][0] for header in donors}))
                    self.assertEqual(3, len({header[0][1].duration for header in donors}))

        effect = EffV2(
            opcode=326,
            target=1,
            power=0,
            parameter1=201,
            parameter2=7,
            timing=1,
            duration=0,
            probability1=100,
            probability2=0,
            resource="CBRTEST",
            flags=0xA5C39E71,
        )
        encoded_eff = effect.to_bytes()
        self.assertEqual(0xA5C39E71, int.from_bytes(encoded_eff[0x5C:0x60], "little"))
        parsed_eff = EffV2.from_bytes(encoded_eff)
        self.assertEqual(effect, parsed_eff)
        self.assertEqual(0xA5C39E71, parsed_eff.flags)

        embedded = SplEffect(opcode=326, resist_dispel=3)
        encoded_embedded = embedded.to_bytes()
        self.assertEqual(3, encoded_embedded[0x0D])
        self.assertEqual(3, SplEffect.from_bytes(encoded_embedded).resist_dispel)
        self.assertFalse(hasattr(parsed_eff, "resist_dispel"))

    def test_condition_graph_follows_opcode_146_from_repeating_eff(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cbr-strength-graph-") as temporary:
            fixture = build_fixture(
                Path(temporary),
                "additive",
                strength_helpers_layout="exact",
            )
            evaluator = _ConditionGraph(fixture.root)
            pulse = read_eff_v2(
                fixture.root / f"{STRENGTH_PULSE_BY_FLOOR[18]}.eff"
            )
            self.assertEqual(
                (18, 100),
                evaluator._apply((pulse,), strength=10, exceptional=0),
                "the test evaluator must traverse opcode 146 before graph assertions",
            )

    def test_tlk_writer_detection_covers_command_families(self) -> None:
        source = """
        // SAY_EVALUATED STRING_SET_EVALUATE REPLACE_SAY
        /* TLK_WRITE_SUFFIX */
        OUTER_SPRINT harmless ~SAY_EVALUATED is only message text~
        SAY_EVALUATED @1
        STRING_SET_EVALUATE 42 @2
        REPLACE_SAY_EVALUATED ~DIALOG~ 0 @3
        TLK_WRITE_EVALUATED ~elsewhere.tlk~
        """
        self.assertEqual(
            [
                "REPLACE_SAY_EVALUATED",
                "SAY_EVALUATED",
                "STRING_SET_EVALUATE",
                "TLK_WRITE_EVALUATED",
            ],
            _tlk_writes(source),
        )

    def test_bridge_condition_reader_rejects_malformed_graphs(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cbr-bridge-graph-") as temporary:
            root = Path(temporary)
            helper_resref = "CBRAPR6"
            helper = make_spl(
                (
                    SplAbility(
                        required_level=1,
                        target=5,
                        projectile=0,
                        effects=(
                            _helper_effect(321, parameter2=2, resource=helper_resref),
                            _helper_effect(
                                1,
                                parameter1=6,
                                parameter2=0,
                                timing=0,
                                resist_dispel=2,
                                duration=1,
                            ),
                        ),
                    ),
                )
            )
            write_spl(root / f"{helper_resref}.SPL", helper)
            valid = EffV2(
                opcode=326,
                target=2,
                power=4,
                parameter1=210,
                parameter2=4,
                timing=1,
                resource=helper_resref,
                flags=2,
            )
            (root / "VALID.EFF").write_bytes(valid.to_bytes())
            self.assertEqual(
                6,
                _read_conditional_apr_edge(
                    root,
                    "VALID",
                    expected_state=210,
                    active_row=4,
                    expected_helper=helper_resref,
                ),
            )

            invalid = {
                "ALWAYS": dataclasses.replace(valid, opcode=146),
                "WRONGST": dataclasses.replace(valid, parameter1=211),
                "WRONGROW": dataclasses.replace(valid, parameter2=5),
            }
            for resref, effect in invalid.items():
                (root / f"{resref}.EFF").write_bytes(effect.to_bytes())
                with self.subTest(resref=resref), self.assertRaises(AssertionError):
                    _read_conditional_apr_edge(
                        root,
                        resref,
                        expected_state=210,
                        active_row=4,
                        expected_helper=helper_resref,
                    )
            for resref in (helper_resref, "MISSING"):
                with self.subTest(resref=resref), self.assertRaises(AssertionError):
                    _read_conditional_apr_edge(
                        root,
                        resref,
                        expected_state=210,
                        active_row=4,
                        expected_helper=helper_resref,
                    )

    def test_ids_resolution_uses_fixture_symbols(self) -> None:
        ids = IdsFile(entries=((1388, "CLERIC_HOLY_POWER"), (2788, "WIZARD_IMPROVED_HASTE")))
        self.assertEqual(1388, ids.value("cleric_holy_power"))
        self.assertEqual("SPPR388", spell_resref(ids.value("CLERIC_HOLY_POWER"), "CLERIC_HOLY_POWER"))
        self.assertEqual("SPWI788", spell_resref(ids.value("WIZARD_IMPROVED_HASTE"), "WIZARD_IMPROVED_HASTE"))


class HarnessSmokeTests(unittest.TestCase):
    def test_nogame_smoke_copies_without_game_or_tlk(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cbr-weidu-smoke-") as temporary:
            root = Path(temporary)
            run_dir = root / "run"
            run_dir.mkdir()
            output = root / "smoke.out"
            command = [
                str(WEIDU),
                str(HARNESS),
                "--nogame",
                "--force-install-list",
                "0",
                "--args",
                str(ORIGINALS / "OHTEMPUS.2da.orig"),
                "--args",
                str(output),
                "--no-exit-pause",
                "--quick-log",
            ]
            process = subprocess.run(
                command,
                cwd=run_dir,
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            self.assertEqual(0, process.returncode, process.stdout + process.stderr)
            self.assertEqual(
                (ORIGINALS / "OHTEMPUS.2da.orig").read_bytes(), output.read_bytes()
            )
            self.assertFalse(any(root.rglob("dialog.tlk")))
            self.assertFalse(any(root.rglob("chitin.key")))
            harness_source = HARNESS.read_text(encoding="utf-8").upper()
            self.assertNotIn("COPY_EXISTING", harness_source)
            self.assertNotIn("FILE_EXISTS_IN_GAME", harness_source)


class TempusHolyPowerTests(unittest.TestCase):
    _results: list[HarnessResult] = []

    @classmethod
    def tearDownClass(cls) -> None:
        for result in cls._results:
            result.temporary.cleanup()

    def run_case(
        self,
        variant: str = "additive",
        mode: str = "auto",
        *,
        alternate_ids: bool = False,
        phase: str = "full",
        splstate_layout: str = "free",
        splprot_layout: str = "default",
        holy_layout: str = "original",
        strength_helpers_layout: str | None = None,
        clab_layout: str = "original",
        relative_output: bool = False,
        absolute_process_override: bool = False,
        reserved_itm_resref: str | None = None,
        scratch_reserved_resref: str | None = None,
        casting_sentinels: bool = False,
        effect_partition_layout: str = "canonical",
        dangling_apr_owner: str | None = None,
    ) -> HarnessResult:
        result = _run_harness(
            variant,
            mode,
            alternate_ids=alternate_ids,
            phase=phase,
            splstate_layout=splstate_layout,
            splprot_layout=splprot_layout,
            holy_layout=holy_layout,
            strength_helpers_layout=strength_helpers_layout,
            clab_layout=clab_layout,
            relative_output=relative_output,
            absolute_process_override=absolute_process_override,
            reserved_itm_resref=reserved_itm_resref,
            scratch_reserved_resref=scratch_reserved_resref,
            casting_sentinels=casting_sentinels,
            effect_partition_layout=effect_partition_layout,
            dangling_apr_owner=dangling_apr_owner,
        )
        self._results.append(result)
        return result

    def assert_success(self, result: HarnessResult) -> None:
        if not PRODUCTION_TPA.is_file():
            self.fail(
                f"{result.variant}/{result.mode}: missing production library "
                f"{PRODUCTION_TPA}; isolated harness transcript:\n{result.transcript}"
            )
        self.assertTrue(
            result.succeeded,
            f"{result.variant}/{result.mode}: transformation failed\n{result.transcript}",
        )

    def assert_rejected(self, result: HarnessResult) -> None:
        if not PRODUCTION_TPA.is_file():
            self.fail(
                f"{result.variant}/{result.mode}: cannot verify semantic rejection because "
                f"production library is missing: {PRODUCTION_TPA}\n{result.transcript}"
            )
        self.assertFalse(
            result.succeeded,
            f"{result.variant}/{result.mode}: malformed Improved Haste was accepted",
        )
        transcript = result.transcript.upper()
        self.assertIn(result.fixture.haste_resref, transcript)
        self.assertRegex(transcript, r"IMPROVED[ _-]?HASTE|HEADER|OPCODE|PROBABIL")

    def assert_allocation_rejected(self, result: HarnessResult) -> None:
        if not PRODUCTION_TPA.is_file():
            self.fail(
                "cannot verify SPLSTATE rejection because production library is missing: "
                f"{PRODUCTION_TPA}\n{result.transcript}"
            )
        self.assertFalse(result.succeeded, "invalid SPLSTATE layout was accepted")
        self.assertRegex(result.transcript.upper(), r"SPLSTATE|SPELL[ _-]?STATE|COLLIS|EXHAUST")

    def test_improved_haste_classification(self) -> None:
        for variant in ("additive", "doubling", "doubling317"):
            with self.subTest(variant=variant, expected="accepted"):
                self.assert_success(self.run_case(variant, "auto", phase="classify"))
        for variant in ("mixed", "duplicate_additive", "missing", "probabilistic", "conditional", "inconsistent"):
            for mode in ("auto", "force_double", "force_additive"):
                with self.subTest(variant=variant, mode=mode, expected="rejected"):
                    self.assert_rejected(self.run_case(variant, mode, phase="classify"))

    def test_auto_vs_forced_modes(self) -> None:
        self.assert_success(self.run_case("additive", "auto", phase="classify"))
        self.assert_success(self.run_case("additive", "force_additive", phase="classify"))
        self.assert_rejected(self.run_case("additive", "force_double", phase="classify"))
        self.assert_success(self.run_case("doubling", "auto", phase="classify"))
        self.assert_success(self.run_case("doubling", "force_double", phase="classify"))
        self.assert_rejected(self.run_case("doubling", "force_additive", phase="classify"))

    def test_rejects_unsafe_additive_donor_delivery_metadata(self) -> None:
        variants = (
            "delayed_additive",
            "save_conditioned_additive",
            "metadata_additive",
            "mr_resistible_additive",
        )
        for variant in variants:
            for mode in ("auto", "force_additive"):
                with self.subTest(variant=variant, mode=mode):
                    result = self.run_case(variant, mode, phase="classify")
                    self.assert_rejected(result)
                    self.assertRegex(
                        result.transcript,
                        r"(?i)IMPROVED[ _-]?HASTE|ADDITIVE|DONOR|TIMING|SAVE|METADATA|RESIST",
                    )

    def test_rejects_nonpartitioned_parent_effect_tables_before_writes(self) -> None:
        for layout in ("ih_orphan", "ih_overlap"):
            with self.subTest(layout=layout):
                result = self.run_case(
                    "additive",
                    phase="full",
                    effect_partition_layout=layout,
                )
                self.assert_rejected(result)
                self.assertRegex(result.transcript, r"(?i)EFFECT|TABLE|PARTITION|ORPHAN|OVERLAP|REFER")
                self.assertEqual({}, _raw_file_tree(result.output))

    def test_doubling_rejects_dangling_additive_bridge_artifacts(self) -> None:
        for owner in ("holy", "ih"):
            with self.subTest(owner=owner):
                result = self.run_case(
                    "doubling",
                    phase="full",
                    holy_layout="valid_30",
                    dangling_apr_owner=owner,
                )
                self.assertFalse(result.succeeded, f"dangling {owner} APR bridge was accepted")
                self.assertRegex(result.transcript, r"(?i)APR|BRIDGE|CBRAPR|DANGL|DOUBL")
                self.assertEqual({}, _raw_file_tree(result.output))
        private_states = self.run_case(
            "doubling",
            phase="full",
            holy_layout="valid_30",
            splstate_layout="reuse",
        )
        self.assertFalse(private_states.succeeded, "doubling accepted private APR bridge states")
        self.assertRegex(private_states.transcript, r"(?i)SPLSTATE|PRIVATE|CBR_TEMPUS|DOUBL|BRIDGE")
        self.assertEqual({}, _raw_file_tree(private_states.output))

    def test_state_and_splprot_allocation(self) -> None:
        result = self.run_case(phase="allocate")
        self.assert_success(result)
        before_ids = read_ids(result.fixture.root / "SPLSTATE.IDS")
        after_ids = read_ids(result.output / "SPLSTATE.IDS")
        private = [
            (value, symbol.upper())
            for value, symbol in after_ids.entries
            if symbol.upper() in PRIVATE_STATE_SYMBOLS
        ]
        self.assertEqual(set(PRIVATE_STATE_SYMBOLS), {symbol for _, symbol in private})
        self.assertEqual(4, len(private))
        self.assertEqual(len(private), len({value for value, _ in private}))
        self.assertTrue(all(0 <= value <= 255 for value, _ in private))
        self.assertTrue({value for value, _ in private}.isdisjoint(before_ids.values()))

        before = read_2da(result.fixture.root / "SPLPROT.2DA")
        after = read_2da(result.output / "SPLPROT.2DA")
        self.assertEqual(before.rows, after.rows[: len(before.rows)], "SPLPROT must be append-only")
        semantics = [tuple(int(value, 0) for value in row) for _, row in after.rows]
        for required in ((0x112, -1, 1), (36, -1, 2), (36, -1, 1), (37, -1, 2)):
            with self.subTest(required=required):
                self.assertEqual(1, semantics.count(required))
        second = _rerun_harness(result, phase="allocate")
        self._results.append(second)
        self.assert_success(second)
        self.assertEqual(after_ids.canonical(), read_ids(second.output / "SPLSTATE.IDS").canonical())
        self.assertEqual(after.canonical(), read_2da(second.output / "SPLPROT.2DA").canonical())
        self.assertEqual(
            (result.output / "SPLSTATE.IDS").read_bytes(),
            (second.output / "SPLSTATE.IDS").read_bytes(),
            "second allocation changed raw SPLSTATE.IDS bytes",
        )
        self.assertEqual(
            (result.output / "SPLPROT.2DA").read_bytes(),
            (second.output / "SPLPROT.2DA").read_bytes(),
            "second allocation changed raw SPLPROT.2DA bytes",
        )

        reuse = self.run_case(phase="allocate", splstate_layout="reuse")
        self.assert_success(reuse)
        reuse_before = read_ids(reuse.fixture.root / "SPLSTATE.IDS")
        reuse_after = read_ids(reuse.output / "SPLSTATE.IDS")
        for symbol in PRIVATE_STATE_SYMBOLS:
            with self.subTest(layout="reuse", symbol=symbol):
                self.assertEqual(reuse_before.value(symbol), reuse_after.value(symbol))
        self.assertEqual(reuse_before.canonical(), reuse_after.canonical())
        self.assertEqual(
            (reuse.fixture.root / "SPLSTATE.IDS").read_bytes(),
            (reuse.output / "SPLSTATE.IDS").read_bytes(),
            "unique preallocated private states must be reused without rewriting SPLSTATE.IDS",
        )

    def test_splprot_reuses_lowest_duplicate_semantic_alias_without_rewrite(self) -> None:
        result = self.run_case(
            phase="allocate",
            splprot_layout="duplicate_semantics",
        )
        self.assert_success(result)
        before = result.fixture.root / "SPLPROT.2DA"
        after = result.output / "SPLPROT.2DA"
        self.assertEqual(
            before.read_bytes(),
            after.read_bytes(),
            "existing duplicate semantic aliases must be reused without appending or rewriting",
        )
        table = read_2da(after)
        semantics = [tuple(int(value, 0) for value in row) for _, row in table.rows]
        self.assertEqual(
            [1, 4],
            [i for i, row in enumerate(semantics) if row == ACTIVE_SPLSTATE_SEMANTIC],
        )
        self.assertEqual(
            [5, 6],
            [i for i, row in enumerate(semantics) if row == STR_EQ_SEMANTIC],
        )
        self.assertEqual(1, _active_splstate_row(result.output))

    def test_splprot_rejects_nonnumeric_predicate_rows(self) -> None:
        result = self.run_case(
            phase="allocate",
            splprot_layout="malformed_numeric",
        )
        self.assertFalse(result.succeeded, result.transcript)
        self.assertRegex(result.transcript, r"(?i)SPLPROT|NUMERIC|STAT|VALUE|RELATION|MALFORM")
        self.assertEqual({}, _raw_file_tree(result.output))

    def test_doubling_allocation_skips_additive_bridge_states(self) -> None:
        result = self.run_case(
            "doubling",
            phase="allocate",
            splprot_layout="no_active_state",
        )
        self.assert_success(result)
        before_ids = read_ids(result.fixture.root / "SPLSTATE.IDS")
        after_ids = read_ids(result.output / "SPLSTATE.IDS")
        self.assertEqual(before_ids.canonical(), after_ids.canonical())
        after_symbols = {symbol.upper() for _, symbol in after_ids.entries}
        self.assertTrue(
            set(PRIVATE_STATE_SYMBOLS).isdisjoint(after_symbols),
            "true-doubling Improved Haste must not allocate additive bridge states",
        )
        before_semantics = [
            tuple(int(value, 0) for value in row)
            for _, row in read_2da(result.fixture.root / "SPLPROT.2DA").rows
        ]
        after_semantics = [
            tuple(int(value, 0) for value in row)
            for _, row in read_2da(result.output / "SPLPROT.2DA").rows
        ]
        self.assertEqual(
            before_semantics.count(ACTIVE_SPLSTATE_SEMANTIC),
            after_semantics.count(ACTIVE_SPLSTATE_SEMANTIC),
            "doubling mode must not create active-Improved-Haste SPLSTATE infrastructure",
        )
        for required in ((36, -1, 2), (36, -1, 1), (37, -1, 2)):
            with self.subTest(required=required):
                self.assertEqual(1, after_semantics.count(required))

    def test_partial_clean_splstates_are_reused_and_completed(self) -> None:
        result = self.run_case(phase="allocate", splstate_layout="partial_clean")
        self.assert_success(result)
        before = read_ids(result.fixture.root / "SPLSTATE.IDS")
        after = read_ids(result.output / "SPLSTATE.IDS")
        after_symbols = {symbol.upper() for _, symbol in after.entries}
        self.assertEqual(set(PRIVATE_STATE_SYMBOLS), after_symbols & set(PRIVATE_STATE_SYMBOLS))
        private_values = [after.value(symbol) for symbol in PRIVATE_STATE_SYMBOLS]
        self.assertEqual(4, len(set(private_values)))
        for symbol in (PRIVATE_STATE_SYMBOLS[0], PRIVATE_STATE_SYMBOLS[2]):
            with self.subTest(symbol=symbol):
                self.assertEqual(before.value(symbol), after.value(symbol))
        new_symbols = (PRIVATE_STATE_SYMBOLS[1], PRIVATE_STATE_SYMBOLS[3])
        self.assertTrue(
            {after.value(symbol) for symbol in new_symbols}.isdisjoint(before.values())
        )

    def test_splstate_hex_rows_are_counted_for_collision_and_reuse(self) -> None:
        collision = self.run_case(phase="allocate", splstate_layout="hex_collision")
        self.assert_success(collision)
        collision_ids = read_ids(collision.output / "SPLSTATE.IDS")
        values = [value for value, _ in collision_ids.entries]
        self.assertEqual(len(values), len(set(values)), "hex 0xFF row was numerically aliased")
        self.assertNotIn(
            255,
            [collision_ids.value(symbol) for symbol in PRIVATE_STATE_SYMBOLS],
        )

        reuse = self.run_case(phase="allocate", splstate_layout="hex_reuse")
        self.assert_success(reuse)
        reuse_ids = read_ids(reuse.output / "SPLSTATE.IDS")
        self.assertEqual(
            [240, 241, 242, 243],
            [reuse_ids.value(symbol) for symbol in PRIVATE_STATE_SYMBOLS],
        )
        self.assertEqual(
            (reuse.fixture.root / "SPLSTATE.IDS").read_bytes(),
            (reuse.output / "SPLSTATE.IDS").read_bytes(),
            "hex/leading-whitespace private states were not reused byte-identically",
        )

    def test_rejects_stale_cloned_30_header_holy_power(self) -> None:
        result = self.run_case(phase="classify", holy_layout="stale_30")
        self.assertFalse(result.succeeded, "stale cloned 30-header Holy Power was accepted")
        self.assertRegex(
            result.transcript.upper(),
            r"OHTMPS1|HOLY[ _-]?POWER|30[ _-]?HEADER|THAC0|DURATION|APR",
        )

    def test_rejects_ambiguous_original_20_holy_power(self) -> None:
        for holy_layout in (
            "original_bad_cleanup_order",
            "original_bad_thac0",
            "original_bad_hp_duration",
            "original_bad_strength",
            "original_bad_owned_pulse",
            "original_duplicate_owned_thac0",
        ):
            with self.subTest(holy_layout=holy_layout):
                result = self.run_case(phase="classify", holy_layout=holy_layout)
                self.assertFalse(
                    result.succeeded,
                    f"ambiguous original20 Holy Power was accepted: {holy_layout}",
                )
                self.assertRegex(
                    result.transcript.upper(),
                    r"OHTMPS1|HOLY[ _-]?POWER|20[ _-]?HEADER|LEGACY|CLEANUP|THAC0|STRENGTH|APR",
                )

    def test_accepts_exact_future_30_header_holy_power(self) -> None:
        result = self.run_case(
            phase="classify",
            alternate_ids=True,
            holy_layout="valid_30",
        )
        self.assert_success(result)
        holy = read_spl(result.fixture.root / f"{HOLY_RESREF}.SPL")
        self.assertEqual(30, len(holy.abilities))
        for level, ability in enumerate(holy.abilities, start=1):
            with self.subTest(level=level):
                duration = 18 if level <= 6 else 24 if level <= 12 else 30
                owned_pulses = [
                    effect
                    for effect in ability.effects
                    if effect.opcode == 272
                    and effect.resource.upper() in STRENGTH_PULSE_RESREFS
                ]
                self.assertEqual(1, len(owned_pulses))
                pulse = owned_pulses[0]
                self.assertEqual(_strength_pulse_resref(level), pulse.resource.upper())
                self.assertEqual(
                    (1, 4, 1, 3, 0, 3, duration, 100, 0, 0, 0, 0, 0, 0),
                    (
                        pulse.target,
                        pulse.power,
                        pulse.parameter1,
                        pulse.parameter2,
                        pulse.timing,
                        pulse.resist_dispel,
                        pulse.duration,
                        pulse.probability1,
                        pulse.probability2,
                        pulse.dice_number,
                        pulse.dice_size,
                        pulse.save_type,
                        pulse.save_bonus,
                        pulse.special,
                    ),
                )
                foreign_owned_bytes = {
                    effect.to_bytes() for effect in _foreign_owned_opcode_pack()
                }
                present_foreign_owned_bytes = {
                    effect.to_bytes()
                    for effect in ability.effects
                    if effect.resource.upper() in FOREIGN_OWNED_OPCODE_RESREFS
                }
                self.assertEqual(
                    foreign_owned_bytes if level >= 20 else set(),
                    present_foreign_owned_bytes,
                    "the foreign opcode pack must remain exact in header 20 and its clones",
                )
                self.assertEqual(
                    level >= 20,
                    any(
                        effect.opcode == 272
                        and effect.resource.upper() == FOREIGN_PULSE_RESREF
                        for effect in ability.effects
                    ),
                    "header 20 foreign opcode 272 must clone only into levels 21-30",
                )
        self.assertTrue(
            any(
                effect.resource.upper() == SENTINEL_RESOURCE
                for ability in holy.abilities
                for effect in ability.effects
            ),
            "valid patched fixture must retain a foreign effect",
        )

    def test_rejects_malformed_future_strength_pulses(self) -> None:
        for holy_layout in (
            "valid_30_missing_pulse",
            "valid_30_duplicate_pulse",
            "valid_30_wrong_tier_pulse",
            "valid_30_bad_p1",
            "valid_30_bad_p2",
            "valid_30_bad_timing",
            "valid_30_bad_resist_dispel",
            "valid_30_bad_duration",
            "valid_30_bad_target",
            "valid_30_bad_power",
            "valid_30_bad_probability1",
            "valid_30_bad_probability2",
            "valid_30_bad_dice_number",
            "valid_30_bad_dice_size",
            "valid_30_bad_save_type",
            "valid_30_bad_save_bonus",
            "valid_30_bad_special",
        ):
            with self.subTest(holy_layout=holy_layout):
                result = self.run_case(
                    phase="classify",
                    alternate_ids=True,
                    holy_layout=holy_layout,
                )
                self.assertFalse(
                    result.succeeded,
                    f"malformed owned Strength pulse was accepted: {holy_layout}",
                )
                self.assertRegex(
                    result.transcript.upper(),
                    r"OHTMPS1|30[ _-]?HEADER|STRENGTH|PULSE|OPCODE[ _-]?272|CBRSE",
                )

    def test_rejects_malformed_future_recast_cleanup(self) -> None:
        for holy_layout in (
            "valid_30_missing_recast_cleanup",
            "valid_30_duplicate_recast_cleanup",
            "valid_30_misplaced_recast_cleanup",
        ):
            with self.subTest(holy_layout=holy_layout):
                result = self.run_case(
                    phase="classify",
                    holy_layout=holy_layout,
                )
                self.assertFalse(
                    result.succeeded,
                    f"malformed setter recast cleanup was accepted: {holy_layout}",
                )
                self.assertRegex(
                    result.transcript.upper(),
                    r"OHTMPS1|30[ _-]?HEADER|STRENGTH|CLEAN|RECAST|CBRST|OPCODE[ _-]?321",
                )

    def test_rejects_malformed_future_strength_expiry_cleanup(self) -> None:
        for holy_layout in (
            "valid_30_missing_expiry_cleanup",
            "valid_30_duplicate_expiry_cleanup",
            "valid_30_bad_expiry_duration",
        ):
            with self.subTest(holy_layout=holy_layout):
                result = self.run_case(
                    phase="classify",
                    holy_layout=holy_layout,
                )
                self.assertFalse(
                    result.succeeded,
                    f"malformed setter expiry cleanup was accepted: {holy_layout}",
                )
                self.assertRegex(
                    result.transcript.upper(),
                    r"OHTMPS1|30[ _-]?HEADER|STRENGTH|CLEAN|EXPIR|CBRST|OPCODE[ _-]?321",
                )

    def test_original_20_rejects_reserved_strength_helper_collision(self) -> None:
        result = self.run_case(
            phase="classify",
            strength_helpers_layout="exact",
        )
        self.assertFalse(result.succeeded, "original20 accepted reserved helper resources")
        self.assertRegex(
            result.transcript.upper(),
            r"HELPER|RESERVED|COLLIS|CBRST|CBRSC|CBRSE|CBRSX",
        )

    def test_rejects_reserved_private_itm_namespace_collisions(self) -> None:
        accepted: list[tuple[str, str]] = []
        for holy_layout in ("original", "valid_30"):
            for resref in RESERVED_PRIVATE_RESREFS:
                result = self.run_case(
                    phase="classify",
                    holy_layout=holy_layout,
                    reserved_itm_resref=resref,
                )
                if result.succeeded:
                    accepted.append((holy_layout, resref))
                else:
                    self.assertRegex(
                        result.transcript.upper(),
                        r"ITM|ITEM|NAMESPACE|RESERVED|COLLIS",
                    )
        self.assertEqual(
            [],
            accepted,
            "reserved private resrefs accepted same-name ITM resources",
        )

    def test_rejects_parent_buff_itm_cleanup_collisions(self) -> None:
        divine_resref = spell_resref(1499, "CLERIC_HOLY_POWER")
        for resref in (HOLY_RESREF, divine_resref):
            with self.subTest(resref=resref):
                result = self.run_case(
                    phase="classify",
                    reserved_itm_resref=resref,
                )
                self.assertFalse(
                    result.succeeded,
                    f"opcode-321 parent cleanup accepted collateral {resref}.ITM",
                )
                self.assertRegex(result.transcript.upper(), r"ITM|ITEM|PARENT|COLLIS|CLEANUP")
        process = _run_key_collision_harness(HOLY_RESREF, "ITM")
        self.assertNotEqual(0, process.returncode, process.stdout + process.stderr)
        self.assertRegex((process.stdout + process.stderr).upper(), r"OHTMPS1|ITM|COLLIS|CLEANUP")

    def test_rejects_key_only_private_namespace_collisions_for_all_extensions(self) -> None:
        accepted: list[str] = []
        for resref in RESERVED_PRIVATE_RESREFS:
            for extension in KEY_RESOURCE_TYPE_BY_EXTENSION:
                with self.subTest(resref=resref, extension=extension):
                    process = _run_key_collision_harness(resref, extension)
                    transcript = process.stdout + process.stderr
                    if process.returncode == 0:
                        accepted.append(f"{resref}.{extension}")
                    else:
                        self.assertRegex(
                            transcript.upper(),
                            rf"{resref}.*{extension}|{extension}.*{resref}",
                        )
                        self.assertRegex(
                            transcript.upper(),
                            r"KEY|NAMESPACE|RESERVED|COLLIS",
                        )
        self.assertEqual(
            [],
            accepted,
            "private resources visible only through chitin.key were accepted",
        )

    def test_recognized_30_accepts_only_exact_strength_helpers(self) -> None:
        exact = self.run_case(
            phase="classify",
            holy_layout="valid_30",
            strength_helpers_layout="exact",
        )
        self.assert_success(exact)

        for layout in ("missing", "corrupt", "wrong_extension", "cross_extension"):
            with self.subTest(layout=layout):
                malformed = self.run_case(
                    phase="classify",
                    holy_layout="valid_30",
                    strength_helpers_layout=layout,
                )
                self.assertFalse(
                    malformed.succeeded,
                    f"recognized30 accepted malformed Strength helpers: {layout}",
                )
                self.assertRegex(
                    malformed.transcript.upper(),
                    r"HELPER|STRENGTH|COLLIS|MISSING|WRONG|CBRST|CBRSC|CBRSE|CBRSX",
                )

    def test_recognized_30_rejects_eff_timing_high_word(self) -> None:
        malformed = self.run_case(
            phase="classify",
            holy_layout="valid_30",
            strength_helpers_layout="timing_high_word",
        )
        self.assertFalse(
            malformed.succeeded,
            "recognized30 accepted an EFF V2 timing value with a nonzero high word",
        )
        self.assertRegex(
            malformed.transcript.upper(),
            r"HELPER|STRENGTH|TIMING|CBRSE",
        )

    def test_recognized_30_rejects_noncanonical_helper_bytes(self) -> None:
        accepted: list[str] = []
        for layout in (
            "eff_school_corrupt",
            "eff_parent_resource_corrupt",
            "spl_main_header_corrupt",
            "spl_ability_header_corrupt",
        ):
            result = self.run_case(
                phase="classify",
                holy_layout="valid_30",
                strength_helpers_layout=layout,
            )
            if result.succeeded:
                accepted.append(layout)
            else:
                self.assertRegex(
                    result.transcript.upper(),
                    r"HELPER|STRENGTH|CANON|HEADER|EFF|SPL|CBRST|CBRSE",
                )
        self.assertEqual(
            [],
            accepted,
            "recognized30 accepted noncanonical bytes in reserved helper resources",
        )

    def test_rejects_splstate_collisions_and_exhaustion(self) -> None:
        for layout in (
            "duplicate_private_symbol",
            "shared_private_value",
            "exhausted",
        ):
            with self.subTest(layout=layout):
                self.assert_allocation_rejected(
                    self.run_case(phase="allocate", splstate_layout=layout)
                )

    def test_rejects_partial_clab_cap_and_accepts_complete_cap(self) -> None:
        partial = self.run_case(phase="classify", clab_layout="partial")
        self.assertFalse(partial.succeeded, "partially capped OHTEMPUS.2DA was accepted")
        self.assertRegex(partial.transcript.upper(), r"CLAB|OHTEMPUS|PARTIALLY")

        capped = self.run_case(phase="classify", clab_layout="capped")
        self.assert_success(capped)
        self.assertEqual(
            (capped.fixture.root / CLAB_NAME).read_bytes(),
            (capped.output / CLAB_NAME).read_bytes(),
            "preflight rewrote an already-capped CLAB",
        )

    def test_progression(self) -> None:
        result = self.run_case(phase="progression")
        self.assert_success(result)
        holy = read_spl(result.output / f"{HOLY_RESREF}.SPL")
        self.assertEqual(30, len(holy.abilities))
        self.assertEqual(list(range(1, 31)), [a.required_level for a in holy.abilities])
        self.assertEqual(holy.abilities[-1], holy.ability_for_level(31))
        self.assertEqual(holy.abilities[-1], holy.ability_for_level(50))

        for level in range(1, 31):
            with self.subTest(level=level):
                duration = _tier_duration(level)
                thac0 = max(0, 21 - level)
                hp = min(level, 30)
                apr_key = None if level <= 6 else 6 if level <= 12 else 1 if level <= 24 else 7
                effects = holy.ability_for_level(level).effects
                thac0_signature = _owned_timed_effect(54, thac0, 1, duration).canonical()
                hp_signature = _owned_timed_effect(18, hp, 0, duration).canonical()
                thac0_effects = [
                    effect for effect in effects if effect.canonical() == thac0_signature
                ]
                hp_effects = [
                    effect for effect in effects if effect.canonical() == hp_signature
                ]
                self.assertEqual(1, len(thac0_effects), "THAC0 mechanic must be unique")
                self.assertEqual(1, len(hp_effects), "temporary HP mechanic must be unique")
                thac0_effect = thac0_effects[0]
                hp_effect = hp_effects[0]
                self.assertEqual(
                    (thac0, 1, 0, duration, 3),
                    (
                        thac0_effect.parameter1,
                        thac0_effect.parameter2,
                        thac0_effect.timing,
                        thac0_effect.duration,
                        thac0_effect.resist_dispel,
                    ),
                    "THAC0 must be one flat, temporary, dispellable mechanic",
                )
                self.assertEqual(
                    (hp, 0, 0, duration, 3),
                    (
                        hp_effect.parameter1,
                        hp_effect.parameter2,
                        hp_effect.timing,
                        hp_effect.duration,
                        hp_effect.resist_dispel,
                    ),
                    "HP must be one cumulative, temporary, dispellable mechanic",
                )
                apr = (
                    []
                    if apr_key is None
                    else [
                        effect
                        for effect in effects
                        if effect.canonical()
                        == _owned_timed_effect(
                            1, apr_key, 0, duration
                        ).canonical()
                    ]
                )
                if apr_key is None:
                    self.assertEqual([], apr)
                else:
                    self.assertEqual([(apr_key, duration)], [(e.parameter1, e.duration) for e in apr])
                    self.assertTrue(all(e.resist_dispel == 3 for e in apr))

    def test_strength_floor(self) -> None:
        result = self.run_case(phase="progression")
        self.assert_success(result)
        holy = read_spl(result.output / f"{HOLY_RESREF}.SPL")
        for level, floor, exceptional, duration in ((1, 18, 100, 18), (7, 18, 100, 24), (13, 19, 0, 30), (19, 20, 0, 30), (25, 21, 0, 30)):
            with self.subTest(level=level):
                effects = holy.ability_for_level(level).effects
                legacy_duration = min(level, 20) * 6
                legacy_strength_signatures = {
                    _owned_timed_effect(44, 18, 1, legacy_duration).canonical(),
                    _owned_timed_effect(97, 100, 1, legacy_duration).canonical(),
                }
                self.assertFalse(
                    any(
                        effect.canonical() in legacy_strength_signatures
                        for effect in effects
                    ),
                    "floor may not retain an owned unconditional flat set",
                )
                pulses = [e for e in effects if e.opcode == 272 and e.parameter1 == 1 and e.parameter2 == 3]
                self.assertTrue(any(e.duration == duration for e in pulses), "missing full-duration one-second floor heartbeat")
                evaluator = _ConditionGraph(result.output)
                immediate = evaluator.apply_immediate(holy.ability_for_level(level), strength=10, exceptional=0)
                self.assertEqual((floor, exceptional), immediate, "missing immediate Strength-floor kick")
                low = evaluator.apply_ability(holy.ability_for_level(level), strength=10, exceptional=0)
                self.assertEqual((floor, exceptional), low)
                if floor == 18:
                    self.assertEqual(
                        (18, 100),
                        evaluator.apply_immediate(
                            holy.ability_for_level(level), strength=18, exceptional=50
                        ),
                    )
                high = evaluator.apply_ability(holy.ability_for_level(level), strength=floor + 1, exceptional=0)
                self.assertEqual((floor + 1, 0), high, "floor lowered a higher Strength")
                restored = evaluator.apply_heartbeat(holy.ability_for_level(level), strength=10, exceptional=0)
                self.assertEqual((floor, exceptional), restored, "heartbeat cannot restore floor after stronger temporary Strength expires")

    def test_strength_helper_graph_fields_and_order(self) -> None:
        result = self.run_case(phase="progression")
        self.assert_success(result)
        _assert_strength_helper_graph(result.output, result.fixture.divine_resref)

    def test_strength_setter_covers_slowed_pulse_gap(self) -> None:
        result = self.run_case(phase="progression")
        self.assert_success(result)
        # Opcode 272 can tick late while the recipient is Slowed or diseased.
        # Timing mode 10 is measured in engine ticks.  Thirty-one ticks gives
        # one tick of overlap past the slowed 30-tick (two-second) cadence.
        for floor, setter in STRENGTH_SETTER_BY_FLOOR.items():
            helper = read_spl(result.output / f"{setter}.spl")
            timed_setters = [
                effect
                for effect in helper.abilities[0].effects
                if effect.opcode in (44, 97)
            ]
            self.assertEqual(2 if floor == 18 else 1, len(timed_setters))
            self.assertTrue(
                all(
                    (effect.timing, effect.resist_dispel, effect.duration)
                    == (10, 3, STRENGTH_SETTER_DURATION_TICKS)
                    for effect in timed_setters
                ),
                f"{setter} does not overlap a delayed one-second pulse",
            )

        holy = read_spl(result.output / f"{HOLY_RESREF}.SPL")
        for level, ability in enumerate(holy.abilities, start=1):
            pulses = [
                effect
                for effect in ability.effects
                if effect.opcode == 272
                and effect.resource.upper() in STRENGTH_PULSE_RESREFS
            ]
            self.assertEqual(
                [(1, 3)],
                [(effect.parameter1, effect.parameter2) for effect in pulses],
                f"level {level} changed the approved heartbeat cadence contract",
            )

    def test_holy_recast_cleans_all_tier_setters_before_direct_floor(self) -> None:
        result = self.run_case(phase="progression")
        self.assert_success(result)
        holy = read_spl(result.output / f"{HOLY_RESREF}.SPL")
        str_lt_row = _semantic_splprot_row(result.output, STR_LT_SEMANTIC)
        str_eq_row = _semantic_splprot_row(result.output, STR_EQ_SEMANTIC)
        for level, ability in enumerate(holy.abilities, start=1):
            floor = _strength_floor(level)
            expected_prefix = [
                _helper_effect(321, parameter2=2, resource=result.fixture.divine_resref),
                _helper_effect(321, resource=HOLY_RESREF),
                *(
                    _helper_effect(321, parameter2=2, resource=setter)
                    for setter in STRENGTH_SETTER_BY_FLOOR.values()
                ),
                _helper_effect(
                    326,
                    parameter1=floor,
                    parameter2=str_lt_row,
                    resource=STRENGTH_SETTER_BY_FLOOR[floor],
                ),
            ]
            if floor == 18:
                expected_prefix.append(
                    _helper_effect(
                        326,
                        parameter1=18,
                        parameter2=str_eq_row,
                        resource=STRENGTH_EXCEPTION_18,
                    )
                )
            self.assertEqual(
                [effect.canonical() for effect in expected_prefix],
                [
                    effect.canonical()
                    for effect in ability.effects[: len(expected_prefix)]
                ],
                f"level {level} does not clean the old tier setter before recast",
            )

    def test_holy_expiry_cleans_all_setters_at_exact_parent_duration(self) -> None:
        result = self.run_case(phase="progression")
        self.assert_success(result)
        holy = read_spl(result.output / f"{HOLY_RESREF}.SPL")
        for level, ability in enumerate(holy.abilities, start=1):
            parent_duration = _tier_duration(level)
            expected = [
                _helper_effect(
                    321,
                    parameter2=2,
                    timing=4,
                    duration=parent_duration,
                    resource=setter,
                ).canonical()
                for setter in STRENGTH_SETTER_BY_FLOOR.values()
            ]
            self.assertEqual(
                expected,
                [effect.canonical() for effect in ability.effects[-4:]],
                f"level {level} does not end with exact all-tier parent cleanup",
            )

    def test_strength_floor_documents_portable_initial_higher_value_lag(self) -> None:
        result = self.run_case(phase="progression")
        self.assert_success(result)
        holy = read_spl(result.output / f"{HOLY_RESREF}.SPL")
        evaluator = _ConditionGraph(result.output)
        for level in (1, 13, 19, 25):
            with self.subTest(level=level):
                ability = holy.ability_for_level(level)
                floor = _strength_floor(level)
                self.assertEqual(
                    (floor + 1, 0),
                    evaluator.apply_immediate(
                        ability, strength=floor + 1, exceptional=0
                    ),
                    "casting Holy while already stronger must not lower Strength",
                )
                self.assertEqual(
                    (floor, 100 if floor == 18 else 0),
                    evaluator.apply_heartbeat(
                        ability, strength=10, exceptional=0
                    ),
                    "after the stronger effect expires, the next heartbeat restores the floor",
                )
                pulses = [
                    effect
                    for effect in ability.effects
                    if effect.opcode == 272
                    and effect.resource.upper() in STRENGTH_PULSE_RESREFS
                ]
                self.assertEqual([(1, 3)], [(e.parameter1, e.parameter2) for e in pulses])

    def test_strength_helper_create_is_scoped_to_explicit_output(self) -> None:
        result = self.run_case(phase="progression")
        self.assert_success(result)
        temporary_root = Path(result.temporary.name)
        helper_paths = [
            path
            for path in temporary_root.rglob("*")
            if path.is_file() and path.stem.upper() in STRENGTH_HELPER_RESREFS
        ]
        expected = {
            *(f"OUTPUT/{resref}.SPL" for resref in STRENGTH_SETTER_BY_FLOOR.values()),
            *(f"OUTPUT/{resref}.SPL" for resref in STRENGTH_CHECKER_BY_FLOOR.values()),
            f"OUTPUT/{STRENGTH_EXCEPTION_18}.SPL",
            *(f"OUTPUT/{resref}.EFF" for resref in STRENGTH_PULSE_BY_FLOOR.values()),
        }
        actual = {
            path.relative_to(temporary_root).as_posix().upper() for path in helper_paths
        }
        self.assertEqual(
            expected,
            actual,
            "CREATE publishing left helpers outside explicit output",
        )

    def test_strength_helper_create_supports_relative_override(self) -> None:
        result = self.run_case(phase="progression", relative_output=True)
        self.assert_success(result)
        _assert_strength_helper_graph(result.output, result.fixture.divine_resref)

    def test_strength_helper_create_supports_absolute_process_override(self) -> None:
        result = self.run_case(
            phase="progression",
            absolute_process_override=True,
        )
        self.assert_success(result)
        _assert_strength_helper_graph(result.output, result.fixture.divine_resref)

    def test_absolute_process_override_is_byte_identical_on_second_run(self) -> None:
        first = self.run_case(
            phase="progression",
            absolute_process_override=True,
        )
        self.assert_success(first)
        second = _rerun_harness(
            first,
            phase="progression",
            absolute_process_override=True,
        )
        self._results.append(second)
        self.assert_success(second)
        self.assertEqual(_raw_file_tree(first.output), _raw_file_tree(second.output))

    def test_strength_helper_create_rejects_foreign_scratch_resource(self) -> None:
        cases = (
            {"label": "distinct_original20"},
            {"label": "absolute_alias_original20", "absolute_process_override": True},
            {
                "label": "distinct_recognized30",
                "holy_layout": "valid_30",
                "strength_helpers_layout": "exact",
            },
        )
        for case in cases:
            with self.subTest(case=case["label"]):
                options = {key: value for key, value in case.items() if key != "label"}
                result = self.run_case(
                    phase="progression",
                    scratch_reserved_resref=STRENGTH_SETTER_BY_FLOOR[18],
                    **options,
                )
                self.assertFalse(result.succeeded, "foreign scratch helper was overwritten")
                scratch_path = (
                    result.run_dir
                    / "override"
                    / f"{STRENGTH_SETTER_BY_FLOOR[18]}.spl"
                )
                self.assertTrue(scratch_path.is_file(), "foreign scratch helper was deleted")
                self.assertEqual(SCRATCH_COLLISION_SENTINEL, scratch_path.read_bytes())
                self.assertRegex(
                    result.transcript.upper(),
                    r"SCRATCH|STAG|PUBLISH|RESERVED|COLLIS|CBRST18|HELPER",
                )

    def test_clab_cap(self) -> None:
        result = self.run_case(phase="progression")
        self.assert_success(result)
        before_bytes = (result.fixture.root / CLAB_NAME).read_bytes()
        self.assertEqual(
            _clear_clab_holy_power_grants(before_bytes, LATE_HOLY_POWER_LEVELS),
            (result.output / CLAB_NAME).read_bytes(),
            "CLAB patch changed formatting or bytes outside the five late grants",
        )
        before = read_2da(result.fixture.root / CLAB_NAME)
        after = read_2da(result.output / CLAB_NAME)
        cleared = {str(level) for level in LATE_HOLY_POWER_LEVELS}
        for column in ("1", "6", "11", "16", "21"):
            self.assertEqual("GA_OHTMPS1", after.cell("ABILITY1", column))
        for column in cleared:
            self.assertEqual("****", after.cell("ABILITY1", column))
        self.assertEqual("AP_CDHLYSYM", after.cell("ABILITY1", "25"))
        for row_name, values in before.rows:
            for column, value in zip(before.columns, values):
                if row_name == "ABILITY1" and column in cleared:
                    continue
                self.assertEqual(value, after.cell(row_name, column), f"changed {row_name}/{column}")

    def test_clab_cap_anchors_the_validated_ability1_row(self) -> None:
        result = self.run_case(phase="progression", clab_layout="decoy")
        self.assert_success(result)
        before = (result.fixture.root / CLAB_NAME).read_bytes()
        after = (result.output / CLAB_NAME).read_bytes()
        self.assertEqual(
            _clear_clab_holy_power_grants(before, LATE_HOLY_POWER_LEVELS),
            after,
        )
        self.assertIn(b"// ABILITY1 decoy must remain byte-identical", after)

    def test_preserves_foreign_effects(self) -> None:
        result = self.run_case(phase="progression")
        self.assert_success(result)
        before = read_spl(result.fixture.root / f"{HOLY_RESREF}.SPL")
        after = read_spl(result.output / f"{HOLY_RESREF}.SPL")
        self.assertEqual(before.spell_icon, after.spell_icon)
        raw_foreign_resources = (
            SENTINEL_RESOURCE,
            FOREIGN_PULSE_RESREF,
            *FOREIGN_OWNED_OPCODE_RESREFS,
        )
        for level in range(1, 31):
            source = before.ability_for_level(min(level, 20))
            target = after.ability_for_level(level)
            self.assertEqual(source.icon, target.icon)
            for effect in source.effects:
                preserved = (
                    effect.opcode in (50, 141, 142, 174, 282)
                    or (effect.opcode == 328 and effect.parameter2 in (9, 68))
                    or effect.resource.upper()
                    in raw_foreign_resources
                )
                if preserved:
                    if effect.resource.upper() in raw_foreign_resources:
                        self.assertIn(
                            effect.to_bytes(),
                            [candidate.to_bytes() for candidate in target.effects],
                            "foreign effect was not byte-preserved",
                        )
                    else:
                        key = effect.preservation_key()
                        self.assertIn(key, [candidate.preservation_key() for candidate in target.effects])

    def test_progression_second_run_is_byte_identical(self) -> None:
        first = self.run_case(phase="progression")
        self.assert_success(first)
        second = _rerun_harness(first, phase="progression")
        self._results.append(second)
        self.assert_success(second)
        first_files = _raw_file_tree(first.output)
        second_files = _raw_file_tree(second.output)
        self.assertEqual(set(first_files), set(second_files))
        for relative in sorted(first_files):
            with self.subTest(file=relative):
                self.assertEqual(
                    first_files[relative],
                    second_files[relative],
                    f"raw progression bytes changed on rerun for {relative}",
                )

    def test_divine_power_exclusion(self) -> None:
        result = self.run_case(alternate_ids=True, phase="bridge")
        self.assert_success(result)
        ids = read_ids(result.output / "SPELL.IDS")
        divine_resref = spell_resref(ids.value("CLERIC_HOLY_POWER"), "CLERIC_HOLY_POWER")
        self.assertEqual(result.fixture.divine_resref, divine_resref)
        holy = read_spl(result.output / f"{HOLY_RESREF}.SPL")
        divine_before = read_spl(result.fixture.root / f"{divine_resref}.SPL")
        divine = read_spl(result.output / f"{divine_resref}.SPL")
        self.assertEqual(
            _nonstructural_spl_header(divine_before.header_raw),
            _nonstructural_spl_header(divine.header_raw),
        )
        self.assertEqual(
            tuple(effect.to_bytes() for effect in divine_before.casting_effects),
            tuple(effect.to_bytes() for effect in divine.casting_effects),
        )
        self.assertEqual(len(divine_before.abilities), len(divine.abilities))
        for ability in holy.abilities:
            self.assertEqual((321, divine_resref), (ability.effects[0].opcode, ability.effects[0].resource.upper()))
            self.assertEqual((321, HOLY_RESREF), (ability.effects[1].opcode, ability.effects[1].resource.upper()))
        for before_ability, ability in zip(divine_before.abilities, divine.abilities):
            self.assertEqual(
                _nonstructural_ability_header(before_ability.raw),
                _nonstructural_ability_header(ability.raw),
            )
            expected_cleanup = (
                _helper_effect(321, parameter2=2, resource=HOLY_RESREF),
                *(
                    _helper_effect(321, parameter2=2, resource=setter)
                    for setter in STRENGTH_SETTER_BY_FLOOR.values()
                ),
            )
            cleanup = ability.effects[: len(expected_cleanup)]
            self.assertEqual(
                tuple(effect.canonical() for effect in expected_cleanup),
                tuple(effect.canonical() for effect in cleanup),
                "Divine Power lacks the exact early Holy/Strength cleanup prefix",
            )
            self.assertEqual(
                tuple(effect.to_bytes() for effect in before_ability.effects),
                tuple(effect.to_bytes() for effect in ability.effects[len(expected_cleanup) :]),
                "reciprocal cleanup changed an existing Divine Power effect byte",
            )

    def test_additive_bridge_graph(self) -> None:
        result = self.run_case("additive", "auto", phase="bridge")
        self.assert_success(result)
        state_values = _private_state_values(result.output)
        ih_state = state_values[IH_STATE_SYMBOL]
        tier_state_by_key = {
            key: state_values[symbol] for key, symbol in APR_STATE_SYMBOL_BY_KEY.items()
        }
        active_row = _active_splstate_row(result.output)

        helpers = _strict_apr_helpers(result.output)
        self.assertEqual(3, len(helpers), f"expected one strict APR helper per tier: {helpers}")
        self.assertEqual({1, 6, 7}, set(helpers.values()))
        helper_by_key = {key: resource for resource, key in helpers.items()}
        self.assertEqual(3, len(helper_by_key), "APR helper keys are not one-to-one")
        helper_resrefs = set(helpers)

        conditions = _apr_condition_resources(result.output, helper_resrefs)
        self.assertEqual(
            3,
            len(conditions),
            f"expected one standalone conditional EFF per APR tier: {conditions}",
        )
        condition_by_key = {}
        for condition_resref, condition in conditions.items():
            helper_resref = condition.resource.upper()
            key = helpers[helper_resref]
            self.assertNotIn(key, condition_by_key, f"duplicate conditional EFF for APR key {key}")
            self.assertEqual(
                key,
                _read_conditional_apr_edge(
                    result.output,
                    condition_resref,
                    expected_state=ih_state,
                    active_row=active_row,
                    expected_helper=helper_resref,
                ),
            )
            condition_by_key[key] = condition_resref
        self.assertEqual({1, 6, 7}, set(condition_by_key))

        haste = read_spl(result.output / f"{result.fixture.haste_resref}.SPL")
        haste_before = read_spl(result.fixture.root / f"{result.fixture.haste_resref}.SPL")
        self.assertEqual(
            _nonstructural_spl_header(haste_before.header_raw),
            _nonstructural_spl_header(haste.header_raw),
        )
        self.assertEqual(
            tuple(effect.to_bytes() for effect in haste_before.casting_effects),
            tuple(effect.to_bytes() for effect in haste.casting_effects),
        )
        holy = read_spl(result.output / f"{HOLY_RESREF}.SPL")
        bridge_resources = helper_resrefs | set(conditions)
        bridge_states = {ih_state, *tier_state_by_key.values()}
        for owner, casting_effects in (
            ("Holy Power", holy.casting_effects),
            ("Improved Haste", haste.casting_effects),
        ):
            self.assertFalse(
                any(
                    (effect.opcode == 328 and effect.parameter2 in bridge_states)
                    or (
                        effect.opcode in (272, 326)
                        and effect.resource.upper() in bridge_resources
                    )
                    for effect in casting_effects
                ),
                f"{owner} bridge effects escaped their caster-level headers",
            )

        self.assertEqual(len(haste_before.abilities), len(haste.abilities))
        for header_index, (before_ability, ability) in enumerate(
            zip(haste_before.abilities, haste.abilities)
        ):
            with self.subTest(resource="Improved Haste", header=header_index):
                self.assertEqual(before_ability.required_level, ability.required_level)
                self.assertEqual(
                    (before_ability.target, before_ability.projectile),
                    (ability.target, ability.projectile),
                    "bridge changed the Improved Haste header delivery",
                )
                self.assertEqual(
                    _nonstructural_ability_header(before_ability.raw),
                    _nonstructural_ability_header(ability.raw),
                    "bridge changed an Improved Haste ability byte other than effect count/index",
                )
                donor_before = [
                    effect
                    for effect in before_ability.effects
                    if effect.opcode == 1
                    and effect.parameter1 == 1
                    and effect.parameter2 == 0
                ]
                donor_after = [
                    effect
                    for effect in ability.effects
                    if effect.opcode == 1
                    and effect.parameter1 == 1
                    and effect.parameter2 == 0
                ]
                self.assertEqual(1, len(donor_before))
                self.assertEqual(1, len(donor_after))
                self.assertEqual(donor_before[0].canonical(), donor_after[0].canonical())
                preserved_after = [
                    effect
                    for effect in ability.effects
                    if not (
                        (effect.opcode == 328 and effect.parameter2 == ih_state)
                        or (
                            effect.opcode == 326
                            and effect.resource.upper() in helper_resrefs
                        )
                    )
                ]
                self.assertEqual(
                    tuple(effect.to_bytes() for effect in before_ability.effects),
                    tuple(effect.to_bytes() for effect in preserved_after),
                    "bridge changed or reordered an original Improved Haste effect",
                )
                self.assertFalse(
                    any(
                        effect.opcode in (16, 317) and effect.parameter2 == 1
                        for effect in ability.effects
                    )
                )

                markers = [
                    effect
                    for effect in ability.effects
                    if effect.opcode == 328 and effect.parameter2 == ih_state
                ]
                self.assertEqual(1, len(markers), "IH header must contain exactly one marker")
                marker = markers[0]
                self.assertEqual(
                    (328, 0, ih_state, 1),
                    (marker.opcode, marker.parameter1, marker.parameter2, marker.special),
                )
                self.assertEqual(donor_after[0].delivery_key(), marker.delivery_key())
                self.assertEqual(
                    ("", 0, 0, 0, 0),
                    (
                        marker.resource,
                        marker.dice_number,
                        marker.dice_size,
                        marker.save_type,
                        marker.save_bonus,
                    ),
                    "IH marker copied non-delivery payload fields from its APR donor",
                )

                kicks = [
                    effect
                    for effect in ability.effects
                    if effect.opcode == 326 and effect.resource.upper() in helper_resrefs
                ]
                self.assertEqual(3, len(kicks), "IH header must kick every active Holy APR tier")
                donor_index = ability.effects.index(donor_after[0])
                inserted = ability.effects[donor_index + 1 : donor_index + 5]
                self.assertEqual(
                    [marker, *[next(effect for effect in kicks if effect.parameter1 == tier_state_by_key[key]) for key in (6, 1, 7)]],
                    list(inserted),
                    "IH marker and tier kicks must immediately follow the APR donor before later immunities",
                )
                for key, tier_state in tier_state_by_key.items():
                    matched = [effect for effect in kicks if effect.parameter1 == tier_state]
                    self.assertEqual(1, len(matched), f"missing or duplicate IH kick for APR key {key}")
                    kick = matched[0]
                    self.assertEqual(
                        (
                            326,
                            donor_after[0].target,
                            donor_after[0].power,
                            tier_state,
                            active_row,
                            1,
                            2,
                            0,
                            100,
                            0,
                            helper_by_key[key],
                        ),
                        (
                            kick.opcode,
                            kick.target,
                            kick.power,
                            kick.parameter1,
                            kick.parameter2,
                            kick.timing,
                            kick.resist_dispel,
                            kick.duration,
                            kick.probability1,
                            kick.probability2,
                            kick.resource.upper(),
                        ),
                    )

        self.assertEqual(30, len(holy.abilities))
        self.assertEqual(list(range(1, 31)), [ability.required_level for ability in holy.abilities])
        tier_state_set = set(tier_state_by_key.values())
        for ability in holy.abilities:
            level = ability.required_level
            duration = _tier_duration(level)
            expected_key = None if level <= 6 else 6 if level <= 12 else 1 if level <= 24 else 7
            with self.subTest(resource=HOLY_RESREF, level=level):
                tier_markers = [
                    effect
                    for effect in ability.effects
                    if effect.opcode == 328 and effect.parameter2 in tier_state_set
                ]
                immediate = [
                    effect
                    for effect in ability.effects
                    if effect.opcode == 326 and effect.resource.upper() in helper_resrefs
                ]
                pulses = [
                    effect
                    for effect in ability.effects
                    if effect.opcode == 272 and effect.resource.upper() in bridge_resources
                ]
                if expected_key is None:
                    self.assertEqual([], tier_markers, "levels 1-6 must not carry an APR tier state")
                    self.assertEqual([], immediate, "levels 1-6 must not carry an APR bridge kick")
                    self.assertEqual([], pulses, "levels 1-6 must not carry an APR bridge pulse")
                    continue

                expected_state = tier_state_by_key[expected_key]
                self.assertEqual(1, len(tier_markers), "Holy header must have one APR tier state")
                marker = tier_markers[0]
                self.assertEqual(
                    (328, 0, expected_state, 0, duration, 3, 1),
                    (
                        marker.opcode,
                        marker.parameter1,
                        marker.parameter2,
                        marker.timing,
                        marker.duration,
                        marker.resist_dispel,
                        marker.special,
                    ),
                )

                self.assertEqual(1, len(immediate), "Holy header must have one immediate IH gate")
                kick = immediate[0]
                self.assertEqual(
                    (
                        326,
                        1,
                        4,
                        ih_state,
                        active_row,
                        1,
                        2,
                        0,
                        100,
                        0,
                        helper_by_key[expected_key],
                    ),
                    (
                        kick.opcode,
                        kick.target,
                        kick.power,
                        kick.parameter1,
                        kick.parameter2,
                        kick.timing,
                        kick.resist_dispel,
                        kick.duration,
                        kick.probability1,
                        kick.probability2,
                        kick.resource.upper(),
                    ),
                )

                self.assertEqual(1, len(pulses), "Holy header must have one APR heartbeat")
                pulse = pulses[0]
                self.assertEqual(
                    (272, 1, 3, duration, condition_by_key[expected_key]),
                    (
                        pulse.opcode,
                        pulse.parameter1,
                        pulse.parameter2,
                        pulse.duration,
                        pulse.resource.upper(),
                    ),
                )
                self.assertEqual(
                    expected_key,
                    _read_conditional_apr_edge(
                        result.output,
                        pulse.resource,
                        expected_state=ih_state,
                        active_row=active_row,
                        expected_helper=helper_by_key[expected_key],
                    ),
                )

    def test_doubling_needs_no_bridge(self) -> None:
        result = self.run_case("doubling", "auto", phase="bridge")
        self.assert_success(result)
        haste = read_spl(result.output / f"{result.fixture.haste_resref}.SPL")
        for header_index, ability in enumerate(haste.abilities):
            with self.subTest(header=header_index):
                effects = ability.effects
                self.assertTrue(any(e.opcode in (16, 317) and e.parameter2 == 1 for e in effects))
                self.assertFalse(any(e.opcode == 1 and e.parameter1 == 1 and e.parameter2 == 0 for e in effects))
                self.assertFalse(any(e.opcode == 328 and e.special == 1 for e in effects))
        self.assertEqual({}, _strict_apr_helpers(result.output), "doubling mode created additive bridge resources")
        self.assertEqual(
            (result.fixture.root / f"{result.fixture.haste_resref}.SPL").read_bytes(),
            (result.output / f"{result.fixture.haste_resref}.SPL").read_bytes(),
            "doubling mode rewrote Improved Haste",
        )
        self.assertEqual(
            (result.fixture.root / "SPLSTATE.IDS").read_bytes(),
            (result.output / "SPLSTATE.IDS").read_bytes(),
            "doubling mode allocated bridge states",
        )

    def test_bridge_preserves_headers_casting_effects_and_task4_holy_bytes(self) -> None:
        baseline = self.run_case(
            "additive",
            phase="progression",
            casting_sentinels=True,
        )
        bridged = self.run_case(
            "additive",
            phase="bridge",
            casting_sentinels=True,
        )
        self.assert_success(baseline)
        self.assert_success(bridged)

        state_values = set(_private_state_values(bridged.output).values())
        bridge_resources = set(APR_HELPER_RESREFS + APR_CONDITION_RESREFS)
        holy_before = read_spl(baseline.output / f"{HOLY_RESREF}.SPL")
        holy_after = read_spl(bridged.output / f"{HOLY_RESREF}.SPL")
        self.assertEqual(
            _nonstructural_spl_header(holy_before.header_raw),
            _nonstructural_spl_header(holy_after.header_raw),
        )
        self.assertEqual(
            tuple(effect.to_bytes() for effect in holy_before.casting_effects),
            tuple(effect.to_bytes() for effect in holy_after.casting_effects),
        )
        for before_ability, after_ability in zip(holy_before.abilities, holy_after.abilities):
            self.assertEqual(
                _nonstructural_ability_header(before_ability.raw),
                _nonstructural_ability_header(after_ability.raw),
            )
            preserved = tuple(
                effect.to_bytes()
                for effect in after_ability.effects
                if not (
                    (effect.opcode == 328 and effect.parameter2 in state_values)
                    or effect.resource.upper() in bridge_resources
                )
            )
            self.assertEqual(
                tuple(effect.to_bytes() for effect in before_ability.effects),
                preserved,
                "Task5 changed or reordered a Task4 Holy Power effect",
            )

        for resref in (bridged.fixture.haste_resref, bridged.fixture.divine_resref):
            before = read_spl(bridged.fixture.root / f"{resref}.SPL")
            after = read_spl(bridged.output / f"{resref}.SPL")
            with self.subTest(resref=resref):
                self.assertEqual(
                    _nonstructural_spl_header(before.header_raw),
                    _nonstructural_spl_header(after.header_raw),
                )
                self.assertEqual(
                    tuple(effect.to_bytes() for effect in before.casting_effects),
                    tuple(effect.to_bytes() for effect in after.casting_effects),
                )
                for before_ability, after_ability in zip(before.abilities, after.abilities):
                    self.assertEqual(
                        _nonstructural_ability_header(before_ability.raw),
                        _nonstructural_ability_header(after_ability.raw),
                    )

    def test_full_bridge_reuses_lowest_duplicate_splprot_alias(self) -> None:
        result = self.run_case(
            "additive",
            phase="bridge",
            splprot_layout="duplicate_semantics",
        )
        self.assert_success(result)
        self.assertEqual(
            (result.fixture.root / "SPLPROT.2DA").read_bytes(),
            (result.output / "SPLPROT.2DA").read_bytes(),
        )
        active_row = _active_splstate_row(result.output)
        self.assertEqual(1, active_row)
        helper_resrefs = set(APR_HELPER_RESREFS)
        for resref in APR_CONDITION_RESREFS:
            self.assertEqual(active_row, read_eff_v2(result.output / f"{resref}.EFF").parameter2)
        for spell_resref in (HOLY_RESREF, result.fixture.haste_resref):
            spell = read_spl(result.output / f"{spell_resref}.SPL")
            for ability in spell.abilities:
                for effect in ability.effects:
                    if effect.opcode == 326 and effect.resource.upper() in helper_resrefs:
                        self.assertEqual(active_row, effect.parameter2)

    def test_full_forced_modes_and_opcode317_doubling(self) -> None:
        cases = (
            ("additive", "force_additive", True),
            ("doubling", "force_double", False),
            ("doubling317", "force_double", False),
        )
        for variant, mode, additive in cases:
            with self.subTest(variant=variant, mode=mode):
                result = self.run_case(variant, mode, phase="full")
                self.assert_success(result)
                produced = {path.name.upper() for path in result.output.iterdir()}
                expected = {
                    *(f"{resref}.SPL" for resref in APR_HELPER_RESREFS),
                    *(f"{resref}.EFF" for resref in APR_CONDITION_RESREFS),
                }
                if additive:
                    self.assertTrue(expected <= produced)
                else:
                    self.assertTrue(expected.isdisjoint(produced))

    def test_apr_helper_timeline_accepts_slow_disease_refresh_gap(self) -> None:
        # Opcode 272 normally ticks every 15 engine ticks. Slow or Disease doubles
        # that cadence to 30; both together do not increase it further. The strict
        # one-second APR helper lasts 15 ticks so stale APR expires promptly, at the
        # accepted cost of a gap before the next slowed/diseased heartbeat.
        helper_ticks = 15
        cadence_by_status = {
            "normal": 15,
            "slow": 30,
            "disease": 30,
            "slow_and_disease": 30,
        }
        self.assertEqual(0, cadence_by_status["normal"] - helper_ticks)
        for status in ("slow", "disease", "slow_and_disease"):
            with self.subTest(status=status):
                self.assertEqual(
                    15,
                    cadence_by_status[status] - helper_ticks,
                    "portable APR bridge contract allows at most a one-second refresh gap",
                )

    def test_idempotent_second_application(self) -> None:
        for variant in ("additive", "doubling"):
            with self.subTest(variant=variant):
                first = self.run_case(variant)
                self.assert_success(first)
                second = _rerun_harness(first)
                self._results.append(second)
                self.assert_success(second)
                first_files = _raw_file_tree(first.output)
                copied_fixture_files = _raw_file_tree(second.fixture.root)
                second_files = _raw_file_tree(second.output)
                self.assertEqual(
                    first_files,
                    copied_fixture_files,
                    "second-pass fixture copy changed raw production output before WeiDU ran",
                )
                self.assertEqual(
                    set(first_files),
                    set(second_files),
                    "second application changed the recursive output file set",
                )
                for relative in sorted(first_files):
                    with self.subTest(variant=variant, file=relative):
                        first_bytes = first_files[relative]
                        second_bytes = second_files[relative]
                        self.assertEqual(
                            first_bytes,
                            second_bytes,
                            f"raw bytes changed for {relative}: "
                            f"{hashlib.sha256(first_bytes).hexdigest()} != "
                            f"{hashlib.sha256(second_bytes).hexdigest()}",
                        )
                self.assertEqual(
                    canonical_resource_tree(first.output), canonical_resource_tree(second.output)
                )

    def test_malformed_owned_apr_helper_is_rejected_before_rerun_mutation(self) -> None:
        first = self.run_case("additive")
        self.assert_success(first)
        helper_path = first.output / "CBRAPR1.SPL"
        helper = read_spl(helper_path)
        ability = helper.abilities[0]
        malformed = tuple(
            dataclasses.replace(effect, duration=2)
            if effect.opcode == 1 and effect.parameter1 == 1 and effect.parameter2 == 0
            else effect
            for effect in ability.effects
        )
        write_spl(
            helper_path,
            dataclasses.replace(
                helper,
                abilities=(dataclasses.replace(ability, effects=malformed),),
            ),
        )
        malformed_bytes = helper_path.read_bytes()

        second = _rerun_harness(first)
        self._results.append(second)
        self.assertFalse(second.succeeded, "malformed reserved helper was silently replaced")
        self.assertRegex(second.transcript, r"(?i)APR|HELPER|COLLISION|ONE[ _-]?SECOND")
        self.assertEqual(
            malformed_bytes,
            (second.fixture.root / helper_path.name).read_bytes(),
            "preflight mutated the malformed source fixture before rejecting it",
        )
        self.assertFalse(
            (second.output / "CBR_TEST.OK").exists(),
            "failed helper preflight reached the success marker",
        )

    def test_partial_bridge_corruptions_fail_atomically_before_rerun_writes(self) -> None:
        first = self.run_case("additive")
        self.assert_success(first)
        states = _private_state_values(first.output)
        ih_state = states[IH_STATE_SYMBOL]
        tier_states = set(states[symbol] for symbol in APR_STATE_SYMBOL_BY_KEY.values())

        def mutate_spl_effect(resref: str, header: int, predicate, replacement) -> object:
            def mutate(root: Path) -> None:
                path = root / f"{resref}.SPL"
                spell = read_spl(path)
                ability = spell.abilities[header]
                effects = list(ability.effects)
                matches = [index for index, effect in enumerate(effects) if predicate(effect)]
                self.assertEqual(1, len(matches), f"mutation target {resref} matched {matches}")
                index = matches[0]
                effects[index] = replacement(effects[index])
                abilities = list(spell.abilities)
                abilities[header] = dataclasses.replace(ability, effects=tuple(effects))
                write_spl(path, dataclasses.replace(spell, abilities=tuple(abilities)))
            return mutate

        def reorder_ih_kicks(root: Path) -> None:
            path = root / f"{first.fixture.haste_resref}.SPL"
            spell = read_spl(path)
            ability = spell.abilities[0]
            effects = list(ability.effects)
            indices = [
                index
                for index, effect in enumerate(effects)
                if effect.opcode == 326 and effect.resource.upper() in APR_HELPER_RESREFS
            ]
            self.assertEqual(3, len(indices))
            effects[indices[0]], effects[indices[1]] = effects[indices[1]], effects[indices[0]]
            write_spl(
                path,
                dataclasses.replace(
                    spell,
                    abilities=(dataclasses.replace(ability, effects=tuple(effects)),),
                ),
            )

        corruptions: list[tuple[str, object]] = [
            (
                "ih_marker",
                mutate_spl_effect(
                    first.fixture.haste_resref,
                    0,
                    lambda effect: effect.opcode == 328 and effect.parameter2 == ih_state,
                    lambda effect: dataclasses.replace(effect, special=0),
                ),
            ),
            ("ih_kick_order", reorder_ih_kicks),
            (
                "holy_marker",
                mutate_spl_effect(
                    HOLY_RESREF,
                    12,
                    lambda effect: effect.opcode == 328 and effect.parameter2 in tier_states,
                    lambda effect: dataclasses.replace(effect, special=0),
                ),
            ),
            (
                "holy_gate",
                mutate_spl_effect(
                    HOLY_RESREF,
                    12,
                    lambda effect: effect.opcode == 326 and effect.resource.upper() in APR_HELPER_RESREFS,
                    lambda effect: dataclasses.replace(effect, parameter2=effect.parameter2 + 1),
                ),
            ),
            (
                "holy_pulse",
                mutate_spl_effect(
                    HOLY_RESREF,
                    12,
                    lambda effect: effect.opcode == 272 and effect.resource.upper() in APR_CONDITION_RESREFS,
                    lambda effect: dataclasses.replace(effect, dice_number=1),
                ),
            ),
            (
                "divine_prefix",
                mutate_spl_effect(
                    first.fixture.divine_resref,
                    0,
                    lambda effect: effect.opcode == 321 and effect.resource.upper() == HOLY_RESREF,
                    lambda effect: dataclasses.replace(effect, parameter2=0),
                ),
            ),
        ]
        for helper in APR_HELPER_RESREFS:
            corruptions.append(
                (
                    f"helper_{helper}",
                    mutate_spl_effect(
                        helper,
                        0,
                        lambda effect: effect.opcode == 1,
                        lambda effect: dataclasses.replace(effect, duration=2),
                    ),
                )
            )
        for condition in APR_CONDITION_RESREFS:
            def mutate_condition(root: Path, resref: str = condition) -> None:
                path = root / f"{resref}.EFF"
                effect = read_eff_v2(path)
                path.write_bytes(dataclasses.replace(effect, flags=0).to_bytes())
            corruptions.append((f"condition_{condition}", mutate_condition))

        for name, mutator in corruptions:
            with self.subTest(corruption=name):
                second = _rerun_harness(
                    first,
                    fixture_mutator=mutator,
                    scratch_sentinel=True,
                )
                self._results.append(second)
                self.assertFalse(second.succeeded, f"accepted partial bridge corruption {name}")
                self.assertRegex(
                    second.transcript,
                    r"(?i)CBR|TEMPUS|BRIDGE|HELPER|CONDITION|DIVINE|HOLY|HASTE",
                )
                self.assertEqual(
                    second.source_snapshot,
                    _raw_file_tree(second.fixture.root),
                    f"failed preflight mutated the in-place source tree for {name}",
                )
                self.assertEqual(
                    SCRATCH_COLLISION_SENTINEL,
                    (second.run_dir / "override" / "FOREIGN.KEEP").read_bytes(),
                    f"failed preflight changed process-local scratch state for {name}",
                )
                self.assertEqual(
                    {},
                    _raw_file_tree(second.output),
                    f"failed preflight published output artifacts for {name}",
                )
                self.assertFalse((second.output / "CBR_TEST.OK").exists())

    def test_rerun_rejects_foreign_apr_scratch_alias(self) -> None:
        first = self.run_case("additive")
        self.assert_success(first)

        def seed_foreign_scratch(override: Path) -> None:
            (override / "CBRAPR1.spl").write_bytes(SCRATCH_COLLISION_SENTINEL)

        second = _rerun_harness(first, scratch_mutator=seed_foreign_scratch)
        self._results.append(second)
        self.assertFalse(second.succeeded, "canonical explicit graph accepted a foreign scratch alias")
        self.assertRegex(second.transcript, r"(?i)APR|HELPER|SCRATCH|MISSING|COLLISION")
        self.assertEqual(second.source_snapshot, _raw_file_tree(second.fixture.root))
        self.assertEqual({}, _raw_file_tree(second.output))
        self.assertEqual(
            SCRATCH_COLLISION_SENTINEL,
            (second.run_dir / "override" / "CBRAPR1.spl").read_bytes(),
        )

    def test_no_tlk_operations_in_components_401_403(self) -> None:
        setup_source = _strip_weidu_comments(SETUP_TP2.read_text(encoding="utf-8"))
        blocks = []
        for component in (401, 402, 403):
            match = re.search(
                rf"(?ms)^BEGIN\b.*?^DESIGNATED\s+{component}\b.*?(?=^BEGIN\b|\Z)",
                setup_source,
            )
            self.assertIsNotNone(match, f"component {component} does not exist")
            blocks.append(match.group(0))
        self.assertTrue(PRODUCTION_TPA.is_file(), f"missing {PRODUCTION_TPA}")
        source = "\n".join(blocks) + "\n" + PRODUCTION_TPA.read_text(encoding="utf-8")
        self.assertEqual([], _tlk_writes(source), "components 401-403 contain TLK writers")
        harness_source = _strip_weidu_comments(HARNESS.read_text(encoding="utf-8"))
        self.assertEqual([], _tlk_writes(harness_source), "harness contains TLK writers")
        for banned in (r"\bCOPY_EXISTING\b", r"\bFILE_EXISTS_IN_GAME\b"):
            self.assertIsNone(re.search(banned, harness_source, re.IGNORECASE))


class _ConditionGraph:
    """Evaluate only fixture SPLPROT/op326 resource branches; this is not engine simulation."""

    def __init__(self, root: Path):
        self.root = root
        self.protection = read_2da(root / "SPLPROT.2DA")

    def _row(self, index: int) -> tuple[int, int, int]:
        _, values = self.protection.rows[index]
        return tuple(int(value, 0) for value in values)  # type: ignore[return-value]

    def _matches(self, effect: SplEffect | EffV2, strength: int, exceptional: int) -> bool:
        stat, table_value, relation = self._row(effect.parameter2)
        actual = {36: strength, 37: exceptional}.get(stat)
        if actual is None:
            return False
        expected = effect.parameter1 if table_value == -1 else table_value
        return {0: actual <= expected, 1: actual == expected, 2: actual < expected, 3: actual > expected, 4: actual >= expected, 5: actual != expected}[relation]

    def _resource_effects(self, resource: str) -> tuple[SplEffect | EffV2, ...]:
        for extension in ("spl", "SPL"):
            spl_path = self.root / f"{resource}.{extension}"
            if spl_path.is_file():
                return read_spl(spl_path).abilities[0].effects
        for extension in ("eff", "EFF"):
            eff_path = self.root / f"{resource}.{extension}"
            if eff_path.is_file():
                return (read_eff_v2(eff_path),)
        return ()

    def _apply(self, effects: tuple[SplEffect | EffV2, ...], strength: int, exceptional: int, depth: int = 0) -> tuple[int, int]:
        if depth > 12:
            raise AssertionError("conditional helper graph cycle")
        for effect in effects:
            if effect.opcode == 326 and self._matches(effect, strength, exceptional):
                strength, exceptional = self._apply(self._resource_effects(effect.resource), strength, exceptional, depth + 1)
            elif effect.opcode in (146, 272):
                strength, exceptional = self._apply(self._resource_effects(effect.resource), strength, exceptional, depth + 1)
            elif effect.opcode == 44 and effect.parameter2 == 1:
                strength = effect.parameter1
            elif effect.opcode == 97 and effect.parameter2 == 1:
                exceptional = effect.parameter1
        return strength, exceptional

    def apply_ability(self, ability: SplAbility, *, strength: int, exceptional: int) -> tuple[int, int]:
        return self._apply(ability.effects, strength, exceptional)

    def apply_immediate(self, ability: SplAbility, *, strength: int, exceptional: int) -> tuple[int, int]:
        checks = tuple(effect for effect in ability.effects if effect.opcode == 326)
        return self._apply(checks, strength, exceptional)

    def apply_heartbeat(self, ability: SplAbility, *, strength: int, exceptional: int) -> tuple[int, int]:
        pulses = tuple(effect for effect in ability.effects if effect.opcode == 272)
        return self._apply(pulses, strength, exceptional)


def _semantic_splprot_row(root: Path, semantic: tuple[int, int, int]) -> int:
    table = read_2da(root / "SPLPROT.2DA")
    matches = [
        index
        for index, (_, values) in enumerate(table.rows)
        if tuple(int(value, 0) for value in values) == semantic
    ]
    if not matches:
        raise AssertionError(f"SPLPROT semantic {semantic} is absent")
    return min(matches)


def _assert_helper_spl(
    root: Path,
    resref: str,
    expected_effects: tuple[SplEffect, ...],
) -> None:
    path = root / f"{resref}.spl"
    if not path.is_file() or (root / f"{resref}.eff").exists():
        raise AssertionError(f"{resref} must exist only as an SPL helper")
    spell = read_spl(path)
    if spell.casting_effects or len(spell.abilities) != 1:
        raise AssertionError(f"{resref} must have one header and no casting effects")
    ability = spell.abilities[0]
    if (ability.required_level, ability.target, ability.projectile) != (1, 5, 0):
        raise AssertionError(f"{resref} has an invalid basic self header: {ability}")
    actual = tuple(effect.canonical() for effect in ability.effects)
    expected = tuple(effect.canonical() for effect in expected_effects)
    if actual != expected:
        raise AssertionError(f"{resref} effects differ:\nactual={actual}\nexpected={expected}")


def _assert_strength_helper_graph(root: Path, divine_resref: str) -> None:
    expected_helper_files = {
        *(f"{resref}.SPL" for resref in STRENGTH_SETTER_BY_FLOOR.values()),
        *(f"{resref}.SPL" for resref in STRENGTH_CHECKER_BY_FLOOR.values()),
        f"{STRENGTH_EXCEPTION_18}.SPL",
        *(f"{resref}.EFF" for resref in STRENGTH_PULSE_BY_FLOOR.values()),
    }
    helper_files = [
        path
        for path in root.rglob("*")
        if path.is_file() and path.stem.upper() in STRENGTH_HELPER_RESREFS
    ]
    actual_helper_files = {
        path.relative_to(root).as_posix().upper() for path in helper_files
    }
    if len(helper_files) != len(expected_helper_files) or actual_helper_files != expected_helper_files:
        raise AssertionError(
            "Strength helper CREATE/MOVE output contains missing, duplicate, nested, or "
            f"wrong-extension files: {sorted(actual_helper_files)}"
        )

    str_lt_row = _semantic_splprot_row(root, STR_LT_SEMANTIC)
    str_eq_row = _semantic_splprot_row(root, STR_EQ_SEMANTIC)
    bonus_lt_row = _semantic_splprot_row(root, STR_BONUS_LT_SEMANTIC)

    for floor, setter in STRENGTH_SETTER_BY_FLOOR.items():
        setter_effects = [
            _helper_effect(321, parameter2=2, resource=setter),
            _helper_effect(
                44,
                parameter1=floor,
                parameter2=1,
                timing=10,
                resist_dispel=3,
                duration=STRENGTH_SETTER_DURATION_TICKS,
            ),
        ]
        if floor == 18:
            setter_effects.append(
                _helper_effect(
                    97,
                    parameter1=100,
                    parameter2=1,
                    timing=10,
                    resist_dispel=3,
                    duration=STRENGTH_SETTER_DURATION_TICKS,
                )
            )
        _assert_helper_spl(root, setter, tuple(setter_effects))

        checker_effects = [
            _helper_effect(321, parameter2=2, resource=setter),
            _helper_effect(
                326,
                parameter1=floor,
                parameter2=str_lt_row,
                resource=setter,
            ),
        ]
        if floor == 18:
            checker_effects.append(
                _helper_effect(
                    326,
                    parameter1=18,
                    parameter2=str_eq_row,
                    resource=STRENGTH_EXCEPTION_18,
                )
            )
        _assert_helper_spl(
            root,
            STRENGTH_CHECKER_BY_FLOOR[floor],
            tuple(checker_effects),
        )

        pulse = STRENGTH_PULSE_BY_FLOOR[floor]
        if not (root / f"{pulse}.eff").is_file() or (root / f"{pulse}.spl").exists():
            raise AssertionError(f"{pulse} must exist only as an EFF helper")
        actual_eff = read_eff_v2(root / f"{pulse}.eff")
        expected_eff = EffV2(
            opcode=146,
            target=2,
            power=4,
            parameter1=0,
            parameter2=1,
            timing=1,
            duration=0,
            probability1=100,
            probability2=0,
            resource=STRENGTH_CHECKER_BY_FLOOR[floor],
            flags=2,
        )
        if actual_eff.canonical() != expected_eff.canonical():
            raise AssertionError(
                f"{pulse} EFF differs:\nactual={actual_eff.canonical()}\n"
                f"expected={expected_eff.canonical()}"
            )

    _assert_helper_spl(
        root,
        STRENGTH_EXCEPTION_18,
        (
            _helper_effect(
                326,
                parameter1=100,
                parameter2=bonus_lt_row,
                resource=STRENGTH_SETTER_BY_FLOOR[18],
            ),
        ),
    )

    holy = read_spl(root / f"{HOLY_RESREF}.SPL")
    for level, ability in enumerate(holy.abilities, start=1):
        floor = _strength_floor(level)
        expected_immediate = [
            _helper_effect(
                326,
                parameter1=floor,
                parameter2=str_lt_row,
                resource=STRENGTH_SETTER_BY_FLOOR[floor],
            )
        ]
        if floor == 18:
            expected_immediate.append(
                _helper_effect(
                    326,
                    parameter1=18,
                    parameter2=str_eq_row,
                    resource=STRENGTH_EXCEPTION_18,
                )
            )
        expected_cleanups = (
            _helper_effect(321, parameter2=2, resource=divine_resref),
            _helper_effect(321, resource=HOLY_RESREF),
            *(
                _helper_effect(321, parameter2=2, resource=setter)
                for setter in STRENGTH_SETTER_BY_FLOOR.values()
            ),
        )
        actual_cleanups = tuple(
            effect.canonical() for effect in ability.effects[:6]
        )
        if actual_cleanups != tuple(
            effect.canonical() for effect in expected_cleanups
        ):
            raise AssertionError(
                f"level {level} does not begin exact Divine/self/recast cleanup"
            )
        actual_immediate = tuple(
            effect.canonical()
            for effect in ability.effects[6 : 6 + len(expected_immediate)]
        )
        if actual_immediate != tuple(effect.canonical() for effect in expected_immediate):
            raise AssertionError(f"level {level} has an invalid immediate Strength graph")
        pulses = [
            effect
            for effect in ability.effects
            if effect.opcode == 272 and effect.resource.upper() in STRENGTH_PULSE_RESREFS
        ]
        expected_pulse = SplEffect(
            opcode=272,
            target=1,
            power=4,
            parameter1=1,
            parameter2=3,
            timing=0,
            resist_dispel=3,
            duration=_tier_duration(level),
            probability1=100,
            probability2=0,
            resource=STRENGTH_PULSE_BY_FLOOR[floor],
        )
        if [effect.canonical() for effect in pulses] != [expected_pulse.canonical()]:
            raise AssertionError(f"level {level} has an invalid Strength heartbeat")
        expected_expiry = tuple(
            _helper_effect(
                321,
                parameter2=2,
                timing=4,
                duration=_tier_duration(level),
                resource=setter,
            ).canonical()
            for setter in STRENGTH_SETTER_BY_FLOOR.values()
        )
        actual_expiry = tuple(effect.canonical() for effect in ability.effects[-4:])
        if actual_expiry != expected_expiry:
            raise AssertionError(
                f"level {level} lacks exact all-tier Strength cleanup at parent expiry"
            )


def _private_state_values(root: Path) -> dict[str, int]:
    ids = read_ids(root / "SPLSTATE.IDS")
    values = {symbol: ids.value(symbol) for symbol in PRIVATE_STATE_SYMBOLS}
    if len(set(values.values())) != len(values):
        raise AssertionError(f"private SPLSTATE values are not unique: {values}")
    return values


def _active_splstate_row(root: Path) -> int:
    table = read_2da(root / "SPLPROT.2DA")
    rows = [
        index
        for index, (_, values) in enumerate(table.rows)
        if tuple(int(value, 0) for value in values) == ACTIVE_SPLSTATE_SEMANTIC
    ]
    if not rows:
        raise AssertionError("active-SPLSTATE semantic row is absent")
    return min(rows)


def _read_apr_helper(root: Path, resource: str) -> int:
    resource = resource.upper()
    path = root / f"{resource}.SPL"
    if not path.is_file():
        raise AssertionError(f"APR helper SPL does not exist: {resource}")
    spell = read_spl(path)
    if len(spell.abilities) != 1:
        raise AssertionError(f"APR helper {resource} has {len(spell.abilities)} headers")
    if spell.casting_effects:
        raise AssertionError(f"APR helper {resource} unexpectedly has casting effects")
    ability = spell.abilities[0]
    if (ability.required_level, ability.target, ability.projectile) != (1, 5, 0):
        raise AssertionError(
            f"APR helper {resource} has a noncanonical self header: "
            f"{(ability.required_level, ability.target, ability.projectile)}"
        )
    effects = ability.effects
    apr = [effect for effect in effects if effect.opcode == 1 and effect.parameter2 == 0]
    if len(apr) != 1:
        raise AssertionError(f"APR helper {resource} has {len(apr)} cumulative APR effects")
    mechanic = apr[0]
    expected = (
        _helper_effect(321, parameter2=2, resource=resource),
        _helper_effect(
            1,
            parameter1=mechanic.parameter1,
            parameter2=0,
            timing=0,
            resist_dispel=2,
            duration=1,
        ),
    )
    if tuple(effect.canonical() for effect in effects) != tuple(
        effect.canonical() for effect in expected
    ):
        raise AssertionError(
            f"APR helper {resource} must contain exactly the timed-only self cleanup "
            "followed by one one-second cumulative APR effect"
        )
    return mechanic.parameter1


def _strict_apr_helpers(root: Path) -> dict[str, int]:
    helpers = {}
    for path in root.glob("*.SPL"):
        try:
            key = _read_apr_helper(root, path.stem)
        except AssertionError:
            continue
        if key in APR_STATE_SYMBOL_BY_KEY:
            helpers[path.stem.upper()] = key
    return helpers


def _apr_condition_resources(
    root: Path, helper_resrefs: set[str]
) -> dict[str, EffV2]:
    conditions = {}
    for path in root.glob("*.EFF"):
        effect = read_eff_v2(path)
        if effect.resource.upper() in helper_resrefs:
            conditions[path.stem.upper()] = effect
    return conditions


def _read_conditional_apr_edge(
    root: Path,
    resource: str,
    *,
    expected_state: int,
    active_row: int,
    expected_helper: str,
) -> int:
    resource = resource.upper()
    expected_helper = expected_helper.upper()
    path = root / f"{resource}.EFF"
    if not path.is_file():
        raise AssertionError(
            f"heartbeat {resource} must be a standalone conditional EFF, not a direct or missing helper"
        )
    effect = read_eff_v2(path)
    actual = effect.canonical()
    expected = EffV2(
        opcode=326,
        target=2,
        power=4,
        parameter1=expected_state,
        parameter2=active_row,
        timing=1,
        duration=0,
        probability1=100,
        probability2=0,
        resource=expected_helper,
        flags=2,
    ).canonical()
    if actual != expected:
        raise AssertionError(
            f"conditional EFF {resource} has {actual}, expected active-SPLSTATE edge {expected}"
        )
    return _read_apr_helper(root, expected_helper)


def _tier_duration(level: int) -> int:
    if level <= 6:
        return 18
    if level <= 12:
        return 24
    return 30


def _strip_weidu_comments(source: str) -> str:
    source = re.sub(r"/\*.*?\*/", "", source, flags=re.DOTALL)
    return re.sub(r"//.*$", "", source, flags=re.MULTILINE)


def _tlk_writes(source: str) -> list[str]:
    uncommented = _strip_weidu_comments(source)
    writers = []
    if re.search(r"DIALOGF?\s*\.\s*TLK", uncommented, re.IGNORECASE):
        writers.append("DIALOG.TLK")
    without_strings = re.sub(r"~.*?~|\".*?\"", " ", uncommented, flags=re.DOTALL)
    tokens = re.findall(r"\b[A-Z][A-Z0-9_]*\b", without_strings.upper())
    for token in tokens:
        if (
            re.fullmatch(r"(?:[A-Z0-9]+_)*SAY(?:_[A-Z0-9]+)*", token)
            or re.fullmatch(r"(?:[A-Z0-9]+_)*STRING_SET(?:_[A-Z0-9]+)*", token)
            or token.startswith("RESOLVE_STR_REF")
            or re.fullmatch(r"(?:TLK_(?:APPEND|WRITE|PATCH|ALTER|SET)|(?:APPEND|WRITE|PATCH|ALTER|SET)_TLK)(?:_[A-Z0-9]+)*", token)
            or token in {"ADD_TRANSLATED_STRING", "REPLACE_SAY"}
        ):
            writers.append(token)
    return sorted(set(writers))


def _raw_file_tree(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(
            (candidate for candidate in root.rglob("*") if candidate.is_file()),
            key=lambda candidate: candidate.relative_to(root).as_posix().upper(),
        )
    }


def _nonstructural_spl_header(raw: bytes) -> bytes:
    normalized = bytearray(raw)
    normalized[0x64:0x72] = b"\0" * 0x0E
    return bytes(normalized)


def _nonstructural_ability_header(raw: bytes) -> bytes:
    normalized = bytearray(raw)
    normalized[0x1E:0x22] = b"\0" * 4
    return bytes(normalized)


if __name__ == "__main__":
    unittest.main()
