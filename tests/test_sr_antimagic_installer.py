"""Public SR antimagic installers on disposable games, never a live install.

Resources and TLKs are synthetic; dynamic parent slots and child names ensure
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

from tests.ie_formats import SplAbility, SplEffect, SplFile
from tests.test_emotion_hope_courage_installer import _write_key_and_bif
from tests.test_sr_hardiness import _strings, _tlk, _tree


ROOT = Path(__file__).resolve().parents[1]
WEIDU = ROOT / "weidu.exe"
SETUP = ROOT / "setup-chriz-bg-rebalance.tp2"
TAIL = ROOT / "live-patch/CBR_SR_ANTIMAGIC"
PM, SS = "SPWI643", "SPWI947"
PM_BODY, SS_BODY = "ZPMBODY", "ZSSBODY"
PM_SHIELD, SS_SHIELD = "ZPMSHLD", "ZSSSHLD"
ORIGINAL_STRINGS = ("Synthetic spell", "Shared original description.", "Unrelated text.")
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
                 symbols: bool = True, eeex: bool = True, archive: Path | None = None):
        root.mkdir()
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
            f"{PM_SHIELD}.SPL": _spell((_effect(221, 9, 19),)),
            f"{SS_SHIELD}.SPL": _spell((_effect(221, 9, 19),)),
            "ZSHIELD.SPL": _spell((_effect(206, resource=PM_BODY), _effect(206, resource=SS_BODY))),
            "ZLOWER.SPL": _spell((_effect(166, -40, 0, timing=0, duration=120),), level=5),
            "ZPIERCE.SPL": _spell((_effect(230, 9, 1), _effect(221, 9, 7), _effect(221, 9, 23)), level=8),
            "SPWI608.SPL": _payload(False), "SPWI903.SPL": _payload(True),
        }
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
            if name in (f"{PM}.SPL", f"{PM_BODY}.SPL"):
                resources.append((name[:-4], "SPL", data))
            else:
                (self.override / name).write_bytes(data)
        self.bif = _write_key_and_bif(root, tuple(resources))
        self.tlk = root / "lang/en_us/dialog.tlk"
        self.tlk.parent.mkdir(parents=True)
        self.tlk.write_bytes(_tlk(ORIGINAL_STRINGS))
        (root / "dialog.tlk").write_bytes(_tlk(ORIGINAL_STRINGS))
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

    def effective(self, resref: str) -> bytes:
        path = self.override / f"{resref}.SPL"
        return path.read_bytes() if path.exists() else self.before[f"{resref}.SPL"]

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
            self.assertEqual(f"{digest}  {name}", archive.with_suffix(".zip.sha256").read_text().strip())
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
        self.assertEqual(list(ORIGINAL_STRINGS), _strings(game.tlk)[:len(ORIGINAL_STRINGS)])
        for resource in (PM_SHIELD, SS_SHIELD, "ZSHIELD", "ZLOWER", "ZPIERCE", "SPWI608", "SPWI903"):
            self.assertEqual(game.before[f"{resource}.SPL"], game.effective(resource), resource)
        self.assertEqual(game.original_override["SPLPROT.2DA"], (game.override / "SPLPROT.2DA").read_bytes())
        if "M___EEEX.LUA" in game.original_override:
            self.assertEqual(game.original_override["M___EEEX.LUA"], (game.override / "M___EEex.lua").read_bytes())

    def assert_installed(self, game, result, component):
        transcript = result.stdout + result.stderr
        self.assertEqual(0, result.returncode, transcript)
        self.assertIn("SUCCESSFULLY INSTALLED", transcript)
        self.assertRegex(game.log(), rf"(?m)#0\s+#{component}\b")
        self.assert_stable(game)

    def assert_rejected(self, game, result, component, *, skipped=False):
        transcript = result.stdout + result.stderr
        self.assertIn("SKIPPING" if skipped else "NOT INSTALLED DUE TO ERRORS", transcript)
        self.assertNotRegex(game.log(), rf"(?m)#0\s+#{component}\b")
        self.assertEqual(game.original_override, _tree(game.override))
        self.assertEqual(_tlk(ORIGINAL_STRINGS), game.tlk.read_bytes())
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

    def test_foreign_pierce_magic_namespace_collision_fails_without_writes(self):
        for name in ("CBRPM.SPL", "CBRPM.EFF", "CBRPM.ITM", "M_CBRPM.LUA"):
            with self.subTest(name=name):
                game = self.make_game(changed={name: b"foreign owner sentinel"})
                result = game.run(210)
                self.assert_rejected(game, result, 210,
                                     skipped="NOT INSTALLED DUE TO ERRORS" not in result.stdout + result.stderr)

    def test_recognized_existing_runtime_is_accepted_and_restored_on_uninstall(self):
        template = (ROOT / "chriz-bg-rebalance/lua/M_CBRPM.lua").read_bytes()
        prior_runtime = template.replace(b"%CBR_PM_MR_STAT%", str(SYNTHETIC_MR_STAT).encode("ascii"))
        game = self.make_game(changed={"M_CBRPM.LUA": prior_runtime})
        self.assert_installed(game, game.run(210), 210)
        self.assert_pierce_magic_payload(game)
        result = game.run(210, uninstall=True)
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertEqual(game.original_override, _tree(game.override))

    def test_malformed_pierce_magic_payload_rolls_back_before_runtime_publication(self):
        original = SplFile.from_bytes(_payload(False))
        abilities = list(original.abilities)
        abilities[-1] = dataclasses.replace(abilities[-1], effects=tuple(
            dataclasses.replace(fx, parameter2=0) if fx.opcode == 166 else fx
            for fx in abilities[-1].effects))
        malformed = dataclasses.replace(original, abilities=tuple(abilities)).to_bytes()
        game = self.make_game(changed={f"{PM_BODY}.SPL": malformed})
        self.assert_rejected(game, game.run(210), 210)
        self.assertFalse((game.override / "M_CBRPM.lua").exists())

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

    def test_sr_main_is_required_not_just_warrior_hlas(self):
        for sr_component in (None, 65):
            for component in (210, 211):
                with self.subTest(sr_component=sr_component, component=component):
                    game = self.make_game(sr_component=sr_component)
                    self.assert_rejected(game, game.run(component), component, skipped=True)

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
                result = game.run(component)
                self.assert_rejected(game, result, component,
                                     skipped="NOT INSTALLED DUE TO ERRORS" not in result.stdout + result.stderr)

    def test_missing_effective_child_rolls_back_atomically(self):
        for component, body in ((210, PM_BODY), (211, SS_BODY)):
            with self.subTest(component=component):
                game = self.make_game(changed={f"{body}.SPL": None})
                result = game.run(component)
                self.assert_rejected(game, result, component,
                                     skipped="NOT INSTALLED DUE TO ERRORS" not in result.stdout + result.stderr)

    def test_malformed_spellstrike_payload_does_not_publish_description(self):
        original = SplFile.from_bytes(_payload(True))
        abilities = list(original.abilities)
        abilities[-1] = dataclasses.replace(abilities[-1], effects=tuple(
            fx for fx in abilities[-1].effects if not (fx.opcode == 60 and fx.parameter2 == 1)))
        malformed = dataclasses.replace(original, abilities=tuple(abilities)).to_bytes()
        game = self.make_game(changed={f"{SS_BODY}.SPL": malformed})
        self.assert_rejected(game, game.run(211), 211)

    def test_ambiguous_effective_spellstrike_children_fail_closed(self):
        parent = _spell((_effect(146, resource=SS_BODY), _effect(146, resource="OTHERSS"),
                          _effect(146, resource=SS_SHIELD)), level=9)
        game = self.make_game(changed={f"{SS}.SPL": parent, "OTHERSS.SPL": _payload(True)})
        self.assert_rejected(game, game.run(211), 211)

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


if __name__ == "__main__":
    unittest.main()
