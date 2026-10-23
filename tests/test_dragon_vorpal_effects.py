"""Real WeiDU binary generation and isolated Lua contracts for CBR 110.

Only disposable directories are modified. Lua mocks validate our callback's
decisions and API arguments, not the engine's lethal/protection behavior.
"""
from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

from tests.ie_formats import EffV2, SplFile
from tests.test_ambient_readiness_listener import _find_lua

ROOT = Path(__file__).resolve().parents[1]
WEIDU = ROOT / "weidu.exe"
LIB = ROOT / "chriz-bg-rebalance/lib/dragon_vorpal_effects.tpa"
LUA = ROOT / "chriz-bg-rebalance/lua/M_CBRDVG.lua"
HARNESS = ROOT / "tests/weidu/dragon_vorpal_effects_harness.tp2"
PROFILES = {"15": (15, -4), "10": (10, -2), "05": (5, -2)}
FILES = ({f"CBRDV{profile}.SPL" for profile in PROFILES}
         | {f"CBRDVE{profile}.EFF" for profile in PROFILES}
         | {"CBRDVREM.SPL", "M_CBRDVG.lua"})


def snapshot(root: Path) -> dict[str, bytes]:
    return {p.name: p.read_bytes() for p in root.iterdir() if p.is_file()}


@unittest.skipUnless(WEIDU.is_file(), "WeiDU executable not available")
class DragonVorpalEffectsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="cbr-vorpal-effects-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.fixture = self.root / "resources"
        self.fixture.mkdir()
        self.run_number = 0

    def run_library(self, phase: str = "full", *, success: bool = True,
                    template: Path = LUA) -> str:
        self.run_number += 1
        run = self.root / f"run-{self.run_number}"
        run.mkdir()
        result = subprocess.run([
            str(WEIDU), str(HARNESS), "--nogame", "--force-install-list", "1",
            "--args", str(LIB), "--args", str(self.fixture),
            "--args", str(template), "--args", phase,
            "--no-exit-pause", "--quick-log",
        ], cwd=run, capture_output=True, text=True, timeout=60, check=False)
        transcript = result.stdout + result.stderr
        if success:
            self.assertEqual(result.returncode, 0, transcript)
            self.assertIn("SUCCESSFULLY INSTALLED", transcript)
        else:
            self.assertIn("NOT INSTALLED DUE TO ERRORS", transcript)
        return transcript

    def test_canonical_binary_delivery_and_single_death_save(self) -> None:
        self.run_library()
        self.assertEqual(set(snapshot(self.fixture)), FILES)
        self.assertEqual((self.fixture / "M_CBRDVG.lua").read_bytes(), LUA.read_bytes())
        for profile, (chance, penalty) in PROFILES.items():
            with self.subTest(profile=profile):
                spl = SplFile.from_bytes((self.fixture / f"CBRDV{profile}.SPL").read_bytes())
                self.assertEqual(len(spl.abilities), 1)
                self.assertEqual(spl.casting_effects, ())
                ability = spl.abilities[0]
                self.assertEqual(ability.target, 5)
                self.assertEqual([fx.opcode for fx in ability.effects], [321, 321, 321, 248])
                self.assertEqual(ability.effects[0].resource, f"CBRDV{profile}")
                self.assertEqual({fx.resource for fx in ability.effects[:3]},
                                 {"CBRDV15", "CBRDV10", "CBRDV05"})
                self.assertTrue(all(fx.target == 1 and fx.resist_dispel == 2
                                    and fx.save_type == 0 and fx.save_bonus == 0
                                    and (fx.probability1, fx.probability2) == (100, 0)
                                    for fx in ability.effects))
                rider = ability.effects[-1]
                self.assertEqual(rider.parameter2, 0)  # all successful melee attacks
                self.assertEqual(rider.timing, 9)
                self.assertEqual(rider.resource, f"CBRDVE{profile}")
                eff = EffV2.from_bytes((self.fixture / (rider.resource + ".EFF")).read_bytes())
                self.assertEqual((eff.opcode, eff.target, eff.timing, eff.flags), (402, 2, 1, 2))
                self.assertEqual((eff.save_type, eff.save_bonus), (4, penalty))
                self.assertEqual(eff.resource, "CBRDVGO")
                self.assertEqual((eff.probability1, eff.probability2), (chance - 1, 0))
                # Enumerate actual engine roll values, including both endpoints.
                accepted = [roll for roll in range(100)
                            if eff.probability2 <= roll <= eff.probability1]
                self.assertEqual(accepted, list(range(chance)))
                self.assertEqual(eff.parameter1, 0)
                self.assertEqual(eff.parameter2, 0)
        remove = SplFile.from_bytes((self.fixture / "CBRDVREM.SPL").read_bytes())
        self.assertEqual([fx.opcode for fx in remove.all_effects()], [321] * 3)
        self.assertEqual({fx.resource for fx in remove.all_effects()},
                         {"CBRDV15", "CBRDV10", "CBRDV05"})

    def test_preflight_is_read_only_and_full_is_byte_idempotent(self) -> None:
        (self.fixture / "foreign.SPL").write_bytes(b"unrelated")
        before = snapshot(self.fixture)
        self.run_library("preflight")
        self.assertEqual(snapshot(self.fixture), before)
        self.run_library()
        once = snapshot(self.fixture)
        self.run_library("preflight")
        self.run_library()
        self.assertEqual(snapshot(self.fixture), once)
        self.assertEqual(once["foreign.SPL"], b"unrelated")

    def test_each_reserved_collision_fails_before_any_resource_is_published(self) -> None:
        for filename in sorted(FILES):
            with self.subTest(filename=filename):
                collision = self.fixture / filename
                collision.write_bytes(b"foreign resource")
                before = snapshot(self.fixture)
                transcript = self.run_library(success=False)
                self.assertIn("reserved resource collision", transcript)
                self.assertRegex(transcript, r"Will uninstall\s+0 files")
                self.assertEqual(snapshot(self.fixture), before)
                collision.unlink()

    def test_same_resref_items_cannot_lose_foreign_effects_to_cleanup(self) -> None:
        for profile in PROFILES:
            with self.subTest(profile=profile):
                item = self.fixture / f"CBRDV{profile}.ITM"
                item.write_bytes(b"foreign item with same source resref")
                before = snapshot(self.fixture)
                transcript = self.run_library(success=False)
                self.assertIn("cross-type resource collision", transcript)
                self.assertRegex(transcript, r"Will uninstall\s+0 files")
                self.assertEqual(snapshot(self.fixture), before)
                item.unlink()

    def test_reserved_directory_fails_before_any_resource_is_published(self) -> None:
        (self.fixture / "M_CBRDVG.lua").mkdir()
        transcript = self.run_library(success=False)
        self.assertIn("reserved resource path is a directory", transcript)
        self.assertRegex(transcript, r"Will uninstall\s+0 files")
        self.assertEqual(snapshot(self.fixture), {})

    def test_modified_owned_bytes_and_truncation_are_not_overwritten(self) -> None:
        self.run_library()
        target = self.fixture / "CBRDVE15.EFF"
        original = target.read_bytes()
        variants = [original[:-1], original[:0x44] + b"\0\0\0\0" + original[0x48:]]
        for changed in variants:
            with self.subTest(length=len(changed)):
                target.write_bytes(changed)
                before = snapshot(self.fixture)
                self.run_library(success=False)
                self.assertEqual(snapshot(self.fixture), before)

    def test_full_revalidates_after_an_earlier_preflight(self) -> None:
        self.run_library("preflight")
        (self.fixture / "M_CBRDVG.lua").write_bytes(b"late namespace collision")
        before = snapshot(self.fixture)
        self.run_library(success=False)
        self.assertEqual(snapshot(self.fixture), before)

    def test_bad_inputs_do_not_publish(self) -> None:
        self.assertIn("unknown resource phase", self.run_library("unknown", success=False))
        self.assertIn("runtime template is missing", self.run_library(
            template=self.root / "missing.lua", success=False))
        bad = self.root / "bad.lua"
        bad.write_text("-- not a CBR template\n", encoding="ascii")
        self.assertIn("unrecognized dragon vorpal runtime template",
                      self.run_library(template=bad, success=False))
        self.assertEqual(snapshot(self.fixture), {})


class DragonVorpalLuaTests(unittest.TestCase):
    def run_lua(self, assertions: str, *, setup: str = "") -> None:
        executable = _find_lua()
        if executable is None:
            self.skipTest("Lua interpreter not available")
        script = r'''
local calls, messages = {}, {}
print = function(text) messages[#messages + 1] = text end
EEex_Active = true
EEex_Sprite_GetStat = function(target, stat)
    assert(stat == 83)
    return target.minimum_hp
end
EEex_GameObject_ApplyEffect = function(target, args)
    calls[#calls + 1] = {target = target, args = args}
end
local source = {m_sourceId = 71, m_sourceTarget = 92,
    m_sourceRes = {get = function() return "CBRDVE15" end},
    m_sourceType = 2, m_sourceFlags = 0x1234}
local target = {minimum_hp = 0, death_ward = true, stoneskins = 5,
    physical_resistance = 100, gore = false, no_permanent_death = true}
''' + setup + "\nassert(loadfile([[" + LUA.as_posix() + "]]))()\n" + assertions
        with tempfile.TemporaryDirectory(prefix="cbr-vorpal-lua-") as temp:
            path = Path(temp) / "check.lua"
            path.write_text(script, encoding="ascii")
            result = subprocess.run([executable, str(path)], cwd=temp,
                                    capture_output=True, text=True, timeout=30, check=False)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_callback_requests_one_native_death_without_reroll_or_protection_edits(self) -> None:
        self.run_lua(r'''
CBRDVGO(source, target)
assert(#calls == 1 and #messages == 0)
local args = calls[1].args
assert(calls[1].target == target)
assert(args.effectID == 13 and args.dwFlags == 8 and args.durationType == 1)
assert(args.noSave == 1 and args.immediateResolve == 1 and args.m_flags == 2)
assert(args.savingThrow == 0 and args.saveMod == 0)
assert(args.probabilityLower == 0 and args.probabilityUpper == 100)
assert(args.sourceID == 71 and args.sourceTarget == 92)
assert(args.m_sourceRes == "CBRDVE15" and args.m_sourceType == 2)
assert(args.m_sourceFlags == 0x1234)
assert(target.death_ward and target.stoneskins == 5)
assert(target.physical_resistance == 100 and not target.gore and target.no_permanent_death)
assert(target.minimum_hp == 0)
''')

    def test_every_positive_minimum_hp_preserves_plot_immortality(self) -> None:
        self.run_lua(r'''
for _, minimum in ipairs({1, 2, 255, 65535}) do
    target.minimum_hp = minimum
    CBRDVGO(source, target)
end
assert(#calls == 0 and #messages == 0)
target.minimum_hp = 0
CBRDVGO(source, target)
assert(#calls == 1)
''')

    def test_absent_apis_fail_closed_with_one_labelled_diagnostic(self) -> None:
        for setup in ("EEex_Active = false", "EEex_GameObject_ApplyEffect = nil",
                      "EEex_Sprite_GetStat = nil"):
            with self.subTest(setup=setup):
                self.run_lua(r'''
CBRDVGO(source, target)
CBRDVGO(source, target)
assert(#calls == 0 and #messages == 1)
assert(messages[1]:find("[CBR 110]", 1, true))
''', setup=setup)

    def test_unreadable_guard_or_source_metadata_fails_closed(self) -> None:
        self.run_lua(r'''
target.minimum_hp = nil
CBRDVGO(source, target)
target.minimum_hp = 0 / 0
CBRDVGO(source, target)
target.minimum_hp = 0
source.m_sourceRes = nil
CBRDVGO(source, target)
assert(#calls == 0 and #messages == 2)
''')

    def test_application_failure_does_not_retry_or_change_protections(self) -> None:
        self.run_lua(r'''
local attempts = 0
EEex_GameObject_ApplyEffect = function() attempts = attempts + 1; error("mock failure") end
CBRDVGO(source, target)
assert(attempts == 1 and #messages == 1)
assert(target.death_ward and target.stoneskins == 5)
assert(target.physical_resistance == 100 and target.no_permanent_death)
''')


if __name__ == "__main__":
    unittest.main()
