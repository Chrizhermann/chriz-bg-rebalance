"""Public SR antimagic installers on disposable games, never a live install.

Resources and TLKs are synthetic except the captured SR shield helpers;
dynamic parent slots and child names ensure
the installer discovers the effective payload instead of assuming SR suffixes.
Uninstall exercises only this module's isolated fixtures. No engine claim follows.
"""

from __future__ import annotations

import dataclasses
import hashlib
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

from tests.ie_formats import ItmAbility, ItmFile, SplAbility, SplEffect, SplFile
from tests.test_emotion_hope_courage_installer import _write_key_and_bif
from tests.test_sr_hardiness import _strings, _tlk, _tree


ROOT = Path(__file__).resolve().parents[1]
WEIDU = ROOT / "weidu.exe"
SETUP = ROOT / "setup-chriz-bg-rebalance.tp2"
TAIL = ROOT / "live-patch/CBR_SR_ANTIMAGIC"
PM, SS = "SPWI643", "SPWI947"
PM_BODY, SS_BODY = "ZPMBODY", "ZSSBODY"
PM_SHIELD, SS_SHIELD = "ZPMSHLD", "ZSSSHLD"
PM_NAME, SS_NAME = "Synthetic Pierce", "Synthetic Strike"
# Spell Revisions shares one description strref between a spell, its hidden
# payload spells and its scroll. OLD_TEXT is long enough to be compared by text.
OLD_TEXT = ("Shared original description of the synthetic anti-magic spell, as Spell "
            "Revisions shares it between a spell, its hidden payload spells and its scroll.")
OWN_TEXT = "House rule: this scroll is described in the owner's own words, not the spell's."
UNRELATED_TEXT = "Unrelated text."
PM_OLD_SPECIAL = ("Lowers target's Magic Resistance by 20% for 2  turns and removes one "
                  "spell protection from target")
SS_OLD_SPECIAL = "Dispels all specific and combat protections on target"
BREACH_ENTRY = ("\u2013 Breach\n  Special: Dispels all specific and combat protections on target\n"
                "  Range: 40 ft.\n  Area of Effect: 1 creature\n\n")


def _wand_text(name: str, special: str) -> str:
    return ("Ironically, these wands are both prized and hated by wizards.\n\nSTATISTICS:\n\n"
            "Charge abilities:\n" + BREACH_ENTRY + f"\u2013 {name}\n  Special: {special}\n"
            "  Range: 40 ft.\n  Area of Effect: 1 creature\n\nRequires:\n 9 Intelligence\n\nWeight: 1")


ORIGINAL_STRINGS = (
    "Synthetic spell",                       # 0
    OLD_TEXT,                                # 1: shared by the spells and scrolls
    UNRELATED_TEXT,                          # 2
    OWN_TEXT,                                # 3
    _wand_text(PM_NAME, PM_OLD_SPECIAL),     # 4: a Pierce Magic wand
    OLD_TEXT,                                # 5: a copy of 1 under another strref
    "A wand of unspecified purpose.",        # 6
    PM_NAME,                                 # 7
    SS_NAME,                                 # 8
    _wand_text(SS_NAME, SS_OLD_SPECIAL),     # 9: a Spellstrike wand
    _wand_text(PM_NAME, "Says nothing about the old rules."),  # 10: unrecognizable line
)
PM_SIBLING, SS_SIBLING = "ZPMWNDS", "ZSSWNDS"          # SCS-style wand spells
PM_SCROLL, SS_SCROLL = "SCRL7L", "SCRL9M"
OWN_SCROLL, COPY_SCROLL = "ZOWNSCR", "ZCOPYSC"
PM_WAND, SS_WAND, ODD_WAND, ODD2_WAND = "WAND18", "ZSSWAND", "ZODDWND", "ZODD2WN"
INLINE_ITEM, UNRELATED_ITEM = "ZINLINE", "ZUNREL"
SYNTHETIC_MR_STAT = 37


def _spell(effects: tuple[SplEffect, ...], *, level: int = 6, secondary: int = 1,
           headers: int = 2, casting: bool = True) -> bytes:
    header = bytearray(0x72)
    struct.pack_into("<H", header, 0x1C, 1)
    struct.pack_into("<I", header, 0x18, 0x01004000)  # opaque flags incl. invisibility behavior
    struct.pack_into("<I", header, 0x34, level)
    struct.pack_into("<I", header, 0x50, 1)
    header[0x25], header[0x27] = 1, secondary
    abilities = []
    for index in range(headers):
        raw = bytearray(0x28)
        raw[0], raw[0x12] = 1, 6 if level == 6 else 5
        raw[0x16:0x1C] = bytes((32, 17, 21, 8, 9, 10))
        abilities.append(SplAbility(required_level=1 if index == 0 else 20,
                                    target=2, projectile=129, effects=effects,
                                    icon="ANTIMAG", raw=bytes(raw)))
    hooks = (SplEffect(opcode=146, target=1, power=0, timing=1, resource="DWHOOK"),) if casting else ()
    return SplFile(tuple(abilities), casting_effects=hooks, header_raw=bytes(header)).to_bytes()


def _effect(opcode: int, p1: int = 0, p2: int = 0, *, timing: int = 1,
            duration: int = 0, resource: str = "") -> SplEffect:
    return SplEffect(opcode=opcode, target=2, power=0, parameter1=p1, parameter2=p2,
                     timing=timing, duration=duration, resist_dispel=2, resource=resource)


def _payload(spellstrike: bool) -> bytes:
    effects = [_effect(221 if spellstrike else 230, 9 if spellstrike else 8, 1)]
    if spellstrike:
        effects += [_effect(60, amount, mode, timing=0, duration=duration)
                    for amount, duration in ((100, 6), (50, 12)) for mode in (0, 1)]
        effects += [_effect(221, 9, 23)]  # install-specific Dispelling Screen category
    else:
        effects += [_effect(166, 0, 1, timing=0, duration=12),
                    _effect(142, 0, 106, timing=0, duration=12),
                    _effect(174, timing=4, duration=12, resource="EFF_E06")]
    effects += [_effect(142, 0, 83, timing=0, duration=12),
                _effect(328, 0, 901 if spellstrike else 902, timing=0, duration=12),
                _effect(139, 2)]
    return _spell(tuple(effects), level=9 if spellstrike else 6)


def _wrapper(body: str, shield: str, *, spellstrike: bool) -> bytes:
    return _spell((_effect(146, resource=body), _effect(146, resource=shield),
                   _effect(139, 2)), level=9 if spellstrike else 6)


def _named(spell: bytes, name_strref: int) -> bytes:
    data = bytearray(spell)
    struct.pack_into("<I", data, 0x08, name_strref)
    return bytes(data)


def _item(*abilities: tuple[SplEffect, ...], identified: int, unidentified: int = 2) -> bytes:
    return ItmFile(abilities=tuple(ItmAbility(effects=effects) for effects in abilities),
                   unidentified_name=0, identified_name=0,
                   unidentified_description=unidentified, identified_description=identified).to_bytes()


def _cast(resource: str, opcode: int = 146) -> SplEffect:
    return SplEffect(opcode=opcode, target=2, timing=1, resource=resource)


def _tra_string(number: int) -> str:
    text = (ROOT / "chriz-bg-rebalance/languages/english/setup.tra").read_text(encoding="utf-8")
    match = re.search(rf"(?ms)^@{number}\s*=\s*~(.*?)~", text)
    assert match, number
    return match.group(1).replace("\r\n", "\n")


def _copy_tail(root: Path) -> str:
    package = root / "CBR_SR_ANTIMAGIC"
    shutil.copytree(TAIL, package)
    # Source templates share precisely these canonical production libraries.
    (package / "lib").mkdir(exist_ok=True)
    for library in ("sr_antimagic.tpa", "sr_spellstrike.tpa"):
        shutil.copy2(ROOT / "chriz-bg-rebalance/lib" / library, package / "lib" / library)
    (package / "languages/english").mkdir(parents=True, exist_ok=True)
    shutil.copy2(ROOT / "chriz-bg-rebalance/languages/english/setup.tra",
                 package / "languages/english/setup.tra")
    (package / "lua").mkdir(exist_ok=True)
    shutil.copy2(ROOT / "chriz-bg-rebalance/lua/M_CBRPM.lua", package / "lua/M_CBRPM.lua")
    return "CBR_SR_ANTIMAGIC/setup-cbr_sr_antimagic.tp2"


class AntimagicGame:
    def __init__(self, root: Path, *, direct: bool = False, sr_component: int | None = 0,
                 game: str = "bg2ee", tail: bool = False, changed: dict[str, bytes | None] | None = None,
                 symbols: bool = True, eeex: bool = True, archive: Path | None = None,
                 strings: tuple[str, ...] | None = None):
        root.mkdir()
        self.strings = strings or ORIGINAL_STRINGS
        self.root, self.direct = root, direct
        self.override = root / "override"
        self.override.mkdir()
        if eeex:
            (self.override / "M___EEex.lua").write_bytes(b"-- synthetic EEex marker\n")
        (self.override / "SPLPROT.2DA").write_bytes(b"2DA V1.0\n0\nSTAT VALUE RELATION\n0 0 0 0\n")
        self.before = {
            f"{PM}.SPL": _payload(False) if direct else _wrapper(PM_BODY, PM_SHIELD, spellstrike=False),
            f"{SS}.SPL": _payload(True) if direct else _wrapper(SS_BODY, SS_SHIELD, spellstrike=True),
            f"{PM_BODY}.SPL": _payload(False), f"{SS_BODY}.SPL": _payload(True),
            f"{PM_SHIELD}.SPL": (ROOT / "tests/fixtures/sr_antimagic/SPWI608C.SPL").read_bytes(),
            f"{SS_SHIELD}.SPL": (ROOT / "tests/fixtures/sr_antimagic/SPWI903C.SPL").read_bytes(),
            "ZSHIELD.SPL": _spell((_effect(206, resource=PM_BODY), _effect(206, resource=SS_BODY))),
            "ZLOWER.SPL": _spell((_effect(166, -40, 0, timing=0, duration=120),), level=5),
            "ZPIERCE.SPL": _spell((_effect(230, 9, 1), _effect(221, 9, 7), _effect(221, 9, 23)), level=8),
            "SPWI608.SPL": _payload(False), "SPWI903.SPL": _payload(True),
            # Sibling spells that reach the payload (SCS's wand spell; share the old text).
            f"{PM_SIBLING}.SPL": _spell((_effect(146, resource=PM_BODY), _effect(146, resource=PM_SHIELD))),
            f"{SS_SIBLING}.SPL": _spell((_effect(146, resource=SS_BODY), _effect(146, resource=SS_SHIELD)), level=9),
            # A scroll teaches and casts the parent; its text is the spell's text.
            f"{PM_SCROLL}.ITM": _item((_cast(PM),), (_cast(PM, 147),), identified=1),
            f"{SS_SCROLL}.ITM": _item((_cast(SS),), (_cast(SS, 147),), identified=1),
            f"{OWN_SCROLL}.ITM": _item((_cast(PM, 147),), identified=3),
            f"{COPY_SCROLL}.ITM": _item((_cast(PM),), identified=5),
            # Wands reach the payload through the sibling spell; their text is their own.
            f"{PM_WAND}.ITM": _item((_cast("ZUNRELS"),), (_cast(PM_SIBLING),), identified=4),
            f"{SS_WAND}.ITM": _item((_cast(SS_SIBLING),), identified=9),
            f"{ODD_WAND}.ITM": _item((_cast(PM_SIBLING),), identified=6),
            f"{ODD2_WAND}.ITM": _item((_cast(PM_SIBLING),), identified=10),
            # Inline effects of their own are nobody's business here.
            f"{INLINE_ITEM}.ITM": _item((_effect(166, -20, 0, timing=0, duration=120),), identified=4),
            f"{UNRELATED_ITEM}.ITM": _item((_effect(12, 1, 0),), identified=2),
            "ZUNRELS.SPL": _spell((_effect(12, 1, 0),)),
        }
        self.before[f"{PM}.SPL"] = _named(self.before[f"{PM}.SPL"], 7)
        self.before[f"{SS}.SPL"] = _named(self.before[f"{SS}.SPL"], 8)
        for name, data in (changed or {}).items():
            if data is None:
                self.before.pop(name.upper(), None)
            else:
                self.before[name.upper()] = data
        ids = "IDS V1.0\n"
        if symbols:
            ids += "2643 WIZARD_PIERCE_MAGIC\n2947 WIZARD_SPELL_STRIKE\n"
        self.ids = ids.encode("ascii")
        resources = [("SPELL", "IDS", self.ids),
                     ("STATS", "IDS", f"IDS V1.0\n{SYNTHETIC_MR_STAT} RESISTMAGIC\n".encode("ascii")),
                     ("KIT", "IDS", b"IDS V1.0\n")]
        resources.append(("OH1000" if game == "bgee" else "OH6000", "ARE", b"synthetic game marker"))
        if game == "eet":
            (self.override / "EET.FLAG").write_bytes(b"synthetic EET marker")
        # Mix BIFF-only parents/payloads and loose payloads so both publication
        # paths and byte-exact removal/restoration are exercised.
        for name, data in self.before.items():
            if name in (f"{PM}.SPL", f"{PM_BODY}.SPL", f"{PM_SCROLL}.ITM", f"{SS_SCROLL}.ITM",
                        f"{ODD_WAND}.ITM", f"{UNRELATED_ITEM}.ITM"):
                resources.append((name[:-4], name[-3:], data))
            else:
                (self.override / name).write_bytes(data)
        self.bif = _write_key_and_bif(root, tuple(resources))
        self.tlk = root / "lang/en_us/dialog.tlk"
        self.tlk.parent.mkdir(parents=True)
        self.tlk.write_bytes(_tlk(self.strings))
        (root / "dialog.tlk").write_bytes(_tlk(self.strings))
        (root / "weidu.log").write_text("", encoding="ascii")
        if sr_component is not None:
            (root / "weidu.log").write_text(
                f"~SPELL_REV/SETUP-SPELL_REV.TP2~ #0 #{sr_component} // synthetic SR\n", encoding="ascii")
        self.weidu = WEIDU
        if archive is not None:
            # The distribution test starts with no unpacked mod/source tree.
            # Both the executable and every installer dependency come from ZIP.
            with zipfile.ZipFile(archive) as bundle:
                for name in bundle.namelist():
                    if not (root / name).resolve().is_relative_to(root.resolve()):
                        raise ValueError(f"archive member escapes fixture: {name}")
                bundle.extractall(root)
            self.setup = "CBR_SR_ANTIMAGIC/setup-cbr_sr_antimagic.tp2"
            self.weidu = root / "Setup-cbr_sr_antimagic.exe"
        elif tail:
            self.setup = _copy_tail(root)
        else:
            shutil.copy2(SETUP, root / SETUP.name)
            shutil.copytree(ROOT / "chriz-bg-rebalance", root / "chriz-bg-rebalance")
            self.setup = SETUP.name
        self.original_override = _tree(self.override)
        self.stable = {str(path.relative_to(root)): path.read_bytes()
                       for path in (root / "chitin.key", self.bif, root / "dialog.tlk")}

    def run(self, *components: int, uninstall: bool = False):
        return subprocess.run([str(self.weidu), self.setup, "--game", str(self.root),
                               "--force-uninstall-list" if uninstall else "--force-install-list",
                               *map(str, components), "--language", "0", "--use-lang", "en_us",
                               "--no-exit-pause", "--quick-log"],
                              cwd=self.root, capture_output=True, text=True, timeout=90, check=False)

    def effective(self, resref: str, extension: str = "SPL") -> bytes:
        path = self.override / f"{resref}.{extension}"
        return path.read_bytes() if path.exists() else self.before[f"{resref}.{extension}"]

    def strref(self, resref: str, extension: str = "SPL", *, unidentified: bool = False) -> int:
        data = self.effective(resref, extension)
        offset = 0x50 if extension == "SPL" or unidentified else 0x54
        return struct.unpack_from("<i", data, offset)[0]

    def text(self, resref: str, extension: str = "SPL") -> str:
        return _strings(self.tlk)[self.strref(resref, extension)]

    def log(self) -> str:
        path = self.root / "weidu.log"
        return "\n".join(line for line in path.read_text(errors="replace").splitlines()
                         if not line.lstrip().startswith("//")) if path.exists() else ""


class AntimagicInstallerTests(unittest.TestCase):
    def make_game(self, **kwargs) -> AntimagicGame:
        holder = tempfile.TemporaryDirectory(prefix="cbr-antimagic-installer-")
        self.addCleanup(holder.cleanup)
        return AntimagicGame(Path(holder.name) / "game", **kwargs)

    def build_packages(self) -> tuple[Path, str]:
        holder = tempfile.TemporaryDirectory(prefix="cbr-antimagic-packages-")
        self.addCleanup(holder.cleanup)
        output = Path(holder.name)
        result = subprocess.run([sys.executable, str(ROOT / "tools/package_sr_antimagic.py"),
                                 "--output", str(output)],
                                cwd=ROOT, capture_output=True, text=True, timeout=90, check=False)
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        match = re.search(r"VERSION ~([^~]+)~", SETUP.read_text())
        self.assertIsNotNone(match)
        return output, match.group(1)

    def test_packager_builds_three_version_matched_archives_with_canonical_tail(self):
        output, version = self.build_packages()
        expected = {f"{name}-{version}-windows.zip" for name in
                    ("chriz-bg-rebalance", "CBR_SR_HARDINESS", "CBR_SR_ANTIMAGIC")}
        self.assertEqual(expected, {path.name for path in output.glob("*.zip")})
        self.assertEqual({name + ".sha256" for name in expected},
                         {path.name for path in output.glob("*.sha256")})
        for name in expected:
            archive = output / name
            digest = hashlib.sha256(archive.read_bytes()).hexdigest()
            # Exact bytes: sha256sum -c rejects the CRLF that text mode writes on Windows.
            self.assertEqual(f"{digest}  {name}\n".encode(), archive.with_suffix(".zip.sha256").read_bytes())
        anti = output / f"CBR_SR_ANTIMAGIC-{version}-windows.zip"
        with zipfile.ZipFile(anti) as bundle:
            # An exact publication allowlist also proves no bulk SR files,
            # research captures, saves or unrelated mod modules are carried.
            self.assertEqual({"LICENSE", "WEIDU-LICENSE.txt", "Setup-cbr_sr_antimagic.exe",
                              "CBR_SR_ANTIMAGIC/setup-cbr_sr_antimagic.tp2",
                              "CBR_SR_ANTIMAGIC/README.md",
                              "CBR_SR_ANTIMAGIC/lib/sr_antimagic.tpa",
                              "CBR_SR_ANTIMAGIC/lib/sr_spellstrike.tpa",
                              "CBR_SR_ANTIMAGIC/lua/M_CBRPM.lua",
                              "CBR_SR_ANTIMAGIC/languages/english/setup.tra"}, set(bundle.namelist()))
            for relative in ("lib/sr_antimagic.tpa", "lib/sr_spellstrike.tpa", "lua/M_CBRPM.lua",
                             "languages/english/setup.tra"):
                self.assertEqual((ROOT / "chriz-bg-rebalance" / relative).read_bytes(),
                                 bundle.read(f"CBR_SR_ANTIMAGIC/{relative}"))
            self.assertEqual(WEIDU.read_bytes(), bundle.read("Setup-cbr_sr_antimagic.exe"))
            tail_source = bundle.read("CBR_SR_ANTIMAGIC/setup-cbr_sr_antimagic.tp2")
            self.assertEqual((TAIL / "setup-cbr_sr_antimagic.tp2").read_bytes(), tail_source)
            self.assertIn(f"VERSION ~{version}~", tail_source.decode("utf-8"))

    def test_extracted_antimagic_archive_installs_both_components_without_source_tree(self):
        output, version = self.build_packages()
        game = self.make_game(archive=output / f"CBR_SR_ANTIMAGIC-{version}-windows.zip")
        self.assertFalse((game.root / "chriz-bg-rebalance").exists())
        self.assertFalse((game.root / SETUP.name).exists())
        self.assertFalse((game.root / "spell_rev").exists())
        result = game.run(210, 211)
        for component in (210, 211):
            self.assert_installed(game, result, component)
        self.assert_pierce_magic_payload(game)
        self.assert_spellstrike_payload(game)
        for parent, component in ((PM, 210), (SS, 211)):
            self.assert_description_and_wrapper(game, parent, component=component)

    def assert_stable(self, game: AntimagicGame):
        for relative, payload in game.stable.items():
            self.assertEqual(payload, (game.root / relative).read_bytes(), relative)
        self.assertEqual(list(game.strings), _strings(game.tlk)[:len(game.strings)])
        for resource in (PM_SHIELD, SS_SHIELD, "ZSHIELD", "ZLOWER", "ZPIERCE", "SPWI608", "SPWI903"):
            self.assertEqual(game.before[f"{resource}.SPL"], game.effective(resource), resource)
        self.assertEqual(game.original_override["SPLPROT.2DA"], (game.override / "SPLPROT.2DA").read_bytes())
        if "M___EEEX.LUA" in game.original_override:
            self.assertEqual(game.original_override["M___EEEX.LUA"], (game.override / "M___EEex.lua").read_bytes())

    def assert_installed(self, game, result, component):
        transcript = result.stdout + result.stderr
        self.assertEqual(0, result.returncode, transcript)
        self.assertIn("SUCCESSFULLY INSTALLED", transcript)
        self.assertNotIn("INSTALLED WITH WARNINGS", transcript)
        self.assertRegex(game.log(), rf"(?m)#0\s+#{component}\b")
        self.assert_stable(game)

    def assert_rejected(self, game, result, component, *, skipped=False):
        transcript = result.stdout + result.stderr
        self.assertIn("SKIPPING" if skipped else "NOT INSTALLED DUE TO ERRORS", transcript)
        self.assertNotRegex(game.log(), rf"(?m)#0\s+#{component}\b")
        self.assertEqual(game.original_override, _tree(game.override))
        self.assertEqual(_tlk(game.strings), game.tlk.read_bytes())
        self.assert_stable(game)

    def assert_description_and_wrapper(self, game, parent, *, component):
        original, output = game.before[f"{parent}.SPL"], game.effective(parent)
        old_ref = SplFile.from_bytes(original).description_strref
        new_ref = SplFile.from_bytes(output).description_strref
        self.assertNotEqual(old_ref, new_ref)
        description = _strings(game.tlk)[new_ref].lower()
        if component == 211:
            self.assertIn("15%", description)
            self.assertNotIn("100%", description)
            self.assertNotIn("50%", description)
        else:
            self.assertIn("10", description)
            self.assertIn("40", description)
            self.assertTrue("30 seconds" in description or "5 rounds" in description, description)
        self.assertIn("invisible", description)
        if not game.direct:
            expected = bytearray(original)
            struct.pack_into("<I", expected, 0x50, new_ref)
            self.assertEqual(bytes(expected), output, "wrapper mechanics or Spell Shield delivery changed")

    def assert_spellstrike_payload(self, game):
        resource = SS if game.direct else SS_BODY
        old = SplFile.from_bytes(game.before[f"{resource}.SPL"])
        new = SplFile.from_bytes(game.effective(resource))
        old_header, new_header = bytearray(old.header_raw), bytearray(new.header_raw)
        if game.direct:
            old_header[0x50:0x54] = new_header[0x50:0x54]
        self.assertEqual(old_header, new_header)
        self.assertEqual([fx.to_bytes() for fx in old.casting_effects], [fx.to_bytes() for fx in new.casting_effects])
        self.assertEqual(len(old.abilities), len(new.abilities))
        for original, output in zip(old.abilities, new.abilities):
            old_raw, new_raw = bytearray(original.raw), bytearray(output.raw)
            old_raw[0x1E:0x22] = new_raw[0x1E:0x22]
            self.assertEqual(old_raw, new_raw)
            refresh = dataclasses.replace(_effect(321, 0, 2, resource=resource), timing=1)
            self.assertEqual(refresh.to_bytes(), output.effects[0].to_bytes())
            failure = [fx for fx in output.effects if fx.opcode == 60]
            self.assertEqual(2, len(failure))
            self.assertEqual({0, 1}, {fx.parameter2 for fx in failure})
            for fx in failure:
                self.assertEqual(_effect(60, 15, fx.parameter2, timing=0, duration=12).to_bytes(), fx.to_bytes())
            original_foreign = [fx.to_bytes() for fx in original.effects if fx.opcode != 60]
            output_foreign = [fx.to_bytes() for fx in output.effects[1:] if fx.opcode != 60]
            self.assertEqual(original_foreign, output_foreign)

    def assert_pierce_magic_payload(self, game):
        resource = PM if game.direct else PM_BODY
        old = SplFile.from_bytes(game.before[f"{resource}.SPL"])
        new = SplFile.from_bytes(game.effective(resource))
        old_header, new_header = bytearray(old.header_raw), bytearray(new.header_raw)
        if game.direct:
            old_header[0x50:0x54] = new_header[0x50:0x54]
        self.assertEqual(old_header, new_header)
        self.assertEqual([fx.to_bytes() for fx in old.casting_effects], [fx.to_bytes() for fx in new.casting_effects])
        self.assertEqual(len(old.abilities), len(new.abilities))
        for original, output in zip(old.abilities, new.abilities):
            old_raw, new_raw = bytearray(original.raw), bytearray(output.raw)
            old_raw[0x1E:0x22] = new_raw[0x1E:0x22]
            self.assertEqual(old_raw, new_raw)
            callback = [fx for fx in output.effects if fx.opcode == 402]
            self.assertEqual([_effect(402, resource="CBRPM").to_bytes()], [fx.to_bytes() for fx in callback])
            self.assertEqual(callback[0].to_bytes(), output.effects[0].to_bytes(),
                             "impact-time MR must be measured before protection stripping")
            self.assertFalse(any(fx.opcode == 166 for fx in output.effects))
            def old_owned(fx):
                return (fx.opcode == 166 or (fx.opcode == 142 and fx.parameter2 == 106)
                        or (fx.opcode == 174 and fx.resource == "EFF_E06"))
            self.assertEqual([fx.to_bytes() for fx in original.effects if not old_owned(fx)],
                             [fx.to_bytes() for fx in output.effects if fx.opcode != 402])
        template = (ROOT / "chriz-bg-rebalance/lua/M_CBRPM.lua").read_bytes()
        expected = template.replace(b"%CBR_PM_MR_STAT%", str(SYNTHETIC_MR_STAT).encode("ascii"))
        self.assertEqual(expected, (game.override / "M_CBRPM.lua").read_bytes())

    def test_pierce_magic_dynamic_payload_callback_and_private_runtime(self):
        game = self.make_game()
        self.assert_installed(game, game.run(210), 210)
        self.assert_pierce_magic_payload(game)
        self.assert_description_and_wrapper(game, PM, component=210)
        self.assertEqual(game.before[f"{SS}.SPL"], game.effective(SS))
        self.assertEqual(game.before[f"{SS_BODY}.SPL"], game.effective(SS_BODY))

    def test_pierce_magic_direct_sr_payload_without_child_wrapper(self):
        game = self.make_game(direct=True)
        self.assert_installed(game, game.run(210), 210)
        self.assert_pierce_magic_payload(game)
        self.assert_description_and_wrapper(game, PM, component=210)
        self.assertEqual(game.before[f"{PM_BODY}.SPL"], game.effective(PM_BODY))

    def test_eeex_required_for_pierce_magic_but_not_spellstrike(self):
        game = self.make_game(eeex=False)
        self.assert_rejected(game, game.run(210), 210, skipped=True)
        self.assert_installed(game, game.run(211), 211)
        self.assert_spellstrike_payload(game)
        self.assertFalse((game.override / "M_CBRPM.lua").exists())

    def test_components_are_independent_and_install_together(self):
        game = self.make_game()
        result = game.run(210, 211)
        for component in (210, 211):
            self.assert_installed(game, result, component)
        self.assert_pierce_magic_payload(game)
        self.assert_spellstrike_payload(game)
        for parent, component in ((PM, 210), (SS, 211)):
            self.assert_description_and_wrapper(game, parent, component=component)

    def test_owned_runtime_overwrites_namespace_collisions(self):
        for name in ("CBRPM.SPL", "CBRPM.EFF", "CBRPM.ITM", "M_CBRPM.LUA"):
            with self.subTest(name=name):
                game = self.make_game(changed={name: b"foreign owner sentinel"})
                result = game.run(210)
                self.assert_installed(game, result, 210)
                self.assert_pierce_magic_payload(game)
                if name != "M_CBRPM.LUA":
                    self.assertEqual(b"foreign owner sentinel", game.effective(name[:-4], name[-3:]))

    def test_recognized_existing_runtime_is_accepted_and_restored_on_uninstall(self):
        template = (ROOT / "chriz-bg-rebalance/lua/M_CBRPM.lua").read_bytes()
        prior_runtime = template.replace(b"%CBR_PM_MR_STAT%", str(SYNTHETIC_MR_STAT).encode("ascii"))
        game = self.make_game(changed={"M_CBRPM.LUA": prior_runtime})
        self.assert_installed(game, game.run(210), 210)
        self.assert_pierce_magic_payload(game)
        result = game.run(210, uninstall=True)
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertEqual(game.original_override, _tree(game.override))

    def test_edited_pierce_magic_payload_is_replaced(self):
        original = SplFile.from_bytes(_payload(False))
        abilities = list(original.abilities)
        abilities[-1] = dataclasses.replace(abilities[-1], effects=tuple(
            dataclasses.replace(fx, parameter2=0) if fx.opcode == 166 else fx
            for fx in abilities[-1].effects))
        malformed = dataclasses.replace(original, abilities=tuple(abilities)).to_bytes()
        game = self.make_game(changed={f"{PM_BODY}.SPL": malformed})
        self.assert_installed(game, game.run(210), 210)
        self.assert_pierce_magic_payload(game)

    def test_pierce_magic_reinstall_and_uninstall_are_byte_exact_in_synthetic_game(self):
        game = self.make_game()
        self.assert_installed(game, game.run(210), 210)
        before = _tree(game.override)
        self.assert_installed(game, game.run(210), 210)
        self.assertEqual(before, _tree(game.override))
        result = game.run(210, uninstall=True)
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertEqual(game.original_override, _tree(game.override))
        self.assertNotRegex(game.log(), r"(?m)#0\s+#210\b")
        self.assert_stable(game)

    def test_spellstrike_dynamic_wrapped_payload_and_descriptions(self):
        game = self.make_game()
        self.assert_installed(game, game.run(211), 211)
        self.assert_spellstrike_payload(game)
        self.assert_description_and_wrapper(game, SS, component=211)
        self.assertEqual(game.before[f"{PM}.SPL"], game.effective(PM))
        self.assertEqual(game.before[f"{PM_BODY}.SPL"], game.effective(PM_BODY))

    def test_spellstrike_direct_sr_payload_without_child_wrapper(self):
        game = self.make_game(direct=True)
        self.assert_installed(game, game.run(211), 211)
        self.assert_spellstrike_payload(game)
        self.assert_description_and_wrapper(game, SS, component=211)
        self.assertEqual(game.before[f"{SS_BODY}.SPL"], game.effective(SS_BODY))

    def test_antimagic_choices_install_without_sr(self):
        for tail in (False, True):
            for sr_component in (None, 65):
                for component in (210, 211):
                    with self.subTest(tail=tail, sr_component=sr_component, component=component):
                        game = self.make_game(tail=tail, sr_component=sr_component)
                        result = game.run(component)
                        self.assert_installed(game, result, component)
                        self.assertNotIn("WARNING", result.stdout + result.stderr)
                        if component == 210:
                            self.assert_pierce_magic_payload(game)
                        else:
                            self.assert_spellstrike_payload(game)

    def test_bgee_is_rejected(self):
        for component in (210, 211):
            with self.subTest(component=component):
                game = self.make_game(game="bgee")
                self.assert_rejected(game, game.run(component), component, skipped=True)

    def test_eet_is_accepted_for_spellstrike(self):
        game = self.make_game(game="eet")
        self.assert_installed(game, game.run(211), 211)
        self.assert_spellstrike_payload(game)

    def test_missing_dynamic_symbol_does_not_fall_back_to_native_slots(self):
        for component in (210, 211):
            with self.subTest(component=component):
                game = self.make_game(symbols=False)
                self.assert_installed(game, game.run(component), component)
                self.assertEqual(game.original_override, _tree(game.override))
                self.assertEqual(_tlk(game.strings), game.tlk.read_bytes())

    def test_missing_effective_child_costs_only_that_resource(self):
        for component, body in ((210, PM_BODY), (211, SS_BODY)):
            with self.subTest(component=component):
                game = self.make_game(changed={f"{body}.SPL": None})
                result = game.run(component)
                self.assert_installed(game, result, component)
                self.assertIn(f"{body}.spl is absent", result.stdout)
                self.assertNotIn("WARNING", result.stdout + result.stderr)

    def test_missing_spellstrike_failure_mode_is_restored(self):
        original = SplFile.from_bytes(_payload(True))
        abilities = list(original.abilities)
        abilities[-1] = dataclasses.replace(abilities[-1], effects=tuple(
            fx for fx in abilities[-1].effects if not (fx.opcode == 60 and fx.parameter2 == 1)))
        malformed = dataclasses.replace(original, abilities=tuple(abilities)).to_bytes()
        game = self.make_game(changed={f"{SS_BODY}.SPL": malformed})
        self.assert_installed(game, game.run(211), 211)
        self.assert_spellstrike_payload(game)
        self.assert_description_and_wrapper(game, SS, component=211)

    def test_all_effective_spellstrike_children_receive_the_package(self):
        parent = _spell((_effect(146, resource=SS_BODY), _effect(146, resource="OTHERSS"),
                          _effect(146, resource=SS_SHIELD)), level=9)
        game = self.make_game(changed={f"{SS}.SPL": parent, "OTHERSS.SPL": _payload(True)})
        self.assert_installed(game, game.run(211), 211)
        self.assert_spellstrike_payload(game)
        for ability in SplFile.from_bytes(game.effective("OTHERSS")).abilities:
            self.assertEqual([(15, 0), (15, 1)], [(fx.parameter1, fx.parameter2)
                for fx in ability.effects if fx.opcode == 60])

    def test_spellstrike_is_byte_idempotent_on_public_reinstall(self):
        game = self.make_game()
        self.assert_installed(game, game.run(211), 211)
        before = _tree(game.override)
        self.assert_installed(game, game.run(211), 211)
        self.assertEqual(before, _tree(game.override))

    def test_spellstrike_uninstall_restores_synthetic_originals(self):
        for direct in (False, True):
            with self.subTest(direct=direct):
                game = self.make_game(direct=direct)
                self.assert_installed(game, game.run(211), 211)
                result = game.run(211, uninstall=True)
                self.assertEqual(0, result.returncode, result.stdout + result.stderr)
                self.assertEqual(game.original_override, _tree(game.override))
                self.assertNotRegex(game.log(), r"(?m)#0\s+#211\b")
                self.assert_stable(game)

    def test_tail_spellstrike_uses_the_same_payload_behavior(self):
        game = self.make_game(tail=True)
        self.assert_installed(game, game.run(211), 211)
        self.assert_spellstrike_payload(game)
        self.assert_description_and_wrapper(game, SS, component=211)

    def test_tail_pierce_magic_uses_same_callback_and_runtime(self):
        game = self.make_game(tail=True)
        self.assert_installed(game, game.run(210), 210)
        self.assert_pierce_magic_payload(game)
        self.assert_description_and_wrapper(game, PM, component=210)

    def test_same_component_cannot_overlap_main_and_tail(self):
        for tail_first in (False, True):
            for component in (210, 211):
                with self.subTest(tail_first=tail_first, component=component):
                    game = self.make_game(tail=tail_first)
                    self.assert_installed(game, game.run(component), component)
                    baseline = _tree(game.override), game.tlk.read_bytes(), game.log()
                    if tail_first:
                        shutil.copy2(SETUP, game.root / SETUP.name)
                        shutil.copytree(ROOT / "chriz-bg-rebalance", game.root / "chriz-bg-rebalance")
                        game.setup = SETUP.name
                    else:
                        game.setup = _copy_tail(game.root)
                    result = game.run(component)
                    self.assertIn("SKIPPING", result.stdout + result.stderr)
                    self.assertEqual(baseline, (_tree(game.override), game.tlk.read_bytes(), game.log()))

    # ---- descriptions: the spell, scrolls, wands and sibling spells -----------------

    def assert_only_description_changed(self, game, resref, extension, *, unidentified: bool = False):
        """Every byte but the description strref equals the original resource."""
        original, output = game.before[f"{resref}.{extension}"], game.effective(resref, extension)
        offset = 0x50 if extension == "SPL" or unidentified else 0x54
        expected = bytearray(original)
        expected[offset:offset + 4] = output[offset:offset + 4]
        if extension == "ITM" and resref in (PM_SCROLL, SS_SCROLL):
            expected[0x50:0x54] = output[0x50:0x54]
        self.assertEqual(bytes(expected), output, f"{resref}.{extension} changed beyond its description")

    def assert_untouched(self, game, resref, extension):
        self.assertEqual(game.before[f"{resref}.{extension}"], game.effective(resref, extension),
                         f"{resref}.{extension} must not change")

    def test_spell_revisions_layout_of_the_two_texts(self):
        layout = ("Level:", "School:", "Range:", "Duration:", "Casting Time:", "Area of Effect:", "Saving Throw:")
        protections = ("Dispelling Screen", "Entropy Shield", "Fiendish Warding", "Globe of Invulnerability",
                       "Greater Spell Deflection", "Minor Globe of Invulnerability", "Minor Spell Deflection",
                       "Non-Detection", "Sel\u00fbne's Blessing", "Shield of the Archons", "Spell Deflection")
        for number, name, level, speed in ((2100, "Pierce Magic", "6", "6"), (2110, "Spellstrike", "9", "5")):
            with self.subTest(name=name):
                lines = _tra_string(number).split("\n")
                self.assertEqual(name, lines[0])
                for expected, line in zip(layout, lines[1:8]):
                    self.assertTrue(line.startswith(expected), line)
                self.assertEqual(f"Level: {level}", lines[1])
                self.assertEqual("School: Abjuration", lines[2])
                self.assertEqual("Range: Long", lines[3])
                self.assertEqual(f"Casting Time: {speed}", lines[5])
                self.assertEqual("Area of Effect: 1 creature", lines[6])
                self.assertEqual("Saving Throw: None", lines[7])
                self.assertEqual("", lines[8])
                body = "\n".join(lines[9:])
                self.assertIn(f"The spell protection spells dispelled by {name} are:", body)
                for protection in protections:
                    self.assertIn(protection, body)
                self.assertNotIn("nullified", body)
                self.assertNotIn("100%", body)
        pierce, strike = _tra_string(2100), _tra_string(2110)
        self.assertIn("by half for 5 rounds", pierce)
        self.assertIn("at least 10 and at most 40 percentage points", pierce)
        self.assertNotIn("2 rounds", pierce)
        self.assertNotIn("Spell Trap", pierce)
        self.assertIn("a 15% chance of failing to cast arcane or divine spells for 2 rounds", strike)
        self.assertIn("and Spell Trap.", strike)
        for number in (2101, 2111):
            self.assertNotIn("\n", _tra_string(number))

    def test_pierce_magic_description_scrolls_wand_and_sibling_spell(self):
        game = self.make_game()
        result = game.run(210)
        self.assert_installed(game, result, 210)
        new_ref = game.strref(PM)
        description = _strings(game.tlk)[new_ref]
        self.assertEqual(_tra_string(2100) + "\n\n" + _tra_string(2102), description)
        self.assertEqual(7, len(description.split("\n\n")[0].split("\n")) - 1)
        # The owned scroll and linked spell receive complete descriptions.
        for resource, extension in ((PM_SCROLL, "ITM"), (PM_SIBLING, "SPL")):
            self.assertEqual(new_ref, game.strref(resource, extension), resource)
            self.assert_only_description_changed(game, resource, extension)
        # Hidden helpers keep their original descriptions, including the real
        # SR shield helper's captured strref.
        for resource in (PM_BODY, PM_SHIELD):
            before_ref = struct.unpack_from("<i", game.before[f"{resource}.SPL"], 0x50)[0]
            self.assertEqual(before_ref, game.strref(resource), resource)
        for resource in (OWN_SCROLL, COPY_SCROLL):
            self.assert_untouched(game, resource, "ITM")
        # The wand: only the Special value of this spell's own entry changes.
        wand = _strings(game.tlk)[game.strref(PM_WAND, "ITM")]
        self.assertEqual(_wand_text(PM_NAME, _tra_string(2101)), wand)
        self.assertIn("Special: Dispels all specific and combat protections on target\n", wand)
        self.assert_only_description_changed(game, PM_WAND, "ITM")
        # Other callers own their text even when they invoke the same spell.
        for resource in (ODD_WAND, ODD2_WAND):
            self.assert_untouched(game, resource, "ITM")
        # Items with inline effects, unrelated items and Spellstrike's items stay.
        for resource in (INLINE_ITEM, UNRELATED_ITEM, SS_SCROLL, SS_WAND):
            self.assert_untouched(game, resource, "ITM")
        for resource in (SS, SS_SIBLING, "ZUNRELS"):
            self.assert_untouched(game, resource, "SPL")

    def test_spellstrike_description_scrolls_wand_and_sibling_spell(self):
        game = self.make_game()
        result = game.run(211)
        self.assert_installed(game, result, 211)
        new_ref = game.strref(SS)
        self.assertEqual(_tra_string(2110) + "\n\n" + _tra_string(2102), _strings(game.tlk)[new_ref])
        for resource, extension in ((SS_SCROLL, "ITM"), (SS_SIBLING, "SPL")):
            self.assertEqual(new_ref, game.strref(resource, extension), resource)
            self.assert_only_description_changed(game, resource, extension)
        self.assert_untouched(game, SS_WAND, "ITM")
        for resource in (PM_SCROLL, COPY_SCROLL, OWN_SCROLL, PM_WAND, ODD_WAND, INLINE_ITEM, UNRELATED_ITEM):
            self.assert_untouched(game, resource, "ITM")
        self.assert_untouched(game, PM_SIBLING, "SPL")

    def test_direct_sr_payload_scroll_follows_the_parent_text(self):
        game = self.make_game(direct=True)
        self.assert_installed(game, game.run(210), 210)
        self.assertEqual(game.strref(PM), game.strref(PM_SCROLL, "ITM"))
        self.assertNotEqual(1, game.strref(PM_SCROLL, "ITM"))
        self.assert_untouched(game, OWN_SCROLL, "ITM")

    def test_scroll_text_changed_by_another_mod_is_overwritten(self):
        # Our stock scroll gets our text regardless of its previous wording.
        strings = list(ORIGINAL_STRINGS)
        strings[5] = "Another mod rewrote this scroll: it now explains the spell in its own words, at length."
        game = self.make_game(strings=tuple(strings), changed={
            f"{PM_SCROLL}.ITM": _item((_cast(PM),), identified=5, unidentified=3),
        })
        result = game.run(210)
        self.assert_installed(game, result, 210)
        self.assert_untouched(game, COPY_SCROLL, "ITM")
        self.assert_only_description_changed(game, PM_SCROLL, "ITM")
        self.assertEqual(game.strref(PM), game.strref(PM_SCROLL, "ITM"))

    def test_owned_wand_refreshes_either_antimagic_charge_without_an_old_text_gate(self):
        for tail in (False, True):
            for component, parent, sibling, name, template in (
                (210, PM, PM_SIBLING, PM_NAME, 2101),
                (211, SS, SS_SIBLING, SS_NAME, 2111),
            ):
                for call in (parent, sibling):
                    with self.subTest(tail=tail, component=component, call=call):
                        game = self.make_game(tail=tail, changed={
                            f"{PM_WAND}.ITM": _item((_cast("ZUNRELS"),), (_cast(call),),
                                                   identified=3, unidentified=6),
                        })
                        self.assert_installed(game, game.run(component), component)
                        self.assertEqual(_wand_text(name, _tra_string(template)), game.text(PM_WAND, "ITM"))
                        self.assertEqual(6, game.strref(PM_WAND, "ITM", unidentified=True))
                        self.assert_only_description_changed(game, PM_WAND, "ITM")

    def test_other_staff_and_wand_keep_both_descriptions_and_other_abilities(self):
        for tail in (False, True):
            with self.subTest(tail=tail):
                strings = ORIGINAL_STRINGS + (
                    "Staff of Many Uses: grants healing and fires a magic bolt.",
                    "An unexamined staff with three buttons.",
                    "Single-charge wand: invokes an anti-magic spell. No other charges.",
                    "An unexamined wand.",
                )
                staff = _item((_cast(PM),), (_cast(SS),), (_effect(17, 20),),
                              identified=11, unidentified=12)
                wand = _item((_cast(PM_SIBLING),), (_cast(SS_SIBLING),),
                             identified=13, unidentified=14)
                game = self.make_game(tail=tail, strings=strings,
                                      changed={"ZSTAFF.ITM": staff, "ZNEWAND.ITM": wand})
                self.assert_installed(game, game.run(210, 211), 210)
                self.assert_pierce_magic_payload(game)
                self.assert_spellstrike_payload(game)
                for item in ("ZSTAFF", "ZNEWAND"):
                    self.assert_untouched(game, item, "ITM")
                    self.assertNotIn("Breach", game.text(item, "ITM"))
                self.assert_installed(game, game.run(210, 211), 211)
                if tail:
                    self.assert_installed(game, game.run(212, 213), 212)
                for item in ("ZSTAFF", "ZNEWAND"):
                    self.assert_untouched(game, item, "ITM")

    def test_description_install_twice_changes_nothing_and_uninstall_restores_everything(self):
        game = self.make_game()
        self.assert_installed(game, game.run(210, 211), 210)
        after, strings = _tree(game.override), _strings(game.tlk)
        self.assert_installed(game, game.run(210, 211), 210)
        self.assertEqual(after, _tree(game.override))
        self.assertEqual(strings, _strings(game.tlk), "no string is added twice")
        result = game.run(210, 211, uninstall=True)
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertEqual(game.original_override, _tree(game.override))

    def test_item_scan_survives_malformed_items_and_spells(self):
        junk = {f"ZJUNK1.ITM": b"ITM V1  " + b"\x00" * 8, "ZJUNK2.ITM": b"not an item at all",
                "ZJUNK3.SPL": b"SPL V1  " + b"\x07" * 0x80, "ZJUNK4.SPL": b"short"}
        game = self.make_game(changed=junk)
        self.assert_installed(game, game.run(210), 210)
        for name, data in junk.items():
            self.assertEqual(data, (game.override / name).read_bytes(), name)

    # ---- texts-only tail components (212, 213) -------------------------------

    def stale(self, game):
        """Restore the stale item/spell files an old installation left behind."""
        for resource, extension in ((PM_SCROLL, "ITM"), (SS_SCROLL, "ITM"), (COPY_SCROLL, "ITM"),
                                    (PM_WAND, "ITM"), (SS_WAND, "ITM"), (PM_SIBLING, "SPL"), (SS_SIBLING, "SPL")):
            (game.override / f"{resource}.{extension}").write_bytes(game.before[f"{resource}.{extension}"])

    def test_texts_tail_updates_an_installation_that_already_has_the_mechanic(self):
        game = self.make_game(tail=True)
        self.assert_installed(game, game.run(210, 211), 210)
        mechanic = {name: data for name, data in _tree(game.override).items() if name.startswith(("ZPMBODY", "ZSSBODY", "M_CBRPM"))}
        parents = {PM: game.effective(PM), SS: game.effective(SS)}
        # What a private tail leaves: the changed mechanic, a short parent text, stale items.
        for parent, short in ((PM, 2), (SS, 2)):
            data = bytearray(parents[parent])
            struct.pack_into("<i", data, 0x50, short)
            (game.override / f"{parent}.SPL").write_bytes(bytes(data))
        self.stale(game)
        result = game.run(212, 213)
        for component in (212, 213):
            self.assertRegex(game.log(), rf"(?m)#0\s+#{component}\b")
        transcript = result.stdout + result.stderr
        self.assertEqual(0, result.returncode, transcript)
        self.assertIn("SUCCESSFULLY INSTALLED", transcript)
        for parent, template in ((PM, 2100), (SS, 2110)):
            self.assertEqual(_tra_string(template) + "\n\n" + _tra_string(2102), game.text(parent))
        self.assertEqual(game.strref(PM), game.strref(PM_SCROLL, "ITM"))
        self.assert_untouched(game, COPY_SCROLL, "ITM")
        self.assertEqual(game.strref(SS), game.strref(SS_SCROLL, "ITM"))
        self.assertEqual(_wand_text(PM_NAME, _tra_string(2101)), game.text(PM_WAND, "ITM"))
        self.assert_untouched(game, SS_WAND, "ITM")
        # Texts only: the mechanic and the runtime are exactly as they were.
        for name, data in mechanic.items():
            self.assertEqual(data, _tree(game.override)[name], name)
        # Uninstalling the texts component restores the earlier files.
        undo = game.run(212, 213, uninstall=True)
        self.assertEqual(0, undo.returncode, undo.stdout + undo.stderr)

    def test_texts_tail_replaces_private_spellstrike_text_with_full_template(self):
        # A private tail wrote this Spellstrike text in Spell Revisions' layout already.
        private = (SS_NAME + "\nLevel: 9\nSchool: Abjuration\nRange: Long\nDuration: Special\nCasting Time: 5\n"
                   "Area of Effect: 1 creature\nSaving Throw: None\n\nA private text with a 15% chance of spell failure.")
        game = self.make_game(tail=True, strings=ORIGINAL_STRINGS + (private,))
        private_ref = len(ORIGINAL_STRINGS)
        self.assert_installed(game, game.run(211), 211)
        data = bytearray(game.effective(SS))
        struct.pack_into("<i", data, 0x50, private_ref)
        (game.override / f"{SS}.SPL").write_bytes(bytes(data))
        self.stale(game)
        self.assert_installed(game, game.run(213), 213)
        self.assertEqual(_tra_string(2110) + "\n\n" + _tra_string(2102), game.text(SS))
        self.assertEqual(game.strref(SS), game.strref(SS_SCROLL, "ITM"))
        self.assertEqual(game.strref(SS), game.strref(SS_SIBLING, "SPL"))
        self.assert_untouched(game, SS_WAND, "ITM")

    def test_texts_tail_rewrites_a_short_spellstrike_text_that_has_no_header(self):
        # The text 211 wrote before this release: the name, a blank line, no header.
        short = (SS_NAME + "\n\nThis spell removes all spell protections of 9th level or lower. It also gives "
                 "the target a 15% chance of failing to cast arcane or divine spells for 2 rounds.")
        game = self.make_game(tail=True, strings=ORIGINAL_STRINGS + (short,))
        self.assert_installed(game, game.run(211), 211)
        data = bytearray(game.effective(SS))
        struct.pack_into("<i", data, 0x50, len(ORIGINAL_STRINGS))
        (game.override / f"{SS}.SPL").write_bytes(bytes(data))
        self.stale(game)
        self.assert_installed(game, game.run(213), 213)
        self.assertEqual(_tra_string(2110) + "\n\n" + _tra_string(2102), game.text(SS))
        self.assertEqual(game.strref(SS), game.strref(SS_SCROLL, "ITM"))
        self.assertEqual(game.strref(SS), game.strref(SS_SIBLING, "SPL"))

    def test_texts_tail_writes_text_without_gating_on_the_mechanic(self):
        for component, body in ((212, PM_BODY), (213, SS_BODY)):
            with self.subTest(component=component):
                game = self.make_game(tail=True)
                self.assert_installed(game, game.run(component), component)
                self.assertEqual(game.before[f"{body}.SPL"], game.effective(body))

    def test_texts_tail_without_sr_and_absent_symbol(self):
        for component in (212, 213):
            game = self.make_game(tail=True, sr_component=None)
            result = game.run(component)
            self.assert_installed(game, result, component)
            self.assertNotIn("WARNING", result.stdout + result.stderr)
            parent, template = (PM, 2100) if component == 212 else (SS, 2110)
            self.assertEqual(_tra_string(template) + "\n\n" + _tra_string(2102), game.text(parent))
            game = self.make_game(tail=True, symbols=False)
            self.assert_installed(game, game.run(component), component)
            self.assertEqual(game.original_override, _tree(game.override))

    def test_texts_tail_over_the_main_installers_components(self):
        # Installed by the main installer (the 0.1.0 situation), refreshed by the tail.
        game = self.make_game()
        self.assert_installed(game, game.run(210, 211), 210)
        before = _tree(game.override)
        game.setup = _copy_tail(game.root)
        result = game.run(212, 213)
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertEqual(before, _tree(game.override), "the texts are already current")

    def test_missing_all_payload_effects_empty_abilities_and_extra_records(self):
        for component, body in ((210, PM_BODY), (211, SS_BODY)):
            for effects in ((), (_effect(139, 2),),
                            (_effect(166, 99, 0, timing=4),) * 3 if component == 210 else
                            (_effect(60, 88, 0, timing=4),) * 3):
                with self.subTest(component=component, effects=effects):
                    game = self.make_game(changed={f"{body}.SPL": _spell(effects)})
                    self.assert_installed(game, game.run(component), component)
                    for ability in SplFile.from_bytes(game.effective(body)).abilities:
                        if component == 210:
                            self.assertEqual(1, sum(f.opcode == 402 and f.resource == "CBRPM" for f in ability.effects))
                            self.assertEqual([(8, 1)], [(f.parameter1, f.parameter2) for f in ability.effects if f.opcode == 230])
                        else:
                            self.assertEqual([(15, 0), (15, 1)], [(f.parameter1, f.parameter2) for f in ability.effects if f.opcode == 60])
                    before = game.effective(body)
                    self.assert_installed(game, game.run(component), component)
                    self.assertEqual(before, game.effective(body))

    def test_multihop_payload_and_cyclic_dead_branch(self):
        parent = _spell((_effect(146, resource="ZMIDDLE"), _effect(146, resource=SS_SHIELD)))
        middle = _spell((_effect(146, resource=SS_BODY), _effect(146, resource="ZLOOP")))
        game = self.make_game(changed={f"{SS}.SPL": parent, "ZMIDDLE.SPL": middle,
                                      "ZLOOP.SPL": _spell((_effect(146, resource="ZLOOP"),))})
        self.assert_installed(game, game.run(211), 211)
        self.assert_spellstrike_payload(game)

    def test_damaged_payload_does_not_block_other_component(self):
        game = self.make_game(changed={f"{PM_BODY}.SPL": b"short"})
        result = game.run(210, 211)
        self.assert_installed(game, result, 210)
        self.assert_installed(game, result, 211)
        self.assertEqual(b"short", game.effective(PM_BODY))
        self.assert_spellstrike_payload(game)
        self.assertNotIn("WARNING", result.stdout + result.stderr)

    def test_untranslated_language_retains_all_texts(self):
        game = self.make_game()
        translated = game.root / "lang/de_de"
        translated.mkdir()
        (translated / "dialog.tlk").write_bytes(_tlk(game.strings))
        game.tlk = translated / "dialog.tlk"
        result = subprocess.run([str(game.weidu), game.setup, "--game", str(game.root),
            "--force-install-list", "210", "211", "--language", "0", "--use-lang", "de_de",
            "--no-exit-pause", "--quick-log"], cwd=game.root, capture_output=True, text=True, timeout=90)
        self.assert_installed(game, result, 210)
        self.assertEqual(_tlk(game.strings), game.tlk.read_bytes())
        self.assert_pierce_magic_payload(game)
        self.assert_spellstrike_payload(game)


    def test_empty_ability_table_shared_slices_and_changed_strip(self):
        for component, body in ((210, PM_BODY), (211, SS_BODY)):
            original = _payload(component == 211)
            empty = bytearray(original[:0x72])
            struct.pack_into("<IHIHH", empty, 0x64, 0x72, 0, 0x72, 0, 0)
            shared = bytearray(original)
            struct.pack_into("<H", shared, 0x72 + 40 + 0x20,
                             struct.unpack_from("<H", shared, 0x72 + 0x20)[0])
            for variant in (bytes(empty), bytes(shared)):
                with self.subTest(component=component, empty=variant == bytes(empty)):
                    game = self.make_game(changed={f"{body}.SPL": variant})
                    self.assert_installed(game, game.run(component), component)
                    self.assertTrue(SplFile.from_bytes(game.effective(body)).abilities)
                    for ability in SplFile.from_bytes(game.effective(body)).abilities:
                        self.assertTrue(any(f.opcode == (402 if component == 210 else 60) for f in ability.effects))

    def test_missing_stat_symbol_and_item_resources(self):
        game = self.make_game()
        (game.override / "STATS.IDS").write_bytes(b"IDS V1.0\n")
        self.assert_installed(game, game.run(210), 210)
        self.assertIn(b"18 RESISTMAGIC", (game.override / "STATS.IDS").read_bytes())
        self.assertIn(b"local MR_STAT = 18", (game.override / "M_CBRPM.lua").read_bytes())
        removed = {f"{r}.ITM": None for r in (PM_SCROLL, SS_SCROLL, COPY_SCROLL, OWN_SCROLL,
                   PM_WAND, SS_WAND, ODD_WAND, ODD2_WAND, INLINE_ITEM, UNRELATED_ITEM)}
        game = self.make_game(changed=removed)
        self.assert_installed(game, game.run(210), 210)



if __name__ == "__main__":
    unittest.main()
