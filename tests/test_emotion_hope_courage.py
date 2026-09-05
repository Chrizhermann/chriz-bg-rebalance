"""RED contract tests for component 301: Hope/Courage mutual exclusion.

The fixtures intentionally use install-time-looking, noncanonical resrefs.
Nothing in this suite assumes SPWI428/SPWI429 or looks through a game KEY.
The Courage fixture also captures the observed IWDification relocation
regression: two removals of Fear and no self-removal.
"""

from __future__ import annotations

import dataclasses
import re
import struct
import subprocess
import tempfile
import unittest
from pathlib import Path

from tests.ie_formats import (
    ITM_ABILITY_SIZE,
    ITM_HEADER_SIZE,
    SPL_ABILITY_SIZE,
    SPL_HEADER_SIZE,
    ItmAbility,
    ItmFile,
    SplAbility,
    SplEffect,
    SplFile,
    read_itm,
    read_spl,
    write_itm,
    write_spl,
)


ROOT = Path(__file__).resolve().parents[1]
WEIDU = ROOT / "weidu.exe"
HARNESS = ROOT / "tests" / "weidu" / "emotion_hope_courage_harness.tp2"
PRODUCTION_TPA = ROOT / "chriz-bg-rebalance" / "lib" / "emotion_hope_courage.tpa"

# Deliberately unrelated to the vanilla/IWDification slots.  The production
# API receives these explicitly; deriving a resref from a numeric slot would
# make these tests fail.
COURAGE = "CXCRG42"
HOPE = "HXHOP77"
FEAR = "FXFER88"
HORROR = "WXHOR44"
INNATE_HORROR = "IXHOR33"
HOPELESSNESS = "DXHPL66"
SYMBOL = "SXHPL55"

COURAGE_STATE = 217
HOPE_STATE = 219
COURAGE_NAME = 810001
COURAGE_DESC = 810002
HOPE_NAME = 810003
HOPE_DESC = 810004

OLD_COURAGE_NAME = 710001
OLD_COURAGE_DESC = 710002
OLD_HOPE_NAME = 710003
OLD_HOPE_DESC = 710004

ERR_BENEFICIAL_TYPE = "CBR_EM_ERR_BENEFICIAL_TYPE"
ERR_BENEFICIAL_LEVEL = "CBR_EM_ERR_BENEFICIAL_LEVEL"
ERR_SPL_SIGNATURE = "CBR_EM_ERR_SPL_SIGNATURE"
ERR_BENEFICIAL_PARTITION = "CBR_EM_ERR_BENEFICIAL_PARTITION"
ERR_CASTING_PARTITION = "CBR_EM_ERR_CASTING_PARTITION"
ERR_ADVERSE_PARTITION = "CBR_EM_ERR_ADVERSE_PARTITION"
ERR_ITM_PARTITION = "CBR_EM_ERR_ITM_PARTITION"
ERR_RESREF_EMPTY = "CBR_EM_ERR_RESREF_EMPTY"
ERR_RESREF_LENGTH = "CBR_EM_ERR_RESREF_LENGTH"
ERR_RESREF_COLLISION = "CBR_EM_ERR_RESREF_COLLISION"
ERR_MISSING_COURAGE = "CBR_EM_ERR_MISSING_COURAGE"
ERR_MISSING_HOPE = "CBR_EM_ERR_MISSING_HOPE"
ERR_SCROLL_AMBIGUOUS = "CBR_EM_ERR_SCROLL_AMBIGUOUS"

def _put_resref(data: bytearray, offset: int, value: str) -> None:
    encoded = value.encode("ascii")
    if len(encoded) > 8:
        raise ValueError(value)
    data[offset : offset + 8] = encoded.ljust(8, b"\0")


def _read_i32(data: bytes, offset: int) -> int:
    return struct.unpack_from("<i", data, offset)[0]


def _spell(
    effects: tuple[SplEffect, ...],
    *,
    name: int,
    description: int,
    icon: str,
    ability_icon: str,
    projectile: int,
    secondary_type: int,
    completion_sound: str,
    casting_effects: tuple[SplEffect, ...] = (),
) -> SplFile:
    header = bytearray(SPL_HEADER_SIZE)
    header[:8] = b"SPL V1  "
    struct.pack_into("<ii", header, 0x08, name, name)
    _put_resref(header, 0x10, completion_sound)
    struct.pack_into("<H", header, 0x1C, 1)  # wizard spell type
    struct.pack_into("<H", header, 0x22, 11)  # Enchantment casting animation
    header[0x25] = 4  # Enchantment/Charm school
    header[0x27] = secondary_type
    struct.pack_into("<I", header, 0x34, 4)  # wizard level
    _put_resref(header, 0x3A, icon)
    struct.pack_into("<i", header, 0x50, description)
    ability_raw = bytearray(SPL_ABILITY_SIZE)
    ability_raw[0x00] = 2  # spell ability
    ability_raw[0x02] = 2  # spellbook location
    struct.pack_into("<H", ability_raw, 0x0E, 50)  # visual range
    struct.pack_into("<H", ability_raw, 0x12, 4)  # casting time
    struct.pack_into("<H", ability_raw, 0x1C, 1)  # engine-required count
    struct.pack_into("<H", ability_raw, 0x22, 1)  # one use/charge
    struct.pack_into("<H", ability_raw, 0x24, 1)  # no depletion
    return SplFile(
        abilities=(
            SplAbility(
                required_level=1,
                target=4,
                projectile=projectile,
                effects=effects,
                icon=ability_icon,
                raw=bytes(ability_raw),
            ),
        ),
        casting_effects=casting_effects,
        header_raw=bytes(header),
    )


def _transition(resource: str) -> SplEffect:
    """Timed-only self/reciprocal transition; the newly cast buff wins."""
    return SplEffect(
        opcode=321,
        target=2,
        power=4,
        parameter1=0,
        parameter2=2,
        timing=1,
        resist_dispel=2,
        duration=0,
        probability1=100,
        probability2=0,
        resource=resource,
        save_type=0,
        save_bonus=0,
        special=0,
    )


def _cleanse(resource: str) -> SplEffect:
    """Unconditional beneficial removal of an adverse fear/emotion source."""
    return SplEffect(
        opcode=321,
        target=2,
        power=4,
        parameter1=0,
        parameter2=0,
        timing=1,
        resist_dispel=2,
        duration=0,
        probability1=100,
        probability2=0,
        resource=resource,
        save_type=0,
        save_bonus=0,
        special=0,
    )


def _old_removal(
    resource: str,
    *,
    resist_dispel: int = 0,
    save_type: int = 0,
    save_bonus: int = 0,
) -> SplEffect:
    """The noncanonical administrative shape present in upstream fixtures."""
    return SplEffect(
        opcode=321,
        target=2,
        power=4,
        parameter2=0,
        timing=1,
        resist_dispel=resist_dispel,
        resource=resource,
        save_type=save_type,
        save_bonus=save_bonus,
    )


def _marker(state: int) -> SplEffect:
    return SplEffect(
        opcode=328,
        target=2,
        power=4,
        parameter1=1,
        parameter2=state,
        timing=0,
        resist_dispel=3,
        duration=300,
        special=1,
    )


COURAGE_CHROME = (
    SplEffect(opcode=141, target=2, power=4, parameter2=10, timing=1, resist_dispel=3),
    SplEffect(opcode=174, target=2, power=4, timing=1, resist_dispel=3, resource="CRGAUD"),
    SplEffect(
        opcode=61,
        target=2,
        power=4,
        parameter1=509245440,
        parameter2=1638400,
        timing=1,
        resist_dispel=3,
    ),
    SplEffect(opcode=215, target=2, power=4, timing=1, resist_dispel=3, resource="CRGVVC"),
    SplEffect(
        opcode=174,
        target=2,
        power=4,
        timing=4,
        resist_dispel=3,
        duration=300,
        resource="CRGLOOP",
    ),
    SplEffect(
        opcode=142,
        target=2,
        power=4,
        parameter2=187,
        timing=0,
        resist_dispel=3,
        duration=300,
    ),
)

HOPE_CHROME = (
    SplEffect(opcode=141, target=2, power=4, parameter2=11, timing=1, resist_dispel=3),
    SplEffect(opcode=174, target=2, power=4, timing=1, resist_dispel=3, resource="HOPAUD"),
    SplEffect(
        opcode=61,
        target=2,
        power=4,
        parameter1=492468224,
        parameter2=1572864,
        timing=1,
        resist_dispel=3,
    ),
    SplEffect(opcode=215, target=2, power=4, timing=1, resist_dispel=3, resource="HOPVVC"),
    SplEffect(
        opcode=174,
        target=2,
        power=4,
        timing=4,
        resist_dispel=3,
        duration=300,
        resource="HOPLOOP",
    ),
    SplEffect(
        opcode=142,
        target=2,
        power=4,
        parameter2=186,
        timing=0,
        resist_dispel=3,
        duration=300,
    ),
)

COURAGE_MECHANICS = (
    SplEffect(opcode=54, target=2, power=4, parameter1=1, timing=0, resist_dispel=3, duration=300),
    SplEffect(opcode=73, target=2, power=4, parameter1=3, timing=0, resist_dispel=3, duration=300),
    SplEffect(opcode=18, target=2, power=4, parameter1=5, timing=0, resist_dispel=3, duration=300),
    SplEffect(
        opcode=23,
        target=2,
        power=4,
        parameter1=20,
        parameter2=1,
        timing=0,
        resist_dispel=3,
        duration=300,
        special=0,
    ),
    SplEffect(opcode=240, target=2, power=4, parameter2=36, timing=1, resist_dispel=3),
    SplEffect(opcode=161, target=2, power=4, timing=1, resist_dispel=3),
)

HOPE_MECHANICS = (
    SplEffect(opcode=23, target=2, power=4, parameter1=2, timing=0, resist_dispel=3, duration=300),
    SplEffect(opcode=54, target=2, power=4, parameter1=2, timing=0, resist_dispel=3, duration=300),
    SplEffect(opcode=73, target=2, power=4, parameter1=2, timing=0, resist_dispel=3, duration=300),
    SplEffect(opcode=325, target=2, power=4, parameter1=2, timing=0, resist_dispel=3, duration=300),
)

COURAGE_CASTING = (
    SplEffect(opcode=146, target=1, resource="CRGCAST", timing=1),
    SplEffect(opcode=215, target=1, resource="CRGCVVC", timing=1),
)
HOPE_CASTING = (
    SplEffect(opcode=146, target=1, resource="HOPCAST", timing=1),
    SplEffect(opcode=215, target=1, resource="HOPCVVC", timing=1),
)

COURAGE_FOREIGN_MARKER = SplEffect(
    opcode=328,
    target=2,
    power=4,
    parameter1=1,
    parameter2=333,
    timing=0,
    resist_dispel=3,
    duration=211,
    special=1,
)
HOPE_FOREIGN_MARKER = SplEffect(
    opcode=328,
    target=2,
    power=4,
    parameter1=1,
    parameter2=335,
    timing=0,
    resist_dispel=3,
    duration=223,
    special=1,
)


def _adverse_spell(
    *,
    positive: str,
    mechanic_opcode: int,
    resource_prefix: str,
    header_count: int,
    power: int,
    removal_mode: str = "hostile",
) -> SplFile:
    abilities = []
    for index in range(header_count):
        probability1 = 90 - index * 17
        probability2 = 3 + index * 11
        exclusion = SplEffect(
            opcode=324,
            target=2,
            power=power,
            parameter2=55,
            timing=10,
            resist_dispel=0,
            probability1=100,
            probability2=0,
            resource=f"{resource_prefix}EX",
            save_type=0,
            save_bonus=0,
        )
        mechanic = SplEffect(
            opcode=mechanic_opcode,
            target=2,
            power=power,
            parameter1=index + 1,
            timing=0,
            resist_dispel=1,
            duration=30 + index,
            probability1=probability1,
            probability2=probability2,
            save_type=1,
            save_bonus=-index,
        )
        leading_chrome = SplEffect(
            opcode=215,
            target=2,
            power=power,
            timing=1,
            resist_dispel=0,
            resource=f"{resource_prefix}V{index}",
        )
        saved_chrome = SplEffect(
            opcode=174,
            target=2,
            power=power,
            timing=1,
            resist_dispel=1,
            probability1=probability1,
            probability2=probability2,
            resource=f"{resource_prefix}{index}",
            save_type=1,
            save_bonus=-index,
        )
        if removal_mode == "hostile":
            existing_removal = _adverse_remover(positive, mechanic)
        elif removal_mode == "unconditional":
            existing_removal = _old_removal(positive)
        else:
            raise ValueError(removal_mode)
        if index == 0:
            middle = (existing_removal,)
        elif index == 1:
            middle = ()
        else:
            # One stale unsaved clone plus a duplicate correct clone exercises
            # normalization against the explicitly located hostile opcode.
            middle = (
                _old_removal(positive),
                existing_removal,
            )
        if removal_mode == "unconditional":
            effects = (*middle, exclusion, leading_chrome, mechanic, saved_chrome)
        else:
            effects = (exclusion, leading_chrome, *middle, mechanic, saved_chrome)
        ability_raw = bytearray(SPL_ABILITY_SIZE)
        ability_raw[0x00] = 2
        ability_raw[0x02] = 2
        ability_raw[0x01] = 0xA0 | index
        struct.pack_into("<H", ability_raw, 0x0E, 50)
        struct.pack_into("<H", ability_raw, 0x12, 7 + index)
        struct.pack_into("<H", ability_raw, 0x1C, 1)
        abilities.append(
            SplAbility(
                required_level=1 + index,
                target=4,
                projectile=670 + index,
                effects=effects,
                icon=f"{resource_prefix}B",
                raw=bytes(ability_raw),
            )
        )
    header = bytearray(SPL_HEADER_SIZE)
    header[:8] = b"SPL V1  "
    struct.pack_into("<ii", header, 0x08, 720000, 720000)
    struct.pack_into("<H", header, 0x1C, 1)
    struct.pack_into("<I", header, 0x18, 0x10203040)
    struct.pack_into("<H", header, 0x22, 11)
    header[0x25] = 4
    struct.pack_into("<I", header, 0x34, 4)
    struct.pack_into("<i", header, 0x50, 720001)
    _put_resref(header, 0x3A, f"{resource_prefix}A")
    casting_effects = (
        SplEffect(opcode=146, target=1, power=power, timing=1, resource=f"{resource_prefix}C"),
        SplEffect(opcode=215, target=1, power=power, timing=1, resource=f"{resource_prefix}V"),
    )
    return SplFile(
        abilities=tuple(abilities),
        casting_effects=casting_effects,
        header_raw=bytes(header),
    )


def _scroll_item(
    learned_spell: str,
    *,
    use_spell: str,
    unidentified_name: int,
    identified_name: int,
    unidentified_description: int,
    identified_description: int,
    icon: str,
    usability: int,
    price: int,
) -> ItmFile:
    """Build the small ITM V1 subset WeiDU needs for a learn-spell scroll."""
    header = bytearray(ITM_HEADER_SIZE)
    header[:8] = b"ITM V1  "
    struct.pack_into("<H", header, 0x1C, 11)  # scroll item type
    struct.pack_into("<I", header, 0x1E, usability)
    struct.pack_into("<I", header, 0x34, price)
    _put_resref(header, 0x44, icon)

    use_ability = bytearray(ITM_ABILITY_SIZE)
    use_ability[0] = 3  # magical ability
    use_ability[0x01] = 0x5A
    use_ability[0x0C] = 1
    struct.pack_into("<H", use_ability, 0x22, 1)  # one charge

    learn_ability = bytearray(ITM_ABILITY_SIZE)
    learn_ability[0] = 3
    learn_ability[0x01] = 0xA5
    learn_ability[0x0C] = 7
    struct.pack_into("<H", learn_ability, 0x22, 2)

    use = SplEffect(
        opcode=148,
        target=1,
        power=4,
        parameter1=17,
        parameter2=23,
        timing=1,
        resist_dispel=2,
        resource=use_spell,
    )
    learn = SplEffect(
        opcode=147,
        target=1,
        power=4,
        timing=1,
        resist_dispel=2,
        resource=learned_spell,
    )
    globals_ = (
        SplEffect(opcode=319, target=1, parameter1=11, parameter2=3, timing=2, resource="SCRLG01"),
        SplEffect(opcode=319, target=1, parameter1=29, parameter2=7, timing=2, resource="SCRLG02"),
    )
    return ItmFile(
        abilities=(
            ItmAbility(effects=(use,), icon=icon, raw=bytes(use_ability)),
            ItmAbility(effects=(learn,), icon=f"{icon[:7]}L", raw=bytes(learn_ability)),
        ),
        unidentified_name=unidentified_name,
        identified_name=identified_name,
        unidentified_description=unidentified_description,
        identified_description=identified_description,
        global_effects=globals_,
        header_raw=bytes(header),
    )


@dataclasses.dataclass(frozen=True)
class FixtureOptions:
    markers: bool = True
    adverse_resources: bool = True
    matching_scrolls: bool = True
    missing_adverse: str | None = None
    single_matching_scroll: str | None = None
    malformed: str | None = None


def build_fixture(root: Path, options: FixtureOptions = FixtureOptions()) -> None:
    root.mkdir(parents=True)
    (root / "CBR_INPUT.OK").write_bytes(b"component-301 fixture\n")
    if options.missing_adverse not in {None, FEAR, HORROR, INNATE_HORROR, HOPELESSNESS, SYMBOL}:
        raise ValueError(options.missing_adverse)
    if options.single_matching_scroll not in {None, "courage", "hope"}:
        raise ValueError(options.single_matching_scroll)

    # Captures the live regression exactly at the relationship level that
    # matters: both leading administrative effects point at Fear and neither
    # points at Courage itself.
    courage_effects = (
        _old_removal(FEAR),
        _old_removal(FEAR),
        *COURAGE_CHROME,
        *COURAGE_MECHANICS[:-1],
        _old_removal(HORROR),
        _old_removal(INNATE_HORROR),
        COURAGE_MECHANICS[-1],
        COURAGE_FOREIGN_MARKER,
    )
    hope_effects = (
        _old_removal(HOPE),
        _old_removal(HOPELESSNESS),
        _old_removal(SYMBOL),
        *HOPE_CHROME,
        *HOPE_MECHANICS,
        HOPE_FOREIGN_MARKER,
    )
    if options.markers:
        courage_effects += (
            _marker(COURAGE_STATE),
            dataclasses.replace(_marker(COURAGE_STATE), parameter1=7, duration=299),
        )
        hope_effects += (
            _marker(HOPE_STATE),
            dataclasses.replace(_marker(HOPE_STATE), parameter1=9, duration=298),
        )

    courage = _spell(
        courage_effects,
        name=OLD_COURAGE_NAME,
        description=OLD_COURAGE_DESC,
        icon="CRGICON",
        ability_icon="CRGAB",
        projectile=611,
        secondary_type=7,
        completion_sound="CRGCMP7",
        casting_effects=COURAGE_CASTING,
    )
    hope = _spell(
        hope_effects,
        name=OLD_HOPE_NAME,
        description=OLD_HOPE_DESC,
        icon="HOPICON",
        ability_icon="HOPAB",
        projectile=612,
        secondary_type=2,
        completion_sound="HOPCMP2",
        casting_effects=HOPE_CASTING,
    )
    if options.malformed != "missing_courage":
        write_spl(root / f"{COURAGE}.SPL", courage)
    if options.malformed != "missing_hope":
        write_spl(root / f"{HOPE}.SPL", hope)
    if options.adverse_resources:
        adverse_fixtures = (
            (
                FEAR,
                _adverse_spell(
                    positive=COURAGE,
                    mechanic_opcode=24,
                    resource_prefix="FER",
                    header_count=3,
                    power=4,
                ),
            ),
            (
                HOPELESSNESS,
                _adverse_spell(
                    positive=HOPE,
                    mechanic_opcode=45,
                    resource_prefix="HPL",
                    header_count=3,
                    power=4,
                    removal_mode="unconditional",
                ),
            ),
            (
                SYMBOL,
                _adverse_spell(
                    positive=HOPE,
                    mechanic_opcode=45,
                    resource_prefix="SYM",
                    header_count=2,
                    power=7,
                ),
            ),
            (
                HORROR,
                _adverse_spell(
                    positive="OTHBUFF",
                    mechanic_opcode=24,
                    resource_prefix="HOR",
                    header_count=1,
                    power=2,
                ),
            ),
            (
                INNATE_HORROR,
                _adverse_spell(
                    positive="OTHBUFF",
                    mechanic_opcode=24,
                    resource_prefix="INH",
                    header_count=1,
                    power=2,
                ),
            ),
        )
        for resref, spell in adverse_fixtures:
            if resref != options.missing_adverse:
                write_spl(root / f"{resref}.SPL", spell)

    if options.matching_scrolls:
        if options.single_matching_scroll in {None, "courage"}:
            write_itm(
                root / "ZCRGSC1.ITM",
                _scroll_item(
                    COURAGE,
                    use_spell="CRGUSE",
                    unidentified_name=730001,
                    identified_name=OLD_COURAGE_NAME,
                    unidentified_description=730002,
                    identified_description=OLD_COURAGE_DESC,
                    icon="SCRCRG",
                    usability=0x10203041,
                    price=11117,
                ),
            )
        if options.single_matching_scroll in {None, "hope"}:
            write_itm(
                root / "ZHOPSC2.ITM",
                _scroll_item(
                    HOPE,
                    use_spell="HOPUSE",
                    unidentified_name=730003,
                    identified_name=OLD_HOPE_NAME,
                    unidentified_description=730004,
                    identified_description=OLD_HOPE_DESC,
                    icon="SCRHOP",
                    usability=0x50607082,
                    price=22229,
                ),
            )
    write_itm(
        root / "FOREIGN.ITM",
        _scroll_item(
            "OTHRSPL",
            # A non-learning opcode deliberately references Courage.  If the
            # implementation scans by resource alone instead of opcode 147,
            # the foreign-item byte-preservation assertion catches it.
            use_spell=COURAGE,
            unidentified_name=740001,
            identified_name=740002,
            unidentified_description=740003,
            identified_description=740004,
            icon="OTHICON",
            usability=0x90A0B0C3,
            price=33347,
        ),
    )

    if options.malformed == "courage_signature":
        path = root / f"{COURAGE}.SPL"
        data = bytearray(path.read_bytes())
        data[:8] = b"ITM V1  "
        path.write_bytes(data)
    elif options.malformed in {"fear_slice", "beneficial_slice"}:
        resref = FEAR if options.malformed == "fear_slice" else COURAGE
        path = root / f"{resref}.SPL"
        data = bytearray(path.read_bytes())
        ability_offset = struct.unpack_from("<I", data, 0x64)[0]
        struct.pack_into("<H", data, ability_offset + 0x1E, 0x7FFF)
        path.write_bytes(data)
    elif options.malformed in {"beneficial_gap", "beneficial_overlap", "beneficial_trailing"}:
        path = root / f"{COURAGE}.SPL"
        data = bytearray(path.read_bytes())
        ability_offset = struct.unpack_from("<I", data, 0x64)[0]
        count, first = struct.unpack_from("<HH", data, ability_offset + 0x1E)
        if options.malformed == "beneficial_gap":
            count, first = count - 1, first + 1
        elif options.malformed == "beneficial_overlap":
            count, first = count + 1, first - 1
        else:
            count -= 1
        struct.pack_into("<HH", data, ability_offset + 0x1E, count, first)
        path.write_bytes(data)
    elif options.malformed == "casting_slice":
        path = root / f"{HOPE}.SPL"
        data = bytearray(path.read_bytes())
        struct.pack_into("<HH", data, 0x6E, 0x7FFE, 2)
        path.write_bytes(data)
    elif options.malformed == "casting_orphan":
        path = root / f"{HOPE}.SPL"
        data = bytearray(path.read_bytes())
        struct.pack_into("<H", data, 0x70, 1)
        path.write_bytes(data)
    elif options.malformed in {"scroll_gap", "scroll_overlap", "scroll_trailing", "scroll_orphan"}:
        path = root / "ZCRGSC1.ITM"
        data = bytearray(path.read_bytes())
        ability_offset = struct.unpack_from("<I", data, 0x64)[0]
        if options.malformed == "scroll_gap":
            struct.pack_into("<H", data, 0x70, 1)
        elif options.malformed == "scroll_overlap":
            struct.pack_into("<HH", data, ability_offset + 0x1E, 1, 1)
        elif options.malformed == "scroll_trailing":
            struct.pack_into("<H", data, ability_offset + ITM_ABILITY_SIZE + 0x1E, 0)
        else:
            struct.pack_into("<H", data, ability_offset + 0x1E, 0)
        path.write_bytes(data)
    elif options.malformed in {"beneficial_partial", "scroll_partial"}:
        path = (
            root / f"{COURAGE}.SPL"
            if options.malformed == "beneficial_partial"
            else root / "ZCRGSC1.ITM"
        )
        path.write_bytes(path.read_bytes() + b"\xA5")
    elif options.malformed == "adverse_zero_abilities":
        path = root / f"{FEAR}.SPL"
        spell = read_spl(path)
        write_spl(path, dataclasses.replace(spell, abilities=()))
    elif options.malformed in {"scroll_ambiguous_courage_first", "scroll_ambiguous_hope_first"}:
        path = root / "ZCRGSC1.ITM"
        item = read_itm(path)
        hope_learn_raw = bytearray(item.abilities[1].raw)
        hope_learn_raw[0x01] ^= 0x3C
        hope_learn = ItmAbility(
            effects=(dataclasses.replace(item.abilities[1].effects[0], resource=HOPE),),
            icon="AMBHOP",
            raw=bytes(hope_learn_raw),
        )
        if options.malformed == "scroll_ambiguous_courage_first":
            abilities = (*item.abilities, hope_learn)
        else:
            abilities = (item.abilities[0], hope_learn, item.abilities[1])
        write_itm(path, dataclasses.replace(item, abilities=abilities))
    elif options.malformed == "wrong_type":
        path = root / f"{COURAGE}.SPL"
        data = bytearray(path.read_bytes())
        struct.pack_into("<H", data, 0x1C, 2)
        path.write_bytes(data)
    elif options.malformed == "wrong_level":
        path = root / f"{HOPE}.SPL"
        data = bytearray(path.read_bytes())
        struct.pack_into("<I", data, 0x34, 5)
        path.write_bytes(data)
    elif options.malformed in {"missing_courage", "missing_hope"}:
        pass
    elif options.malformed is not None:
        raise ValueError(options.malformed)


class HarnessResult:
    def __init__(
        self,
        fixture: Path,
        *,
        courage_state: int = COURAGE_STATE,
        hope_state: int = HOPE_STATE,
        resrefs: dict[str, str] | None = None,
    ) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="cbr-emotion-")
        base = Path(self.temporary.name)
        self.output = base / "output"
        self.run_dir = base / "weidu-run"
        self.run_dir.mkdir()
        command = [
            str(WEIDU),
            str(HARNESS),
            "--nogame",
            "--force-install-list",
            "0",
            "--args",
            str(PRODUCTION_TPA),
            "--args",
            str(fixture),
            "--args",
            str(self.output),
        ]
        final_resrefs = {
            "courage": COURAGE,
            "hope": HOPE,
            "fear": FEAR,
            "horror": HORROR,
            "innate_horror": INNATE_HORROR,
            "hopelessness": HOPELESSNESS,
            "symbol": SYMBOL,
        }
        if resrefs is not None:
            final_resrefs.update(resrefs)
        self.resrefs = final_resrefs
        for value in (
            final_resrefs["courage"],
            final_resrefs["hope"],
            final_resrefs["fear"],
            final_resrefs["horror"],
            final_resrefs["innate_horror"],
            final_resrefs["hopelessness"],
            final_resrefs["symbol"],
            str(courage_state),
            str(hope_state),
            str(COURAGE_NAME),
            str(COURAGE_DESC),
            str(HOPE_NAME),
            str(HOPE_DESC),
        ):
            command.extend(("--args", value))
        command.extend(("--no-exit-pause", "--quick-log"))
        self.process = subprocess.run(
            command,
            cwd=self.run_dir,
            capture_output=True,
            text=True,
            timeout=45,
            check=False,
        )

    @property
    def transcript(self) -> str:
        return f"{self.process.stdout}\n{self.process.stderr}"

    @property
    def succeeded(self) -> bool:
        return (
            self.process.returncode == 0
            and (self.output / "CBR_TEST.OK").exists()
            and "SUCCESSFULLY INSTALLED" in self.transcript
        )

    def cleanup(self) -> None:
        self.temporary.cleanup()


def _raw_tree(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix().upper(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file() and path.name.upper() != "CBR_TEST.OK"
    }


def _expected_courage(*, adverse: bool = True, marker: bool = True) -> tuple[SplEffect, ...]:
    effects: tuple[SplEffect, ...] = (_transition(COURAGE), _transition(HOPE))
    if adverse:
        effects += (_cleanse(FEAR), _cleanse(HORROR), _cleanse(INNATE_HORROR))
    effects += COURAGE_CHROME + COURAGE_MECHANICS
    if marker:
        effects += (_marker(COURAGE_STATE),)
    return effects + (COURAGE_FOREIGN_MARKER,)


def _expected_hope(*, adverse: bool = True, marker: bool = True) -> tuple[SplEffect, ...]:
    effects: tuple[SplEffect, ...] = (_transition(HOPE), _transition(COURAGE))
    if adverse:
        effects += (_cleanse(HOPELESSNESS), _cleanse(SYMBOL))
    effects += HOPE_CHROME + HOPE_MECHANICS
    if marker:
        effects += (_marker(HOPE_STATE),)
    return effects + (HOPE_FOREIGN_MARKER,)


def _masked(data: bytes, *ranges: tuple[int, int]) -> bytes:
    value = bytearray(data)
    for start, end in ranges:
        value[start:end] = bytes(end - start)
    return bytes(value)


def _raw_partition_coverage(data: bytes, ability_size: int) -> tuple[int, list[int]]:
    """Decode only raw partition offsets/counts, independently of ie_formats."""
    ability_offset = struct.unpack_from("<I", data, 0x64)[0]
    ability_count = struct.unpack_from("<H", data, 0x68)[0]
    effect_offset = struct.unpack_from("<I", data, 0x6A)[0]
    global_first, global_count = struct.unpack_from("<HH", data, 0x6E)
    effect_bytes = len(data) - effect_offset
    if effect_bytes < 0 or effect_bytes % 0x30:
        return -1, []
    effect_count = effect_bytes // 0x30
    coverage = list(range(global_first, global_first + global_count))
    for index in range(ability_count):
        header = ability_offset + index * ability_size
        count, first = struct.unpack_from("<HH", data, header + 0x1E)
        coverage.extend(range(first, first + count))
    return effect_count, coverage


def _assert_exact_partition_coverage(test: unittest.TestCase, data: bytes, ability_size: int) -> None:
    effect_count, coverage = _raw_partition_coverage(data, ability_size)
    test.assertGreaterEqual(effect_count, 0)
    test.assertEqual(list(range(effect_count)), sorted(coverage), "effect-table gap or orphan")
    test.assertEqual(len(coverage), len(set(coverage)), "effect-table partition overlap")


def _adverse_remover(resource: str, donor: SplEffect) -> SplEffect:
    return SplEffect(
        opcode=321,
        target=donor.target,
        power=donor.power,
        parameter1=0,
        parameter2=0,
        timing=1,
        resist_dispel=donor.resist_dispel,
        duration=0,
        probability1=donor.probability1,
        probability2=donor.probability2,
        resource=resource,
        save_type=donor.save_type,
        save_bonus=donor.save_bonus,
        special=donor.special,
    )


class EmotionHopeCourageTests(unittest.TestCase):
    def run_case(
        self,
        options: FixtureOptions = FixtureOptions(),
        *,
        courage_state: int = COURAGE_STATE,
        hope_state: int = HOPE_STATE,
        resrefs: dict[str, str] | None = None,
        expect_success: bool = True,
    ) -> tuple[HarnessResult, Path]:
        holder = tempfile.TemporaryDirectory(prefix="cbr-emotion-fixture-")
        self.addCleanup(holder.cleanup)
        fixture = Path(holder.name) / "fixture"
        build_fixture(fixture, options)
        result = HarnessResult(
            fixture,
            courage_state=courage_state,
            hope_state=hope_state,
            resrefs=resrefs,
        )
        self.addCleanup(result.cleanup)
        if expect_success:
            if not PRODUCTION_TPA.is_file():
                self.fail(
                    f"missing production library {PRODUCTION_TPA}; "
                    f"the RED harness reached INCLUDE as intended:\n{result.transcript}"
                )
            self.assertTrue(result.succeeded, result.transcript)
        else:
            if not PRODUCTION_TPA.is_file():
                self.fail(
                    f"cannot test malformed-input rejection until {PRODUCTION_TPA} exists; "
                    f"the RED harness reached INCLUDE as intended:\n{result.transcript}"
                )
            self.assertFalse(result.succeeded, "malformed fixture was accepted")
            self.assertFalse((result.output / "CBR_TEST.OK").exists())
            self.assertIn("NOT INSTALLED DUE TO ERRORS", result.transcript)
            self.assertEqual(
                {},
                _raw_tree(result.output),
                "failed preflight left a partial output tree instead of rolling back",
            )
        return result, fixture

    def test_raw_fixture_partitions_cover_each_effect_exactly_once(self) -> None:
        holder = tempfile.TemporaryDirectory(prefix="cbr-emotion-partitions-")
        self.addCleanup(holder.cleanup)
        fixture = Path(holder.name) / "fixture"
        build_fixture(fixture)
        for path in (*fixture.glob("*.SPL"), *fixture.glob("*.ITM")):
            with self.subTest(path=path.name):
                ability_size = SPL_ABILITY_SIZE if path.suffix.upper() == ".SPL" else ITM_ABILITY_SIZE
                _assert_exact_partition_coverage(self, path.read_bytes(), ability_size)

        malformed_cases = (
            ("beneficial_slice", COURAGE, ".SPL", SPL_ABILITY_SIZE),
            ("beneficial_gap", COURAGE, ".SPL", SPL_ABILITY_SIZE),
            ("beneficial_overlap", COURAGE, ".SPL", SPL_ABILITY_SIZE),
            ("beneficial_trailing", COURAGE, ".SPL", SPL_ABILITY_SIZE),
            ("beneficial_partial", COURAGE, ".SPL", SPL_ABILITY_SIZE),
            ("casting_orphan", HOPE, ".SPL", SPL_ABILITY_SIZE),
            ("fear_slice", FEAR, ".SPL", SPL_ABILITY_SIZE),
            ("scroll_gap", "ZCRGSC1", ".ITM", ITM_ABILITY_SIZE),
            ("scroll_overlap", "ZCRGSC1", ".ITM", ITM_ABILITY_SIZE),
            ("scroll_trailing", "ZCRGSC1", ".ITM", ITM_ABILITY_SIZE),
            ("scroll_orphan", "ZCRGSC1", ".ITM", ITM_ABILITY_SIZE),
            ("scroll_partial", "ZCRGSC1", ".ITM", ITM_ABILITY_SIZE),
        )
        for malformed, resref, suffix, ability_size in malformed_cases:
            with self.subTest(malformed=malformed):
                case_root = Path(holder.name) / malformed
                build_fixture(case_root, FixtureOptions(malformed=malformed))
                count, coverage = _raw_partition_coverage(
                    (case_root / f"{resref}{suffix}").read_bytes(), ability_size
                )
                self.assertTrue(
                    count < 0
                    or sorted(coverage) != list(range(count))
                    or len(coverage) != len(set(coverage)),
                    f"{malformed} did not create a raw partition-coverage defect",
                )

    def test_repairs_observed_regression_and_builds_canonical_beneficial_spells(self) -> None:
        result, fixture = self.run_case()
        for resref, expected in (
            (COURAGE, _expected_courage()),
            (HOPE, _expected_hope()),
        ):
            before_raw = (fixture / f"{resref}.SPL").read_bytes()
            after_raw = (result.output / f"{resref}.SPL").read_bytes()
            _assert_exact_partition_coverage(self, before_raw, SPL_ABILITY_SIZE)
            _assert_exact_partition_coverage(self, after_raw, SPL_ABILITY_SIZE)
            before = SplFile.from_bytes(before_raw)
            after = SplFile.from_bytes(after_raw)
            self.assertEqual(1, len(after.abilities), f"{resref} gained an extra ability")
            self.assertEqual(
                tuple(effect.canonical() for effect in expected),
                tuple(effect.canonical() for effect in after.abilities[0].effects),
                f"{resref} complete ordered recipient package",
            )
            self.assertEqual(len(expected), len(after.abilities[0].effects))
            self.assertEqual(
                _masked(before.header_raw, (0x08, 0x10), (0x50, 0x54)),
                _masked(after.header_raw, (0x08, 0x10), (0x50, 0x54)),
                f"{resref} non-text header bytes",
            )
            self.assertEqual(
                [effect.to_bytes() for effect in before.casting_effects],
                [effect.to_bytes() for effect in after.casting_effects],
                f"{resref} casting-feature bytes",
            )
            self.assertEqual(
                _masked(before.abilities[0].raw, (0x1E, 0x22)),
                _masked(after.abilities[0].raw, (0x1E, 0x22)),
                f"{resref} non-partition ability bytes",
            )

        courage = read_spl(result.output / f"{COURAGE}.SPL")
        courage_admin = [effect for effect in courage.abilities[0].effects if effect.opcode == 321]
        self.assertEqual(
            [COURAGE, HOPE, FEAR, HORROR, INNATE_HORROR],
            [effect.resource for effect in courage_admin],
        )
        self.assertEqual(
            [_transition(COURAGE).canonical(), _transition(HOPE).canonical()],
            [effect.canonical() for effect in courage_admin[:2]],
        )
        self.assertEqual(
            [_cleanse(FEAR).canonical(), _cleanse(HORROR).canonical(), _cleanse(INNATE_HORROR).canonical()],
            [effect.canonical() for effect in courage_admin[2:]],
        )

    def test_preserves_distinct_visual_audio_chrome_and_dynamic_markers(self) -> None:
        result, fixture = self.run_case()
        before_courage = read_spl(fixture / f"{COURAGE}.SPL")
        before_hope = read_spl(fixture / f"{HOPE}.SPL")
        courage = read_spl(result.output / f"{COURAGE}.SPL")
        hope = read_spl(result.output / f"{HOPE}.SPL")

        self.assertEqual(b"CRGCMP7\0", before_courage.header_raw[0x10:0x18])
        self.assertEqual(b"HOPCMP2\0", before_hope.header_raw[0x10:0x18])
        self.assertEqual((7, 2), (before_courage.header_raw[0x27], before_hope.header_raw[0x27]))
        self.assertEqual(before_courage.header_raw[0x10:0x18], courage.header_raw[0x10:0x18])
        self.assertEqual(before_hope.header_raw[0x10:0x18], hope.header_raw[0x10:0x18])
        self.assertEqual((7, 2), (courage.header_raw[0x27], hope.header_raw[0x27]))

        chrome_opcodes = {61, 141, 142, 174, 215}
        for before, after, label in (
            (before_courage, courage, "Courage"),
            (before_hope, hope, "Hope"),
        ):
            self.assertEqual(before.casting_effects, after.casting_effects, f"{label} casting chrome")
            before_chrome = [
                effect.to_bytes()
                for effect in before.abilities[0].effects
                if effect.opcode in chrome_opcodes
            ]
            after_chrome = [
                effect.to_bytes()
                for effect in after.abilities[0].effects
                if effect.opcode in chrome_opcodes
            ]
            self.assertEqual(before_chrome, after_chrome, f"{label} recipient chrome")
        self.assertNotEqual(COURAGE_CHROME, HOPE_CHROME)
        for before, after, state, requested, foreign, label in (
            (before_courage, courage, COURAGE_STATE, _marker(COURAGE_STATE), COURAGE_FOREIGN_MARKER, "Courage"),
            (before_hope, hope, HOPE_STATE, _marker(HOPE_STATE), HOPE_FOREIGN_MARKER, "Hope"),
        ):
            self.assertEqual(
                2,
                len([effect for effect in before.abilities[0].effects if effect.opcode == 328 and effect.parameter2 == state]),
                f"{label} fixture lost its duplicate requested marker",
            )
            output_markers = [effect for effect in after.abilities[0].effects if effect.opcode == 328]
            self.assertEqual(
                [requested.canonical()],
                [effect.canonical() for effect in output_markers if effect.parameter2 == state],
            )
            self.assertEqual(
                [foreign.canonical()],
                [effect.canonical() for effect in output_markers if effect.parameter2 == foreign.parameter2],
            )

    def test_optional_spell_state_markers_can_be_absent(self) -> None:
        result, _fixture = self.run_case(
            FixtureOptions(markers=False), courage_state=-1, hope_state=-1
        )
        for resref, requested_state, foreign in (
            (COURAGE, COURAGE_STATE, COURAGE_FOREIGN_MARKER),
            (HOPE, HOPE_STATE, HOPE_FOREIGN_MARKER),
        ):
            spell = read_spl(result.output / f"{resref}.SPL")
            self.assertFalse(
                any(effect.opcode == 328 and effect.parameter2 == requested_state for effect in spell.abilities[0].effects),
                f"unexpected requested op328 marker in {resref}",
            )
            self.assertEqual(
                [foreign.canonical()],
                [effect.canonical() for effect in spell.abilities[0].effects if effect.opcode == 328],
            )

    def test_each_spell_state_symbol_can_be_independently_absent(self) -> None:
        for courage_state, hope_state, courage_marker, hope_marker in (
            (-1, HOPE_STATE, False, True),
            (COURAGE_STATE, -1, True, False),
        ):
            with self.subTest(courage_state=courage_state, hope_state=hope_state):
                result, _fixture = self.run_case(
                    FixtureOptions(markers=False),
                    courage_state=courage_state,
                    hope_state=hope_state,
                )
                courage = read_spl(result.output / f"{COURAGE}.SPL")
                hope = read_spl(result.output / f"{HOPE}.SPL")
                self.assertEqual(
                    tuple(effect.canonical() for effect in _expected_courage(marker=courage_marker)),
                    tuple(effect.canonical() for effect in courage.abilities[0].effects),
                )
                self.assertEqual(
                    tuple(effect.canonical() for effect in _expected_hope(marker=hope_marker)),
                    tuple(effect.canonical() for effect in hope.abilities[0].effects),
                )

    def assert_adverse_transformed(
        self,
        result: HarnessResult,
        fixture: Path,
        resref: str,
        positive: str,
        mechanic_opcode: int,
        power: int,
        removal_mode: str,
    ) -> None:
        before_raw = (fixture / f"{resref}.SPL").read_bytes()
        after_raw = (result.output / f"{resref}.SPL").read_bytes()
        _assert_exact_partition_coverage(self, before_raw, SPL_ABILITY_SIZE)
        _assert_exact_partition_coverage(self, after_raw, SPL_ABILITY_SIZE)
        before = SplFile.from_bytes(before_raw)
        after = SplFile.from_bytes(after_raw)
        self.assertEqual(before.header_raw, after.header_raw, f"{resref} header bytes")
        self.assertEqual(
            [effect.to_bytes() for effect in before.casting_effects],
            [effect.to_bytes() for effect in after.casting_effects],
            f"{resref} casting bytes",
        )
        self.assertEqual(len(before.abilities), len(after.abilities))
        probabilities = set()
        for index, (before_ability, after_ability) in enumerate(
            zip(before.abilities, after.abilities, strict=True)
        ):
            exclusion = next(effect for effect in before_ability.effects if effect.opcode == 324)
            self.assertEqual((0, 0), (exclusion.resist_dispel, exclusion.save_type))
            if removal_mode == "unconditional" and index != 1:
                self.assertEqual(_old_removal(positive).canonical(), before_ability.effects[0].canonical())
            else:
                self.assertEqual(324, before_ability.effects[0].opcode)
            donor = next(effect for effect in before_ability.effects if effect.opcode == mechanic_opcode)
            probabilities.add((donor.probability1, donor.probability2))
            removals = [
                effect
                for effect in after_ability.effects
                if effect.opcode == 321 and effect.resource == positive
            ]
            self.assertEqual(1, len(removals), f"{resref} header {index}")
            removal = removals[0]
            expected = (
                _old_removal(positive)
                if removal_mode == "unconditional"
                else _adverse_remover(positive, donor)
            )
            self.assertEqual(expected.canonical(), removal.canonical())
            donor_after_index = next(
                position
                for position, effect in enumerate(after_ability.effects)
                if effect.opcode == mechanic_opcode
            )
            expected_position = 0 if removal_mode == "unconditional" else donor_after_index - 1
            self.assertEqual(expected_position, after_ability.effects.index(removal))
            if removal_mode == "unconditional":
                self.assertEqual(removal, after_ability.effects[0])
            self.assertEqual(power, removal.power)
            before_foreign = [
                effect.to_bytes()
                for effect in before_ability.effects
                if not (effect.opcode == 321 and effect.resource == positive)
            ]
            after_foreign = [
                effect.to_bytes()
                for effect in after_ability.effects
                if not (effect.opcode == 321 and effect.resource == positive)
            ]
            self.assertEqual(before_foreign, after_foreign, f"{resref} header {index} chrome")
            self.assertEqual(
                _masked(before_ability.raw, (0x1E, 0x22)),
                _masked(after_ability.raw, (0x1E, 0x22)),
                f"{resref} header {index} non-partition ability bytes",
            )
        self.assertEqual(len(before.abilities), len(probabilities), f"{resref} probability fixtures")

    def test_adverse_emotions_remove_the_matching_benefit_in_every_header(self) -> None:
        result, fixture = self.run_case()
        for case in (
            (FEAR, COURAGE, 24, 4, "hostile"),
            (HOPELESSNESS, HOPE, 45, 4, "unconditional"),
            (SYMBOL, HOPE, 45, 7, "hostile"),
        ):
            self.assert_adverse_transformed(result, fixture, *case)

        for untouched in (HORROR, INNATE_HORROR):
            self.assertEqual(
                (fixture / f"{untouched}.SPL").read_bytes(),
                (result.output / f"{untouched}.SPL").read_bytes(),
            )

    def test_repoints_spell_and_matching_scroll_string_references_only(self) -> None:
        result, fixture = self.run_case()
        for resref, name, description in (
            (COURAGE, COURAGE_NAME, COURAGE_DESC),
            (HOPE, HOPE_NAME, HOPE_DESC),
        ):
            data = (result.output / f"{resref}.SPL").read_bytes()
            self.assertEqual(name, _read_i32(data, 0x08))
            self.assertEqual(name, _read_i32(data, 0x0C))
            self.assertEqual(description, _read_i32(data, 0x50))

        for filename, learned, name, description, usability, price in (
            ("ZCRGSC1.ITM", COURAGE, COURAGE_NAME, COURAGE_DESC, 0x10203041, 11117),
            ("ZHOPSC2.ITM", HOPE, HOPE_NAME, HOPE_DESC, 0x50607082, 22229),
        ):
            before_raw = (fixture / filename).read_bytes()
            after_raw = (result.output / filename).read_bytes()
            expected_raw = bytearray(before_raw)
            struct.pack_into("<i", expected_raw, 0x0C, name)
            struct.pack_into("<i", expected_raw, 0x54, description)
            self.assertEqual(bytes(expected_raw), after_raw, f"{filename} changed outside text fields")
            before = ItmFile.from_bytes(before_raw)
            after = ItmFile.from_bytes(after_raw)
            self.assertEqual(usability, struct.unpack_from("<I", before_raw, 0x1E)[0])
            self.assertEqual(price, struct.unpack_from("<I", before_raw, 0x34)[0])
            self.assertEqual(usability, struct.unpack_from("<I", after_raw, 0x1E)[0])
            self.assertEqual(price, struct.unpack_from("<I", after_raw, 0x34)[0])
            self.assertEqual([319, 319], [effect.opcode for effect in before.global_effects])
            self.assertEqual([[148], [147]], [[effect.opcode for effect in ability.effects] for ability in before.abilities])
            self.assertEqual(2, len(before.abilities))
            _assert_exact_partition_coverage(self, before_raw, ITM_ABILITY_SIZE)
            _assert_exact_partition_coverage(self, after_raw, ITM_ABILITY_SIZE)
            self.assertEqual(
                [learned],
                [
                    effect.resource
                    for ability in after.abilities
                    for effect in ability.effects
                    if effect.opcode == 147
                ],
            )
        self.assertEqual(
            (fixture / "FOREIGN.ITM").read_bytes(),
            (result.output / "FOREIGN.ITM").read_bytes(),
        )

    def test_optional_adverse_resources_may_be_absent(self) -> None:
        result, _fixture = self.run_case(FixtureOptions(adverse_resources=False))
        courage = read_spl(result.output / f"{COURAGE}.SPL")
        hope = read_spl(result.output / f"{HOPE}.SPL")
        self.assertEqual(
            tuple(effect.canonical() for effect in _expected_courage(adverse=False)),
            tuple(effect.canonical() for effect in courage.abilities[0].effects),
        )
        self.assertEqual(
            tuple(effect.canonical() for effect in _expected_hope(adverse=False)),
            tuple(effect.canonical() for effect in hope.abilities[0].effects),
        )
        for resref in (FEAR, HORROR, INNATE_HORROR, HOPELESSNESS, SYMBOL):
            self.assertFalse((result.output / f"{resref}.SPL").exists())

    def test_one_optional_adverse_resource_may_be_absent_independently(self) -> None:
        transformed = (
            (FEAR, COURAGE, 24, 4, "hostile"),
            (HOPELESSNESS, HOPE, 45, 4, "unconditional"),
            (SYMBOL, HOPE, 45, 7, "hostile"),
        )
        for missing in (FEAR, HORROR, INNATE_HORROR, HOPELESSNESS, SYMBOL):
            with self.subTest(missing=missing):
                result, fixture = self.run_case(FixtureOptions(missing_adverse=missing))
                courage = read_spl(result.output / f"{COURAGE}.SPL")
                hope = read_spl(result.output / f"{HOPE}.SPL")
                expected_courage = tuple(
                    effect for effect in _expected_courage()
                    if not (effect.opcode == 321 and effect.resource == missing)
                )
                expected_hope = tuple(
                    effect for effect in _expected_hope()
                    if not (effect.opcode == 321 and effect.resource == missing)
                )
                self.assertEqual(
                    tuple(effect.canonical() for effect in expected_courage),
                    tuple(effect.canonical() for effect in courage.abilities[0].effects),
                )
                self.assertEqual(
                    tuple(effect.canonical() for effect in expected_hope),
                    tuple(effect.canonical() for effect in hope.abilities[0].effects),
                )
                self.assertFalse((result.output / f"{missing}.SPL").exists())
                for case in transformed:
                    if case[0] != missing:
                        self.assert_adverse_transformed(result, fixture, *case)
                for untouched in (HORROR, INNATE_HORROR):
                    if untouched != missing:
                        self.assertEqual(
                            (fixture / f"{untouched}.SPL").read_bytes(),
                            (result.output / f"{untouched}.SPL").read_bytes(),
                        )

    def test_exactly_one_matching_scroll_is_a_valid_input(self) -> None:
        for selected, filename, absent, name, description in (
            ("courage", "ZCRGSC1.ITM", "ZHOPSC2.ITM", COURAGE_NAME, COURAGE_DESC),
            ("hope", "ZHOPSC2.ITM", "ZCRGSC1.ITM", HOPE_NAME, HOPE_DESC),
        ):
            with self.subTest(selected=selected):
                result, fixture = self.run_case(FixtureOptions(single_matching_scroll=selected))
                before_raw = (fixture / filename).read_bytes()
                expected_raw = bytearray(before_raw)
                struct.pack_into("<i", expected_raw, 0x0C, name)
                struct.pack_into("<i", expected_raw, 0x54, description)
                self.assertEqual(bytes(expected_raw), (result.output / filename).read_bytes())
                self.assertFalse((result.output / absent).exists())
                self.assertEqual(
                    (fixture / "FOREIGN.ITM").read_bytes(),
                    (result.output / "FOREIGN.ITM").read_bytes(),
                )

    def test_no_matching_scroll_is_a_valid_task4_boundary(self) -> None:
        result, fixture = self.run_case(FixtureOptions(matching_scrolls=False))
        self.assertFalse((result.output / "ZCRGSC1.ITM").exists())
        self.assertFalse((result.output / "ZHOPSC2.ITM").exists())
        self.assertEqual(
            (fixture / "FOREIGN.ITM").read_bytes(),
            (result.output / "FOREIGN.ITM").read_bytes(),
        )

    def test_second_application_is_exactly_byte_idempotent(self) -> None:
        first, _fixture = self.run_case()
        second = HarnessResult(first.output)
        self.addCleanup(second.cleanup)
        if not PRODUCTION_TPA.is_file():
            self.fail(f"missing production library {PRODUCTION_TPA}")
        self.assertTrue(second.succeeded, second.transcript)
        self.assertEqual(_raw_tree(first.output), _raw_tree(second.output))

    def test_preflight_rejects_wrong_type_and_level_atomically(self) -> None:
        for malformed, token in (
            ("wrong_type", ERR_BENEFICIAL_TYPE),
            ("wrong_level", ERR_BENEFICIAL_LEVEL),
        ):
            with self.subTest(malformed=malformed):
                result, _fixture = self.run_case(FixtureOptions(malformed=malformed), expect_success=False)
                self.assertIn(token, result.transcript)

    def test_preflight_rejects_malformed_signatures_and_partitions_atomically(self) -> None:
        cases = (
            ("courage_signature", ERR_SPL_SIGNATURE),
            ("beneficial_slice", ERR_BENEFICIAL_PARTITION),
            ("beneficial_gap", ERR_BENEFICIAL_PARTITION),
            ("beneficial_overlap", ERR_BENEFICIAL_PARTITION),
            ("beneficial_trailing", ERR_BENEFICIAL_PARTITION),
            ("beneficial_partial", ERR_BENEFICIAL_PARTITION),
            ("casting_slice", ERR_CASTING_PARTITION),
            ("casting_orphan", ERR_CASTING_PARTITION),
            ("fear_slice", ERR_ADVERSE_PARTITION),
            ("scroll_gap", ERR_ITM_PARTITION),
            ("scroll_overlap", ERR_ITM_PARTITION),
            ("scroll_trailing", ERR_ITM_PARTITION),
            ("scroll_orphan", ERR_ITM_PARTITION),
            ("scroll_partial", ERR_ITM_PARTITION),
        )
        for malformed, token in cases:
            with self.subTest(malformed=malformed):
                result, _fixture = self.run_case(FixtureOptions(malformed=malformed), expect_success=False)
                self.assertIn(token, result.transcript)

    def test_preflight_rejects_empty_long_and_identical_resrefs_atomically(self) -> None:
        cases = (
            ({"courage": ""}, ERR_RESREF_EMPTY),
            ({"hope": "TOO_LONG9"}, ERR_RESREF_LENGTH),
            ({"hope": COURAGE}, ERR_RESREF_COLLISION),
            ({"hope": COURAGE.lower()}, ERR_RESREF_COLLISION),
            ({"fear": COURAGE}, ERR_RESREF_COLLISION),
            ({"horror": COURAGE}, ERR_RESREF_COLLISION),
            ({"innate_horror": COURAGE}, ERR_RESREF_COLLISION),
            ({"hopelessness": HOPE}, ERR_RESREF_COLLISION),
            ({"symbol": HOPE}, ERR_RESREF_COLLISION),
        )
        for resrefs, token in cases:
            with self.subTest(resrefs=resrefs):
                result, _fixture = self.run_case(resrefs=resrefs, expect_success=False)
                self.assertIn(token, result.transcript)

    def test_preflight_rejects_missing_beneficial_resources_atomically(self) -> None:
        for malformed, token in (
            ("missing_courage", ERR_MISSING_COURAGE),
            ("missing_hope", ERR_MISSING_HOPE),
        ):
            with self.subTest(malformed=malformed):
                result, _fixture = self.run_case(FixtureOptions(malformed=malformed), expect_success=False)
                self.assertIn(token, result.transcript)

    def test_preflight_rejects_present_adverse_with_zero_abilities_atomically(self) -> None:
        holder = tempfile.TemporaryDirectory(prefix="cbr-emotion-zero-adverse-")
        self.addCleanup(holder.cleanup)
        fixture = Path(holder.name) / "fixture"
        build_fixture(fixture, FixtureOptions(malformed="adverse_zero_abilities"))
        fear_raw = (fixture / f"{FEAR}.SPL").read_bytes()
        _assert_exact_partition_coverage(self, fear_raw, SPL_ABILITY_SIZE)
        self.assertEqual(0, len(SplFile.from_bytes(fear_raw).abilities))

        result = HarnessResult(fixture)
        self.addCleanup(result.cleanup)
        self.assertFalse(result.succeeded, "zero-header adverse SPL was accepted")
        self.assertIn(ERR_ADVERSE_PARTITION, result.transcript)
        self.assertFalse((result.output / "CBR_TEST.OK").exists())
        self.assertEqual({}, _raw_tree(result.output), "failed preflight did not roll back atomically")

    def test_preflight_rejects_scroll_that_teaches_both_emotions_atomically(self) -> None:
        for malformed, expected_order in (
            ("scroll_ambiguous_courage_first", [COURAGE, HOPE]),
            ("scroll_ambiguous_hope_first", [HOPE, COURAGE]),
        ):
            with self.subTest(malformed=malformed):
                holder = tempfile.TemporaryDirectory(prefix="cbr-emotion-ambiguous-scroll-")
                self.addCleanup(holder.cleanup)
                fixture = Path(holder.name) / "fixture"
                build_fixture(fixture, FixtureOptions(malformed=malformed))
                item_raw = (fixture / "ZCRGSC1.ITM").read_bytes()
                _assert_exact_partition_coverage(self, item_raw, ITM_ABILITY_SIZE)
                item = ItmFile.from_bytes(item_raw)
                learned = [
                    effect.resource
                    for ability in item.abilities
                    for effect in ability.effects
                    if effect.opcode == 147
                ]
                self.assertEqual(expected_order, learned)
                self.assertTrue(all(len(ability.effects) == 1 for ability in item.abilities))

                result = HarnessResult(fixture)
                self.addCleanup(result.cleanup)
                self.assertFalse(result.succeeded, "dual-Emotion learn scroll was accepted")
                self.assertIn(ERR_SCROLL_AMBIGUOUS, result.transcript)
                self.assertFalse((result.output / "CBR_TEST.OK").exists())
                self.assertEqual(
                    {}, _raw_tree(result.output), "ambiguous-scroll preflight did not roll back atomically"
                )

    def test_harness_is_hermetic_and_calls_the_public_action_once(self) -> None:
        source = re.sub(r"//[^\n]*", "", HARNESS.read_text(encoding="utf-8"))
        self.assertEqual(
            1,
            len(re.findall(r"\bLAF\s+cbr_apply_emotion_hope_courage\b", source)),
        )
        for required in (
            "resource_dir",
            "courage_resref",
            "hope_resref",
            "fear_resref",
            "horror_resref",
            "innate_horror_resref",
            "hopelessness_resref",
            "symbol_resref",
            "courage_spell_state",
            "hope_spell_state",
            "courage_name_strref",
            "courage_desc_strref",
            "hope_name_strref",
            "hope_desc_strref",
        ):
            self.assertRegex(source, rf"\b{required}\b")
        for forbidden in (r"\bCOPY_EXISTING\b", r"\bFILE_EXISTS_IN_GAME\b"):
            self.assertNotRegex(source, forbidden)

        if PRODUCTION_TPA.is_file():
            production_source = re.sub(
                r"//[^\n]*", "", PRODUCTION_TPA.read_text(encoding="utf-8")
            )
            for forbidden in (
                r"\bCOPY_EXISTING(?:_REGEXP)?\b",
                r"\bFILE_EXISTS_IN_GAME\b",
                r"\bRES_NUM_OF_SPELL_NAME\b",
                r"\bIDS_OF_SYMBOL\b",
                r"\bADD_SPELL\b",
                r"\bCREATE\b",
                r"\bGAME_IS\b",
                r"\bGAME_INCLUDES\b",
            ):
                self.assertNotRegex(production_source, forbidden)

        result, fixture = self.run_case()
        expected_output = {
            path.relative_to(fixture).as_posix().upper()
            for path in fixture.rglob("*")
            if path.is_file()
        } | {"CBR_TEST.OK"}
        actual_output = {
            path.relative_to(result.output).as_posix().upper()
            for path in result.output.rglob("*")
            if path.is_file()
        }
        self.assertEqual(expected_output, actual_output)
        self.assertLessEqual(
            {path.name.upper() for path in result.run_dir.iterdir()},
            {"WEIDU.LOG", "BACKUP"},
        )
        self.assertFalse(
            any("OVERRIDE" in {part.upper() for part in path.parts} for path in result.run_dir.rglob("*"))
        )


if __name__ == "__main__":
    unittest.main()
