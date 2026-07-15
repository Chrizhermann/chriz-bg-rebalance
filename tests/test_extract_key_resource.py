"""Tests for the repository-owned KEY/BIFF resource extractor."""

from __future__ import annotations

import hashlib
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from research.scripts import extract_key_resource


SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "research"
    / "scripts"
    / "extract_key_resource.py"
)
SPL_TYPE = 1006


def write_biff(
    path: Path,
    payload: bytes,
    *,
    locator: int = 0x35,
    declared_size: int | None = None,
) -> None:
    """Write the smallest BIFF V1 file containing one variable resource."""
    path.parent.mkdir(parents=True, exist_ok=True)
    table_offset = 0x14
    payload_offset = table_offset + 0x10
    size = len(payload) if declared_size is None else declared_size
    data = bytearray(struct.pack("<4s4sIII", b"BIFF", b"V1  ", 1, 0, table_offset))
    data.extend(struct.pack("<IIIHH", locator, payload_offset, size, SPL_TYPE, 0))
    data.extend(payload)
    path.write_bytes(data)


def write_key(path: Path, bif_paths: list[Path], locator: int) -> None:
    """Write a KEY V1 file indexing MIXED.SPL in the requested BIF."""
    encoded_names = [
        (str(bif_path).replace("/", "\\") + "\0").encode("ascii")
        for bif_path in bif_paths
    ]
    bif_table_offset = 0x18
    resource_table_offset = bif_table_offset + len(bif_paths) * 0x0C
    names_offset = resource_table_offset + 0x0E

    header = struct.pack(
        "<4s4sIIII",
        b"KEY ",
        b"V1  ",
        len(bif_paths),
        1,
        bif_table_offset,
        resource_table_offset,
    )
    bif_entries = bytearray()
    next_name_offset = names_offset
    for bif_path, encoded_name in zip(bif_paths, encoded_names, strict=True):
        bif_entries.extend(
            struct.pack(
                "<IIHH",
                (path.parent / bif_path).stat().st_size,
                next_name_offset,
                len(encoded_name),
                0,
            )
        )
        next_name_offset += len(encoded_name)

    resource = struct.pack("<8sHI", b"MiXeD\0\0\0", SPL_TYPE, locator)
    path.write_bytes(header + bif_entries + resource + b"".join(encoded_names))


class ExtractKeyResourceTests(unittest.TestCase):
    def make_fixture(
        self,
        root: Path,
        *,
        target_locator: int = 0x35,
        target_size: int | None = None,
    ) -> tuple[Path, bytes]:
        decoy = b"wrong BIF"
        target = b"the requested SPL payload"
        bif_paths = [Path("DATA/DECOY.BIF"), Path("DATA/UNUSED.BIF"), Path("DATA/TARGET.BIF")]
        write_biff(root / bif_paths[0], decoy)
        write_biff(root / bif_paths[1], b"unused")
        write_biff(
            root / bif_paths[2],
            target,
            locator=target_locator,
            declared_size=target_size,
        )
        key_path = root / "chitin.key"
        write_key(key_path, bif_paths, (2 << 20) | 0x35)
        return key_path, target

    def test_resolves_case_insensitively_and_uses_key_locator_parts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            key_path, target = self.make_fixture(root)
            output = root / "chosen-output.bin"
            files_before = {path.relative_to(root) for path in root.rglob("*") if path.is_file()}

            result = extract_key_resource.extract_resource(
                key_path=key_path,
                game_root=root,
                resref="mixed",
                resource_type="sPl",
                output_path=output,
            )

            self.assertEqual(output.read_bytes(), target)
            self.assertEqual(result.bif_index, 2)
            self.assertEqual(result.resource_index, 0x35)
            self.assertEqual(result.bif_resource_locator, 0x35)
            files_after = {path.relative_to(root) for path in root.rglob("*") if path.is_file()}
            self.assertEqual(files_after - files_before, {Path("chosen-output.bin")})
            self.assertFalse((root / "MIXED.SPL").exists())

    def test_refuses_overwrite_without_matching_expected_payload_hash(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            key_path, target = self.make_fixture(root)
            output = root / "existing.bin"
            output.write_bytes(b"keep me")

            with self.assertRaisesRegex(extract_key_resource.ExtractionError, "already exists"):
                extract_key_resource.extract_resource(
                    key_path=key_path,
                    game_root=root,
                    resref="MIXED",
                    resource_type="SPL",
                    output_path=output,
                )
            self.assertEqual(output.read_bytes(), b"keep me")

            with self.assertRaisesRegex(extract_key_resource.ExtractionError, "SHA-256"):
                extract_key_resource.extract_resource(
                    key_path=key_path,
                    game_root=root,
                    resref="MIXED",
                    resource_type="SPL",
                    output_path=output,
                    expected_sha256="0" * 64,
                )
            self.assertEqual(output.read_bytes(), b"keep me")

            expected = hashlib.sha256(target).hexdigest()
            extract_key_resource.extract_resource(
                key_path=key_path,
                game_root=root,
                resref="MIXED",
                resource_type="SPL",
                output_path=output,
                expected_sha256=expected.upper(),
            )
            self.assertEqual(output.read_bytes(), target)

    def test_cli_requires_every_input_and_output_path(self) -> None:
        completed = subprocess.run(
            [sys.executable, str(SCRIPT)],
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(completed.returncode, 2)
        for option in ("--key", "--game-root", "--resref", "--type", "--output"):
            self.assertIn(option, completed.stderr)

    def test_cli_fails_cleanly_on_locator_or_size_mismatch(self) -> None:
        cases = (
            ("locator", {"target_locator": 0x36}, "locator"),
            ("size", {"target_size": 10_000}, "size"),
        )
        for label, fixture_args, expected_message in cases:
            with self.subTest(label=label), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                key_path, _ = self.make_fixture(root, **fixture_args)
                output = root / "must-not-exist.spl"
                completed = subprocess.run(
                    [
                        sys.executable,
                        str(SCRIPT),
                        "--key",
                        str(key_path),
                        "--game-root",
                        str(root),
                        "--resref",
                        "mixed",
                        "--type",
                        "spl",
                        "--output",
                        str(output),
                    ],
                    check=False,
                    capture_output=True,
                    text=True,
                )

                self.assertEqual(completed.returncode, 1)
                self.assertIn(expected_message, completed.stderr.lower())
                self.assertNotIn("Traceback", completed.stderr)
                self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
