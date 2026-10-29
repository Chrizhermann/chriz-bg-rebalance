"""Druid and Alaghor weapon access (410/411) on disposable synthetic games.

Real WeiDU, public installer. The fixtures model the layouts the components
must handle: vanilla-shaped WEAPPROF/KITLIST tables plus kits that share or
reuse columns, Artisan's C0PR#CL grant table (or none), items with and without
the Kitpack's usability gate, EET's three class-text tables, and stacks where
fighter/clerics may train every weapon. 411 also needs EEex and a game
executable with the kit-proficiency lookup its hook patches; synthetic PE32+
images stand in for Baldur.exe. They establish installer behaviour, not
in-game acceptance.
"""
from __future__ import annotations

import copy
import dataclasses
import struct
import tempfile
import unittest
from pathlib import Path

from tests.ie_formats import ItmAbility, ItmFile, SplAbility, SplEffect, SplFile, TwoDA, make_spl
from tests.test_cloud_forms import ROOT, Game
from tests.test_flail_of_ages import strings
from tests.test_potion_uniqueness import run


WEAPON_ROWS = (
    ("BASTARDSWORD", 89), ("LONGSWORD", 90), ("SHORTSWORD", 91), ("AXE", 92),
    ("TWOHANDEDSWORD", 93), ("KATANA", 94), ("SCIMITARWAKISASHININJATO", 95),
    ("DAGGER", 96), ("WARHAMMER", 97), ("CLUB", 115), ("SPEAR", 98),
    ("HALBERD", 99), ("FLAILMORNINGSTAR", 100), ("MACE", 101),
    ("QUARTERSTAFF", 102), ("CROSSBOW", 103), ("LONGBOW", 104),
    ("SHORTBOW", 105), ("DART", 106), ("SLING", 107),
)
WEAPONS = tuple(proficiency for _, proficiency in WEAPON_ROWS)
# BG1 composites reuse the AXE and SPEAR labels; the components key rows by ID.
OTHER_ROWS = (
    ("LARGE_SWORD", 0), ("SPEAR", 3), ("AXE", 6), ("MISSILE", 7),
    ("2HANDED", 111), ("SWORDANDSHIELD", 112), ("SINGLEWEAPON", 113),
    ("2WEAPON", 114), ("EXTRA2", 116),
)
CLASS_COLUMNS = (
    "MAGE", "FIGHTER", "CLERIC", "THIEF", "BARD", "PALADIN", "FIGHTER_MAGE",
    "FIGHTER_CLERIC", "FIGHTER_THIEF", "FIGHTER_MAGE_THIEF", "DRUID", "RANGER",
    "MAGE_THIEF", "CLERIC_MAGE", "CLERIC_THIEF", "FIGHTER_DRUID",
    "FIGHTER_MAGE_CLERIC", "CLERIC_RANGER", "SORCERER", "MONK", "SHAMAN",
)
DRUID_WEAPONS = (95, 96, 115, 98, 102, 106, 107)
CLERIC_WEAPONS = (97, 115, 100, 101, 102, 107)
THIEF_ROW = (90, 91, 94, 95, 96, 115, 102, 103, 105, 106, 107)
STYLES = (111, 112, 113, 114)

DRUID, FIGHTER_DRUID, CLERIC, FIGHTER_CLERIC = 11, 16, 3, 8
ALAGHOR_KIT = 0x4030
CLASS_ROW, KIT_ROW = 2, 3
SPECIAL = 99999

DRUID_TEXT = (
    "DRUID: A synthetic druid description.\n\nCLASS FEATURES:\n\n"
    "– May only wear non-metallic armor.\n"
    "– May only use the following weapons: scimitar, dagger, club, spear, quarterstaff, dart, sling.\n"
    "– May only become Proficient (one slot) in any weapon class.\n"
    "– 18th level: Gains 10% resistance to fire; a further 10% at level 21.")
FD_TEXT = ("FIGHTER/DRUID: A synthetic text whose weapons are restricted to only those "
           "allowed by the Druid's ethos. May Specialize in any weapon they can use.")
ALAGHOR_TEXT = (
    "ALAGHOR OF CLANGEDDIN: A synthetic kit text naming the Lord of the Twin Axes.\n\n"
    "Advantages:\n\n- 8th level: May cast Spiritual Axe once per day.\n\n"
    "Disadvantages:\n\n- Race restricted to dwarf.")
TEXTS = [
    "Untouched shared sentinel.",
    DRUID_TEXT,
    FD_TEXT,
    ALAGHOR_TEXT,
    DRUID_TEXT.replace("synthetic druid", "synthetic BG1 druid"),
    FD_TEXT.replace("synthetic text", "synthetic BG1 text"),
]
NEW_WEAPONS = "spear, quarterstaff, dart, sling, axe, short bow."
LONG_BOWS = "allowed by the Druid's ethos, plus long bows."
BULLET = ("- May use axes, Clangeddin's chosen weapon, alongside the cleric weapons, "
          "and may specialize in them like a Fighter/Cleric.\n")


# ---------------------------------------------------------------------------
# Fixture model
# ---------------------------------------------------------------------------

@dataclasses.dataclass
class Kit:
    name: str
    klass: int
    column: str


def base_columns():
    """Vanilla-shaped class columns plus the kit columns the fixture uses."""
    values = {name: {} for name in CLASS_COLUMNS}
    for proficiency in WEAPONS:
        values["FIGHTER"][proficiency] = 5
    for proficiency in DRUID_WEAPONS:
        values["DRUID"][proficiency] = 1
        values["FIGHTER_DRUID"][proficiency] = 2
    for proficiency in CLERIC_WEAPONS:
        values["CLERIC"][proficiency] = 1
        values["FIGHTER_CLERIC"][proficiency] = 2
    for proficiency in (92, 96, 115, 98, 102, 105, 106, 107):
        values["SHAMAN"][proficiency] = 1
    for column, cap in (("DRUID", 1), ("FIGHTER_DRUID", 2), ("CLERIC", 1), ("FIGHTER_CLERIC", 2), ("SHAMAN", 1)):
        for style in STYLES:
            values[column][style] = cap
    values["FIGHTER_DRUID"][114] = 3
    values["FIGHTER_CLERIC"][114] = 3
    values["DRUID"][6] = 0  # the BG1 composite AXE row stays untouched
    values["FIGHTER"][6] = 2
    values["TOTEMIC_DRUID"] = dict(values["DRUID"])
    values["SHAPESHIFTER"] = dict(values["DRUID"])
    values["HIGHAXE"] = {**values["DRUID"], 92: 3}
    values["FD_KIT"] = dict(values["FIGHTER_DRUID"])
    values["SHARED_DC"] = dict(values["CLERIC"])
    values["DRUID_FD_SHARED"] = dict(values["DRUID"])
    values["LK_ALAGHOR"] = {proficiency: 1 for proficiency in THIEF_ROW}
    values["LK_ALAGHOR"].update({style: 1 for style in STYLES})
    values["LK_ALAGHOR"][116] = 1
    values["PRIEST_KIT"] = dict(values["CLERIC"])
    return values


BASE_KITS = (
    Kit("TOTEMIC_DRUID", DRUID, "TOTEMIC_DRUID"),
    Kit("SHAPESHIFTER", DRUID, "SHAPESHIFTER"),
    Kit("HIGHAXE", DRUID, "HIGHAXE"),
    Kit("REUSER", DRUID, "DRUID"),              # a kit reusing the class column
    Kit("FD_KIT", FIGHTER_DRUID, "FD_KIT"),
    Kit("SHARED_DRUIDKIT", DRUID, "SHARED_DC"),  # shared with a cleric kit
    Kit("SHARED_CLERICKIT", CLERIC, "SHARED_DC"),
    Kit("DFD_DRUIDKIT", DRUID, "DRUID_FD_SHARED"),
    Kit("DFD_FDKIT", FIGHTER_DRUID, "DRUID_FD_SHARED"),
    Kit("LK_ALAGHOR", CLERIC, "LK_ALAGHOR"),
    Kit("PRIEST_KIT", CLERIC, "PRIEST_KIT"),
)
# Hand-derived from BASE_KITS: the columns 410 owns.
DRUID_OWNED = ("DRUID", "TOTEMIC_DRUID", "SHAPESHIFTER", "HIGHAXE", "DRUID_FD_SHARED")
FD_OWNED = ("FIGHTER_DRUID", "FD_KIT")


def kit_columns(kits):
    seen = []
    for kit in kits:
        if kit.column not in CLASS_COLUMNS and kit.column not in seen:
            seen.append(kit.column)
    return seen


def weapprof_text(values, kits):
    columns = ["ID", "NAME_REF", "DESC_REF", *CLASS_COLUMNS, *kit_columns(kits)]
    width = 26
    lines = ["2DA".ljust(width) + "V1.0", "0", " " * width + "".join(c.ljust(width) for c in columns)]
    rows = sorted(OTHER_ROWS[:4]) + list(WEAPON_ROWS) + list(OTHER_ROWS[4:])
    for label, proficiency in rows:
        cells = [str(proficiency), "100", "200"]
        cells += [str(values.get(column, {}).get(proficiency, 0)) for column in columns[3:]]
        lines.append(label.ljust(width) + "".join(cell.ljust(width) for cell in cells))
    return "\r\n".join(lines) + "\r\n"


def kitlist_text(kits, *, shuffled=False):
    weapprof_columns = ["ID", "NAME_REF", "DESC_REF", *CLASS_COLUMNS, *kit_columns(kits)]
    header = ["ROWNAME", "LOWER", "MIXED", "HELP", "ABILITIES", "PROFICIENCY", "UNUSABLE", "CLASS", "KITIDS"]
    if shuffled:
        header = ["ROWNAME", "CLASS", "LOWER", "PROFICIENCY", "MIXED", "HELP", "ABILITIES", "UNUSABLE", "KITIDS"]
    lines = ["2DA V1.0", "*", "    " + " ".join(header), "0 RESERVE " + " ".join("*" for _ in header[1:])]
    for index, kit in enumerate(kits, 1):
        cell = {
            "ROWNAME": kit.name, "LOWER": "0", "MIXED": "0",
            "HELP": "3" if kit.name == "LK_ALAGHOR" else "0", "ABILITIES": "CLAB" + str(index),
            "PROFICIENCY": str(weapprof_columns.index(kit.column)), "UNUSABLE": "0x00000000",
            "CLASS": str(kit.klass),
            "KITIDS": hex(ALAGHOR_KIT if kit.name == "LK_ALAGHOR" else 0x4000 + index),
        }
        lines.append(f"{index} " + " ".join(cell[name] for name in header))
    return "\n".join(lines) + "\n"


def class_text(rows):
    lines = ["2DA V1.0", "-1", "    CLASSID KITID LOWER DESCSTR MIXED"]
    lines += [f"{name} {klass} 0 0 {strref} 0" for name, klass, strref in rows]
    return "\n".join(lines) + "\n"


SPLPROT_TEXT = (
    "2DA V1.0\n*\n      STAT VALUE RELATION\n"
    "0_ANYONE 0x106 0 1\n1_SOURCE 0x100 * *\n2_CLASS=n 0x10d -1 1\n3_KIT=n 152 -1 1\n"
    "4_AXE>0 300 0 2\n5_SHORTBOW>0 301 0 2\n6_LONGBOW>0 302 0 2\n7_DAGGER>0 303 0 2\n")


def fx(opcode, p1=0, p2=0, resource="", *, special=0, target=2, **kwargs):
    return SplEffect(opcode=opcode, target=target, parameter1=p1, parameter2=p2,
                     resource=resource, special=special, probability1=100, **kwargs)


def class_grant(klass, proficiency, row=CLASS_ROW):
    return fx(326, klass, row, f"C0PR#{proficiency}", special=SPECIAL)


def grant_effects(*, extra=()):
    """C0PR#CL's shape: remove all grants, pip grants, class grants, trailing re-application."""
    effects = [fx(321, resource=f"C0PR#{p}") for p in (92, 95, 96, 97, 104, 105)]
    effects += [fx(326, 0, row, f"C0PR#{p}") for row, p in ((4, 92), (5, 105), (6, 104), (7, 96))]
    effects += [class_grant(DRUID, p) for p in (95, 96)]
    effects += [class_grant(FIGHTER_DRUID, p) for p in (95, 96)]
    effects += [class_grant(CLERIC, 97), class_grant(FIGHTER_CLERIC, 97)]
    effects += list(extra)
    effects += [fx(206, resource="FOREIGN"), fx(326, 0, 0, "C0PR#KG")]
    return effects


def c0prcl(effects=None):
    return make_spl((SplAbility(1, 5, 1, tuple(grant_effects() if effects is None else effects)),)).to_bytes()


def permission_spell(stat):
    return make_spl((SplAbility(1, 5, 1, (fx(401, 1, stat, target=1, timing=9),)),)).to_bytes()


def item(proficiency, *, usability=0, equipped=(), ability_effects=()):
    header = bytearray(0x72)
    header[:8] = b"ITM V1  "
    struct.pack_into("<I", header, 0x1E, usability)
    header[0x31] = proficiency
    abilities = (ItmAbility(effects=tuple(ability_effects)),) if ability_effects else ()
    return ItmFile(abilities=abilities, global_effects=tuple(equipped), header_raw=bytes(header)).to_bytes()


def usable_by_not(klass, power=0):
    return SplEffect(opcode=319, target=1, power=power, parameter1=klass, parameter2=5, timing=2)


GATE = SplEffect(opcode=319, target=1, power=3, parameter2=455, timing=2)
KIT_LOCK = SplEffect(opcode=319, target=1, power=0, parameter1=0x4011, parameter2=9, timing=2)
DRUID_BIT, FD_BIT, FIGHTER_BIT, MAGE_BIT = 0x40000000, 0x1000, 0x800, 0x40000


def items():
    return {
        # Swept by the Kitpack: governed by its gate, left alone.
        "AXGATED.ITM": item(92, equipped=(GATE, usable_by_not(DRUID))),
        # Tweaks Anthology-style two-handed axe: druids barred by opcode 319.
        # The same record in an ability header is not a usability rule: kept.
        "AX2H.ITM": item(92, usability=0x20000000, equipped=(usable_by_not(DRUID), KIT_LOCK),
                         ability_effects=(usable_by_not(DRUID),)),
        "SBOWBIT.ITM": item(105, usability=DRUID_BIT | FD_BIT, ability_effects=(usable_by_not(DRUID),)),
        "LBOW.ITM": item(104, usability=DRUID_BIT | FD_BIT, equipped=(usable_by_not(DRUID),)),
        "LBOWFD.ITM": item(104, equipped=(usable_by_not(FIGHTER_DRUID), usable_by_not(DRUID))),
        # Fighters cannot use it: an item-level restriction, not a weapon type.
        "MAGEBOW.ITM": item(105, usability=FIGHTER_BIT | DRUID_BIT | FD_BIT),
        # Usable only by druids (power 1): stays exactly as it is.
        "DRUIDAXE.ITM": item(92, equipped=(usable_by_not(DRUID, power=1),)),
        "SWORD.ITM": item(90, usability=DRUID_BIT | FD_BIT | MAGE_BIT),
    }


def expected_items(original):
    expected = dict(original)

    def lifted(name, *, clear, drop):
        parsed = ItmFile.from_bytes(original[name])
        header = bytearray(parsed.header_raw)
        usability, = struct.unpack_from("<I", header, 0x1E)
        struct.pack_into("<I", header, 0x1E, usability & ~clear)
        kept = tuple(e for e in parsed.global_effects
                     if not (e.opcode == 319 and e.power == 0 and e.parameter2 == 5 and e.parameter1 in drop))
        expected[name] = dataclasses.replace(parsed, global_effects=kept, header_raw=bytes(header)).to_bytes()

    if "AX2H.ITM" in expected:
        lifted("AX2H.ITM", clear=DRUID_BIT | FD_BIT, drop=(DRUID, FIGHTER_DRUID))
    if "SBOWBIT.ITM" in expected:
        lifted("SBOWBIT.ITM", clear=DRUID_BIT | FD_BIT, drop=(DRUID, FIGHTER_DRUID))
    if "LBOW.ITM" in expected:
        lifted("LBOW.ITM", clear=FD_BIT, drop=(FIGHTER_DRUID,))
    if "LBOWFD.ITM" in expected:
        lifted("LBOWFD.ITM", clear=FD_BIT, drop=(FIGHTER_DRUID,))
    return expected


@dataclasses.dataclass
class Fixture:
    values: dict = dataclasses.field(default_factory=base_columns)
    kits: tuple = BASE_KITS
    kitpack: bool = True
    shuffled_kitlist: bool = False
    texts: list = dataclasses.field(default_factory=lambda: list(TEXTS))
    c0prcl: bytes | None = None
    splprot: str = SPLPROT_TEXT
    eeex: str = "current"  # "current", "old" (no conditional-jump hooks) or "none"

    def resources(self):
        resources = {
            "WEAPPROF.2DA": weapprof_text(self.values, self.kits).encode(),
            "KITLIST.2DA": kitlist_text(self.kits, shuffled=self.shuffled_kitlist).encode(),
            "CLASS.IDS": b"IDS V1.0\n3 CLERIC\n8 FIGHTER_CLERIC\n11 DRUID\n16 FIGHTER_DRUID\n21 SHAMAN\n",
            "KIT.IDS": b"IDS V1.0\n0x4000 TRUECLASS\n0x4030 LK_ALAGHOR\n",
            "STATS.IDS": b"IDS V1.0\n152 KIT\n269 CLASS\n",
            # Other components' predicates read SPELL.IDS; keep their probes quiet.
            "SPELL.IDS": b"IDS V1.0\n",
            "CLASTEXT.2DA": class_text((("DRUID", 11, 1), ("FIGHTER_DRUID", 16, 2), ("CLERIC", 3, 0))).encode(),
            "BGCLATXT.2DA": class_text((("DRUID", 11, 4), ("FIGHTER_DRUID", 16, 5))).encode(),
            "SODCLTXT.2DA": class_text((("DRUID", 11, 4), ("FIGHTER_DRUID", 16, 5))).encode(),
            **items(),
        }
        if self.kitpack:
            resources.update({
                "SPLPROT.2DA": self.splprot.encode(),
                "C0PR#CL.SPL": self.c0prcl if self.c0prcl is not None else c0prcl(),
                **{f"C0PR#{p}.SPL": permission_spell(300 + p) for p in (92, 95, 96, 97, 104, 105)},
            })
        if self.eeex != "none":
            resources["M___EEex.lua"] = b"-- fixture bootstrap\n"
        return resources


def weapprof_cells(raw):
    table = TwoDA.from_text(raw.decode())
    cells = {}
    for _, values in table.rows:
        proficiency = int(values[0])
        for column, value in zip(table.columns[1:], values[1:]):
            cells[(column, proficiency)] = int(value)
    return cells


def expected_410_cells(cells, *, druid_owned=DRUID_OWNED, fd_owned=FD_OWNED):
    expected = dict(cells)
    druid_cap = max(cells[("DRUID", p)] for p in WEAPONS)
    fd_cap = max(cells[("FIGHTER_DRUID", p)] for p in WEAPONS)
    for column in druid_owned:
        for proficiency in (92, 105):
            expected[(column, proficiency)] = max(cells[(column, proficiency)], druid_cap)
    for column in fd_owned:
        for proficiency in (92, 105, 104):
            expected[(column, proficiency)] = max(cells[(column, proficiency)], fd_cap)
    return expected


def expected_411_cells(cells, column="LK_ALAGHOR"):
    expected = dict(cells)
    cap = max(cells[("FIGHTER_CLERIC", p)] for p in WEAPONS if cells[("CLERIC", p)] > 0)
    for proficiency in {p for _, p in cells}:
        cleric, fc = cells[("CLERIC", proficiency)], cells[("FIGHTER_CLERIC", proficiency)]
        if proficiency not in WEAPONS:
            value = fc  # fighting styles and other rows: what Yeslick has without the hook
        elif cleric > 0:
            value = fc if fc > 0 else cleric
        elif proficiency == 92:
            value = fc if fc > 0 else cap
        else:
            value = 0
        expected[(column, proficiency)] = value
    return expected


def is_weapon_record(effect):
    resource = effect.resource.upper()
    return effect.opcode in (321, 326) and resource.startswith("C0PR#") and resource[5:].isdigit()


def expected_grants(effects, grants, *, class_rows=(CLASS_ROW,), special=None, row_of=None):
    """Independent oracle: each missing grant is a copy of the last class grant,
    inserted right after the last weapon-grant record."""
    effects = list(effects)
    for value, row, proficiency, condition_rows in grants:
        resource = f"C0PR#{proficiency}"
        if any(e.opcode == 326 and e.parameter1 == value and e.parameter2 in condition_rows
               and e.resource.upper() == resource for e in effects):
            continue
        last = max(i for i, e in enumerate(effects) if is_weapon_record(e))
        templates = [e for e in effects if is_weapon_record(e) and e.opcode == 326
                     and e.parameter1 > 0 and e.parameter2 in class_rows]
        template = templates[-1] if templates else SplEffect(opcode=326, target=2, probability1=100)
        new = dataclasses.replace(template, parameter1=value, parameter2=row, resource=resource, raw=b"")
        if special is not None:
            new = dataclasses.replace(new, special=special)
        effects.insert(last + 1, new)
    return effects


DRUID_GRANTS = tuple((DRUID, CLASS_ROW, p, (CLASS_ROW,)) for p in (92, 105)) + \
    tuple((FIGHTER_DRUID, CLASS_ROW, p, (CLASS_ROW,)) for p in (92, 105, 104))


def new_druid_text(text):
    return text.replace("spear, quarterstaff, dart, sling.", NEW_WEAPONS)


def new_fd_text(text):
    return text.replace("allowed by the Druid's ethos.", LONG_BOWS)


def new_alaghor_text(text):
    return text.replace("Advantages:\n\n", "Advantages:\n\n" + BULLET, 1)


# ---------------------------------------------------------------------------
# EEex and the game executable (411)
# ---------------------------------------------------------------------------

KP_DB = ROOT / "chriz-bg-rebalance/kitprof/CBRKP.db"
KP_RUNTIME = ROOT / "chriz-bg-rebalance/lua/M_CBRKP.lua"
ALAGHOR_REGISTRATION = ("CBR_8_16432", ("8", "16432"))  # FIGHTER_CLERIC and LK_ALAGHOR


def kit_lookup_pattern():
    """The EEex pattern 411 installs: its bytes (None for wildcards) and the label offset."""
    fields = dict(line.split("=", 1) for line in KP_DB.read_text().splitlines()
                  if "=" in line and not line.startswith(";"))
    text = fields["Pattern"].strip()
    pattern = [None if text[i:i + 2] == "??" else int(text[i:i + 2], 16) for i in range(0, len(text), 2)]
    operation, offset = fields["Operations"].split()
    assert operation == "ADD"
    return pattern, int(offset)


def kit_lookup_site(fill, *, hooked=False):
    """The lookup with its varying displacements set from `fill`; `hooked` models
    another mod that already replaced the JNE and the MOVSX with a jump."""
    pattern, label = kit_lookup_pattern()
    site = bytearray((fill + i) & 0xFF if byte is None else byte for i, byte in enumerate(pattern))
    if hooked:
        site[label:label + 9] = b"\xE9\x10\x20\x30\x40" + b"\x90" * 4
    return bytes(site)


def kit_lookup_executable(*, text_sites=1, hooked_sites=0, data_sites=0, fill=0x11, magic=0x20B):
    """A minimal x64 PE image: an executable .text and a read-only .rdata section."""
    image = bytearray(0x1000)
    image[0:2] = b"MZ"
    struct.pack_into("<I", image, 0x3C, 0x80)
    image[0x80:0x84] = b"PE\0\0"
    struct.pack_into("<HH", image, 0x84, 0x8664, 2)
    struct.pack_into("<H", image, 0x94, 0xF0)
    struct.pack_into("<H", image, 0x98, magic)
    for index, (name, start, flags) in enumerate(((b".text", 0x400, 0x60000020),
                                                  (b".rdata", 0xA00, 0x40000040))):
        entry = 0x80 + 24 + 0xF0 + index * 40
        image[entry:entry + 8] = name.ljust(8, b"\0")
        struct.pack_into("<IIII", image, entry + 8, 0x600, start, 0x600, start)
        struct.pack_into("<I", image, entry + 36, flags)
    sites = [kit_lookup_site(fill + 0x10 * i) for i in range(text_sites)]
    sites += [kit_lookup_site(fill, hooked=True) for _ in range(hooked_sites)]
    for index, site in enumerate(sites):
        start = 0x440 + index * 0x100
        image[start:start + len(site)] = site
    for index in range(data_sites):
        start = 0xA40 + index * 0x100
        site = kit_lookup_site(fill)
        image[start:start + len(site)] = site
    return bytes(image)


EEEX_SCRIPTS = {
    "current": {
        "EEex_Assembly_x86-64.lua": (
            "function EEex_HookAfterRestoreWithLabels(address, restoreDelay, restoreSize, returnDelay, labelPairs, assemblyT)\nend\n\n"
            "function EEex_HookConditionalJumpOnSuccess(address, restoreSize, assemblyT)\nend\n"),
        "EEex_Resource.lua": (
            "function EEex_Resource_Load2DA(resref)\nend\n\n"
            "function EEex_Resource_Get2DARowTableIterator(array, bIncludeLabel)\nend\n"),
    },
}
EEEX_SCRIPTS["old"] = {
    **EEEX_SCRIPTS["current"],
    "EEex_Assembly_x86-64.lua": (
        "function EEex_HookAfterRestoreWithLabels(address, restoreDelay, restoreSize, returnDelay, labelPairs, assemblyT)\nend\n"),
}


def install_eeex(root, flavour):
    if flavour == "none":
        return
    scripts = root / "EEex_scripts"
    (scripts / "extra_pattern_dbs").mkdir(parents=True)
    for name, text in EEEX_SCRIPTS[flavour].items():
        (scripts / name).write_text(text, encoding="ascii")


def pattern_db(game):
    return game.root / "EEex_scripts/extra_pattern_dbs/CBRKP.db"


def registration(values):
    return tuple(int(value, 0) for value in values)


class ClassWeaponAccessTests(unittest.TestCase):
    def game(self, fixture=None, *, resources=None, texts=None, exes=None):
        fixture = fixture or Fixture()
        holder = tempfile.TemporaryDirectory(prefix="cbr-cwa-")
        self.addCleanup(holder.cleanup)
        game = Game(Path(holder.name), fixture.resources() if resources is None else resources,
                    public=True, texts=fixture.texts if texts is None else texts)
        install_eeex(game.root, fixture.eeex)
        for name, raw in ({"Baldur.exe": kit_lookup_executable()} if exes is None else exes).items():
            (game.root / name).write_bytes(raw)
        return game

    def install(self, game, *components):
        code, output = run(game, *components)
        self.assertEqual(0, code, output)
        self.assertIn("SUCCESSFULLY INSTALLED", output)
        self.assertNotIn("NOT INSTALLED", output)
        return output

    def failed_unchanged(self, game, component, message):
        code, output = run(game, component)
        self.assertNotEqual(0, code, output)
        self.assertIn("NOT INSTALLED DUE TO ERRORS", output)
        self.assertIn(message, output)
        self.assertEqual(game.original, game.snapshot(), output)
        self.assertEqual(game.original_tlk, game.tlk.read_bytes(), output)

    def skipped_unchanged(self, game, component):
        code, output = run(game, component)
        self.assertEqual(0, code, output)
        self.assertIn("SKIPPING", output)
        self.assertNotIn("SUCCESSFULLY INSTALLED", output)
        self.assertEqual(game.original, game.snapshot(), output)
        return output

    def table_ref(self, raw, row_name, column="DESCSTR", match_column=None):
        table = TwoDA.from_text(raw.decode())
        if match_column is None:
            return int(table.cell(row_name, column))
        index = table.columns.index(match_column)
        refs = [int(values[table.columns.index(column)]) for _, values in table.rows if values[index] == row_name]
        self.assertEqual(1, len(refs))
        return refs[0]

    def assert_descriptions(self, game, after):
        texts = strings(game.tlk)
        self.assertEqual(game.original_texts, texts[:len(game.original_texts)])
        for table, druid, fd in (("CLASTEXT.2DA", 1, 2), ("BGCLATXT.2DA", 4, 5), ("SODCLTXT.2DA", 4, 5)):
            druid_ref = self.table_ref(after[table], "DRUID")
            fd_ref = self.table_ref(after[table], "FIGHTER_DRUID")
            self.assertGreaterEqual(druid_ref, len(game.original_texts), table)
            self.assertGreaterEqual(fd_ref, len(game.original_texts), table)
            self.assertEqual(new_druid_text(game.original_texts[druid]), texts[druid_ref], table)
            self.assertEqual(new_fd_text(game.original_texts[fd]), texts[fd_ref], table)
        self.assertEqual(0, self.table_ref(after["CLASTEXT.2DA"], "CLERIC"))

    def assert_410(self, game, fixture, *, kitpack=True, druid_owned=DRUID_OWNED, fd_owned=FD_OWNED):
        after = game.snapshot()
        before = game.original
        self.assertEqual(expected_410_cells(weapprof_cells(before["WEAPPROF.2DA"]),
                                            druid_owned=druid_owned, fd_owned=fd_owned),
                         weapprof_cells(after["WEAPPROF.2DA"]))
        expected = expected_items(before)
        for name in items():
            self.assertEqual(expected[name], after[name], name)
        if kitpack:
            spell = SplFile.from_bytes(before["C0PR#CL.SPL"])
            wanted = dataclasses.replace(spell, abilities=(dataclasses.replace(
                spell.abilities[0], effects=tuple(expected_grants(spell.abilities[0].effects, DRUID_GRANTS))),))
            self.assertEqual(wanted.to_bytes(), after["C0PR#CL.SPL"])
            self.assertEqual(before["SPLPROT.2DA"], after["SPLPROT.2DA"])
        self.assert_descriptions(game, after)
        untouched = set(before) - {"WEAPPROF.2DA", "C0PR#CL.SPL", "CLASTEXT.2DA", "BGCLATXT.2DA",
                                   "SODCLTXT.2DA", *items()}
        for name in untouched:
            self.assertEqual(before[name], after[name], name)
        self.assertEqual(set(before), set(after))

    # -- 410 ------------------------------------------------------------------

    def test_410_kitpack_layout_exact_delta_and_uninstall(self):
        fixture = Fixture()
        game = self.game(fixture)
        output = self.install(game, 410)
        self.assert_410(game, fixture)
        self.assertIn("kit SHARED_DRUIDKIT shares WEAPPROF column SHARED_DC", output)
        self.assertIn("kit DFD_FDKIT shares WEAPPROF column DRUID_FD_SHARED", output)
        self.assertIn("kit REUSER uses the class column DRUID", output)
        code, output = run(game, 410, uninstall=True)
        self.assertEqual(0, code, output)
        self.assertEqual(game.original, game.snapshot())

    def test_410_rerun_on_its_own_output_changes_nothing(self):
        first = self.game()
        self.install(first, 410)
        installed = first.snapshot()
        texts = strings(first.tlk)
        second = self.game(resources=installed, texts=texts)
        output = self.install(second, 410)
        self.assertEqual(second.original, second.snapshot())
        self.assertEqual(texts, strings(second.tlk))
        self.assertIn("descriptions are unchanged", output)

    def test_410_without_kitpack_changes_tables_items_and_texts_only(self):
        fixture = Fixture(kitpack=False)
        game = self.game(fixture)
        self.install(game, 410)
        self.assert_410(game, fixture, kitpack=False)
        self.assertFalse(any(name.startswith("C0PR#") or name == "SPLPROT.2DA" for name in game.snapshot()))

    def test_410_incomplete_kitpack_fails_without_changes(self):
        resources = Fixture().resources()
        del resources["C0PR#104.SPL"]
        game = self.game(resources=resources)
        self.failed_unchanged(game, 410, "Artisan's Kitpack proficiency system is incomplete")

    def test_410_unrecognized_grant_table_fails_without_changes(self):
        fixture = Fixture(c0prcl=c0prcl([fx(206, resource="FOREIGN"), fx(326, 0, 0, "C0PR#KG")]))
        self.failed_unchanged(self.game(fixture), 410, "layout is not recognized")

    def test_410_higher_caps_kept_and_druid_cap_followed(self):
        values = base_columns()
        for column in ("DRUID", "TOTEMIC_DRUID"):
            values[column][96] = 2  # another mod lets druids specialize in daggers
        values["FD_KIT"][104] = 3
        fixture = Fixture(values=values)
        game = self.game(fixture)
        self.install(game, 410)
        cells = weapprof_cells(game.snapshot()["WEAPPROF.2DA"])
        self.assertEqual((2, 2), (cells[("DRUID", 92)], cells[("DRUID", 105)]))
        self.assertEqual((2, 2), (cells[("SHAPESHIFTER", 92)], cells[("TOTEMIC_DRUID", 105)]))
        self.assertEqual(3, cells[("HIGHAXE", 92)])
        self.assertEqual(3, cells[("FD_KIT", 104)])
        self.assertEqual(0, cells[("DRUID", 104)])
        self.assertEqual(0, cells[("DRUID", 6)])
        self.assert_410(game, fixture)

    def test_410_kitlist_column_order_is_not_assumed(self):
        fixture = Fixture(shuffled_kitlist=True)
        game = self.game(fixture)
        self.install(game, 410)
        self.assert_410(game, fixture)

    def test_410_existing_grant_on_an_equivalent_row_is_not_duplicated(self):
        splprot = SPLPROT_TEXT + "8_CLASS_ALIAS 0x10d -1 1\n"
        effects = grant_effects(extra=(class_grant(DRUID, 92, row=8),))
        fixture = Fixture(splprot=splprot, c0prcl=c0prcl(effects))
        game = self.game(fixture)
        self.install(game, 410)
        after = SplFile.from_bytes(game.snapshot()["C0PR#CL.SPL"])
        grants = [(e.parameter1, e.resource) for e in after.abilities[0].effects
                  if e.opcode == 326 and e.parameter1 in (DRUID, FIGHTER_DRUID)]
        self.assertEqual(1, grants.count((DRUID, "C0PR#92")))
        wanted = expected_grants(effects, tuple((v, CLASS_ROW, p, (CLASS_ROW, 8)) for v, _, p, _ in DRUID_GRANTS),
                                 class_rows=(CLASS_ROW, 8))
        self.assertEqual([e.canonical() for e in wanted], [e.canonical() for e in after.abilities[0].effects])

    def test_410_every_grant_header_and_a_trailing_casting_slice(self):
        spell = c0prcl_multi()
        fixture = Fixture(c0prcl=spell)
        game = self.game(fixture)
        self.install(game, 410)
        self.assertEqual(expected_multi(spell), game.snapshot()["C0PR#CL.SPL"])

    def test_410_header_without_class_grants_gets_the_plain_grant_shape(self):
        effects = [fx(321, resource="C0PR#92"), fx(326, 0, 4, "C0PR#92"), fx(326, 0, 0, "C0PR#KG")]
        fixture = Fixture(c0prcl=c0prcl(effects))
        game = self.game(fixture)
        self.install(game, 410)
        after = SplFile.from_bytes(game.snapshot()["C0PR#CL.SPL"]).abilities[0].effects
        new = [e for e in after if e.parameter1 in (DRUID, FIGHTER_DRUID)]
        self.assertEqual(5, len(new))
        for effect in new:
            self.assertEqual((326, 2, 0, CLASS_ROW, 0, 0, 100, 0), (
                effect.opcode, effect.target, effect.power, effect.parameter2, effect.timing,
                effect.special, effect.probability1, effect.dice_number))
        self.assertEqual("C0PR#KG", after[-1].resource)

    def test_410_other_languages_and_finished_texts_keep_their_descriptions(self):
        texts = list(TEXTS)
        texts[1] = "DRUIDE: Darf nur folgende Waffen benutzen: Krummsäbel, Dolch."
        texts[2] = FD_TEXT.replace("Druid's ethos.", "Druid's ethos and long bows.")
        texts[4] = DRUID_TEXT.replace("dart, sling.", "dart, sling, battleaxe.")
        texts[5] = texts[2]
        fixture = Fixture(texts=texts)
        game = self.game(fixture)
        self.install(game, 410)
        after = game.snapshot()
        new = strings(game.tlk)
        self.assertEqual(1, self.table_ref(after["CLASTEXT.2DA"], "DRUID"))
        self.assertEqual(2, self.table_ref(after["CLASTEXT.2DA"], "FIGHTER_DRUID"))
        self.assertEqual(5, self.table_ref(after["BGCLATXT.2DA"], "FIGHTER_DRUID"))
        ref = self.table_ref(after["BGCLATXT.2DA"], "DRUID")
        self.assertEqual(texts[4].replace("battleaxe.", "battleaxe, short bow."), new[ref])

    # -- 411 ------------------------------------------------------------------

    def assert_411(self, game, *, row=KIT_ROW, splprot_changed=False):
        after = game.snapshot()
        before = game.original
        self.assertEqual(expected_411_cells(weapprof_cells(before["WEAPPROF.2DA"])),
                         weapprof_cells(after["WEAPPROF.2DA"]))
        spell = SplFile.from_bytes(before["C0PR#CL.SPL"])
        effects = expected_grants(spell.abilities[0].effects, ((ALAGHOR_KIT, row, 92, (row,)),), special=0)
        wanted = dataclasses.replace(spell, abilities=(dataclasses.replace(spell.abilities[0], effects=tuple(effects)),))
        self.assertEqual(wanted.to_bytes(), after["C0PR#CL.SPL"])
        texts = strings(game.tlk)
        self.assertEqual(game.original_texts, texts[:len(game.original_texts)])
        ref = self.table_ref(after["KITLIST.2DA"], "LK_ALAGHOR", column="HELP", match_column="ROWNAME")
        self.assertEqual(new_alaghor_text(game.original_texts[3]), texts[ref])
        hook = {"CBRKPKIT.2DA", "M_CBRKP.LUA"}
        changed = {"WEAPPROF.2DA", "C0PR#CL.SPL", "KITLIST.2DA", *hook} | ({"SPLPROT.2DA"} if splprot_changed else set())
        for name in set(before) - changed:
            self.assertEqual(before[name], after[name], name)
        self.assertEqual(set(before) | hook, set(after))
        self.assert_hook_installed(game, after)

    def assert_hook_installed(self, game, after):
        """The runtime, its pattern and one FIGHTER_CLERIC/LK_ALAGHOR registration
        after any registrations other components made."""
        before = game.original
        self.assertEqual(KP_RUNTIME.read_bytes(), after["M_CBRKP.LUA"])
        self.assertEqual(KP_DB.read_bytes(), pattern_db(game).read_bytes())
        registry = TwoDA.from_text(after["CBRKPKIT.2DA"].decode())
        self.assertEqual(("CLASS", "KIT"), registry.columns)
        earlier = TwoDA.from_text(before["CBRKPKIT.2DA"].decode()).rows if "CBRKPKIT.2DA" in before else ()
        ours = registration(ALAGHOR_REGISTRATION[1])
        added = () if any(registration(values) == ours for _, values in earlier) else (ALAGHOR_REGISTRATION,)
        self.assertEqual((*earlier, *added), registry.rows)

    def assert_uninstalled(self, game, *components):
        code, output = run(game, *components, uninstall=True)
        self.assertEqual(0, code, output)
        self.assertEqual(game.original, game.snapshot())
        self.assertFalse(pattern_db(game).exists())

    def test_411_alaghor_trains_cleric_weapons_and_axes_exact_and_uninstall(self):
        game = self.game()
        self.install(game, 411)
        self.assert_411(game)
        cells = weapprof_cells(game.snapshot()["WEAPPROF.2DA"])
        self.assertEqual({p: 2 for p in (*CLERIC_WEAPONS, 92)},
                         {p: cells[("LK_ALAGHOR", p)] for p in WEAPONS if cells[("LK_ALAGHOR", p)]})
        # The fighting styles and the other rows: the fighter/cleric limits he has without the hook.
        self.assertEqual([2, 2, 2, 3, 0], [cells[("LK_ALAGHOR", p)] for p in (*STYLES, 116)])
        self.assert_uninstalled(game, 411)

    def test_411_fighter_clerics_training_every_weapon_do_not_widen_alaghor(self):
        values = base_columns()
        for proficiency in WEAPONS:
            values["FIGHTER_CLERIC"][proficiency] = 2
        values["FIGHTER_CLERIC"][113] = 1  # another mod's style limits are followed, not constants
        values["FIGHTER_CLERIC"][116] = 2
        game = self.game(Fixture(values=values))
        self.install(game, 411)
        self.assert_411(game)
        cells = weapprof_cells(game.snapshot()["WEAPPROF.2DA"])
        self.assertEqual(sorted((*CLERIC_WEAPONS, 92)),
                         sorted(p for p in WEAPONS if cells[("LK_ALAGHOR", p)]))
        self.assertEqual([2, 2, 1, 3, 2], [cells[("LK_ALAGHOR", p)] for p in (*STYLES, 116)])

    def test_411_rerun_on_its_own_output_changes_nothing(self):
        first = self.game()
        self.install(first, 411)
        installed = first.snapshot()
        texts = strings(first.tlk)
        second = self.game(resources=installed, texts=texts)
        pattern_db(second).write_bytes(pattern_db(first).read_bytes())
        output = self.install(second, 411)
        self.assertEqual(second.original, second.snapshot())
        self.assertEqual(texts, strings(second.tlk))
        self.assertIn("WEAPPROF cells changed: 0", output)

    def test_411_keeps_other_registrations_and_restores_them_on_uninstall(self):
        resources = Fixture().resources()
        resources["CBRKPKIT.2DA"] = b"2DA V1.0\r\n****\r\n          CLASS KIT\r\nOTHER_MOD 14 0x4010\r\n"
        game = self.game(resources=resources)
        self.install(game, 411)
        self.assert_411(game)
        self.assertEqual(2, len(TwoDA.from_text(game.snapshot()["CBRKPKIT.2DA"].decode()).rows))
        self.assert_uninstalled(game, 411)

    def test_411_refuses_an_unsupported_registry(self):
        for name, registry in (
            ("third column", b"2DA V1.0\n****\n   CLASS KIT TABLE\nOTHER 14 16400 X\n"),
            ("other columns", b"2DA V1.0\n****\n   KIT CLASS\n"),
            ("text cell", b"2DA V1.0\n****\n   CLASS KIT\nOTHER FIGHTER 16400\n"),
        ):
            with self.subTest(name):
                resources = Fixture().resources()
                resources["CBRKPKIT.2DA"] = registry
                game = self.game(resources=resources)
                self.failed_unchanged(game, 411, "CBRKPKIT.2DA")
                self.assertFalse(pattern_db(game).exists())

    def test_411_requires_eeex_and_its_conditional_jump_hooks(self):
        for flavour in ("none", "old"):
            with self.subTest(flavour):
                game = self.game(Fixture(eeex=flavour))
                self.skipped_unchanged(game, 411)
                self.assertFalse(pattern_db(game).exists())

    def test_411_without_a_game_executable_fails_unchanged(self):
        self.failed_unchanged(self.game(exes={}), 411, "could not find the game's executable")

    def test_411_other_displacements_baldurii_and_a_patched_decoy(self):
        exe = kit_lookup_executable(fill=0xA5, hooked_sites=1)
        game = self.game(exes={"BaldurII.exe": exe})
        output = self.install(game, 411)
        self.assert_411(game)
        self.assertIn("compatible kit-proficiency lookup found in BaldurII.exe at file offset 1088", output)

    def test_411_refuses_executables_without_exactly_one_compatible_lookup(self):
        for name, exe, message in (
            ("missing", kit_lookup_executable(text_sites=0), "found 0"),
            ("already hooked", kit_lookup_executable(text_sites=0, hooked_sites=1), "found 0"),
            ("ambiguous", kit_lookup_executable(text_sites=2), "found 2"),
            ("not code", kit_lookup_executable(text_sites=0, data_sites=1), "outside an executable section"),
            ("32-bit", kit_lookup_executable(magic=0x10B), "not a supported 64-bit PE image"),
        ):
            with self.subTest(name):
                game = self.game(exes={"Baldur.exe": exe})
                self.failed_unchanged(game, 411, message)
                self.assertFalse(pattern_db(game).exists())

    def test_411_appends_a_kit_row_when_splprot_has_none(self):
        splprot = SPLPROT_TEXT.replace("3_KIT=n 152 -1 1\n", "3_UNUSED 60 1 1\n")
        game = self.game(Fixture(splprot=splprot))
        self.install(game, 411)
        rows = TwoDA.from_text(game.snapshot()["SPLPROT.2DA"].decode()).rows
        self.assertEqual(("CBR_CWA_KIT_EQ", ("152", "-1", "1")), rows[-1])
        self.assert_411(game, row=len(rows) - 1, splprot_changed=True)

    def test_411_requires_artisans_permission_system(self):
        self.skipped_unchanged(self.game(Fixture(kitpack=False)), 411)

    def test_411_skips_without_the_kit(self):
        resources = Fixture().resources()
        resources["KIT.IDS"] = b"IDS V1.0\n0x4000 TRUECLASS\n"
        self.skipped_unchanged(self.game(resources=resources), 411)

    def test_411_refuses_a_shared_column(self):
        kits = BASE_KITS + (Kit("ALAGHOR_TWIN", CLERIC, "LK_ALAGHOR"),)
        self.failed_unchanged(self.game(Fixture(kits=kits)), 411, "shares its WEAPPROF column with ALAGHOR_TWIN")

    def test_410_and_411_together_and_reverse_uninstall(self):
        game = self.game()
        self.install(game, 410, 411)
        after = game.snapshot()
        cells = weapprof_cells(after["WEAPPROF.2DA"])
        self.assertEqual(expected_411_cells(expected_410_cells(weapprof_cells(game.original["WEAPPROF.2DA"]))),
                         cells)
        effects = SplFile.from_bytes(after["C0PR#CL.SPL"]).abilities[0].effects
        self.assertEqual("C0PR#KG", effects[-1].resource)
        kit_grants = [e for e in effects if e.parameter1 == ALAGHOR_KIT]
        self.assertEqual([(326, KIT_ROW, "C0PR#92", 0)],
                         [(e.opcode, e.parameter2, e.resource, e.special) for e in kit_grants])
        self.assert_hook_installed(game, after)
        self.assert_uninstalled(game, 411, 410)


# ---------------------------------------------------------------------------
# Multi-header C0PR#CL with the casting slice after the ability slices
# ---------------------------------------------------------------------------

MULTI_HEADERS = (
    (1, grant_effects()),
    (5, [fx(139, 1), fx(206, resource="NOGRANTS")]),        # no weapon grants: untouched
    (10, grant_effects(extra=(class_grant(DRUID, 105),))),  # already grants druids short bows
)
MULTI_CASTING = (fx(139, 2, target=1),)


def c0prcl_multi():
    """Header slices first, casting slice last, so insertions must move it."""
    header = bytearray(0x72)
    header[:8] = b"SPL V1  "
    abilities, effects = bytearray(), []
    for level, slice_effects in MULTI_HEADERS:
        raw = bytearray(0x28)
        struct.pack_into("<H", raw, 0x10, level)
        struct.pack_into("<HH", raw, 0x1E, len(slice_effects), len(effects))
        abilities += raw
        effects += slice_effects
    struct.pack_into("<IH", header, 0x64, 0x72, len(MULTI_HEADERS))
    struct.pack_into("<I", header, 0x6A, 0x72 + len(abilities))
    struct.pack_into("<HH", header, 0x6E, len(effects), len(MULTI_CASTING))
    effects += MULTI_CASTING
    return bytes(header) + bytes(abilities) + b"".join(e.to_bytes() for e in effects)


def expected_multi(raw):
    """Rebuild the same layout from per-header oracle results."""
    header = bytearray(raw[:0x72])
    abilities, effects = bytearray(), []
    for index, (level, slice_effects) in enumerate(MULTI_HEADERS):
        if any(is_weapon_record(e) for e in slice_effects):
            slice_effects = expected_grants(slice_effects, DRUID_GRANTS)
        original = raw[0x72 + index * 0x28:0x72 + (index + 1) * 0x28]
        ability = bytearray(original)
        struct.pack_into("<HH", ability, 0x1E, len(slice_effects), len(effects))
        abilities += ability
        effects += slice_effects
    struct.pack_into("<HH", header, 0x6E, len(effects), len(MULTI_CASTING))
    effects += MULTI_CASTING
    return bytes(header) + bytes(abilities) + b"".join(e.to_bytes() for e in effects)


if __name__ == "__main__":
    unittest.main()
