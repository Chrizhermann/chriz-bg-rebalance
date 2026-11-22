"""Offline WeiDU 249 tests for Ducal Palace Coronation fix (102) & standalone package."""
from __future__ import annotations

import hashlib
import re
import shutil
import struct
import subprocess
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from tests.test_scs_weapon_semantics import _write_minimal_script_ids
from tests.test_tempus_holy_power_installer import (
    ONE_EMPTY_STRING_TLK,
    RESOURCE_TYPE,
    _write_key_and_bif,
)
from tests.test_time_stop_haste_clocks_installer import (
    ROOT,
    TP2,
    WEIDU,
    executable,
    tree,
)
from tools import package_ducal_palace as packager

PACKAGE = "CBR_DUCAL_PALACE"
TAIL_TP2 = f"{PACKAGE}/setup-cbr_ducal_palace.tp2"
TAIL_EXE = "Setup-cbr_ducal_palace.exe"
VERSION = packager.version_of(ROOT / TP2)
ARCHIVE_NAME = f"{PACKAGE}-{VERSION}-windows.zip"
MEMBERS = {
    "LICENSE": ROOT / "LICENSE",
    "WEIDU-LICENSE.txt": ROOT / "WEIDU-LICENSE.txt",
    TAIL_EXE: WEIDU,
    TAIL_TP2: ROOT / "live-patch" / TAIL_TP2,
    f"{PACKAGE}/README.md": ROOT / "live-patch" / PACKAGE / "README.md",
    f"{PACKAGE}/lib/ducal_palace.tpa": ROOT / "chriz-bg-rebalance/lib/ducal_palace.tpa",
    f"{PACKAGE}/languages/english/setup.tra": ROOT / "chriz-bg-rebalance/languages/english/setup.tra",
}


def write_ducal_ids(override: Path, *, with_ds: bool = False) -> None:
    _write_minimal_script_ids(override, "IDS V1.0\n")
    with (override / "TRIGGER.IDS").open("a", encoding="ascii", newline="\n") as f:
        f.write(
            "0x0002 AttackedBy(O:Object*,I:Style*AStyles)\n"
            "0x4030 False()\n"
            "0x4039 NumTimesTalkedTo(I:Num*)\n"
            "0x4040 GlobalTimerExpired(S:Name*,S:Area*)\n"
            "0x4051 Dead(S:Name*)\n"
            "0x407E AreaCheck(S:ResRef*)\n"
            "0x4083 CombatCounter(I:Number*)\n"
        )
    with (override / "ACTION.IDS").open("a", encoding="ascii", newline="\n") as f:
        f.write(
            "3 Attack(O:Target*)\n"
            "8 Dialog(O:Object*)\n"
            "10 Enemy()\n"
            "134 AttackReevaluate(O:Target*,I:ReevaluationPeriod*)\n"
            "137 StartDialogue(S:DialogFile*,O:Target*)\n"
            "177 TriggerActivation(O:Object*,I:State*Boolean)\n"
        )
    with (override / "OBJECT.IDS").open("a", encoding="ascii", newline="\n") as f:
        f.write("10 LastAttackerOf\n")
    with (override / "EA.IDS").open("a", encoding="ascii", newline="\n") as f:
        f.write("2 PC\n29 GOODBUTBLUE\n30 GOODCUTOFF\n128 NEUTRAL\n")
    with (override / "STATE.IDS").open("a", encoding="ascii", newline="\n") as f:
        f.write("0x80000000 STATE_CONFUSED\n")
    (override / "ASTYLES.IDS").write_text("IDS V1.0\n0 DEFAULT\n", encoding="ascii")
    (override / "BOOLEAN.IDS").write_text("IDS V1.0\n0 FALSE\n1 TRUE\n", encoding="ascii")
    if with_ds:
        with (override / "SPLSTATE.IDS").open("a", encoding="ascii", newline="\n") as f:
            f.write("119 CHARM_IMMUNITY\n129 PANIC_IMMUNITY\n130 CONFUSION_IMMUNITY\n")


def make_cre(
    *,
    eff_v: int,
    effects: list[dict[str, object]],
    items: int = 2,
    override_script: str = "",
) -> bytes:
    header = bytearray(0x2D4)
    header[0:8] = b"CRE V1.0"
    header[0x33] = eff_v
    if override_script:
        raw_scr = override_script.encode("ascii")[:8]
        header[0x248 : 0x248 + len(raw_scr)] = raw_scr

    mem_info = bytes(17 * 16)
    fx_off = 0x2D4 + len(mem_info)
    stride = 0x108 if eff_v == 1 else 0x30
    fx_buf = bytearray(len(effects) * stride)
    for i, fx in enumerate(effects):
        o = i * stride
        op = int(fx["opcode"])
        tgt = int(fx.get("target", 1))
        p1 = int(fx.get("parameter1", 0))
        p2 = int(fx.get("parameter2", 0))
        tim = int(fx.get("timing", 9))
        rd = int(fx.get("resist_dispel", 0))
        pr1 = int(fx.get("probability1", 100))
        spec = int(fx.get("special", 0))
        res = str(fx.get("resource", "")).encode("ascii")[:8]
        if eff_v == 1:
            struct.pack_into("<IIIIII", fx_buf, o + 0x08, op, tgt, 0, p1, p2, tim)
            struct.pack_into("<HH", fx_buf, o + 0x24, pr1, 0)
            fx_buf[o + 0x28 : o + 0x28 + len(res)] = res
            struct.pack_into("<I", fx_buf, o + 0x54, rd)
            struct.pack_into("<I", fx_buf, o + 0x40, spec)
        else:
            struct.pack_into("<HBBIIBB", fx_buf, o, op, tgt, 0, p1, p2, tim, rd)
            struct.pack_into("<BB", fx_buf, o + 0x12, pr1, 0)
            fx_buf[o + 0x14 : o + 0x14 + len(res)] = res
            struct.pack_into("<I", fx_buf, o + 0x2C, spec)

    items_off = fx_off + len(fx_buf)
    items_buf = b"".join(struct.pack("<8s12s", f"ITEM{i:02d}".encode("ascii"), b"\0" * 12) for i in range(items))
    slots_off = items_off + len(items_buf)
    slots_buf = bytes(0x50)

    struct.pack_into("<II", header, 0x2A0, 0x2D4, 0)
    struct.pack_into("<II", header, 0x2A8, 0x2D4, 17)
    struct.pack_into("<II", header, 0x2B0, fx_off, 0)
    struct.pack_into("<I", header, 0x2B8, slots_off)
    struct.pack_into("<II", header, 0x2BC, items_off, items)
    struct.pack_into("<II", header, 0x2C4, fx_off, len(effects))
    return bytes(header) + mem_info + bytes(fx_buf) + items_buf + slots_buf


def parse_cre(data: bytes) -> tuple[int, int, int, int, list[dict[str, object]]]:
    eff_v = data[0x33]
    stride = 0x108 if eff_v == 1 else 0x30
    slots_off = struct.unpack_from("<I", data, 0x2B8)[0]
    items_off, items_cnt = struct.unpack_from("<II", data, 0x2BC)
    fx_off, fx_cnt = struct.unpack_from("<II", data, 0x2C4)
    assert items_off == fx_off + fx_cnt * stride, (items_off, fx_off, fx_cnt, stride)
    assert slots_off == items_off + items_cnt * 0x14, (slots_off, items_off, items_cnt)
    assert len(data) == slots_off + 0x50, (len(data), slots_off)
    effs: list[dict[str, object]] = []
    for i in range(fx_cnt):
        o = fx_off + i * stride
        if eff_v == 1:
            op, tgt, _pwr, p1, p2, tim = struct.unpack_from("<IIIIII", data, o + 0x08)
            pr1 = struct.unpack_from("<H", data, o + 0x24)[0]
            res = data[o + 0x28 : o + 0x30].split(b"\0", 1)[0].decode("ascii")
            rd = struct.unpack_from("<I", data, o + 0x54)[0]
            spec = struct.unpack_from("<I", data, o + 0x40)[0]
        else:
            op, tgt, _pwr, p1, p2, tim, rd = struct.unpack_from("<HBBIIBB", data, o)
            pr1 = data[o + 0x12]
            res = data[o + 0x14 : o + 0x1C].split(b"\0", 1)[0].decode("ascii")
            spec = struct.unpack_from("<I", data, o + 0x2C)[0]
        effs.append(
            {
                "opcode": op,
                "target": tgt,
                "parameter1": p1,
                "parameter2": p2,
                "timing": tim,
                "resist_dispel": rd,
                "probability1": pr1,
                "resource": res,
                "special": spec,
            }
        )
    return eff_v, items_off, slots_off, items_cnt, effs


def compile_baf(game_root: Path, name: str, text: str) -> bytes:
    with tempfile.TemporaryDirectory(prefix="cbr-102-baf-") as tmp:
        src = Path(tmp) / f"{name}.baf"
        out = Path(tmp) / "out"
        out.mkdir()
        src.write_text(text, encoding="ascii", newline="\n")
        res = subprocess.run(
            [str(WEIDU), "--game", str(game_root), str(src), "--out", str(out), "--use-lang", "en_us", "--no-exit-pause"],
            cwd=game_root,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert res.returncode == 0, res.stdout + res.stderr
        return (out / f"{name}.bcs").read_bytes()


def decompile_bcs(game_root: Path, bcs_path: Path) -> str:
    with tempfile.TemporaryDirectory(prefix="cbr-102-bcs-") as tmp:
        out = Path(tmp)
        res = subprocess.run(
            [str(WEIDU), "--game", str(game_root), str(bcs_path), "--out", str(out), "--use-lang", "en_us", "--no-exit-pause"],
            cwd=game_root,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert res.returncode == 0, res.stdout + res.stderr
        baf = out / (bcs_path.stem + ".baf")
        return baf.read_text(encoding="ascii")


def belt_baf(betrayal: str = '  AttackedBy([GOODCUTOFF],DEFAULT)\n  !Global("SarevokBehavior","GLOBAL",3)') -> str:
    head = (
        f'IF\n{betrayal}\nTHEN\n  RESPONSE #100\n    SetGlobal("SarevokBehavior","GLOBAL",3)\nEND\n'
        if betrayal
        else ""
    )
    return head + (
        'IF\n  Range([PC],15)\n  NumTimesTalkedTo(0)\nTHEN\n  RESPONSE #100\n'
        '    StartDialogue("belt",[PC])\nEND\n'
        'IF\n  See(NearestEnemyOf(Myself))\n  Global("SarevokBehavior","GLOBAL",3)\nTHEN\n  RESPONSE #10\n'
        '    AttackReevaluate(NearestEnemyOf(Myself),15)\nEND\n'
    )


def liia_baf(betrayal: str = '  AttackedBy([GOODCUTOFF],DEFAULT)\n  !Global("SarevokBehavior","GLOBAL",3)') -> str:
    head = (
        f'IF\n{betrayal}\nTHEN\n  RESPONSE #100\n    SetGlobal("SarevokBehavior","GLOBAL",3)\nEND\n'
        if betrayal
        else ""
    )
    return head + (
        'IF\n  Global("SarevokBehavior","GLOBAL",1)\n  Global("DukeThanks","GLOBAL",0)\n  Dead("Belt")\nTHEN\n'
        '  RESPONSE #100\n    Dialog([PC])\nEND\n'
    )


def sarevok_baf(area: str = "ar0108") -> str:
    return (
        f'IF\n  AreaCheck("{area}")\n  Allegiance(Myself,NEUTRAL)\n'
        '  AttackedBy([GOODCUTOFF],DEFAULT)\n  !Global("SarevokBehavior","GLOBAL",3)\nTHEN\n'
        '  RESPONSE #100\n    SetGlobal("SarevokBehavior","GLOBAL",3)\nEND\n'
        'IF\n  AttackedBy([PC],DEFAULT)\n  !Range(NearestEnemyOf(Myself),7)\nTHEN\n'
        '  RESPONSE #10\n    AttackReevaluate(LastAttackerOf(Myself),30)\nEND\n'
    )


class DucalGame:
    def __init__(
        self,
        root: Path,
        *,
        edition: str = "bgee",
        eff_v: int = 0,
        with_ds: bool = False,
        package: Path | None = None,
        with_liia: bool = True,
        belt_betrayal: str = '  AttackedBy([GOODCUTOFF],DEFAULT)\n  !Global("SarevokBehavior","GLOBAL",3)',
        biff_inputs: bool = False,
    ) -> None:
        self.root = root
        root.mkdir()
        self.override = root / "override"
        self.override.mkdir()
        self.package = package
        self.install_sources(package)
        write_ducal_ids(self.override, with_ds=with_ds)

        marker = ("OH6000", "ARE", b"x") if edition in ("bg2ee", "eet") else ("OH1000", "ARE", b"x")
        resources: list[tuple[str, str, bytes]] = [marker]
        if edition == "sod":
            resources.append(("CAMPAIGN", "2DA", b"2DA V1.0\n*\n CAMPAIGN\n1 SOD\n"))
        with patch.dict(RESOURCE_TYPE, {"2DA": 1012}):
            _write_key_and_bif(root, tuple(resources))
        for path in (root / "dialog.tlk", root / "lang/en_us/dialog.tlk"):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(ONE_EMPTY_STRING_TLK)
        (root / "Baldur.exe").write_bytes(executable())
        if edition == "eet":
            (self.override / "EET.FLAG").write_bytes(b"1")

        belt_fx = (
            [
                {"opcode": 326, "parameter1": 19, "parameter2": 105, "resource": "C0PR#AT1"},
                {"opcode": 101, "parameter2": 148},
                {"opcode": 101, "parameter2": 24},
                {"opcode": 101, "parameter2": 241},
                {"opcode": 101, "parameter2": 5},
                {"opcode": 233, "parameter1": 5, "parameter2": 89},
            ]
            if eff_v == 1
            else [{"opcode": 233, "parameter1": 5, "parameter2": 89}]
        )
        liia_fx = (
            [
                {"opcode": 326, "parameter1": 1, "parameter2": 105, "resource": "C0PR#EK1"},
                {"opcode": 101, "parameter2": 148},
                {"opcode": 233, "parameter1": 1, "parameter2": 96},
            ]
            if eff_v == 1
            else [{"opcode": 233, "parameter1": 1, "parameter2": 96}]
        )

        area = "BG0108" if edition == "eet" else "ar0108"
        sar_scr = "SAREVOK_" if edition == "eet" else "SAREVOK"

        cre_map = {
            "BELT": make_cre(eff_v=eff_v, effects=belt_fx, items=4),
            "SAREVO2": make_cre(eff_v=eff_v, effects=[], items=1, override_script=sar_scr),
        }
        bcs_map = {
            "BELT": compile_baf(root, "belt", belt_baf(belt_betrayal)),
            sar_scr: compile_baf(root, sar_scr.lower(), sarevok_baf(area)),
        }
        if with_liia:
            cre_map["LIIA"] = make_cre(eff_v=eff_v, effects=liia_fx, items=3)
            bcs_map["LIIA"] = compile_baf(root, "liia", liia_baf(belt_betrayal))

        if biff_inputs:
            for k, v in cre_map.items():
                resources.append((k, "CRE", v))
            for k, v in bcs_map.items():
                resources.append((k, "BCS", v))
            with patch.dict(RESOURCE_TYPE, {"2DA": 1012, "CRE": 1009, "BCS": 1007}):
                _write_key_and_bif(root, tuple(resources))
        else:
            for k, v in cre_map.items():
                (self.override / f"{k}.CRE").write_bytes(v)
            for k, v in bcs_map.items():
                (self.override / f"{k}.BCS").write_bytes(v)

        self.before = tree(self.override)
        self.sar_scr = sar_scr
        self.area = area

    def install_sources(self, package: Path | None) -> None:
        if package is None:
            shutil.copy2(WEIDU, self.root / "Setup-chriz-bg-rebalance.exe")
            if not (self.root / TP2).exists():
                shutil.copy2(ROOT / TP2, self.root / TP2)
                shutil.copytree(ROOT / "chriz-bg-rebalance", self.root / "chriz-bg-rebalance")
        else:
            with zipfile.ZipFile(package) as bundle:
                for name in bundle.namelist():
                    if not (self.root / name).resolve().is_relative_to(self.root.resolve()):
                        raise ValueError(f"archive member escapes game: {name}")
                bundle.extractall(self.root)

    def invoke(self, *, tail: bool | None = None, uninstall: bool = False) -> subprocess.CompletedProcess[str]:
        if tail is None:
            tail = self.package is not None
        tp2 = TAIL_TP2 if tail else TP2
        mode = "--force-uninstall-list" if uninstall else "--force-install-list"
        return subprocess.run(
            [
                str(WEIDU), tp2, "--game", str(self.root), mode, "102",
                "--language", "0", "--use-lang", "en_US", "--no-exit-pause", "--quick-log",
            ],
            cwd=self.root,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=90,
        )

    def invoke_exe(self, *, uninstall: bool = False) -> subprocess.CompletedProcess[str]:
        mode = "--force-uninstall-list" if uninstall else "--force-install-list"
        return subprocess.run(
            [
                str(self.root / TAIL_EXE), "--game", str(self.root), mode, "102",
                "--language", "0", "--use-lang", "en_US", "--no-exit-pause", "--quick-log",
            ],
            cwd=self.root,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=90,
        )

    def active_log(self) -> str:
        log = self.root / "WeiDU.log"
        if not log.exists():
            return ""
        return "\n".join(
            line for line in log.read_text(encoding="utf-8", errors="replace").splitlines()
            if not line.lstrip().startswith("//")
        )


def setUpModule() -> None:
    holder = tempfile.TemporaryDirectory(prefix="cbr-102-build-")
    unittest.addModuleCleanup(holder.cleanup)
    DucalPalaceTests.package = packager.build(Path(holder.name))[0]


@unittest.skipUnless(WEIDU.exists(), "WeiDU executable not available")
class DucalPalaceTests(unittest.TestCase):
    package: Path

    def game(self, **kwargs: object) -> DucalGame:
        holder = tempfile.TemporaryDirectory(prefix="cbr-102-")
        self.addCleanup(holder.cleanup)
        return DucalGame(Path(holder.name) / "game", **kwargs)

    def assert_success(self, res: subprocess.CompletedProcess[str]) -> None:
        out = res.stdout + res.stderr
        self.assertEqual(res.returncode, 0, out)
        self.assertIn("SUCCESSFULLY INSTALLED", out)
        self.assertNotIn("INSTALLED WITH WARNINGS", out)

    def assert_ducal_scripts(
        self,
        game: DucalGame,
        *,
        area: str,
        expected_sarevok_sets: int = 1,
    ) -> None:
        for name in ("BELT", "LIIA"):
            text = decompile_bcs(game.root, game.override / f"{name}.BCS")
            self.assertNotIn("GOODCUTOFF", text)
            self.assertEqual(len(re.findall(r'\bGlobal\("CBR_DucalFF","MYAREA",0\)', text)), 1, text)
            self.assertEqual(len(re.findall(r'\bGlobal\("CBR_DucalFF","MYAREA",1\)', text)), 1, text)
            self.assertEqual(len(re.findall(r'\bSetGlobal\("SarevokBehavior","GLOBAL",3\)', text)), expected_sarevok_sets, text)
            self.assertIn("AttackedBy([PC],DEFAULT)", text)
            self.assertIn("!StateCheck(LastAttackerOf(Myself),STATE_CONFUSED)", text)
            self.assertIn('GlobalTimerExpired("CBR_DucalFF_CD","MYAREA")', text)
        belt_txt = decompile_bcs(game.root, game.override / "BELT.BCS")
        self.assertIn('StartDialogue("belt",[PC])', belt_txt)
        self.assertIn("AttackReevaluate(NearestEnemyOf(Myself),15)", belt_txt)
        liia_txt = decompile_bcs(game.root, game.override / "LIIA.BCS")
        self.assertIn('Global("DukeThanks","GLOBAL",0)', liia_txt)

        sar_txt = decompile_bcs(game.root, game.override / f"{game.sar_scr}.BCS")
        self.assertNotIn("GOODCUTOFF", sar_txt)
        self.assertEqual(len(re.findall(r'\bGlobal\("CBR_DucalFF","MYAREA",0\)', sar_txt)), 1, sar_txt)
        self.assertEqual(len(re.findall(r'\bGlobal\("CBR_DucalFF","MYAREA",1\)', sar_txt)), 1, sar_txt)
        self.assertEqual(len(re.findall(r'\bSetGlobal\("SarevokBehavior","GLOBAL",3\)', sar_txt)), 1, sar_txt)
        self.assertEqual(sar_txt.upper().count(f'AREACHECK("{area.upper()}")'), 2, sar_txt)
        self.assertIn("Allegiance(Myself,NEUTRAL)", sar_txt)
        self.assertIn("AttackReevaluate(LastAttackerOf(Myself),30)", sar_txt)

    def test_vanilla_bgee_v1_cre_and_byte_exact_uninstall(self) -> None:
        game = self.game(edition="bgee", eff_v=0, with_ds=False, biff_inputs=True)
        self.assert_success(game.invoke())
        for name, exp_p1 in (("BELT", 5), ("LIIA", 1)):
            eff_v, _io, _so, _ic, fx = parse_cre((game.override / f"{name}.CRE").read_bytes())
            self.assertEqual(eff_v, 0)
            self.assertIn((233, exp_p1), [(e["opcode"], e["parameter1"]) for e in fx])
            op101 = sorted(e["parameter2"] for e in fx if e["opcode"] == 101)
            self.assertEqual(op101, [5, 24, 128, 241])
            op169 = sorted(e["parameter2"] for e in fx if e["opcode"] == 169)
            self.assertEqual(op169, [0, 1, 2, 3, 36])
            self.assertEqual([e for e in fx if e["opcode"] == 328], [])
        self.assert_ducal_scripts(game, area="AR0108")
        un = game.invoke(uninstall=True)
        self.assertEqual(un.returncode, 0, un.stdout + un.stderr)
        self.assertEqual(tree(game.override), game.before)

    def test_eet_scs_v2_cre_removes_148_preserves_326_233_and_offsets(self) -> None:
        game = self.game(edition="eet", eff_v=1, with_ds=True)
        self.assert_success(game.invoke())
        for name, tag, exp_items in (("BELT", "C0PR#AT1", 4), ("LIIA", "C0PR#EK1", 3)):
            eff_v, _io, _so, ic, fx = parse_cre((game.override / f"{name}.CRE").read_bytes())
            self.assertEqual(eff_v, 1)
            self.assertEqual(ic, exp_items)
            self.assertTrue(any(e["opcode"] == 326 and e["resource"] == tag for e in fx))
            self.assertTrue(any(e["opcode"] == 233 for e in fx))
            op101 = sorted(e["parameter2"] for e in fx if e["opcode"] == 101)
            self.assertEqual(op101, [5, 24, 128, 241])
            self.assertNotIn(148, op101)
            op169 = sorted(e["parameter2"] for e in fx if e["opcode"] == 169)
            self.assertEqual(op169, [0, 1, 2, 3, 36])
            op328 = sorted((e["parameter2"], e["special"]) for e in fx if e["opcode"] == 328)
            self.assertEqual(op328, [(119, 1), (129, 1), (130, 1)])
        self.assert_ducal_scripts(game, area="BG0108")
        # Double-install idempotence over the already-patched files (fresh WeiDU log).
        snapshot = tree(game.override)
        again = self.game(edition="eet", eff_v=1, with_ds=True)
        for k in ("BELT.CRE", "LIIA.CRE", "BELT.BCS", "LIIA.BCS", "SAREVOK_.BCS"):
            (again.override / k).write_bytes(snapshot[k])
        self.assert_success(again.invoke())
        self.assert_ducal_scripts(again, area="BG0108")
        for name in ("BELT", "LIIA"):
            _v, _io, _so, _ic, fx = parse_cre((again.override / f"{name}.CRE").read_bytes())
            self.assertEqual(sorted(e["parameter2"] for e in fx if e["opcode"] == 101), [5, 24, 128, 241])
            self.assertEqual(sorted(e["parameter2"] for e in fx if e["opcode"] == 169), [0, 1, 2, 3, 36])
            self.assertEqual(sorted(e["parameter2"] for e in fx if e["opcode"] == 328), [119, 129, 130])

    def test_we_overwrite_mutations_absent_liia_and_bg2ee_refusal(self) -> None:
        for variant in (
            '  AttackedBy([PC],DEFAULT)\n  !Global("SarevokBehavior","GLOBAL",3)',
            '  False()\n  !Global("SarevokBehavior","GLOBAL",3)',
            "",
        ):
            with self.subTest(variant=variant):
                game = self.game(edition="bgee", eff_v=0, belt_betrayal=variant)
                self.assert_success(game.invoke())
                self.assert_ducal_scripts(
                    game,
                    area="AR0108",
                    expected_sarevok_sets=2 if "False()" in variant else 1,
                )

        no_liia = self.game(edition="bgee", eff_v=0, with_liia=False)
        self.assert_success(no_liia.invoke())
        self.assertNotIn("LIIA.CRE", tree(no_liia.override))
        self.assertIn("BELT.CRE", tree(no_liia.override))

        bg2 = self.game(edition="bg2ee", eff_v=1)
        res = bg2.invoke()
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertNotIn("#102", bg2.active_log())
        self.assertEqual(tree(bg2.override), bg2.before)

    def test_standalone_archive_reproducibility_install_uninstall_and_reciprocal_guard(self) -> None:
        first = self.package
        with tempfile.TemporaryDirectory(prefix="cbr-102-repeat-") as tmp:
            second = packager.build(Path(tmp))[0]
            self.assertEqual(first.read_bytes(), second.read_bytes())
        digest = hashlib.sha256(first.read_bytes()).hexdigest()
        self.assertEqual(first.with_suffix(".zip.sha256").read_bytes(), f"{digest}  {first.name}\n".encode())
        with zipfile.ZipFile(first) as z:
            self.assertCountEqual(z.namelist(), MEMBERS.keys())
            for name, src in MEMBERS.items():
                self.assertEqual(z.read(name), src.read_bytes(), name)

        for edition, eff_v, area in (("bgee", 0, "AR0108"), ("sod", 0, "AR0108"), ("eet", 1, "BG0108")):
            with self.subTest(edition=edition):
                game = self.game(edition=edition, eff_v=eff_v, with_ds=(edition == "eet"), package=first)
                self.assert_success(game.invoke_exe())
                self.assertRegex(game.active_log(), r"SETUP-CBR_DUCAL_PALACE\.TP2.*#102\b")
                self.assert_ducal_scripts(game, area=area)
                un = game.invoke_exe(uninstall=True)
                self.assertEqual(un.returncode, 0, un.stdout + un.stderr)
                self.assertEqual(tree(game.override), game.before)

        # Reciprocal guard: standalone -> full blocked; full -> standalone blocked.
        g1 = self.game(edition="eet", eff_v=1, package=first)
        g1.install_sources(None)
        self.assert_success(g1.invoke(tail=True))
        res1 = g1.invoke(tail=False)
        self.assertEqual(res1.returncode, 0)
        self.assertNotIn("SETUP-CHRIZ-BG-REBALANCE.TP2", g1.active_log())

        g2 = self.game(edition="eet", eff_v=1, package=None)
        g2.install_sources(first)
        self.assert_success(g2.invoke(tail=False))
        res2 = g2.invoke(tail=True)
        self.assertEqual(res2.returncode, 0)
        self.assertNotIn("SETUP-CBR_DUCAL_PALACE.TP2", g2.active_log())

    def test_packager_refuses_version_mismatch(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cbr-102-mismatch-") as tmp:
            root = Path(tmp)
            for rel in (TP2, "live-patch/" + TAIL_TP2):
                dest = root / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(ROOT / rel, dest)
            tail = root / "live-patch" / TAIL_TP2
            tail.write_text(tail.read_text(encoding="utf-8").replace(VERSION, "v9.9.9"), encoding="utf-8")
            with patch.object(packager, "ROOT", root), self.assertRaisesRegex(ValueError, "versions must agree"):
                packager.build(root / "dist")
            self.assertFalse((root / "dist").exists())


if __name__ == "__main__":
    unittest.main()
