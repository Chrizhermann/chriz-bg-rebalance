"""Differential research compiler checks; no game, installer or runtime hooks.

Every existing Python compiler fixture also runs the independent LuaJIT port.
Successful manifests must match every field/key; failures must retain their
diagnostic code. The Python fixture's own behavioral assertions still execute.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import re
import unittest
from unittest.mock import patch

from lupa.luajit21 import LuaRuntime, LuaError
from tests import test_potion_admission_manifest as fixtures
from tests import test_potion_linked_manifest as linked_fixtures

ROOT = Path(__file__).resolve().parents[1] / "research/prototypes/potion-admission"


class LuaCompiler:
    def __init__(self):
        self.lua = LuaRuntime(unpack_returned_tuples=True, encoding=None)
        self.hash = self.lua.execute((ROOT / "CBRPQHash.lua").read_bytes())[b"sha256"]
        self.compile = self.lua.execute((ROOT / "CBRPQCompile.lua").read_bytes())[b"build"]
        self.wrap = self.lua.eval(b"function(callback) return function(name) return callback(name) end end")

    def convert(self, value):
        if isinstance(value, bytes):
            return value.decode("ascii")
        if hasattr(value, "items"):
            return {self.convert(k): self.convert(v) for k, v in value.items()}
        return value

    def build(self, inputs, policy="unique", *, read_resource=None):
        names = self.lua.table_from([name.encode("ascii") for name in inputs])
        options = self.lua.table_from({b"version": 1, b"policy": policy.encode("ascii"), b"names": names})

        def read(name):
            decoded = name.decode("ascii")
            if decoded in inputs:
                return bytes(inputs[decoded])
            if read_resource is None:
                return None
            return bytes(read_resource(decoded))

        # A present binary reader is part of the versioned Lua API. Preserve
        # Python's explicit missing-link-resolver diagnostic in the comparison
        # through a capability marker; ordinary root inputs always remain read.
        options[b"resolveLinks"] = read_resource is not None
        return self.convert(self.compile(options, self.wrap(read), self.hash))


class PotionLuaCompilerDifferentialTests(fixtures.PotionAdmissionManifestTests):
    @classmethod
    def setUpClass(cls):
        cls.port = LuaCompiler()

    def setUp(self):
        original = fixtures.compiler.build_manifest

        def compare(inputs, policy="unique", *, read_resource=None):
            try:
                expected = original(inputs, policy, read_resource=read_resource)
            except fixtures.compiler.ManifestError as error:
                with self.assertRaises(LuaError) as lua_error:
                    self.port.build(inputs, policy, read_resource=read_resource)
                code = re.search(r"\b([A-Z][A-Z_]+):", str(lua_error.exception))
                self.assertIsNotNone(code, str(lua_error.exception))
                self.assertEqual(error.code, code.group(1), str(lua_error.exception))
                raise
            actual = self.port.build(inputs, policy, read_resource=read_resource)
            self.assertEqual(expected, actual)
            return expected

        self.comparison = patch.object(fixtures.compiler, "build_manifest", compare)
        self.comparison.start()
        self.addCleanup(self.comparison.stop)

    def test_hash_matches_known_vectors_and_binary_padding_boundaries(self):
        for value in (b"", b"abc", b"a" * 55, b"a" * 56, b"a" * 63,
                      b"a" * 64, b"a" * 65, bytes(range(256)) * 8):
            with self.subTest(length=len(value)):
                self.assertEqual(hashlib.sha256(value).hexdigest(), self.port.hash(value).decode("ascii"))

    def test_reader_schema_names_and_missing_binary_inputs(self):
        for options in ({b"version": 2, b"names": {}}, {b"version": 1, b"names": {2: b"A.ITM"}},
                        {b"version": 1, b"names": {b"path": b"A.ITM"}}):
            options[b"names"] = self.port.lua.table_from(options[b"names"])
            with self.assertRaisesRegex(LuaError, "INPUT:"):
                self.port.compile(self.port.lua.table_from(options), self.port.wrap(lambda name: None), self.port.hash)
        with self.assertRaisesRegex(LuaError, "INPUT:"):
            self.port.compile(self.port.lua.table_from({b"version": 1,
                b"names": self.port.lua.table_from([b"A.ITM"])}), self.port.wrap(lambda name: None), self.port.hash)


class PotionLuaLinkedCompilerDifferentialTests(linked_fixtures.LinkedManifestTests):
    @classmethod
    def setUpClass(cls):
        cls.port = LuaCompiler()

    def setUp(self):
        # The linked fixtures use the same imported compiler module. Reuse the
        # comparison wrapper while retaining every Python fixture assertion.
        PotionLuaCompilerDifferentialTests.setUp(self)


CAPTURE_ROOTS = [Path(p) for p in os.environ.get("CBR_POTION_COMPILER_ROOTS", "").split(os.pathsep) if p]


@unittest.skipUnless(CAPTURE_ROOTS, "set explicit read-only CBR_POTION_COMPILER_ROOTS for captured differential checks")
class PotionLuaCompilerCapturedTests(unittest.TestCase):
    def test_every_captured_potion_and_compilable_subset_match_both_policies(self):
        port = LuaCompiler()
        for root in CAPTURE_ROOTS:
            self.assertTrue(root.is_absolute() and root.is_dir(), str(root))
            store = fixtures.compiler.audit.ResourceStore(root, game=(root / "chitin.key").is_file())
            inputs = {}
            for name in store.names():
                if name.endswith(".ITM"):
                    data = store.read(name)
                    if len(data) >= 0x1E and fixtures.compiler.audit.u16(data, 0x1C) == 9:
                        inputs[name] = data
            self.assertTrue(inputs, str(root))
            for policy in ("unique", "except_genius"):
                compilable = {}
                selections = []
                for name, data in sorted(inputs.items()):
                    subset = {name: data}
                    match = fixtures.compiler.SCS_COPY.fullmatch(name[:-4])
                    if match and "POTN" + match.group(1) + ".ITM" in inputs:
                        anchor = "POTN" + match.group(1) + ".ITM"
                        subset[anchor] = inputs[anchor]
                    selections.append((name, subset))
                selections.append(("whole profile", inputs))
                for label, subset in selections:
                    with self.subTest(root=str(root), policy=policy, resource=label):
                        try:
                            expected = fixtures.compiler.build_manifest(subset, policy, read_resource=store.read)
                        except fixtures.compiler.ManifestError as expected_error:
                            with self.assertRaises(LuaError) as actual_error:
                                port.build(subset, policy, read_resource=store.read)
                            self.assertIn(expected_error.code + ":", str(actual_error.exception))
                        else:
                            self.assertEqual(expected, port.build(subset, policy, read_resource=store.read))
                            if label != "whole profile":
                                compilable[label] = inputs[label]
                expected = fixtures.compiler.build_manifest(compilable, policy, read_resource=store.read)
                self.assertEqual(expected, port.build(compilable, policy, read_resource=store.read))
            for name, original in inputs.items():
                self.assertEqual(original, store.read(name))


if __name__ == "__main__":
    unittest.main()
