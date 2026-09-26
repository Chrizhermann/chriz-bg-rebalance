"""Public-installer contract for component 301 on synthetic BG2:EE games.

The file-backed transformer has its own exhaustive tests.  This suite covers
the boundary that only the real component can exercise: symbolic spell slots,
KEY/BIFF discovery, ADD_SPELL allocation, scroll/store publication, WeiDU
transactions, reinstall, and uninstall.  All slot, state, item, and store
resrefs are deliberately synthetic.
"""

from __future__ import annotations

import dataclasses
import hashlib
import re
import shutil
import struct
import subprocess
import tempfile
import unittest
import zlib
from pathlib import Path

from tests.ie_formats import (
    IdsFile,
    ItmAbility,
    ItmFile,
    SplEffect,
    TwoDA,
    read_ids,
    read_itm,
    read_spl,
    spell_resref,
    write_itm,
    write_spl,
)
from tests.test_emotion_hope_courage import (
    COURAGE_CHROME,
    COURAGE_MECHANICS,
    HOPE_CHROME,
    HOPE_MECHANICS,
    HARNESS,
    PRODUCTION_TPA,
    ROOT,
    WEIDU,
    _adverse_spell,
    _marker,
    _old_removal,
    _scroll_item,
    _spell,
)


SETUP_TP2 = ROOT / "setup-chriz-bg-rebalance.tp2"
COMPONENT = 301
LABEL = "cbr_emotion_hope_courage_exclusion"
GROUP_REF = 1300
EXCLUSION_SENTENCE = (
    "A creature can be affected by only one of Emotion, Courage and Emotion, Hope at a time."
)

COURAGE_SYMBOL = "WIZARD_EMOTION_COURAGE"
HOPE_SYMBOL = "WIZARD_EMOTION_HOPE"
ENCHANTED_SYMBOL = "WIZARD_ENCHANTED_WEAPON"
FEAR_SYMBOL = "WIZARD_EMOTION_FEAR"
HORROR_SYMBOL = "WIZARD_HORROR"
INNATE_HORROR_SYMBOL = "INNATE_HORROR"
HOPELESS_SYMBOL = "WIZARD_EMOTION_HOPELESSNESS"
SYMBOL_HOPELESS_SYMBOL = "CLERIC_SYMBOL_HOPELESSNESS"

COURAGE_ID = 2442
HOPE_ID = 2477
COURAGE_RESREF = "SPWI442"
HOPE_RESREF = "SPWI477"
ENCHANTED_RESREF = "SPWI463"
FEAR_RESREF = "SPWI464"
HORROR_RESREF = "SPWI265"
INNATE_HORROR_RESREF = "SPIN163"
HOPELESS_RESREF = "SPWI466"
SYMBOL_HOPELESS_RESREF = "SPPR767"
BASE_HOPELESS_ID = 2411
BASE_HOPELESS_RESREF = "SPWI411"
LIVE_INNATE_HORROR_ID = 3105
LIVE_INNATE_HORROR_RESREF = "SPIN105"
LIVE_HOLD_MISSILE_ID = 190
HOLD_MISSILE_ID = 377
IWD_EMOTION_PROJECTILE_SOURCE = "IDPRO407"
IWD_EMOTION_PROJECTILE_SHA256 = (
    "B4725639B39D11DE292932EFC59693C6B6B2D32925472E63A353087FACF1E6BE"
)
PRIVATE_EMOTION_PROJECTILE = "CBR301P"
PRIVATE_EMOTION_VVC = "CBR301V"
PRIVATE_EMOTION_ANIMATION = "CBR301A"
PRIVATE_EMOTION_PROJECTILE_SOUND = "CBR301W"
PRIVATE_EMOTION_EFFECT_SOUND = "CBR301E"
PRIVATE_EMOTION_PROJECTILE_SHA256 = (
    "86E6DCFD8583774898B3D26F8ED3AB307E05F53778FD51BD98836BF232328282"
)
PRIVATE_EMOTION_VVC_SHA256 = (
    "332054F1C378E1DAE16444BD4DABD32D0BD28A2DE535395B11814ADBE7A4C03F"
)
IWD_EMOTION_ICON_SHA256 = {
    "courage": (
        "E0E53967D41C708828C42233C5C750624FE9E7B208976B9996ACC8440F29958C",
        "B107A950BD2AA2E0D7252DB6260CD831024808E763AE02218912205E4B1729AB",
        "BC563D88057570B69AE28EB678116EA8441FA5744351FAF38A190E925379797E",
    ),
    "hope": (
        "869D53B72C94D6C5D2AA028F13E6C4C498E1E359678FB7CD8F534D990ED9B033",
        "DAF665ABBDD70F84BCFF678EC0F50640FFB106252AC1B4C79D1FD7A16EFF926D",
        "7EDD84FE668D42A80BEC7F8BDB6074802EFD5BC3CD30DB58E58FCFB1EF98B778",
    ),
}
IWD_EMOTION_SUPPORT_SHA256 = {
    "#ARE_M21.WAV": "46BDF9F2E7631AA717B2ADA6870B2F6A6D7DE71CA7BC5480B1AD6DE654EBE3B2",
    "#EFF_E03.WAV": "634DFE623FA34E096637F82487373B382CF290CB80E56D5D5DC8DE67EB61DC1F",
    "#GENENCH.VVC": "670B8A6AC5A403263DC2CB64BCCA126BFDF77C9DB87F258E6FA4393DA42F9D8A",
    "ENCHANX.BAM": "730E330EF9390EDF139C77EC01730630D89D1D4030CA86A1E450B7F155C6C33B",
    "IDPRO407.PRO": IWD_EMOTION_PROJECTILE_SHA256,
    "SPWI427A.BAM": IWD_EMOTION_ICON_SHA256["courage"][0],
    "SPWI427B.BAM": IWD_EMOTION_ICON_SHA256["courage"][1],
    "SPWI427C.BAM": IWD_EMOTION_ICON_SHA256["courage"][2],
    "SPWI427D.BAM": "6156D0716907E4DD3195CCBF957B061F97A68051CE20FF9CE9C64A04422DFBCC",
    "SPWI429A.BAM": IWD_EMOTION_ICON_SHA256["hope"][0],
    "SPWI429B.BAM": IWD_EMOTION_ICON_SHA256["hope"][1],
    "SPWI429C.BAM": IWD_EMOTION_ICON_SHA256["hope"][2],
    "SPWI429D.BAM": "4045A535EAF4BD0B90E377B232D7EE8964AE9A09CAD50BC01D7BB523FF00E93E",
}

COURAGE_EXISTING_SCROLL = "CTGBIF"
HOPE_EXISTING_SCROLL = "HTGOVR"
ENCHANTED_DONOR_SCROLL = "DNBIF01"
NATIVE_ENCHANTED_DONOR_SCROLL = "SCRL6M"
HOPELESS_DONOR_SCROLL = "DNOVR02"
AMBIGUOUS_ENCHANTED_DONOR_SCROLL = "DNALT01"
AMBIGUOUS_HOPELESS_DONOR_SCROLL = "DNALT02"
BIF_DONOR_STORE = "BFSTORE"
OVERRIDE_DONOR_STORE = "OVSTORE"
FOREIGN_BIF_ITEM = "BFFOREN"
FOREIGN_BIF_STORE = "BFOTHER"
COURAGE_FALLBACK_SCROLL = "CBRCRGSC"
HOPE_FALLBACK_SCROLL = "CBRHOPSC"
UNRELATED_LEARN_RESREF = "ALTSP147"
UNRELATED_USE_RESREF = "ALTSP148"
UNRELATED_CAST_RESREF = "ALTSP146"

UNRELATED_LEARN_EFFECT = SplEffect(
    opcode=147,
    target=1,
    power=2,
    parameter1=31,
    parameter2=37,
    timing=1,
    resist_dispel=1,
    resource=UNRELATED_LEARN_RESREF,
)
UNRELATED_USE_EFFECT = SplEffect(
    opcode=148,
    target=2,
    power=3,
    parameter1=41,
    parameter2=43,
    timing=2,
    duration=47,
    resist_dispel=3,
    resource=UNRELATED_USE_RESREF,
)
UNRELATED_CAST_EFFECT = SplEffect(
    opcode=146,
    target=1,
    power=3,
    parameter1=53,
    parameter2=59,
    timing=1,
    resist_dispel=2,
    resource=UNRELATED_CAST_RESREF,
)

ONE_EMPTY_STRING_TLK = (
    struct.pack("<8sHII", b"TLK V1  ", 0, 1, 0x2C)
    + struct.pack("<H8siiII", 0, b"\0" * 8, 0, 0, 0, 0)
)

STATDESC_FIXTURE = (
    b"2DA V1.0\n"
    b"-1\n"
    b"DESCRIPTION BAM_FILE\n"
    b"186 -1 ****\n"
    b"187 -1 ****\n"
    b"188 25904 VALIDICN\n"
    b"200 25904 OCCUPIED\n"
)
STATDESC_MALFORMED_SHAPE = (
    b"2DA V1.0\n"
    b"-1\n"
    b"DESCRIPTION\n"
    b"186 -1\n"
)
STATDESC_COURAGE_D_COLLISION = STATDESC_FIXTURE + b"201 25904 SPWI402D\n"

RESOURCE_TYPE = {
    "ITM": 1005,
    "SPL": 1006,
    "IDS": 1008,
    "ARE": 1010,
    "2DA": 1012,
    "STO": 1014,
}


def _raw_tree(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix().upper(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_key_and_bif(
    game_root: Path, resources: tuple[tuple[str, str, bytes], ...]
) -> Path:
    """Write one uncompressed BIFF and a KEY indexing mixed fixture types."""
    bif_relative = Path("DATA/CBREM301.BIF")
    bif_path = game_root / bif_relative
    bif_path.parent.mkdir(parents=True, exist_ok=True)
    table_offset = 0x14
    payload_offset = table_offset + len(resources) * 0x10
    table = bytearray()
    payload = bytearray()
    key_entries: list[tuple[str, int, int]] = []
    for index, (resref, extension, resource) in enumerate(resources):
        extension = extension.upper()
        resource_type = RESOURCE_TYPE[extension]
        table.extend(
            struct.pack("<IIIHH", index, payload_offset + len(payload), len(resource), resource_type, 0)
        )
        payload.extend(resource)
        key_entries.append((resref.upper(), resource_type, index))
    bif_path.write_bytes(
        struct.pack("<4s4sIII", b"BIFF", b"V1  ", len(resources), 0, table_offset)
        + table
        + payload
    )

    bif_name = (str(bif_relative).replace("/", "\\") + "\0").encode("ascii")
    bif_table_offset = 0x18
    resource_table_offset = bif_table_offset + 0x0C
    names_offset = resource_table_offset + len(resources) * 0x0E
    key = bytearray(
        struct.pack(
            "<4s4sIIII", b"KEY ", b"V1  ", 1, len(resources), bif_table_offset, resource_table_offset
        )
    )
    key.extend(struct.pack("<IIHH", bif_path.stat().st_size, names_offset, len(bif_name), 0))
    for resref, resource_type, locator in key_entries:
        key.extend(struct.pack("<8sHI", resref.encode("ascii").ljust(8, b"\0"), resource_type, locator))
    key.extend(bif_name)
    (game_root / "chitin.key").write_bytes(key)
    return bif_path


def _store(entries: tuple[tuple[str, bytes], ...]) -> bytes:
    """Build STO V1.0 with live data after the sale table and trailing bytes."""
    header = bytearray(0x9C)
    header[:8] = b"STORV1.0"
    struct.pack_into("<I", header, 0x08, 0)
    struct.pack_into("<I", header, 0x0C, 810900)
    purchased = struct.pack("<I", 11)
    drinks = b"DRINK-TABLE-SENTINEL"  # 20 bytes
    cures = b"CURE-SENTIN!"  # 12 bytes
    trailing = b"CBR-STO-TRAILING-BYTES"
    purchased_offset = len(header)
    sale_offset = purchased_offset + len(purchased)
    struct.pack_into("<II", header, 0x2C, purchased_offset, 1)
    struct.pack_into("<II", header, 0x34, sale_offset, len(entries))
    rows = bytearray()
    for resref, tail in entries:
        if len(tail) != 0x14:
            raise ValueError("STO sale-entry tail must be exactly 20 bytes")
        rows.extend(resref.encode("ascii").ljust(8, b"\0") + tail)
    drinks_offset = sale_offset + len(rows)
    cures_offset = drinks_offset + len(drinks)
    struct.pack_into("<II", header, 0x4C, drinks_offset, 1)
    struct.pack_into("<II", header, 0x70, cures_offset, 1)
    return bytes(header + purchased + rows + drinks + cures + trailing)


def _store_entries(data: bytes) -> tuple[bytes, ...]:
    if data[:8] != b"STORV1.0":
        raise ValueError("not STO V1.0")
    offset, count = struct.unpack_from("<II", data, 0x34)
    if offset < 0x9C or offset + count * 0x1C > len(data):
        raise ValueError("STO sale table is out of bounds")
    return tuple(data[offset + i * 0x1C : offset + (i + 1) * 0x1C] for i in range(count))


def _store_with_clones(data: bytes, donor_to_scroll: dict[str, str]) -> bytes:
    """Return the exact expected STO bytes after clone insertion."""
    sale_offset, sale_count = struct.unpack_from("<II", data, 0x34)
    sale_end = sale_offset + sale_count * 0x1C
    original_rows = _store_entries(data)
    rows: list[bytes] = []
    for row in original_rows:
        rows.append(row)
        donor = _entry_resref(row)
        if donor in donor_to_scroll:
            rows.append(donor_to_scroll[donor].encode("ascii").ljust(8, b"\0") + row[8:])
    inserted = (len(rows) - len(original_rows)) * 0x1C
    header_and_prefix = bytearray(data[:sale_offset])
    struct.pack_into("<I", header_and_prefix, 0x38, len(rows))
    for field in (0x2C, 0x4C, 0x70):
        value = struct.unpack_from("<I", header_and_prefix, field)[0]
        if value >= sale_end:
            struct.pack_into("<I", header_and_prefix, field, value + inserted)
    return bytes(header_and_prefix) + b"".join(rows) + data[sale_end:]


def _entry_resref(entry: bytes) -> str:
    return entry[:8].split(b"\0", 1)[0].decode("ascii").upper()


def _resref_at(data: bytes, offset: int) -> str:
    return data[offset : offset + 8].split(b"\0", 1)[0].decode("ascii").upper()


def _statdesc_row_has_icon(data: bytes, row: int) -> bool:
    table = TwoDA.from_text(data.decode("ascii"))
    return table.cell(str(row), "BAM_FILE").upper() not in {"", "****", table.default.upper()}


def _bam_frame_dimensions(data: bytes) -> tuple[tuple[int, int], ...]:
    if data[:8] == b"BAMCV1  ":
        data = zlib.decompress(data[12:])
    if data[:8] != b"BAM V1  ":
        raise ValueError(f"not BAM V1: {data[:8]!r}")
    frame_count = struct.unpack_from("<H", data, 0x08)[0]
    frame_offset = struct.unpack_from("<I", data, 0x0C)[0]
    return tuple(
        struct.unpack_from("<HH", data, frame_offset + index * 0x0C)
        for index in range(frame_count)
    )


def _beneficial(resref: str, other: str, *, courage: bool, marker: int | None) -> bytes:
    mechanics = COURAGE_MECHANICS if courage else HOPE_MECHANICS
    chrome = COURAGE_CHROME if courage else HOPE_CHROME
    effects = (_old_removal(other), *chrome, *mechanics)
    if marker is not None:
        effects += (_marker(marker), dataclasses.replace(_marker(marker), parameter1=9, duration=299))
    return _spell(
        effects,
        name=710101 if courage else 710103,
        description=710102 if courage else 710104,
        icon="CRGICON" if courage else "HOPICON",
        ability_icon="CRGAB" if courage else "HOPAB",
        projectile=611 if courage else 612,
        secondary_type=7 if courage else 2,
        completion_sound="CRGCMP7" if courage else "HOPCMP2",
    ).to_bytes()


def _plain_spell(*, level: int = 4) -> bytes:
    spell = _spell(
        (dataclasses.replace(HOPE_MECHANICS[1], parameter1=1),),
        name=710201,
        description=710202,
        icon="DONICON",
        ability_icon="DONAB",
        projectile=190,
        secondary_type=2,
        completion_sound="DONCMP",
    )
    header = bytearray(spell.header_raw)
    struct.pack_into("<I", header, 0x34, level)
    return dataclasses.replace(spell, header_raw=bytes(header)).to_bytes()


def _adverse_bytes(positive: str, opcode: int, prefix: str, *, power: int = 4, unconditional: bool = False) -> bytes:
    return _adverse_spell(
        positive=positive,
        mechanic_opcode=opcode,
        resource_prefix=prefix,
        header_count=2,
        power=power,
        removal_mode="unconditional" if unconditional else "hostile",
    ).to_bytes()


def _base_hopelessness_without_opcode_45(positive: str) -> bytes:
    """Model native SPWI411's relevant shape: 14 headers and no opcode 45."""
    spell = _adverse_spell(
        positive=positive,
        mechanic_opcode=106,
        resource_prefix="HPL",
        header_count=14,
        power=4,
        removal_mode="unconditional",
    )
    return dataclasses.replace(
        spell,
        abilities=tuple(
            dataclasses.replace(
                ability,
                effects=tuple(
                    effect
                    for effect in ability.effects
                    if effect.opcode != 321
                ),
            )
            for ability in spell.abilities
        ),
    ).to_bytes()


def _scroll(learned: str, use: str, seed: int, icon: str) -> bytes:
    scroll = _scroll_item(
        learned,
        use_spell=use,
        unidentified_name=730000 + seed,
        identified_name=731000 + seed,
        unidentified_description=732000 + seed,
        identified_description=733000 + seed,
        icon=icon,
        usability=0x10203040 ^ seed,
        price=10000 + seed,
    )
    # A matching scroll can legitimately contain other spell-use/learn
    # records.  Keep them in distinct table partitions so the installer must
    # select by both opcode and resource, not rewrite every opcode 147/148 in
    # the item merely because one record matched discovery.
    return dataclasses.replace(
        scroll,
        global_effects=scroll.global_effects + (UNRELATED_USE_EFFECT,),
        abilities=scroll.abilities
        + (
            ItmAbility(
                effects=(UNRELATED_LEARN_EFFECT,),
                icon=f"{icon[:7]}X",
            ),
        ),
    ).to_bytes()


def _native_enchanted_weapon_scroll() -> bytes:
    """Model native SCRL6M: opcode 146 use plus opcode 147 learning."""
    scroll = _scroll_item(
        ENCHANTED_RESREF,
        use_spell=ENCHANTED_RESREF,
        unidentified_name=730061,
        identified_name=731061,
        unidentified_description=732061,
        identified_description=733061,
        icon="SCRL6M",
        usability=0x1020306D,
        price=10061,
    )
    use_ability, learn_ability = scroll.abilities
    matching_use = dataclasses.replace(use_ability.effects[0], opcode=146)
    return dataclasses.replace(
        scroll,
        abilities=(
            dataclasses.replace(
                use_ability,
                effects=(matching_use, UNRELATED_CAST_EFFECT),
            ),
            learn_ability,
        ),
    ).to_bytes()


def _learn_only_scroll(data: bytes, spell: str) -> bytes:
    """Remove the matching cast path while retaining the opcode-147 learn path."""
    item = ItmFile.from_bytes(data)
    return dataclasses.replace(
        item,
        abilities=tuple(
            dataclasses.replace(
                ability,
                effects=tuple(
                    effect
                    for effect in ability.effects
                    if not (
                        effect.opcode in {146, 148}
                        and effect.resource.upper() == spell.upper()
                    )
                ),
            )
            for ability in item.abilities
        ),
    ).to_bytes()


def _overlapping_global_scroll(spell: str, seed: int, icon: str) -> bytes:
    """Build a coarse-bounds-valid item whose global/ability slices overlap."""
    raw = bytearray(_scroll(spell, spell, seed, icon))
    global_first, global_count = struct.unpack_from("<HH", raw, 0x6E)
    if global_first != 0:
        raise AssertionError((global_first, global_count))
    struct.pack_into("<H", raw, 0x70, global_count + 1)
    return bytes(raw)


def _native_fallback_spell(
    game: "SyntheticEmotionGame", resref: str, *, courage: bool
) -> bytes:
    stored_projectile = (
        read_ids(game.override / "PROJECTL.IDS").value(PRIVATE_EMOTION_PROJECTILE)
        + 1
    )
    chrome = (
        SplEffect(opcode=141, target=2, power=4, parameter2=10, timing=1, resist_dispel=3),
        SplEffect(
            opcode=174, target=2, power=4, timing=1, resist_dispel=3, resource="EFF_M05"
        ),
        SplEffect(
            opcode=61,
            target=2,
            power=4,
            parameter1=509245440,
            parameter2=1638400,
            timing=1,
            resist_dispel=3,
        ),
        SplEffect(
            opcode=174,
            target=2,
            power=4,
            timing=4,
            duration=300,
            resist_dispel=3,
            resource=PRIVATE_EMOTION_EFFECT_SOUND,
        ),
    )
    statdesc = TwoDA.from_text(game.effective_bytes("STATDESC", "2DA").decode("ascii"))
    bam_column = next(
        index for index, column in enumerate(statdesc.columns)
        if column.upper() == "BAM_FILE"
    )
    portrait_rows = [
        int(row)
        for row, values in statdesc.rows
        if values[bam_column].upper() == f"{resref}D"
    ]
    if len(portrait_rows) != 1:
        raise AssertionError((resref, portrait_rows))
    chrome += (
        SplEffect(
            opcode=142,
            target=2,
            power=4,
            parameter2=portrait_rows[0],
            timing=0,
            resist_dispel=3,
            duration=300,
        ),
    )
    spell = bytearray(_spell(
        chrome + (COURAGE_MECHANICS if courage else HOPE_MECHANICS),
        name=719001 if courage else 719003,
        description=719002 if courage else 719004,
        icon=f"{resref}C",
        ability_icon=f"{resref}B",
        projectile=stored_projectile,
        secondary_type=7 if courage else 2,
        completion_sound="CAS_M05",
    ).to_bytes())
    struct.pack_into("<I", spell, 0x1E, 0x800)
    return bytes(spell)


@dataclasses.dataclass(frozen=True)
class GameOptions:
    symbols: str = "both"  # both | neither | courage_only | hope_only
    markers: str = "present"  # present | partial | absent
    malformed: str | None = None  # wrong_level | target | adverse | missing_donor
    missing_adverse: str | None = None
    ambiguous_donor: str | None = None
    malformed_matching_donor: str | None = None
    learn_only_donor: str | None = None
    supported_game: bool = True
    hopelessness_layout: str = "provider"  # provider | base_spwi411_no_opcode45
    native_courage_donor: bool = False
    innate_horror_id: int = 163
    hold_missile_id: int = HOLD_MISSILE_ID
    statdesc_layout: str = "valid"  # valid | malformed_shape | courage_d_collision


class SyntheticEmotionGame:
    def __init__(self, temporary: tempfile.TemporaryDirectory[str], options: GameOptions):
        if options.symbols not in {"both", "neither", "courage_only", "hope_only"}:
            raise ValueError(options.symbols)
        if options.markers not in {"present", "partial", "absent"}:
            raise ValueError(options.markers)
        if options.missing_adverse not in {
            None, FEAR_RESREF, HORROR_RESREF, INNATE_HORROR_RESREF,
            HOPELESS_RESREF, SYMBOL_HOPELESS_RESREF,
        }:
            raise ValueError(options.missing_adverse)
        if options.ambiguous_donor not in {None, ENCHANTED_RESREF, HOPELESS_RESREF}:
            raise ValueError(options.ambiguous_donor)
        if options.malformed_matching_donor not in {
            None, ENCHANTED_RESREF, HOPELESS_RESREF,
        }:
            raise ValueError(options.malformed_matching_donor)
        if options.learn_only_donor not in {None, ENCHANTED_RESREF, HOPELESS_RESREF}:
            raise ValueError(options.learn_only_donor)
        if options.hopelessness_layout not in {"provider", "base_spwi411_no_opcode45"}:
            raise ValueError(options.hopelessness_layout)
        if options.innate_horror_id not in {163, LIVE_INNATE_HORROR_ID}:
            raise ValueError(options.innate_horror_id)
        if options.hold_missile_id not in {HOLD_MISSILE_ID, LIVE_HOLD_MISSILE_ID}:
            raise ValueError(options.hold_missile_id)
        if options.statdesc_layout not in {
            "valid", "malformed_shape", "courage_d_collision",
        }:
            raise ValueError(options.statdesc_layout)
        self.options = options
        self.hopelessness_resref = (
            BASE_HOPELESS_RESREF
            if options.hopelessness_layout == "base_spwi411_no_opcode45"
            else HOPELESS_RESREF
        )
        self.enchanted_donor_scroll = (
            NATIVE_ENCHANTED_DONOR_SCROLL
            if options.native_courage_donor
            else ENCHANTED_DONOR_SCROLL
        )
        self.innate_horror_resref = (
            LIVE_INNATE_HORROR_RESREF
            if options.innate_horror_id == LIVE_INNATE_HORROR_ID
            else INNATE_HORROR_RESREF
        )
        self.root = Path(temporary.name) / "game"
        self.override = self.root / "override"
        self.override.mkdir(parents=True)
        shutil.copy2(SETUP_TP2, self.root / SETUP_TP2.name)
        shutil.copytree(ROOT / "chriz-bg-rebalance", self.root / "chriz-bg-rebalance")

        ids_entries = [
            (2463, ENCHANTED_SYMBOL),
            (2464, FEAR_SYMBOL),
            (2265, HORROR_SYMBOL),
            (options.innate_horror_id, INNATE_HORROR_SYMBOL),
            (
                BASE_HOPELESS_ID
                if options.hopelessness_layout == "base_spwi411_no_opcode45"
                else 2466,
                HOPELESS_SYMBOL,
            ),
            (1767, SYMBOL_HOPELESS_SYMBOL),
            # A resource collision and an IDS-only collision force ADD_SPELL
            # to search dynamically rather than assume the first two slots.
            (2401, "WIZARD_FOREIGN_IDS_COLLISION"),
        ]
        if options.symbols in {"both", "courage_only"}:
            ids_entries.append((COURAGE_ID, COURAGE_SYMBOL))
        if options.symbols in {"both", "hope_only"}:
            ids_entries.append((HOPE_ID, HOPE_SYMBOL))
        spell_ids = IdsFile(entries=tuple(ids_entries)).to_text().encode("ascii")
        self.initial_spell_ids = IdsFile(entries=tuple(ids_entries))

        splstate_entries: list[tuple[int, str]] = [(61, "FOREIGN_STATE")]
        if options.markers in {"present", "partial"}:
            splstate_entries.append((211, "EMOTION_COURAGE"))
        if options.markers == "present":
            splstate_entries.append((213, "EMOTION_HOPE"))
        splstate = IdsFile(entries=tuple(splstate_entries)).to_text().encode("ascii")

        courage_input_marker = 211 if options.markers in {"present", "partial"} else None
        hope_input_marker = 213 if options.markers == "present" else None
        courage_payload = _beneficial(
            COURAGE_RESREF, HOPE_RESREF, courage=True, marker=courage_input_marker
        )
        if options.malformed == "wrong_level":
            raw = bytearray(courage_payload)
            struct.pack_into("<I", raw, 0x34, 5)
            courage_payload = bytes(raw)
        elif options.malformed == "target":
            courage_payload = b"ITM V1  " + courage_payload[8:]

        hopelessness_payload = (
            _base_hopelessness_without_opcode_45(HOPE_RESREF)
            if options.hopelessness_layout == "base_spwi411_no_opcode45"
            else _adverse_bytes(HOPE_RESREF, 45, "HPL", unconditional=True)
        )
        adverse = {
            FEAR_RESREF: _adverse_bytes(COURAGE_RESREF, 24, "FER"),
            HORROR_RESREF: _adverse_bytes("OTHBUFF", 24, "HOR", power=2),
            self.innate_horror_resref: _adverse_bytes("OTHBUFF", 24, "INH", power=2),
            self.hopelessness_resref: hopelessness_payload,
            SYMBOL_HOPELESS_RESREF: _adverse_bytes(HOPE_RESREF, 45, "SYM", power=7),
        }
        if options.malformed == "adverse":
            raw = bytearray(adverse[FEAR_RESREF])
            ability_offset = struct.unpack_from("<I", raw, 0x64)[0]
            struct.pack_into("<H", raw, ability_offset + 0x1E, 0x7FFF)
            adverse[FEAR_RESREF] = bytes(raw)

        statdesc_payload = {
            "valid": STATDESC_FIXTURE,
            "malformed_shape": STATDESC_MALFORMED_SHAPE,
            "courage_d_collision": STATDESC_COURAGE_D_COLLISION,
        }[options.statdesc_layout]
        bif_resources: list[tuple[str, str, bytes]] = [
            ("SPELL", "IDS", spell_ids),
            ("SPLSTATE", "IDS", splstate),
            (
                "MISSILE",
                "IDS",
                f"IDS\n{options.hold_missile_id} HOLD\n".encode("ascii"),
            ),
            (
                "PROJECTL",
                "IDS",
                (
                    "IDS V1.0\n"
                    f"{options.hold_missile_id - 1} HOLD\n"
                ).encode("ascii"),
            ),
            ("STATS", "IDS", b"0 HIT_POINTS\n36 STRENGTH\n"),
            ("KIT", "IDS", b"0x00000000 TRUECLASS\n"),
            ("STATDESC", "2DA", statdesc_payload),
            (ENCHANTED_RESREF, "SPL", _plain_spell()),
            (FEAR_RESREF, "SPL", adverse[FEAR_RESREF]),
            (HORROR_RESREF, "SPL", adverse[HORROR_RESREF]),
            (self.innate_horror_resref, "SPL", adverse[self.innate_horror_resref]),
            (SYMBOL_HOPELESS_RESREF, "SPL", adverse[SYMBOL_HOPELESS_RESREF]),
            ("SPWI400", "SPL", _plain_spell()),
            (FOREIGN_BIF_ITEM, "ITM", _scroll("SPWI999", "SPWI998", 97, "BFFRGN")),
        ]
        bif_resources.append(
            (
                "OH6000" if options.supported_game else "AR0125",
                "ARE",
                b"synthetic supported-game marker" if options.supported_game else b"synthetic BG2 marker",
            )
        )
        optional_bif_spl = {
            FEAR_RESREF: adverse[FEAR_RESREF],
            HORROR_RESREF: adverse[HORROR_RESREF],
            self.innate_horror_resref: adverse[self.innate_horror_resref],
            SYMBOL_HOPELESS_RESREF: adverse[SYMBOL_HOPELESS_RESREF],
        }
        # Replace the eagerly listed optional adverse resources below with a
        # mode-aware list; their SPELL.IDS symbols deliberately remain present.
        bif_resources = [
            row for row in bif_resources
            if not (row[1] == "SPL" and row[0] in optional_bif_spl)
        ]
        bif_resources.extend(
            (resref, "SPL", payload)
            for resref, payload in optional_bif_spl.items()
            if resref != options.missing_adverse
        )
        if options.symbols in {"both", "courage_only"}:
            bif_resources.append((COURAGE_RESREF, "SPL", courage_payload))
            bif_resources.append(
                (COURAGE_EXISTING_SCROLL, "ITM", _scroll(COURAGE_RESREF, COURAGE_RESREF, 11, "CTGICO"))
            )
        if options.malformed != "missing_donor":
            enchanted_donor = (
                _native_enchanted_weapon_scroll()
                if options.native_courage_donor
                else _scroll(ENCHANTED_RESREF, ENCHANTED_RESREF, 21, "ENCICO")
            )
            if options.learn_only_donor == ENCHANTED_RESREF:
                enchanted_donor = _learn_only_scroll(enchanted_donor, ENCHANTED_RESREF)
            bif_resources.append(
                (
                    self.enchanted_donor_scroll,
                    "ITM",
                    enchanted_donor,
                )
            )
        if options.ambiguous_donor == HOPELESS_RESREF:
            # The ordinary Hopelessness donor is loose; put the second valid
            # candidate in the BIFF so ambiguity cannot be resolved by
            # preferring one resource source over the other.
            bif_resources.append(
                (
                    AMBIGUOUS_HOPELESS_DONOR_SCROLL,
                    "ITM",
                        _scroll(
                            self.hopelessness_resref,
                            self.hopelessness_resref,
                            23,
                            "HPAICO",
                        ),
                )
            )
        elif options.malformed_matching_donor == HOPELESS_RESREF:
            bif_resources.append(
                (
                    AMBIGUOUS_HOPELESS_DONOR_SCROLL,
                    "ITM",
                    _overlapping_global_scroll(
                        self.hopelessness_resref,
                        23,
                        "HPAICO",
                    ),
                )
            )

        tail_a = bytes.fromhex("0100020003000400050000000600000007000000")
        tail_b = bytes.fromhex("080009000A000B000C0000000D0000000E000000")
        bif_store = _store(
            (
                (self.enchanted_donor_scroll, tail_a),
                (self.enchanted_donor_scroll, tail_b),
                (HOPELESS_DONOR_SCROLL, tail_b),
            )
        )
        foreign_store = _store(((FOREIGN_BIF_ITEM, tail_b),))
        bif_resources.extend(
            (
                (BIF_DONOR_STORE, "STO", bif_store),
                (FOREIGN_BIF_STORE, "STO", foreign_store),
            )
        )
        self.bif_payloads = {(r.upper(), e.upper()): p for r, e, p in bif_resources}
        self.bif_path = _write_key_and_bif(self.root, tuple(bif_resources))

        # Override half of the matrix: Hope and its scroll when installed,
        # Hopelessness and its donor scroll, plus a donor-bearing store.
        if options.symbols in {"both", "hope_only"}:
            (self.override / f"{HOPE_RESREF}.SPL").write_bytes(
                _beneficial(
                    HOPE_RESREF,
                    COURAGE_RESREF,
                    courage=False,
                    marker=hope_input_marker,
                )
            )
            (self.override / f"{HOPE_EXISTING_SCROLL}.ITM").write_bytes(
                _scroll(HOPE_RESREF, HOPE_RESREF, 12, "HTGICO")
            )
        if options.missing_adverse != self.hopelessness_resref:
            (self.override / f"{self.hopelessness_resref}.SPL").write_bytes(
                adverse[self.hopelessness_resref]
            )
        hopeless_donor = _scroll(
            self.hopelessness_resref,
            self.hopelessness_resref,
            22,
            "HPLICO",
        )
        if options.learn_only_donor == HOPELESS_RESREF:
            hopeless_donor = _learn_only_scroll(hopeless_donor, self.hopelessness_resref)
        (self.override / f"{HOPELESS_DONOR_SCROLL}.ITM").write_bytes(hopeless_donor)
        if options.ambiguous_donor == ENCHANTED_RESREF:
            # The ordinary Enchanted Weapon donor is BIFF-only; the second
            # candidate is loose to exercise the complete discovery domain.
            (self.override / f"{AMBIGUOUS_ENCHANTED_DONOR_SCROLL}.ITM").write_bytes(
                _scroll(ENCHANTED_RESREF, ENCHANTED_RESREF, 24, "ENAICO")
            )
        elif options.malformed_matching_donor == ENCHANTED_RESREF:
            (self.override / f"{AMBIGUOUS_ENCHANTED_DONOR_SCROLL}.ITM").write_bytes(
                _overlapping_global_scroll(
                    ENCHANTED_RESREF,
                    24,
                    "ENAICO",
                )
            )
        (self.override / f"{OVERRIDE_DONOR_STORE}.STO").write_bytes(
            _store(
                (
                    (self.enchanted_donor_scroll, tail_b),
                    (HOPELESS_DONOR_SCROLL, tail_a),
                )
            )
        )

        self.lang_tlk = self.root / "lang/en_US/dialog.tlk"
        self.lang_tlk.parent.mkdir(parents=True)
        self.lang_tlk.write_bytes(ONE_EMPTY_STRING_TLK)
        self.root_tlk = self.root / "dialog.tlk"
        self.root_tlk.write_bytes(ONE_EMPTY_STRING_TLK)
        self.pre_override = _raw_tree(self.override)
        self.initial_spl_resrefs = {
            resref for resref, extension, _ in bif_resources if extension == "SPL"
        } | {path.stem.upper() for path in self.override.glob("*.SPL")}
        self.pre_lang_tlk = self.lang_tlk.read_bytes()
        self.stable_hashes = {
            "key": _sha256(self.root / "chitin.key"),
            "bif": _sha256(self.bif_path),
            "root_tlk": _sha256(self.root_tlk),
        }

    def run_install(self) -> subprocess.CompletedProcess[str]:
        return self._run("--force-install-list")

    def run_uninstall(self) -> subprocess.CompletedProcess[str]:
        return self._run("--force-uninstall-list")

    def run_reinstall(self) -> subprocess.CompletedProcess[str]:
        return self._run("--force-uninstall-list", "--force-install-list")

    def _run(self, *operations: str) -> subprocess.CompletedProcess[str]:
        operation_args: list[str] = []
        for operation in operations:
            operation_args.extend((operation, str(COMPONENT)))
        return subprocess.run(
            [
                str(WEIDU), str(self.root / SETUP_TP2.name), "--game", str(self.root),
                *operation_args, "--language", "0", "--use-lang", "en_US",
                "--no-exit-pause", "--quick-log",
            ],
            cwd=self.root,
            capture_output=True,
            text=True,
            timeout=90,
            check=False,
        )

    def transcript(self, process: subprocess.CompletedProcess[str]) -> str:
        return f"{process.stdout}\n{process.stderr}".strip()

    def active_log(self) -> str:
        path = self.root / "WeiDU.log"
        if not path.exists():
            return ""
        return "\n".join(
            line for line in path.read_text(encoding="utf-8", errors="replace").splitlines()
            if not line.lstrip().startswith("//")
        )

    def effective_ids(self) -> IdsFile:
        path = self.override / "SPELL.IDS"
        return read_ids(path) if path.exists() else IdsFile.from_text(self.bif_payloads[("SPELL", "IDS")].decode("ascii"))

    def effective_bytes(self, resref: str, extension: str) -> bytes:
        loose = self.override / f"{resref}.{extension}"
        if loose.exists():
            return loose.read_bytes()
        return self.bif_payloads[(resref.upper(), extension.upper())]

    def original_bytes(self, resref: str, extension: str) -> bytes:
        relative = f"{resref}.{extension}".upper()
        if relative in self.pre_override:
            return self.pre_override[relative]
        return self.bif_payloads[(resref.upper(), extension.upper())]

    def assert_engine_inputs_stable(self, test: unittest.TestCase) -> None:
        test.assertEqual(self.stable_hashes["key"], _sha256(self.root / "chitin.key"))
        test.assertEqual(self.stable_hashes["bif"], _sha256(self.bif_path))
        test.assertEqual(self.stable_hashes["root_tlk"], _sha256(self.root_tlk))


def _tlk_string(path: Path, strref: int) -> str:
    data = path.read_bytes()
    if data[:8] != b"TLK V1  ":
        raise ValueError("not TLK V1")
    count, strings_offset = struct.unpack_from("<II", data, 0x0A)
    if strref < 0 or strref >= count:
        raise IndexError(strref)
    entry = 0x12 + strref * 0x1A
    relative, length = struct.unpack_from("<II", data, entry + 0x12)
    return data[strings_offset + relative : strings_offset + relative + length].decode("utf-8")


def _tlk_strings(path: Path) -> list[str]:
    return _tlk_strings_from_bytes(path.read_bytes())


def _tlk_strings_from_bytes(data: bytes) -> list[str]:
    if data[:8] != b"TLK V1  ":
        raise ValueError("not TLK V1")
    count, strings_offset = struct.unpack_from("<II", data, 0x0A)
    strings = []
    for strref in range(count):
        entry = 0x12 + strref * 0x1A
        relative, length = struct.unpack_from("<II", data, entry + 0x12)
        strings.append(
            data[strings_offset + relative : strings_offset + relative + length].decode("utf-8")
        )
    return strings


def _learned_resrefs(item_bytes: bytes) -> set[str]:
    item = read_itm_bytes(item_bytes)
    return {
        effect.resource.upper()
        for ability in item.abilities
        for effect in ability.effects
        if effect.opcode == 147
    }


def read_itm_bytes(data: bytes):
    from tests.ie_formats import ItmFile
    return ItmFile.from_bytes(data)


class EmotionHopeCourageInstallerTests(unittest.TestCase):
    def make_game(self, options: GameOptions = GameOptions()) -> SyntheticEmotionGame:
        temporary = tempfile.TemporaryDirectory(prefix="cbr-emotion-installer-")
        self.addCleanup(temporary.cleanup)
        return SyntheticEmotionGame(temporary, options)

    def assert_installed(self, game: SyntheticEmotionGame, process: subprocess.CompletedProcess[str]) -> None:
        transcript = game.transcript(process)
        self.assertEqual(0, process.returncode, transcript)
        self.assertIn("SUCCESSFULLY INSTALLED", transcript)
        self.assertRegex(game.active_log(), rf"(?m)#0\s+#{COMPONENT}\b")
        game.assert_engine_inputs_stable(self)
        self.assert_spell_ids_contract(game)

    def assert_spell_ids_contract(self, game: SyntheticEmotionGame) -> None:
        final = game.effective_ids()
        initial_pairs = game.initial_spell_ids.canonical()
        final_pairs = final.canonical()
        for pair in initial_pairs:
            self.assertEqual(1, final_pairs.count(pair), f"initial SPELL.IDS mapping changed: {pair}")
        initial_values = game.initial_spell_ids.values()
        allocated_values: list[int] = []
        for symbol in (COURAGE_SYMBOL, HOPE_SYMBOL):
            value = final.value(symbol)
            initial_matches = [
                old_value for old_value, old_symbol in game.initial_spell_ids.entries
                if old_symbol.upper() == symbol
            ]
            if initial_matches:
                self.assertEqual([initial_matches[0]], [value])
            else:
                self.assertGreaterEqual(value, 2400)
                self.assertLess(value, 2500)
                self.assertNotIn(value, initial_values)
                self.assertNotIn(spell_resref(value, symbol), game.initial_spl_resrefs)
                allocated_values.append(value)
            self.assertEqual(
                1,
                sum(1 for _, candidate in final.entries if candidate.upper() == symbol),
                f"duplicate {symbol} mapping",
            )
        self.assertEqual(len(allocated_values), len(set(allocated_values)))

    def assert_failed_atomically(self, game: SyntheticEmotionGame, process: subprocess.CompletedProcess[str]) -> None:
        transcript = game.transcript(process)
        self.assertNotIn("SUCCESSFULLY INSTALLED", transcript)
        self.assertIn("NOT INSTALLED DUE TO ERRORS", transcript)
        skip_lines = [line for line in transcript.splitlines() if "SKIPPING" in line.upper()]
        for line in skip_lines:
            self.assertRegex(
                line,
                r"(?i)automatically\s+skipping.*because\s+of\s+error",
                "attempted failure was confused with a REQUIRE_PREDICATE skip",
            )
        self.assertNotRegex(game.active_log(), rf"(?m)#0\s+#{COMPONENT}\b")
        self.assertEqual(game.pre_override, _raw_tree(game.override), transcript)
        self.assertEqual(game.pre_lang_tlk, game.lang_tlk.read_bytes(), transcript)
        game.assert_engine_inputs_stable(self)

    def test_synthetic_fixture_matrix_is_structurally_self_valid(self) -> None:
        self.assertEqual(0x03F4, RESOURCE_TYPE["2DA"])
        self.assertEqual(0x03F6, RESOURCE_TYPE["STO"])
        self.assertNotEqual(COURAGE_FALLBACK_SCROLL, HOPE_FALLBACK_SCROLL)
        self.assertLessEqual(len(COURAGE_FALLBACK_SCROLL), 8)
        self.assertLessEqual(len(HOPE_FALLBACK_SCROLL), 8)
        for symbols in ("both", "neither", "courage_only", "hope_only"):
            for markers in ("present", "partial", "absent"):
                with self.subTest(symbols=symbols, markers=markers):
                    game = self.make_game(GameOptions(symbols=symbols, markers=markers))
                    ids = game.effective_ids()
                    for symbol in (ENCHANTED_SYMBOL, FEAR_SYMBOL, HORROR_SYMBOL, HOPELESS_SYMBOL, SYMBOL_HOPELESS_SYMBOL):
                        self.assertIsInstance(ids.value(symbol), int)
                    missile = IdsFile.from_text(
                        game.bif_payloads[("MISSILE", "IDS")].decode("ascii")
                    )
                    self.assertEqual(HOLD_MISSILE_ID, missile.value("HOLD"))
                    for (resref, extension), payload in game.bif_payloads.items():
                        if extension == "SPL":
                            read_spl_bytes(payload)
                        elif extension == "ITM":
                            item = read_itm_bytes(payload)
                            self.assertEqual(
                                [UNRELATED_USE_EFFECT.to_bytes()],
                                [
                                    effect.to_bytes()
                                    for effect in item.global_effects
                                    if effect.opcode == 148
                                    and effect.resource.upper() == UNRELATED_USE_RESREF
                                ],
                                resref,
                            )
                            self.assertEqual(
                                [UNRELATED_LEARN_EFFECT.to_bytes()],
                                [
                                    effect.to_bytes()
                                    for ability in item.abilities
                                    for effect in ability.effects
                                    if effect.opcode == 147
                                    and effect.resource.upper() == UNRELATED_LEARN_RESREF
                                ],
                                resref,
                            )
                        elif extension == "STO":
                            self.assertTrue(_store_entries(payload))
                    for path in game.override.iterdir():
                        if path.suffix.upper() == ".SPL":
                            read_spl(path)
                        elif path.suffix.upper() == ".ITM":
                            item = read_itm(path)
                            self.assertEqual(
                                [UNRELATED_USE_EFFECT.to_bytes()],
                                [
                                    effect.to_bytes()
                                    for effect in item.global_effects
                                    if effect.opcode == 148
                                    and effect.resource.upper() == UNRELATED_USE_RESREF
                                ],
                                path.name,
                            )
                            self.assertEqual(
                                [UNRELATED_LEARN_EFFECT.to_bytes()],
                                [
                                    effect.to_bytes()
                                    for ability in item.abilities
                                    for effect in ability.effects
                                    if effect.opcode == 147
                                    and effect.resource.upper() == UNRELATED_LEARN_RESREF
                                ],
                                path.name,
                            )
                        elif path.suffix.upper() == ".STO":
                            self.assertTrue(_store_entries(path.read_bytes()))

    def test_component_301_is_wired_once_with_dynamic_symbols_and_no_fixed_distribution(self) -> None:
        setup = SETUP_TP2.read_text(encoding="utf-8")
        tra = (ROOT / "chriz-bg-rebalance/languages/english/setup.tra").read_text(
            encoding="utf-8"
        )
        library = (ROOT / "chriz-bg-rebalance/lib/emotion_hope_courage.tpa").read_text(
            encoding="utf-8"
        )
        always = re.search(r"(?ms)^ALWAYS\b(?P<body>.*?)^END\s*//\s*ALWAYS\b", setup)
        self.assertIsNotNone(always)
        self.assertRegex(
            always.group("body"),  # type: ignore[union-attr]
            r"(?i)\bINCLUDE\s+~chriz-bg-rebalance/lib/emotion_hope_courage\.tpa~",
        )
        blocks = re.findall(r"(?ms)^BEGIN\b(?:(?!^BEGIN\b).)*", setup)
        components = [block for block in blocks if re.search(r"\bDESIGNATED\s+301\b", block)]
        self.assertEqual(1, len(components))
        component = components[0]
        self.assertRegex(component, r"(?m)^BEGIN\s+@301\b")
        self.assertEqual(1, len(re.findall(rf"\bLABEL\s+~{LABEL}~", component)))
        self.assertRegex(component, rf"\bGROUP\s+@{GROUP_REF}\b")
        self.assertRegex(component, r"(?is)REQUIRE_PREDICATE.*GAME_IS\s+~[^~]*\bbg2ee\b[^~]*\beet\b")
        self.assertRegex(
            component,
            r"(?is)REQUIRE_PREDICATE.*?FILE_EXISTS_IN_GAME\s+~STATDESC\.2DA~",
        )
        self.assertRegex(tra, r"(?im)^@9301\s*=.*STATDESC\.2DA")
        self.assertRegex(tra, r"(?m)^@301\s*=")
        self.assertRegex(tra, rf"(?m)^@{GROUP_REF}\s*=")
        for symbol in (
            COURAGE_SYMBOL, HOPE_SYMBOL, ENCHANTED_SYMBOL, FEAR_SYMBOL, HORROR_SYMBOL,
            INNATE_HORROR_SYMBOL, HOPELESS_SYMBOL, SYMBOL_HOPELESS_SYMBOL,
        ):
            self.assertIn(symbol, component)
        add_spell_paths = re.findall(
            r"(?is)\bADD_SPELL\b(?:(?!\bADD_SPELL\b).)*?\bIF_EXISTING\b", component
        )
        self.assertGreaterEqual(len(add_spell_paths), 2)
        self.assertIn(ENCHANTED_SYMBOL, component)
        self.assertIn(HOPELESS_SYMBOL, component)
        self.assertIn(COURAGE_FALLBACK_SCROLL, component)
        self.assertIn(HOPE_FALLBACK_SCROLL, component)
        self.assertRegex(component, r"(?is)(?:donor|scroll).*\bFAIL\s+@\d+")
        for forbidden in ("SPWI428", "SCRL6M", "SCRL5H", "DECK14", "SHOP08", "RIBALD"):
            self.assertNotIn(forbidden, component.upper())
        emotion_source = component + "\n" + library
        for forbidden_resref in (
            "SPWI428", "SPWI417", "SPWI430", "SPWI205", "SPIN105",
            "SPWI411", "SPPR734", "SCRL6M", "SCRL5H",
        ):
            self.assertNotIn(forbidden_resref, emotion_source.upper())
        self.assertNotRegex(emotion_source, r"(?i)\b(?:194|195)\s+(?:EMOTION_COURAGE|EMOTION_HOPE)\b")
        self.assertNotRegex(emotion_source, r"(?i)\b(?:189|190)\b[^\r\n]*\bHOLD\b|\bHOLD\b[^\r\n]*\b(?:189|190)\b")
        asset_dir = ROOT / "chriz-bg-rebalance/resources/emotion_iwdee"
        shipped_binaries = {
            path.name: hashlib.sha256(path.read_bytes()).hexdigest().upper()
            for path in (ROOT / "chriz-bg-rebalance").rglob("*")
            if path.is_file()
            and path.suffix.upper() in {".SPL", ".ITM", ".STO", ".BAM", ".VVC", ".PRO", ".WAV"}
        }
        self.assertTrue(asset_dir.is_dir())
        self.assertEqual(IWD_EMOTION_SUPPORT_SHA256, shipped_binaries)

    def test_existing_symbols_keep_dynamic_slots_and_patch_bif_only_matching_scroll(self) -> None:
        game = self.make_game(GameOptions(symbols="both", markers="present"))
        before_courage_scroll = game.bif_payloads[(COURAGE_EXISTING_SCROLL, "ITM")]
        before_hope_scroll = game.pre_override[f"{HOPE_EXISTING_SCROLL}.ITM"]
        before_override_store = game.pre_override[f"{OVERRIDE_DONOR_STORE}.STO"]
        before_foreign = game.bif_payloads[(FOREIGN_BIF_ITEM, "ITM")]
        process = game.run_install()
        self.assert_installed(game, process)
        ids = game.effective_ids()
        self.assertEqual(COURAGE_ID, ids.value(COURAGE_SYMBOL))
        self.assertEqual(HOPE_ID, ids.value(HOPE_SYMBOL))
        self.assertTrue((game.override / f"{COURAGE_RESREF}.SPL").exists(), "BIF-only target was not materialized")
        patched_scroll = (game.override / f"{COURAGE_EXISTING_SCROLL}.ITM").read_bytes()
        self.assertEqual(_mask_scroll_text(before_courage_scroll), _mask_scroll_text(patched_scroll))
        self.assertNotEqual(before_courage_scroll, patched_scroll)
        patched_hope_scroll = (game.override / f"{HOPE_EXISTING_SCROLL}.ITM").read_bytes()
        self.assertEqual(_mask_scroll_text(before_hope_scroll), _mask_scroll_text(patched_hope_scroll))
        self.assertFalse((game.override / f"{FOREIGN_BIF_ITEM}.ITM").exists())
        self.assertEqual(before_foreign, game.bif_payloads[(FOREIGN_BIF_ITEM, "ITM")])
        target_scrolls = self.target_scrolls(game, {COURAGE_RESREF, HOPE_RESREF})
        self.assertEqual([COURAGE_EXISTING_SCROLL], target_scrolls[COURAGE_RESREF])
        self.assertEqual([HOPE_EXISTING_SCROLL], target_scrolls[HOPE_RESREF])
        self.assertFalse((game.override / f"{BIF_DONOR_STORE}.STO").exists())
        self.assertEqual(before_override_store, (game.override / f"{OVERRIDE_DONOR_STORE}.STO").read_bytes())
        self.assert_public_semantics(
            game, COURAGE_RESREF, HOPE_RESREF, 211, 213, standalone=set()
        )
        self.assert_publication_delta(
            game,
            {COURAGE_RESREF, HOPE_RESREF},
            target_scrolls,
        )

    def test_neither_symbol_allocates_around_resource_and_ids_collisions_and_builds_scrolls(self) -> None:
        game = self.make_game(GameOptions(symbols="neither", markers="absent"))
        process = game.run_install()
        self.assert_installed(game, process)
        ids = game.effective_ids()
        courage_id = ids.value(COURAGE_SYMBOL)
        hope_id = ids.value(HOPE_SYMBOL)
        self.assertNotIn(courage_id, {2400, 2401, COURAGE_ID, HOPE_ID})
        self.assertNotIn(hope_id, {2400, 2401, COURAGE_ID, HOPE_ID, courage_id})
        courage = spell_resref(courage_id, COURAGE_SYMBOL)
        hope = spell_resref(hope_id, HOPE_SYMBOL)
        self.assert_public_semantics(
            game, courage, hope, None, None, standalone={courage, hope}
        )
        target_scrolls = self.target_scrolls(game, {courage, hope})
        self.assertEqual({courage, hope}, set(target_scrolls))
        self.assertEqual([COURAGE_FALLBACK_SCROLL], target_scrolls[courage])
        self.assertEqual([HOPE_FALLBACK_SCROLL], target_scrolls[hope])
        courage_item = (game.override / f"{target_scrolls[courage][0]}.ITM").read_bytes()
        hope_item = (game.override / f"{target_scrolls[hope][0]}.ITM").read_bytes()
        self.assertEqual(0x142, len(courage_item))
        self.assertEqual(0x142, len(hope_item))
        self.assertNotEqual(
            game.bif_payloads[(ENCHANTED_DONOR_SCROLL, "ITM")], courage_item
        )
        self.assertNotEqual(
            game.pre_override[f"{HOPELESS_DONOR_SCROLL}.ITM"], hope_item
        )
        self.assert_donor_store_mirroring(game, courage, hope, target_scrolls)
        self.assert_publication_delta(game, {courage, hope}, target_scrolls)

    def test_standalone_scrolls_use_the_iwdification_point_cast_contract(self) -> None:
        game = self.make_game(GameOptions(symbols="neither", markers="absent"))
        process = game.run_install()
        self.assert_installed(game, process)
        ids = game.effective_ids()
        targets = (
            (
                spell_resref(ids.value(COURAGE_SYMBOL), COURAGE_SYMBOL),
                COURAGE_FALLBACK_SCROLL,
            ),
            (
                spell_resref(ids.value(HOPE_SYMBOL), HOPE_SYMBOL),
                HOPE_FALLBACK_SCROLL,
            ),
        )

        for spell, scroll in targets:
            with self.subTest(spell=spell, scroll=scroll):
                item = read_itm(game.override / f"{scroll}.ITM")
                self.assertEqual(2, len(item.abilities))
                cast, learn = item.abilities
                expected_icon = f"{spell}A"
                actual_main_icon = (
                    item.header_raw[0x3A : 0x42]
                    .split(b"\0", 1)[0]
                    .decode("ascii")
                )
                self.assertEqual(expected_icon.upper(), actual_main_icon.upper())
                self.assertEqual(expected_icon.upper(), cast.icon.upper())
                self.assertEqual(4, cast.raw[0x0C], "scroll cast must target a point")
                self.assertEqual(
                    50,
                    int.from_bytes(cast.raw[0x0E : 0x10], "little"),
                    "scroll cast must copy the Emotion spell's visual range",
                )
                self.assertEqual(1, len(cast.effects))
                self.assertEqual(148, cast.effects[0].opcode)
                self.assertEqual(1, cast.effects[0].target)
                self.assertEqual(spell, cast.effects[0].resource.upper())
                self.assertEqual(5, learn.raw[0x0C])
                self.assertEqual(1, len(learn.effects))
                self.assertEqual(147, learn.effects[0].opcode)
                self.assertEqual(spell, learn.effects[0].resource.upper())

    def test_standalone_spells_use_the_party_capable_iwdee_emotion_projectile(self) -> None:
        game = self.make_game(GameOptions(symbols="neither", markers="absent"))
        process = game.run_install()
        self.assert_installed(game, process)
        source_projectile = (
            ROOT
            / "chriz-bg-rebalance/resources/emotion_iwdee"
            / f"{IWD_EMOTION_PROJECTILE_SOURCE}.PRO"
        ).read_bytes()
        self.assertEqual(
            IWD_EMOTION_PROJECTILE_SHA256,
            hashlib.sha256(source_projectile).hexdigest().upper(),
        )
        projectile_path = game.override / f"{PRIVATE_EMOTION_PROJECTILE}.PRO"
        self.assertTrue(
            projectile_path.exists(),
            "standalone emotions must publish a private IWDEE party-capable projectile",
        )
        projectile = projectile_path.read_bytes()
        self.assertEqual(len(source_projectile), len(projectile))
        self.assertEqual(
            PRIVATE_EMOTION_PROJECTILE_SHA256,
            hashlib.sha256(projectile).hexdigest().upper(),
        )
        self.assertGreater(len(projectile), 0x201)
        self.assertEqual(
            0xC0,
            projectile[0x200] & 0xC0,
            "the Emotion projectile must enable its faction filter and select allies",
        )
        self.assertEqual(PRIVATE_EMOTION_VVC, _resref_at(projectile, 0x21C))

        vvc_path = game.override / f"{PRIVATE_EMOTION_VVC}.VVC"
        self.assertTrue(vvc_path.exists())
        vvc = vvc_path.read_bytes()
        self.assertEqual(
            PRIVATE_EMOTION_VVC_SHA256,
            hashlib.sha256(vvc).hexdigest().upper(),
        )
        self.assertEqual(PRIVATE_EMOTION_ANIMATION, _resref_at(vvc, 0x08))
        self.assertEqual(PRIVATE_EMOTION_PROJECTILE_SOUND, _resref_at(vvc, 0x78))
        for resref, extension in (
            (PRIVATE_EMOTION_ANIMATION, "BAM"),
            (PRIVATE_EMOTION_PROJECTILE_SOUND, "WAV"),
            (PRIVATE_EMOTION_EFFECT_SOUND, "WAV"),
        ):
            self.assertTrue((game.override / f"{resref}.{extension}").exists())

        projectl_path = game.override / "PROJECTL.IDS"
        self.assertTrue(projectl_path.exists())
        projectl = read_ids(projectl_path)
        stored_projectile = projectl.value(PRIVATE_EMOTION_PROJECTILE) + 1
        ids = game.effective_ids()
        for symbol in (COURAGE_SYMBOL, HOPE_SYMBOL):
            spell = spell_resref(ids.value(symbol), symbol)
            with self.subTest(spell=spell):
                ability = read_spl(game.override / f"{spell}.SPL").abilities[0]
                self.assertEqual(stored_projectile, ability.projectile)
                self.assertNotEqual(HOLD_MISSILE_ID, ability.projectile)

    def test_standalone_spells_publish_the_original_blue_iwdee_icons(self) -> None:
        game = self.make_game(GameOptions(symbols="neither", markers="absent"))
        process = game.run_install()
        self.assert_installed(game, process)
        ids = game.effective_ids()
        targets = (
            (
                spell_resref(ids.value(COURAGE_SYMBOL), COURAGE_SYMBOL),
                IWD_EMOTION_ICON_SHA256["courage"],
            ),
            (
                spell_resref(ids.value(HOPE_SYMBOL), HOPE_SYMBOL),
                IWD_EMOTION_ICON_SHA256["hope"],
            ),
        )
        for spell, expected_hashes in targets:
            with self.subTest(spell=spell):
                actual_hashes = []
                for suffix in "ABCD":
                    path = game.override / f"{spell}{suffix}.BAM"
                    self.assertTrue(path.exists(), f"missing IWDEE icon {path.name}")
                    if suffix == "D":
                        self.assertEqual(
                            ((13, 13),), _bam_frame_dimensions(path.read_bytes())
                        )
                    else:
                        actual_hashes.append(
                            hashlib.sha256(path.read_bytes()).hexdigest().upper()
                        )
                self.assertEqual(expected_hashes, tuple(actual_hashes))
                installed = read_spl(game.override / f"{spell}.SPL")
                self.assertEqual(f"{spell}C", installed.spell_icon.upper())
                self.assertEqual(f"{spell}B", installed.abilities[0].icon.upper())

    def test_native_scrl6m_is_distribution_only_and_cannot_shape_courage_scroll(self) -> None:
        game = self.make_game(
            GameOptions(
                symbols="neither",
                markers="absent",
                native_courage_donor=True,
            )
        )
        donor_raw = game.original_bytes(NATIVE_ENCHANTED_DONOR_SCROLL, "ITM")
        donor = read_itm_bytes(donor_raw)
        donor_effects = [
            *donor.global_effects,
            *(effect for ability in donor.abilities for effect in ability.effects),
        ]
        self.assertEqual(
            1,
            sum(
                effect.opcode == 146
                and effect.resource.upper() == ENCHANTED_RESREF
                for effect in donor_effects
            ),
            "native SCRL6M fixture must cast Enchanted Weapon through opcode 146",
        )
        self.assertEqual(
            1,
            sum(
                effect.opcode == 147
                and effect.resource.upper() == ENCHANTED_RESREF
                for effect in donor_effects
            ),
            "native SCRL6M fixture must teach Enchanted Weapon through opcode 147",
        )
        self.assertFalse(
            any(effect.opcode == 148 for effect in donor_effects),
            "native SCRL6M fixture must not manufacture an opcode-148 use effect",
        )
        self.assertEqual(
            [UNRELATED_CAST_EFFECT.to_bytes()],
            [
                effect.to_bytes()
                for effect in donor_effects
                if effect.opcode == 146
                and effect.resource.upper() == UNRELATED_CAST_RESREF
            ],
        )

        process = game.run_install()
        self.assert_installed(game, process)
        ids = game.effective_ids()
        courage = spell_resref(ids.value(COURAGE_SYMBOL), COURAGE_SYMBOL)
        generated_path = game.override / f"{COURAGE_FALLBACK_SCROLL}.ITM"
        self.assertTrue(generated_path.exists(), "standalone Courage scroll was not generated")
        generated = read_itm(generated_path)
        self.assertEqual(2, len(generated.abilities))
        cast, learn = generated.abilities
        self.assertEqual(4, cast.raw[0x0C])
        self.assertEqual(50, int.from_bytes(cast.raw[0x0E:0x10], "little"))
        self.assertEqual(
            1,
            sum(
                effect.opcode == 148 and effect.resource.upper() == courage
                for effect in cast.effects
            ),
            "CBRCRGSC must use IWDification's point-target opcode 148",
        )
        self.assertEqual(
            1,
            sum(
                effect.opcode == 147 and effect.resource.upper() == courage
                for effect in learn.effects
            ),
            "CBRCRGSC must teach Courage through opcode 147",
        )
        self.assertFalse(
            any(effect.opcode == 146 for ability in generated.abilities for effect in ability.effects),
            "CBRCRGSC must not inherit SCRL6M's actor-target opcode 146",
        )
        self.assertEqual(donor_raw, game.original_bytes(NATIVE_ENCHANTED_DONOR_SCROLL, "ITM"))
        self.assertFalse((game.override / f"{NATIVE_ENCHANTED_DONOR_SCROLL}.ITM").exists())

    def test_installed_provider_portrait_icon_effects_are_preserved(self) -> None:
        game = self.make_game(GameOptions(symbols="both", markers="present"))
        original_statdesc = game.original_bytes("STATDESC", "2DA")
        expected: dict[str, list[bytes]] = {}
        for resref in (COURAGE_RESREF, HOPE_RESREF):
            expected[resref] = [
                effect.to_bytes()
                for effect in read_spl_bytes(game.original_bytes(resref, "SPL")).abilities[0].effects
                if effect.opcode == 142
            ]
            self.assertTrue(expected[resref], f"provider fixture lacks opcode 142: {resref}")

        process = game.run_install()
        self.assert_installed(game, process)
        for resref in (COURAGE_RESREF, HOPE_RESREF):
            actual = [
                effect.to_bytes()
                for effect in read_spl(game.override / f"{resref}.SPL").abilities[0].effects
                if effect.opcode == 142
            ]
            self.assertEqual(expected[resref], actual, f"provider portrait icon changed: {resref}")
        self.assertEqual(original_statdesc, game.effective_bytes("STATDESC", "2DA"))
        self.assertFalse((game.override / f"{COURAGE_RESREF}D.BAM").exists())
        self.assertFalse((game.override / f"{HOPE_RESREF}D.BAM").exists())

    def test_standalone_seeds_publish_named_portrait_status_effects(self) -> None:
        game = self.make_game(GameOptions(symbols="neither", markers="absent"))
        original_statdesc = game.original_bytes("STATDESC", "2DA")
        self.assertFalse(_statdesc_row_has_icon(original_statdesc, 186))
        self.assertFalse(_statdesc_row_has_icon(original_statdesc, 187))

        process = game.run_install()
        self.assert_installed(game, process)
        ids = game.effective_ids()
        statdesc = TwoDA.from_text(game.effective_bytes("STATDESC", "2DA").decode("ascii"))
        rows: list[int] = []
        for symbol, expected_name in (
            (COURAGE_SYMBOL, "Courage"),
            (HOPE_SYMBOL, "Hope"),
        ):
            resref = spell_resref(ids.value(symbol), symbol)
            effects = [
                effect
                for effect in read_spl(game.override / f"{resref}.SPL").abilities[0].effects
                if effect.opcode == 142
            ]
            self.assertEqual(1, len(effects), f"standalone {symbol} needs one status entry")
            effect = effects[0]
            self.assertEqual(
                (2, 4, 0, 0, 3, 300, 100, 0, "", 0, 0, 0, 0, 0),
                (
                    effect.target,
                    effect.power,
                    effect.parameter1,
                    effect.timing,
                    effect.resist_dispel,
                    effect.duration,
                    effect.probability1,
                    effect.probability2,
                    effect.resource,
                    effect.dice_number,
                    effect.dice_size,
                    effect.save_type,
                    effect.save_bonus,
                    effect.special,
                ),
                f"standalone {symbol} status entry uses the wrong delivery contract",
            )
            rows.append(effect.parameter2)
            self.assertGreaterEqual(effect.parameter2, 201)
            self.assertEqual(
                expected_name,
                _tlk_string(game.lang_tlk, int(statdesc.cell(str(effect.parameter2), "DESCRIPTION"))),
            )
            portrait_resref = statdesc.cell(str(effect.parameter2), "BAM_FILE").upper()
            self.assertEqual(f"{resref}D", portrait_resref)
            portrait_path = game.override / f"{portrait_resref}.BAM"
            self.assertTrue(portrait_path.exists(), f"missing portrait BAM: {portrait_path.name}")
            self.assertEqual(((13, 13),), _bam_frame_dimensions(portrait_path.read_bytes()))
        self.assertEqual(2, len(set(rows)), "Courage and Hope must use distinct status rows")

    def test_standalone_accepts_base_spwi411_shape_without_opcode_45(self) -> None:
        game = self.make_game(
            GameOptions(
                symbols="neither",
                markers="absent",
                hopelessness_layout="base_spwi411_no_opcode45",
            )
        )
        self.assertEqual(
            BASE_HOPELESS_ID,
            game.effective_ids().value(HOPELESS_SYMBOL),
        )
        before = read_spl(game.override / f"{BASE_HOPELESS_RESREF}.SPL")
        self.assertEqual(14, len(before.abilities))
        for ability in before.abilities:
            self.assertFalse(
                any(effect.opcode == 45 for effect in ability.effects),
                "base SPWI411 fixture unexpectedly contains opcode 45",
            )
            self.assertFalse(
                any(
                    effect.opcode == 321
                    and effect.resource.upper() == HOPE_RESREF
                    for effect in ability.effects
                ),
                "base SPWI411 fixture already contains the desired Hope remover",
            )

        process = game.run_install()
        self.assert_installed(game, process)
        final_hope = spell_resref(
            game.effective_ids().value(HOPE_SYMBOL), HOPE_SYMBOL
        )
        after = read_spl(game.override / f"{BASE_HOPELESS_RESREF}.SPL")
        self.assertEqual(14, len(after.abilities))
        for ability in after.abilities:
            removers = [
                (index, effect)
                for index, effect in enumerate(ability.effects)
                if effect.opcode == 321
                and effect.resource.upper() == final_hope.upper()
            ]
            self.assertEqual(1, len(removers), ability.required_level)
            index, remover = removers[0]
            self.assertEqual(0, index, ability.required_level)
            self.assertEqual(
                (2, 4, 0, 0, 1, 0, 100, 0, 0, 0, 0),
                (
                    remover.target,
                    remover.power,
                    remover.parameter1,
                    remover.parameter2,
                    remover.timing,
                    remover.resist_dispel,
                    remover.probability1,
                    remover.probability2,
                    remover.save_type,
                    remover.save_bonus,
                    remover.special,
                ),
                ability.required_level,
            )

    def test_innate_horror_3105_resolves_to_spin105_and_is_cleansed(self) -> None:
        game = self.make_game(
            GameOptions(
                symbols="both",
                markers="present",
                innate_horror_id=LIVE_INNATE_HORROR_ID,
            )
        )
        self.assertEqual(
            LIVE_INNATE_HORROR_ID,
            game.effective_ids().value(INNATE_HORROR_SYMBOL),
        )
        read_spl_bytes(game.original_bytes(LIVE_INNATE_HORROR_RESREF, "SPL"))

        process = game.run_install()
        self.assert_installed(game, process)
        courage = read_spl(game.override / f"{COURAGE_RESREF}.SPL")
        removers = [
            effect
            for effect in courage.abilities[0].effects
            if effect.opcode == 321
            and effect.resource.upper() == LIVE_INNATE_HORROR_RESREF
        ]
        self.assertEqual(1, len(removers))
        self.assertEqual(
            (2, 4, 0, 0, 1, 2, 100, 0, 0, 0, 0),
            (
                removers[0].target,
                removers[0].power,
                removers[0].parameter1,
                removers[0].parameter2,
                removers[0].timing,
                removers[0].resist_dispel,
                removers[0].probability1,
                removers[0].probability2,
                removers[0].save_type,
                removers[0].save_bonus,
                removers[0].special,
            ),
        )
        self.assertFalse(
            (game.override / f"{LIVE_INNATE_HORROR_RESREF}.SPL").exists(),
            "cleanse-only Innate Horror should remain BIFF-only",
        )

    def test_hold_id_does_not_determine_the_standalone_emotion_projectile(self) -> None:
        for hold_id in (HOLD_MISSILE_ID, LIVE_HOLD_MISSILE_ID):
            with self.subTest(hold_id=hold_id):
                game = self.make_game(
                    GameOptions(
                        symbols="neither",
                        markers="absent",
                        hold_missile_id=hold_id,
                    )
                )
                process = game.run_install()
                self.assert_installed(game, process)
                stored_projectile = (
                    read_ids(game.override / "PROJECTL.IDS").value(
                        PRIVATE_EMOTION_PROJECTILE
                    )
                    + 1
                )
                ids = game.effective_ids()
                for symbol in (COURAGE_SYMBOL, HOPE_SYMBOL):
                    resref = spell_resref(ids.value(symbol), symbol)
                    spell = read_spl(game.override / f"{resref}.SPL")
                    self.assertEqual(1, len(spell.abilities))
                    self.assertEqual(stored_projectile, spell.abilities[0].projectile)
                    self.assertNotEqual(hold_id, spell.abilities[0].projectile)

    def test_exactly_one_symbol_allocates_only_the_missing_spell_and_respects_partial_marker_ids(self) -> None:
        for symbols in ("courage_only", "hope_only"):
            with self.subTest(symbols=symbols):
                game = self.make_game(GameOptions(symbols=symbols, markers="partial"))
                process = game.run_install()
                self.assert_installed(game, process)
                ids = game.effective_ids()
                courage_id = ids.value(COURAGE_SYMBOL)
                hope_id = ids.value(HOPE_SYMBOL)
                if symbols == "courage_only":
                    self.assertEqual(COURAGE_ID, courage_id)
                    self.assertNotIn(hope_id, {2400, 2401, COURAGE_ID, HOPE_ID})
                    courage, hope = COURAGE_RESREF, spell_resref(hope_id, HOPE_SYMBOL)
                    standalone = {hope}
                else:
                    self.assertEqual(HOPE_ID, hope_id)
                    self.assertNotIn(courage_id, {2400, 2401, COURAGE_ID, HOPE_ID})
                    courage, hope = spell_resref(courage_id, COURAGE_SYMBOL), HOPE_RESREF
                    standalone = {courage}
                self.assert_public_semantics(
                    game, courage, hope, 211, None, standalone=standalone
                )
                scrolls = self.target_scrolls(game, {courage, hope})
                if symbols == "courage_only":
                    self.assertEqual([COURAGE_EXISTING_SCROLL], scrolls[courage])
                    self.assertEqual([HOPE_FALLBACK_SCROLL], scrolls[hope])
                else:
                    self.assertEqual([HOPE_EXISTING_SCROLL], scrolls[hope])
                    self.assertEqual([COURAGE_FALLBACK_SCROLL], scrolls[courage])
                donor_map = (
                    {HOPELESS_DONOR_SCROLL: scrolls[hope][0]}
                    if symbols == "courage_only"
                    else {ENCHANTED_DONOR_SCROLL: scrolls[courage][0]}
                )
                self.assert_exact_store_clones(game, donor_map)
                self.assert_publication_delta(game, {courage, hope}, scrolls)

    def test_wrong_level_missing_donor_and_malformed_resources_roll_back(self) -> None:
        cases = (
            (
                GameOptions(symbols="both", malformed="wrong_level"),
                r"(?i)(?:spell|beneficial).*(?:level|four|4)|(?:level|four|4).*(?:spell|beneficial)",
            ),
            (GameOptions(symbols="both", malformed="target"), r"(?i)SPL|signature|target"),
            (GameOptions(symbols="both", malformed="adverse"), r"(?i)partition|effect|fear"),
            (GameOptions(symbols="neither", malformed="missing_donor"), r"(?i)donor|scroll|enchanted"),
        )
        for options, message in cases:
            with self.subTest(options=options):
                game = self.make_game(options)
                process = game.run_install()
                self.assert_failed_atomically(game, process)
                self.assertRegex(game.transcript(process), message)

    def test_invalid_or_colliding_statdesc_fails_before_tlk_mutation(self) -> None:
        for layout, message in (
            ("malformed_shape", r"(?i)STATDESC.*shape"),
            ("courage_d_collision", r"(?i)status BAM.*conflicting STATDESC"),
        ):
            with self.subTest(layout=layout):
                game = self.make_game(
                    GameOptions(symbols="neither", statdesc_layout=layout)
                )
                process = game.run_install()
                self.assert_failed_atomically(game, process)
                self.assertRegex(game.transcript(process), message)

    def test_ambiguous_fallback_donor_discovery_fails_atomically(self) -> None:
        for donor_spell, candidates in (
            (
                ENCHANTED_RESREF,
                (ENCHANTED_DONOR_SCROLL, AMBIGUOUS_ENCHANTED_DONOR_SCROLL),
            ),
            (
                HOPELESS_RESREF,
                (HOPELESS_DONOR_SCROLL, AMBIGUOUS_HOPELESS_DONOR_SCROLL),
            ),
        ):
            with self.subTest(donor_spell=donor_spell):
                game = self.make_game(
                    GameOptions(symbols="neither", ambiguous_donor=donor_spell)
                )
                for candidate in candidates:
                    item = read_itm_bytes(game.original_bytes(candidate, "ITM"))
                    matches = [
                        effect
                        for ability in item.abilities
                        for effect in ability.effects
                        if effect.opcode == 147
                        and effect.resource.upper() == donor_spell
                    ]
                    self.assertEqual(1, len(matches), candidate)
                process = game.run_install()
                self.assert_failed_atomically(game, process)
                self.assertRegex(
                    game.transcript(process),
                    r"(?i)(?:ambig|multiple|exactly\s+one|donor|scroll)",
                )

    def test_malformed_matching_fallback_donor_is_ignored(self) -> None:
        for donor_spell in (ENCHANTED_RESREF, HOPELESS_RESREF):
            with self.subTest(donor_spell=donor_spell):
                game = self.make_game(
                    GameOptions(
                        symbols="neither",
                        malformed_matching_donor=donor_spell,
                    )
                )
                malformed_resref = (
                    AMBIGUOUS_ENCHANTED_DONOR_SCROLL
                    if donor_spell == ENCHANTED_RESREF
                    else AMBIGUOUS_HOPELESS_DONOR_SCROLL
                )
                malformed = game.original_bytes(malformed_resref, "ITM")
                self.assertEqual((0, 4), struct.unpack_from("<HH", malformed, 0x6E))
                process = game.run_install()
                self.assert_installed(game, process)
                spell_ids = game.effective_ids()
                courage = spell_resref(spell_ids.value(COURAGE_SYMBOL), COURAGE_SYMBOL)
                hope = spell_resref(spell_ids.value(HOPE_SYMBOL), HOPE_SYMBOL)
                self.assertEqual(
                    [COURAGE_FALLBACK_SCROLL],
                    self.target_scrolls(game, {courage, hope})[courage],
                )
                self.assertEqual(
                    [HOPE_FALLBACK_SCROLL],
                    self.target_scrolls(game, {courage, hope})[hope],
                )

    def test_learn_only_fallback_donor_is_rejected_atomically(self) -> None:
        for donor_spell in (ENCHANTED_RESREF, HOPELESS_RESREF):
            with self.subTest(donor_spell=donor_spell):
                game = self.make_game(
                    GameOptions(symbols="neither", learn_only_donor=donor_spell)
                )
                candidate = (
                    game.enchanted_donor_scroll
                    if donor_spell == ENCHANTED_RESREF
                    else HOPELESS_DONOR_SCROLL
                )
                item = read_itm_bytes(game.original_bytes(candidate, "ITM"))
                expected_spell = (
                    game.hopelessness_resref
                    if donor_spell == HOPELESS_RESREF
                    else ENCHANTED_RESREF
                )
                self.assertTrue(
                    any(
                        effect.opcode == 147
                        and effect.resource.upper() == expected_spell
                        for ability in item.abilities
                        for effect in ability.effects
                    )
                )
                self.assertFalse(
                    any(
                        effect.opcode in {146, 148}
                        and effect.resource.upper() == expected_spell
                        for ability in item.abilities
                        for effect in ability.effects
                    )
                )
                process = game.run_install()
                self.assert_failed_atomically(game, process)
                self.assertRegex(game.transcript(process), r"(?i)donor|scroll")

    def test_each_optional_adverse_resource_may_be_absent(self) -> None:
        for missing in (
            FEAR_RESREF, HORROR_RESREF, INNATE_HORROR_RESREF,
            HOPELESS_RESREF, SYMBOL_HOPELESS_RESREF,
        ):
            with self.subTest(missing=missing):
                game = self.make_game(
                    GameOptions(symbols="both", markers="present", missing_adverse=missing)
                )
                process = game.run_install()
                self.assert_installed(game, process)
                self.assert_public_semantics(
                    game, COURAGE_RESREF, HOPE_RESREF, 211, 213, standalone=set()
                )
                scrolls = self.target_scrolls(game, {COURAGE_RESREF, HOPE_RESREF})
                self.assert_publication_delta(
                    game, {COURAGE_RESREF, HOPE_RESREF}, scrolls
                )
                self.assertFalse((game.override / f"{missing}.SPL").exists())

    def test_unsupported_game_is_a_predicate_skip_not_an_attempted_failure(self) -> None:
        game = self.make_game(GameOptions(symbols="both", supported_game=False))
        process = game.run_install()
        transcript = game.transcript(process)
        self.assertNotIn("SUCCESSFULLY INSTALLED", transcript)
        self.assertIn("SKIPPING", transcript.upper())
        self.assertNotIn("NOT INSTALLED DUE TO ERRORS", transcript)
        self.assertNotRegex(game.active_log(), rf"(?m)#0\s+#{COMPONENT}\b")
        self.assertEqual(game.pre_override, _raw_tree(game.override))
        self.assertEqual(game.pre_lang_tlk, game.lang_tlk.read_bytes())
        game.assert_engine_inputs_stable(self)

    def test_force_reinstall_is_byte_stable_and_uninstall_restores_exact_inputs(self) -> None:
        for symbols in ("both", "neither", "courage_only", "hope_only"):
            with self.subTest(symbols=symbols):
                game = self.make_game(GameOptions(symbols=symbols, markers="present"))
                first = game.run_install()
                self.assert_installed(game, first)
                first_override = _raw_tree(game.override)
                first_tlk = game.lang_tlk.read_bytes()
                pre_strings = _tlk_strings_from_bytes(game.pre_lang_tlk)
                first_strings = _tlk_strings(game.lang_tlk)
                missing_statuses = {
                    "both": set(),
                    "courage_only": {"Hope"},
                    "hope_only": {"Courage"},
                    "neither": {"Courage", "Hope"},
                }[symbols]
                self.assertEqual(pre_strings, first_strings[: len(pre_strings)])
                self.assertEqual(
                    len(pre_strings) + 4 + len(missing_statuses), len(first_strings)
                )
                ids = game.effective_ids()
                courage = spell_resref(ids.value(COURAGE_SYMBOL), COURAGE_SYMBOL)
                hope = spell_resref(ids.value(HOPE_SYMBOL), HOPE_SYMBOL)
                courage_spell = read_spl(game.override / f"{courage}.SPL")
                hope_spell = read_spl(game.override / f"{hope}.SPL")
                refs = (
                    struct.unpack_from("<i", courage_spell.header_raw, 0x08)[0],
                    struct.unpack_from("<i", courage_spell.header_raw, 0x50)[0],
                    struct.unpack_from("<i", hope_spell.header_raw, 0x08)[0],
                    struct.unpack_from("<i", hope_spell.header_raw, 0x50)[0],
                )
                self.assertEqual(
                    set(range(len(pre_strings), len(pre_strings) + 4)), set(refs)
                )
                self.assertEqual("Emotion, Courage", first_strings[refs[0]])
                self.assertIn(EXCLUSION_SENTENCE, first_strings[refs[1]])
                self.assertEqual("Emotion, Hope", first_strings[refs[2]])
                self.assertIn(EXCLUSION_SENTENCE, first_strings[refs[3]])
                self.assertEqual(missing_statuses, set(first_strings[len(pre_strings) + 4 :]))
                second = game.run_reinstall()
                self.assert_installed(game, second)
                self.assertEqual(first_override, _raw_tree(game.override), game.transcript(second))
                self.assertEqual(first_tlk, game.lang_tlk.read_bytes(), game.transcript(second))

                uninstall = game.run_uninstall()
                transcript = game.transcript(uninstall)
                self.assertEqual(0, uninstall.returncode, transcript)
                self.assertNotRegex(game.active_log(), rf"(?m)#0\s+#{COMPONENT}\b")
                self.assertEqual(game.pre_override, _raw_tree(game.override), transcript)
                self.assertEqual(first_tlk, game.lang_tlk.read_bytes(), transcript)
                self.assertEqual(first_strings, _tlk_strings(game.lang_tlk), transcript)
                game.assert_engine_inputs_stable(self)

    def assert_public_semantics(
        self,
        game: SyntheticEmotionGame,
        courage_resref: str,
        hope_resref: str,
        courage_state: int | None,
        hope_state: int | None,
        *,
        standalone: set[str],
    ) -> None:
        standalone_projectile = (
            read_ids(game.override / "PROJECTL.IDS").value(
                PRIVATE_EMOTION_PROJECTILE
            )
            + 1
            if standalone
            else None
        )
        for own, other, state, courage in (
            (courage_resref, hope_resref, courage_state, True),
            (hope_resref, courage_resref, hope_state, False),
        ):
            spell = read_spl(game.override / f"{own}.SPL")
            self.assertEqual(1, len(spell.abilities))
            header = spell.header_raw
            ability = spell.abilities[0]
            self.assertEqual(1, struct.unpack_from("<H", header, 0x1C)[0])
            self.assertEqual(11, struct.unpack_from("<H", header, 0x22)[0])
            self.assertEqual(4, header[0x25])
            self.assertEqual(4, struct.unpack_from("<I", header, 0x34)[0])
            self.assertEqual(2, ability.raw[0x00])
            self.assertEqual(2, ability.raw[0x02])
            self.assertEqual(4, ability.target)
            self.assertEqual(50, struct.unpack_from("<H", ability.raw, 0x0E)[0])
            self.assertEqual(4, struct.unpack_from("<H", ability.raw, 0x12)[0])
            if own in standalone:
                self.assertEqual(
                    0x800,
                    struct.unpack_from("<I", header, 0x1E)[0],
                    f"standalone {own} must exclude Invokers as an Enchantment spell",
                )
                self.assertEqual("CAS_M05", _resref_at(header, 0x10))
                self.assertEqual(standalone_projectile, ability.projectile)
                self.assertEqual(f"{own}C", spell.spell_icon.upper())
                self.assertEqual(f"{own}B", ability.icon.upper())
            effects = spell.abilities[0].effects
            if own in standalone:
                portraits = [effect for effect in effects if effect.opcode == 142]
                self.assertEqual(1, len(portraits), f"standalone status entry in {own}")
                statdesc = TwoDA.from_text(
                    game.effective_bytes("STATDESC", "2DA").decode("ascii")
                )
                self.assertEqual(
                    f"{own}D",
                    statdesc.cell(str(portraits[0].parameter2), "BAM_FILE").upper(),
                )
            for resource in (own, other):
                matches = [
                    effect for effect in effects
                    if effect.opcode == 321 and effect.resource.upper() == resource.upper()
                ]
                self.assertEqual(1, len(matches), (own, resource))
                self.assertEqual(2, matches[0].parameter2)
            expected_mechanics = COURAGE_MECHANICS if courage else HOPE_MECHANICS
            for expected in expected_mechanics:
                self.assertTrue(any(effect.canonical() == expected.canonical() for effect in effects), expected)
            markers = [effect for effect in effects if effect.opcode == 328 and (state is None or effect.parameter2 == state)]
            if state is None:
                self.assertFalse(markers, f"unexpected owned marker in {own}")
            else:
                self.assertEqual(1, len(markers), f"marker {state} in {own}")
            if own in standalone:
                self.assertTrue(
                    any(effect.opcode == 141 and effect.parameter2 == 10 for effect in effects)
                )
                self.assertTrue(
                    any(effect.opcode == 174 and effect.resource.upper() == "EFF_M05" for effect in effects)
                )
                self.assertTrue(
                    any(
                        effect.opcode == 174
                        and effect.resource.upper() == PRIVATE_EMOTION_EFFECT_SOUND
                        and effect.timing == 4
                        and effect.duration == 300
                        for effect in effects
                    )
                )
                self.assertTrue(
                    any(
                        effect.opcode == 61
                        and effect.parameter1 == 509245440
                        and effect.parameter2 == 1638400
                        for effect in effects
                    )
                )
            name_ref = struct.unpack_from("<i", header, 0x08)[0]
            self.assertEqual(name_ref, struct.unpack_from("<i", header, 0x0C)[0])
            desc_ref = struct.unpack_from("<i", header, 0x50)[0]
            name = _tlk_string(game.lang_tlk, name_ref)
            description = _tlk_string(game.lang_tlk, desc_ref)
            self.assertEqual("Emotion, Courage" if courage else "Emotion, Hope", name)
            self.assertIn(EXCLUSION_SENTENCE, description)
            self.assertIn("Applying either spell removes the other.", description)
            self.assertRegex(description, r"(?i)Duration:\s*(?:1 hour|300 seconds|50 rounds)")
            self.assertRegex(
                description,
                r"(?i)Area of Effect:[^\r\n]*(?:7[- ]?foot|7 ft|radius)",
            )
            if courage:
                for phrase in (
                    "THAC0", "damage", "Hit Point", "ends fear and morale failure",
                    "Emotion, Fear", "Horror", "Innate Horror",
                ):
                    self.assertIn(phrase.lower(), description.lower())
                self.assertRegex(description, r"(?is)\+1.*THAC0")
                self.assertRegex(description, r"(?is)\+3.*damage")
                self.assertRegex(description, r"(?is)\+5.*Hit Point")
            else:
                for phrase in (
                    "morale", "THAC0", "damage", "saving throw",
                    "Emotion, Hopelessness", "Symbol, Hopelessness",
                ):
                    self.assertIn(phrase.lower(), description.lower())
                for mechanic in ("morale", "THAC0", "damage", "saving throw"):
                    self.assertRegex(description, rf"(?is)\+2.*{re.escape(mechanic)}")

        self.assert_adverse_outputs(game, courage_resref, hope_resref)
        self.assert_matches_transformer_oracle(game, courage_resref, hope_resref)

    def assert_adverse_outputs(
        self, game: SyntheticEmotionGame, courage_resref: str, hope_resref: str
    ) -> None:
        for resref, benefit, domain_opcode, unconditional in (
            (FEAR_RESREF, courage_resref, 24, False),
            (HOPELESS_RESREF, hope_resref, 45, True),
            (SYMBOL_HOPELESS_RESREF, hope_resref, 45, False),
        ):
            if resref == game.options.missing_adverse:
                self.assertFalse((game.override / f"{resref}.SPL").exists())
                continue
            path = game.override / f"{resref}.SPL"
            self.assertTrue(path.exists(), f"writable adverse resource was not staged: {resref}")
            spell = read_spl(path)
            for ability in spell.abilities:
                effects = ability.effects
                domains = [i for i, effect in enumerate(effects) if effect.opcode == domain_opcode]
                removers = [
                    (i, effect) for i, effect in enumerate(effects)
                    if effect.opcode == 321 and effect.resource.upper() == benefit.upper()
                ]
                self.assertEqual(1, len(domains), (resref, ability.required_level))
                self.assertEqual(1, len(removers), (resref, ability.required_level))
                index, remover = removers[0]
                donor = effects[domains[0]]
                self.assertEqual(0, remover.parameter1)
                self.assertEqual(0, remover.parameter2)
                self.assertEqual(1, remover.timing)
                self.assertEqual(0, remover.duration)
                if unconditional:
                    self.assertEqual(0, index, (resref, ability.required_level))
                    self.assertEqual(0, remover.resist_dispel)
                    self.assertEqual((100, 0), (remover.probability1, remover.probability2))
                    self.assertEqual((0, 0, 0), (remover.save_type, remover.save_bonus, remover.special))
                else:
                    self.assertEqual(domains[0] - 1, index, (resref, ability.required_level))
                    self.assertEqual(
                        (
                            donor.target, donor.power, donor.resist_dispel,
                            donor.probability1, donor.probability2,
                            donor.save_type, donor.save_bonus, donor.special,
                        ),
                        (
                            remover.target, remover.power, remover.resist_dispel,
                            remover.probability1, remover.probability2,
                            remover.save_type, remover.save_bonus, remover.special,
                        ),
                    )
        self.assertFalse((game.override / f"{HORROR_RESREF}.SPL").exists())
        self.assertFalse((game.override / f"{INNATE_HORROR_RESREF}.SPL").exists())

    def assert_matches_transformer_oracle(
        self, game: SyntheticEmotionGame, courage_resref: str, hope_resref: str
    ) -> None:
        holder = tempfile.TemporaryDirectory(prefix="cbr-emotion-public-oracle-")
        self.addCleanup(holder.cleanup)
        fixture = Path(holder.name) / "fixture"
        fixture.mkdir()
        (fixture / "CBR_INPUT.OK").write_bytes(b"public installer oracle\n")

        courage_exists = game.options.symbols in {"both", "courage_only"}
        hope_exists = game.options.symbols in {"both", "hope_only"}
        (fixture / f"{courage_resref}.SPL").write_bytes(
            game.original_bytes(COURAGE_RESREF, "SPL")
            if courage_exists
            else _native_fallback_spell(game, courage_resref, courage=True)
        )
        (fixture / f"{hope_resref}.SPL").write_bytes(
            game.original_bytes(HOPE_RESREF, "SPL")
            if hope_exists
            else _native_fallback_spell(game, hope_resref, courage=False)
        )
        role_resrefs = (
            FEAR_RESREF, HORROR_RESREF, INNATE_HORROR_RESREF,
            HOPELESS_RESREF, SYMBOL_HOPELESS_RESREF,
        )
        present_adverse: list[str] = []
        for resref in role_resrefs:
            if resref == game.options.missing_adverse:
                continue
            (fixture / f"{resref}.SPL").write_bytes(game.original_bytes(resref, "SPL"))
            present_adverse.append(resref)

        courage_scroll = (
            COURAGE_EXISTING_SCROLL if courage_exists else COURAGE_FALLBACK_SCROLL
        )
        hope_scroll = HOPE_EXISTING_SCROLL if hope_exists else HOPE_FALLBACK_SCROLL
        (fixture / f"{courage_scroll}.ITM").write_bytes(
            game.original_bytes(COURAGE_EXISTING_SCROLL, "ITM")
            if courage_exists
            else (game.override / f"{COURAGE_FALLBACK_SCROLL}.ITM").read_bytes()
        )
        (fixture / f"{hope_scroll}.ITM").write_bytes(
            game.original_bytes(HOPE_EXISTING_SCROLL, "ITM")
            if hope_exists
            else (game.override / f"{HOPE_FALLBACK_SCROLL}.ITM").read_bytes()
        )

        public_courage = read_spl(game.override / f"{courage_resref}.SPL")
        public_hope = read_spl(game.override / f"{hope_resref}.SPL")
        output = Path(holder.name) / "oracle-output"
        run_dir = Path(holder.name) / "oracle-run"
        run_dir.mkdir()
        public_refs = (
            struct.unpack_from("<i", public_courage.header_raw, 0x08)[0],
            struct.unpack_from("<i", public_courage.header_raw, 0x50)[0],
            struct.unpack_from("<i", public_hope.header_raw, 0x08)[0],
            struct.unpack_from("<i", public_hope.header_raw, 0x50)[0],
        )
        args = (
            courage_resref, hope_resref, FEAR_RESREF, HORROR_RESREF,
            INNATE_HORROR_RESREF, HOPELESS_RESREF, SYMBOL_HOPELESS_RESREF,
            str(211 if game.options.markers in {"present", "partial"} else -1),
            str(213 if game.options.markers == "present" else -1),
            *(str(value) for value in public_refs),
        )
        command = [
            str(WEIDU), str(HARNESS), "--nogame", "--force-install-list", "0",
            "--args", str(PRODUCTION_TPA), "--args", str(fixture), "--args", str(output),
        ]
        for value in args:
            command.extend(("--args", value))
        command.extend(("--no-exit-pause", "--quick-log"))
        process = subprocess.run(
            command, cwd=run_dir, capture_output=True, text=True, timeout=45, check=False
        )
        transcript = f"{process.stdout}\n{process.stderr}"
        self.assertEqual(0, process.returncode, transcript)
        self.assertTrue((output / "CBR_TEST.OK").exists(), transcript)
        self.assertIn("SUCCESSFULLY INSTALLED", transcript)
        for resref in (courage_resref, hope_resref, *present_adverse):
            if resref in {HORROR_RESREF, INNATE_HORROR_RESREF}:
                continue
            self.assertEqual(
                (output / f"{resref}.SPL").read_bytes(),
                (game.override / f"{resref}.SPL").read_bytes(),
                f"public SPL differs from tested transformer oracle: {resref}",
            )
        for item in (courage_scroll, hope_scroll):
            self.assertEqual(
                (output / f"{item}.ITM").read_bytes(),
                (game.override / f"{item}.ITM").read_bytes(),
                f"public ITM differs from tested transformer oracle: {item}",
            )

    def target_scrolls(self, game: SyntheticEmotionGame, targets: set[str]) -> dict[str, list[str]]:
        found = {target: [] for target in targets}
        for path in game.override.glob("*.ITM"):
            item = read_itm(path)
            ability_effects = [
                effect for ability in item.abilities for effect in ability.effects
            ]
            learned = {
                effect.resource.upper()
                for effect in ability_effects
                if effect.opcode == 147
            }
            for target in targets & learned:
                found[target].append(path.stem.upper())
                learn_effects = [
                    effect
                    for effect in ability_effects
                    if effect.opcode == 147 and effect.resource.upper() == target
                ]
                cast_effects = [
                    effect
                    for effect in ability_effects
                    if effect.opcode == 148 and effect.resource.upper() == target
                ]
                self.assertEqual(1, len(learn_effects), path.name)
                self.assertEqual(1, len(cast_effects), path.name)
                self.assertEqual(target, learn_effects[0].resource.upper())
                self.assertEqual(target, cast_effects[0].resource.upper())
                unrelated_learn = [
                    effect
                    for effect in ability_effects
                    if effect.opcode == 147
                    and effect.resource.upper() == UNRELATED_LEARN_RESREF
                ]
                unrelated_use = [
                    effect
                    for effect in item.global_effects
                    if effect.opcode == 148
                    and effect.resource.upper() == UNRELATED_USE_RESREF
                ]
                if path.stem.upper() in {
                    COURAGE_FALLBACK_SCROLL,
                    HOPE_FALLBACK_SCROLL,
                }:
                    self.assertEqual([], unrelated_learn, path.name)
                    self.assertEqual([], unrelated_use, path.name)
                    self.assertEqual(2, len(item.abilities), path.name)
                    self.assertEqual([], list(item.global_effects), path.name)
                else:
                    self.assertEqual(1, len(unrelated_learn), path.name)
                    self.assertEqual(1, len(unrelated_use), path.name)
                    self.assertEqual(
                        UNRELATED_LEARN_EFFECT.to_bytes(), unrelated_learn[0].to_bytes(), path.name
                    )
                    self.assertEqual(
                        UNRELATED_USE_EFFECT.to_bytes(), unrelated_use[0].to_bytes(), path.name
                    )
                spell = read_spl(game.override / f"{target}.SPL")
                name_ref = struct.unpack_from("<i", spell.header_raw, 0x08)[0]
                desc_ref = struct.unpack_from("<i", spell.header_raw, 0x50)[0]
                self.assertEqual(name_ref, item.identified_name)
                self.assertEqual(desc_ref, item.identified_description)
                description = _tlk_string(game.lang_tlk, item.identified_description)
                self.assertIn(EXCLUSION_SENTENCE, description)
                self.assertIn("Applying either spell removes the other.", description)
        return found

    def assert_donor_store_mirroring(
        self,
        game: SyntheticEmotionGame,
        courage: str,
        hope: str,
        target_scrolls: dict[str, list[str]],
    ) -> None:
        self.assert_exact_store_clones(
            game,
            {
                ENCHANTED_DONOR_SCROLL: target_scrolls[courage][0],
                HOPELESS_DONOR_SCROLL: target_scrolls[hope][0],
            },
        )

    def assert_exact_store_clones(
        self, game: SyntheticEmotionGame, donor_to_scroll: dict[str, str]
    ) -> None:
        for store_name in (BIF_DONOR_STORE, OVERRIDE_DONOR_STORE):
            original_bytes = (
                game.bif_payloads[(store_name, "STO")]
                if store_name == BIF_DONOR_STORE
                else game.pre_override[f"{store_name}.STO"]
            )
            expected = _store_with_clones(original_bytes, donor_to_scroll)
            actual = game.effective_bytes(store_name, "STO")
            self.assertEqual(expected, actual, store_name)

    def assert_publication_delta(
        self,
        game: SyntheticEmotionGame,
        final_spells: set[str],
        target_scrolls: dict[str, list[str]],
    ) -> None:
        before_tree = game.pre_override
        actual = _raw_tree(game.override)
        before = set(before_tree)
        after = set(actual)
        added = after - before
        removed = before - after
        modified = {
            relative for relative in before & after if before_tree[relative] != actual[relative]
        }

        courage_exists = game.options.symbols in {"both", "courage_only"}
        hope_exists = game.options.symbols in {"both", "hope_only"}
        any_allocated = not courage_exists or not hope_exists
        expected_added = {
            *(f"{resref}.SPL" for resref in final_spells if f"{resref}.SPL" not in before),
        }
        for adverse in (FEAR_RESREF, SYMBOL_HOPELESS_RESREF):
            if adverse != game.options.missing_adverse:
                expected_added.add(f"{adverse}.SPL")
        expected_modified: set[str] = set()
        if game.options.missing_adverse != HOPELESS_RESREF:
            expected_modified.add(f"{HOPELESS_RESREF}.SPL")
        if courage_exists:
            expected_added.add(f"{COURAGE_EXISTING_SCROLL}.ITM")
            expected_courage_scrolls = [COURAGE_EXISTING_SCROLL]
        else:
            expected_added.add(f"{COURAGE_FALLBACK_SCROLL}.ITM")
            expected_courage_scrolls = [COURAGE_FALLBACK_SCROLL]
        if hope_exists:
            expected_modified.update(
                {f"{HOPE_RESREF}.SPL", f"{HOPE_EXISTING_SCROLL}.ITM"}
            )
            expected_hope_scrolls = [HOPE_EXISTING_SCROLL]
        else:
            expected_added.add(f"{HOPE_FALLBACK_SCROLL}.ITM")
            expected_hope_scrolls = [HOPE_FALLBACK_SCROLL]
        ids = game.effective_ids()
        final_courage = spell_resref(ids.value(COURAGE_SYMBOL), COURAGE_SYMBOL)
        final_hope = spell_resref(ids.value(HOPE_SYMBOL), HOPE_SYMBOL)
        self.assertEqual(
            {
                final_courage: expected_courage_scrolls,
                final_hope: expected_hope_scrolls,
            },
            target_scrolls,
            "existing scrolls must be reused and only missing scrolls created",
        )
        if any_allocated:
            expected_added.update(
                {
                    "SPELL.IDS",
                    "ADD_SPELL.IDS",
                    "SPELL.IDS.INSTALLED",
                    "MISSILE.IDS",
                    "PROJECTL.IDS",
                    f"{PRIVATE_EMOTION_PROJECTILE}.PRO",
                    f"{PRIVATE_EMOTION_VVC}.VVC",
                    f"{PRIVATE_EMOTION_ANIMATION}.BAM",
                    f"{PRIVATE_EMOTION_PROJECTILE_SOUND}.WAV",
                    f"{PRIVATE_EMOTION_EFFECT_SOUND}.WAV",
                    f"{BIF_DONOR_STORE}.STO",
                    "STATDESC.2DA",
                }
            )
            for standalone_spell in (
                *(() if courage_exists else (final_courage,)),
                *(() if hope_exists else (final_hope,)),
            ):
                expected_added.update(
                    f"{standalone_spell}{suffix}.BAM" for suffix in "ABCD"
                )
            expected_modified.add(f"{OVERRIDE_DONOR_STORE}.STO")

        self.assertEqual(expected_added, added, "unexpected published resource set")
        self.assertEqual(expected_modified, modified, "unexpected modified resource set")
        self.assertEqual(set(), removed, "installer removed pre-existing override resources")
        for relative, payload in before_tree.items():
            if relative not in expected_modified:
                self.assertEqual(payload, actual[relative], f"unrelated resource changed: {relative}")
        for relative in expected_modified:
            self.assertNotEqual(before_tree[relative], actual[relative], relative)
        self.assertNotIn(f"{FOREIGN_BIF_ITEM}.ITM", actual)
        self.assertNotIn(f"{FOREIGN_BIF_STORE}.STO", actual)
        self.assertNotIn(f"{ENCHANTED_DONOR_SCROLL}.ITM", actual)
        self.assertNotIn(f"{HORROR_RESREF}.SPL", actual)
        self.assertNotIn(f"{INNATE_HORROR_RESREF}.SPL", actual)


def _mask_scroll_text(data: bytes) -> bytes:
    masked = bytearray(data)
    masked[0x0C:0x10] = b"\0" * 4
    masked[0x54:0x58] = b"\0" * 4
    return bytes(masked)


def read_spl_bytes(data: bytes):
    from tests.ie_formats import SplFile
    return SplFile.from_bytes(data)


if __name__ == "__main__":
    unittest.main()
