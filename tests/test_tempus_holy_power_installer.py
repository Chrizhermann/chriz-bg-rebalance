from __future__ import annotations

import hashlib
import shutil
import struct
import subprocess
import tempfile
import unittest
from pathlib import Path

from tests.test_tempus_holy_power import (
    APR_CONDITION_RESREFS,
    APR_HELPER_RESREFS,
    HOLY_RESREF,
    ROOT,
    SETUP_TP2,
    STRENGTH_HELPER_RESREFS,
    WEIDU,
    _raw_file_tree,
    _run_harness,
    build_fixture,
)


DIVINE_RESREF = "SPPR388"
HASTE_RESREF = "SPWI788"
COMPONENT_SCRATCH = Path("weidu_external/chriz-bg-rebalance/tempus-401")
ONE_EMPTY_STRING_TLK = (
    struct.pack("<8sHII", b"TLK V1  ", 0, 1, 0x2C)
    + struct.pack("<H8siiII", 0, b"\0" * 8, 0, 0, 0, 0)
)

RESOURCE_TYPE = {
    "SPL": 1006,
    "IDS": 1008,
    "ARE": 1010,
}

STRENGTH_PUBLICATIONS = {
    f"{resref}.EFF" if resref.startswith("CBRSE") else f"{resref}.SPL"
    for resref in STRENGTH_HELPER_RESREFS
}
APR_PUBLICATIONS = {
    *(f"{resref}.SPL" for resref in APR_HELPER_RESREFS),
    *(f"{resref}.EFF" for resref in APR_CONDITION_RESREFS),
}
# The public wrapper materializes six effective inputs at their canonical
# override paths inside the WeiDU transaction (never SPELL.IDS, whose staging
# would create WeiDU's SPELL.IDS.INSTALLED tracking file), and the production
# transformer then patches/creates in place.  In every compatibility mode the
# override therefore gains exactly the six staged inputs plus the thirteen
# private Strength helpers; additive semantics adds the six APR bridge
# resources on top.  Doubling semantics leaves the staged Improved Haste and
# SPLSTATE.IDS copies byte-identical to their effective sources.
ALWAYS_MATERIALIZED = {
    f"{HOLY_RESREF}.SPL",
    "OHTEMPUS.2DA",
    f"{DIVINE_RESREF}.SPL",
    f"{HASTE_RESREF}.SPL",
    "SPLSTATE.IDS",
    "SPLPROT.2DA",
    *STRENGTH_PUBLICATIONS,
}
ADDITIVE_CREATED = set(APR_PUBLICATIONS)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _casefold_tree(tree: dict[str, bytes]) -> dict[str, bytes]:
    folded: dict[str, bytes] = {}
    for relative, payload in tree.items():
        key = relative.upper()
        if key in folded:
            raise AssertionError(f"case-colliding synthetic files: {relative}")
        folded[key] = payload
    return folded


def _write_key_and_bif(
    game_root: Path,
    resources: tuple[tuple[str, str, bytes], ...],
) -> Path:
    """Write one uncompressed BIFF and a KEY that indexes every resource."""
    bif_relative = Path("DATA/CBRINST.BIF")
    bif_path = game_root / bif_relative
    bif_path.parent.mkdir(parents=True, exist_ok=True)

    table_offset = 0x14
    payload_offset = table_offset + len(resources) * 0x10
    table = bytearray()
    payloads = bytearray()
    key_entries: list[tuple[str, int, int]] = []
    for index, (resref, extension, payload) in enumerate(resources):
        extension = extension.upper()
        resource_type = RESOURCE_TYPE[extension]
        table.extend(
            struct.pack(
                "<IIIHH",
                index,
                payload_offset + len(payloads),
                len(payload),
                resource_type,
                0,
            )
        )
        payloads.extend(payload)
        key_entries.append((resref.upper(), resource_type, index))
    bif_path.write_bytes(
        struct.pack(
            "<4s4sIII",
            b"BIFF",
            b"V1  ",
            len(resources),
            0,
            table_offset,
        )
        + table
        + payloads
    )

    encoded_bif_name = (str(bif_relative).replace("/", "\\") + "\0").encode(
        "ascii"
    )
    bif_table_offset = 0x18
    resource_table_offset = bif_table_offset + 0x0C
    names_offset = resource_table_offset + len(resources) * 0x0E
    key = bytearray(
        struct.pack(
            "<4s4sIIII",
            b"KEY ",
            b"V1  ",
            1,
            len(resources),
            bif_table_offset,
            resource_table_offset,
        )
    )
    key.extend(
        struct.pack(
            "<IIHH",
            bif_path.stat().st_size,
            names_offset,
            len(encoded_bif_name),
            0,
        )
    )
    for resref, resource_type, locator in key_entries:
        key.extend(
            struct.pack(
                "<8sHI",
                resref.encode("ascii").ljust(8, b"\0"),
                resource_type,
                locator,
            )
        )
    key.extend(encoded_bif_name)
    (game_root / "chitin.key").write_bytes(key)
    return bif_path


class SyntheticGame:
    def __init__(self, temporary: tempfile.TemporaryDirectory[str], variant: str):
        self.temporary = temporary
        self.root = Path(temporary.name) / "game"
        self.root.mkdir()
        self.override = self.root / "override"
        self.override.mkdir()
        self.fixture_root = Path(temporary.name) / "fixture"
        self.fixture = build_fixture(
            self.fixture_root,
            variant,
            divine_id=1388,
            haste_id=2788,
        )

        shutil.copy2(SETUP_TP2, self.root / SETUP_TP2.name)
        shutil.copytree(
            ROOT / "chriz-bg-rebalance",
            self.root / "chriz-bg-rebalance",
        )

        biff_only_names = {
            f"{HOLY_RESREF}.SPL",
            "SPELL.IDS",
            f"{HASTE_RESREF}.SPL",
            "SPLSTATE.IDS",
        }
        for source in self.fixture_root.iterdir():
            if source.name.upper() in biff_only_names:
                continue
            if source.is_file():
                shutil.copy2(source, self.override / source.name)

        self.bif_path = _write_key_and_bif(
            self.root,
            (
                ("OH6000", "ARE", b"synthetic BG2EE marker"),
                (
                    HOLY_RESREF,
                    "SPL",
                    (self.fixture_root / f"{HOLY_RESREF}.SPL").read_bytes(),
                ),
                (
                    "SPELL",
                    "IDS",
                    (self.fixture_root / "SPELL.IDS").read_bytes(),
                ),
                (
                    HASTE_RESREF,
                    "SPL",
                    (self.fixture_root / f"{HASTE_RESREF}.SPL").read_bytes(),
                ),
                (
                    "SPLSTATE",
                    "IDS",
                    (self.fixture_root / "SPLSTATE.IDS").read_bytes(),
                ),
            ),
        )
        self.lang_tlk = self.root / "lang/en_US/dialog.tlk"
        self.lang_tlk.parent.mkdir(parents=True)
        self.lang_tlk.write_bytes(ONE_EMPTY_STRING_TLK)
        self.root_tlk = self.root / "dialog.tlk"
        self.root_tlk.write_bytes(ONE_EMPTY_STRING_TLK)

        self.pre_override = _raw_file_tree(self.override)
        self.stable_hashes = {
            "key": _sha256(self.root / "chitin.key"),
            "bif": _sha256(self.bif_path),
            "lang_tlk": _sha256(self.lang_tlk),
            "root_tlk": _sha256(self.root_tlk),
        }

    @property
    def setup_tp2(self) -> Path:
        return self.root / SETUP_TP2.name

    @property
    def scratch(self) -> Path:
        return self.root / COMPONENT_SCRATCH

    def run_install(self, component: int) -> subprocess.CompletedProcess[str]:
        return self._run("--force-install-list", component)

    def run_uninstall(self, component: int) -> subprocess.CompletedProcess[str]:
        return self._run("--force-uninstall-list", component)

    def _run(self, operation: str, component: int) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                str(WEIDU),
                str(self.setup_tp2),
                "--game",
                str(self.root),
                operation,
                str(component),
                "--language",
                "0",
                "--use-lang",
                "en_US",
                "--no-exit-pause",
                "--quick-log",
            ],
            cwd=self.root,
            capture_output=True,
            text=True,
            timeout=90,
            check=False,
        )

    def transcript(self, process: subprocess.CompletedProcess[str]) -> str:
        return f"{process.stdout}\n{process.stderr}".strip()

    def weidu_log(self) -> str:
        path = self.root / "WeiDU.log"
        return path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""

    def active_weidu_log(self) -> str:
        return "\n".join(
            line
            for line in self.weidu_log().splitlines()
            if not line.lstrip().startswith("//")
        )

    def assert_stable_inputs(self, testcase: unittest.TestCase) -> None:
        testcase.assertEqual(self.stable_hashes["key"], _sha256(self.root / "chitin.key"))
        testcase.assertEqual(self.stable_hashes["bif"], _sha256(self.bif_path))
        testcase.assertEqual(self.stable_hashes["lang_tlk"], _sha256(self.lang_tlk))
        testcase.assertEqual(self.stable_hashes["root_tlk"], _sha256(self.root_tlk))


class TempusHolyPowerPublicInstallerTests(unittest.TestCase):
    def _make_game(self, variant: str) -> SyntheticGame:
        temporary = tempfile.TemporaryDirectory(prefix="cbr-tempus-installer-")
        self.addCleanup(temporary.cleanup)
        return SyntheticGame(temporary, variant)

    def _assert_installed(
        self,
        game: SyntheticGame,
        process: subprocess.CompletedProcess[str],
        component: int,
    ) -> None:
        transcript = game.transcript(process)
        self.assertEqual(0, process.returncode, transcript)
        self.assertIn("SUCCESSFULLY INSTALLED", transcript)
        self.assertRegex(game.active_weidu_log(), rf"(?m)#0\s+#{component}\b")
        game.assert_stable_inputs(self)
        self.assertFalse(game.scratch.exists(), "component left its staging tree behind")

    def _assert_not_installed(
        self,
        game: SyntheticGame,
        process: subprocess.CompletedProcess[str],
        component: int,
    ) -> None:
        transcript = game.transcript(process)
        self.assertNotIn("SUCCESSFULLY INSTALLED", transcript)
        self.assertNotRegex(game.active_weidu_log(), rf"(?m)#0\s+#{component}\b")
        game.assert_stable_inputs(self)

    def _expected_harness_tree(self, variant: str) -> dict[str, bytes]:
        expected = _run_harness(variant, "auto", alternate_ids=True)
        try:
            self.assertTrue(expected.succeeded, expected.transcript)
            return _casefold_tree(_raw_file_tree(expected.output))
        finally:
            expected.temporary.cleanup()

    def _assert_publication_contract(
        self,
        game: SyntheticGame,
        variant: str,
        *,
        additive: bool,
    ) -> None:
        actual = _casefold_tree(_raw_file_tree(game.override))
        before = _casefold_tree(game.pre_override)
        expected = self._expected_harness_tree(variant)
        materialized = set(ALWAYS_MATERIALIZED)
        if additive:
            materialized.update(ADDITIVE_CREATED)
        materialized_keys = {resource.upper() for resource in materialized}

        expected_additions = materialized_keys - set(before)
        self.assertEqual(
            set(before) | expected_additions,
            set(actual),
            "public installer wrote outside its explicit allowlist",
        )
        for resource in sorted(materialized):
            key = resource.upper()
            self.assertIn(key, actual)
            self.assertEqual(
                expected[key],
                actual[key],
                f"public component diverged from production harness for {resource}",
            )
        for key, payload in before.items():
            if key not in materialized_keys:
                self.assertEqual(
                    payload,
                    actual[key],
                    f"preexisting non-materialized resource changed: {key}",
                )

        fixture_tree = _casefold_tree(_raw_file_tree(game.fixture_root))
        if not additive:
            for resource in APR_PUBLICATIONS:
                self.assertNotIn(resource.upper(), actual)
            self.assertEqual(
                fixture_tree[f"{HASTE_RESREF}.SPL"],
                actual[f"{HASTE_RESREF}.SPL"],
                "doubling mode must leave the staged Improved Haste byte-identical",
            )
            self.assertEqual(
                fixture_tree["SPLSTATE.IDS"],
                actual["SPLSTATE.IDS"],
                "doubling mode must leave the staged SPLSTATE.IDS byte-identical",
            )

        self.assertNotIn("SPELL.IDS", actual)
        for key in actual:
            self.assertFalse(
                key.endswith(".INSTALLED"),
                f"public installer triggered WeiDU IDS tracking: {key}",
            )
        self.assertNotIn("SPPR412.SPL", actual)
        self.assertNotIn("SPWI613.SPL", actual)

    def test_component_401_additive_installs_biff_source_and_uninstalls_exactly(self) -> None:
        game = self._make_game("additive")
        self.assertNotIn(f"{HOLY_RESREF}.SPL", _casefold_tree(game.pre_override))

        install = game.run_install(401)
        self._assert_installed(game, install, 401)
        self._assert_publication_contract(game, "additive", additive=True)

        uninstall = game.run_uninstall(401)
        transcript = game.transcript(uninstall)
        self.assertEqual(0, uninstall.returncode, transcript)
        self.assertNotRegex(game.active_weidu_log(), r"(?m)#0\s+#401\b")
        self.assertEqual(game.pre_override, _raw_file_tree(game.override))
        self.assertFalse((game.override / f"{HOLY_RESREF}.SPL").exists())
        self.assertFalse(game.scratch.exists())
        game.assert_stable_inputs(self)

    def test_component_401_double_does_not_publish_additive_resources(self) -> None:
        game = self._make_game("doubling")
        install = game.run_install(401)
        self._assert_installed(game, install, 401)
        self._assert_publication_contract(game, "doubling", additive=False)

    def test_forced_semantic_mismatches_fail_atomically(self) -> None:
        for component, variant in ((402, "additive"), (403, "doubling")):
            with self.subTest(component=component, variant=variant):
                game = self._make_game(variant)
                process = game.run_install(component)
                self._assert_not_installed(game, process, component)
                self.assertEqual(game.pre_override, _raw_file_tree(game.override))
                self.assertFalse(game.scratch.exists())
                self.assertRegex(
                    game.transcript(process),
                    r"(?i)force_(?:double|additive)|semantics|improved haste|mismatch",
                )

    def test_foreign_scratch_file_is_ignored_while_component_installs(self) -> None:
        game = self._make_game("additive")
        game.scratch.mkdir(parents=True)
        sentinel = game.scratch / "FOREIGN.KEEP"
        sentinel_payload = b"foreign scratch sentinel must survive"
        sentinel.write_bytes(sentinel_payload)

        process = game.run_install(401)
        transcript = game.transcript(process)
        self.assertEqual(0, process.returncode, transcript)
        self.assertIn("SUCCESSFULLY INSTALLED", transcript)
        self.assertRegex(game.active_weidu_log(), r"(?m)#0\s+#401\b")
        game.assert_stable_inputs(self)
        self._assert_publication_contract(game, "additive", additive=True)
        self.assertTrue(sentinel.is_file(), game.transcript(process))
        self.assertEqual(sentinel_payload, sentinel.read_bytes())
        self.assertEqual(
            {"FOREIGN.KEEP": sentinel_payload},
            _raw_file_tree(game.scratch),
            "public component used or polluted the retired scratch workspace",
        )


if __name__ == "__main__":
    unittest.main()
