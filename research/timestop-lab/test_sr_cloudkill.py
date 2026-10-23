"""sr_cloudkill.py offline: SR's Cloudkill under lab names, against synthetic SR files and a
synthetic game whose BIF holds PROJECTL.IDS."""

from __future__ import annotations

import hashlib
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest import mock

sys.dont_write_bytecode = True
import sr_cloudkill as ck
from test_qa_menu import write_key_and_bif

STOCK_IDS = b"IDS V1.0\r\n0x0001 ARROW\r\n0x0002 ARROWEX\r\n186 CLOUDKIL\r\n345 RANGE10\r\n"


def spell() -> bytes:
    data = bytearray(0x72 + 0x28 + 2 * 0x30)
    data[:8] = b"SPL V1  "
    struct.pack_into("<iiii", data, 0x08, 13078, 9999999, 0, 0)
    struct.pack_into("<i", data, 0x50, 86012)
    struct.pack_into("<i", data, 0x54, 9999999)
    struct.pack_into("<IHI", data, 0x64, 0x72, 1, 0x9A)
    struct.pack_into("<HH", data, 0x72 + 0x1E, 2, 0)
    struct.pack_into("<H", data, 0x98, 299)
    struct.pack_into("<H", data, 0x9A, 12)
    struct.pack_into("<H", data, 0x9A + 0x30, 177)
    data[0x9A + 0x30 + 0x14:0x9A + 0x30 + 0x1C] = b"SPWI502I"
    return bytes(data)


def effect() -> bytes:
    data = bytearray(272)
    data[:8] = b"EFF V2.0"
    struct.pack_into("<I", data, 0x10, 206)
    data[0x30:0x37] = b"SPWI502"
    return bytes(data)


def projectile() -> bytes:
    data = bytearray(768)
    data[:8] = b"PRO V1.0"
    struct.pack_into("<H", data, 0x08, 3)
    return bytes(data)


class CloudkillTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory(prefix="cbr-sr-cloudkill-")
        self.addCleanup(directory.cleanup)
        root = Path(directory.name)
        self.game, self.sr = root / "game", root / "sr"
        self.game.mkdir()
        write_key_and_bif(self.game, [("PROJECTL", ck.IDS_TYPE, STOCK_IDS)])
        pins = {}
        for key, data in (("spl", spell()), ("eff", effect()), ("pro", projectile())):
            relative = ck.SOURCES[key][0]
            (self.sr / relative).parent.mkdir(parents=True, exist_ok=True)
            (self.sr / relative).write_bytes(data)
            pins[key] = (relative, hashlib.sha256(data).hexdigest())
        patcher = mock.patch.dict(ck.SOURCES, pins)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_builds_the_four_lab_files(self):
        out = Path(tempfile.mkdtemp(prefix="out-", dir=self.game.parent)) / "cloudkill"
        result = ck.build(self.game, self.sr, out)
        self.assertEqual((result["projectl_value"], result["spell_projectile"]), (346, 347))
        self.assertEqual(sorted(p.name for p in out.iterdir()),
                         ["CBRTSRCI.EFF", "CBRTSRCK.SPL", "DVCKILL.PRO", "PROJECTL.IDS"])
        spl = (out / "CBRTSRCK.SPL").read_bytes()
        self.assertEqual(struct.unpack_from("<H", spl, 0x98)[0], 347)
        self.assertEqual(spl[0x9A + 0x30 + 0x14:0x9A + 0x30 + 0x1C], b"CBRTSRCI")
        self.assertEqual(struct.unpack_from("<iiii", spl, 0x08)[:2] + struct.unpack_from("<ii", spl, 0x50), (-1,) * 4)
        # Everything else is SR's own bytes.
        original = bytearray(spell())
        for offset, size in ((0x08, 8), (0x50, 8), (0x98, 2), (0x9A + 0x30 + 0x14, 8)):
            original[offset:offset + size] = spl[offset:offset + size]
        self.assertEqual(spl, bytes(original))
        self.assertEqual((out / "CBRTSRCI.EFF").read_bytes()[0x30:0x38], b"CBRTSRCK")
        self.assertEqual((out / "DVCKILL.PRO").read_bytes(), projectile())
        self.assertEqual((out / "PROJECTL.IDS").read_bytes(), STOCK_IDS + b"346 DVCKILL\r\n")
        self.assertEqual(result["files"]["PROJECTL.IDS"], hashlib.sha256(STOCK_IDS + b"346 DVCKILL\r\n").hexdigest())
        with self.assertRaises(FileExistsError):
            ck.build(self.game, self.sr, out)

    def test_other_sr_bytes_are_refused(self):
        path = self.sr / ck.SOURCES["eff"][0]
        path.write_bytes(path.read_bytes() + b"\0")
        with self.assertRaisesRegex(ck.CloudkillError, "not the reviewed"):
            ck.describe(self.game, self.sr)

    def test_the_projectile_list_takes_the_next_value_once(self):
        ids, number = ck.projectile_list(b"IDS V1.0\n0x00FF HEX\n0099 PADDED\n12 LAST")
        self.assertEqual((number, ids), (256, b"IDS V1.0\n0x00FF HEX\n0099 PADDED\n12 LAST\n256 DVCKILL\n"))
        with self.assertRaisesRegex(ck.CloudkillError, "already lists"):
            ck.projectile_list(b"IDS V1.0\n346 DVCKILL\n")
        with self.assertRaisesRegex(ck.CloudkillError, "no entries"):
            ck.projectile_list(b"not an IDS\n")

    def test_an_unexpected_spell_is_refused(self):
        sources = {"spl": spell().replace(b"SPWI502I", b"SPWI999X"), "eff": effect(), "pro": projectile()}
        with self.assertRaisesRegex(ck.CloudkillError, "SPWI502I once"):
            ck.build_files(sources, STOCK_IDS)


if __name__ == "__main__":
    unittest.main()
