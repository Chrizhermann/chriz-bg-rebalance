"""Save-tool regressions use synthetic containers in disposable directories only."""
import contextlib
import io
import struct
import tempfile
import unittest
import zlib
from pathlib import Path
from unittest.mock import patch

from research.scripts import patch_sav_store as stock


def row(name, amount=1, infinite=0, flags=1):
    return struct.pack('<8sHHHHIII', name.encode('ascii'), 0, 1, 0, 0, flags, amount, infinite)


def store(rows=(), padding=b''):
    header = bytearray(0x9C)
    header[:8] = b'STORV1.0'
    start = len(header) + len(padding)
    end = start + len(rows) * stock.SALE_ENTRY
    struct.pack_into('<II', header, 0x34, start, len(rows))
    for field, offset in ((0x2C, end), (0x4C, end + 4), (0x70, end + 8)):
        struct.pack_into('<II', header, field, offset, 1)
    return bytes(header) + padding + b''.join(rows) + b'foreign sections'


def save(sto, usize=None):
    return stock.build_sav([
        ['RIBALD.STO', len(sto) if usize is None else usize, zlib.compress(sto)],
        ['AR0001.ARE', 7, zlib.compress(b'opaque\xff')],
    ])


class SaveStockTests(unittest.TestCase):
    def test_normal_missing_stock_matches_previous_insertion_bytes(self):
        before = store([row('OTHER')])
        expected = bytearray(before[:0xB8] + row('SCRL9Z', 5) + before[0xB8:])
        struct.pack_into('<I', expected, 0x38, 2)
        for field in (0x2C, 0x4C, 0x70):
            old = struct.unpack_from('<I', before, field)[0]
            struct.pack_into('<I', expected, field, old + stock.SALE_ENTRY)
        self.assertEqual(stock.sto_add_item(before, 'scrl9z', 5), bytes(expected))

    def test_edited_and_duplicate_stock_gets_one_decided_entry(self):
        for rows in (
            [row('scrl9z', 0, 1, 8)],
            [row('OTHER', 42), row('Scrl9z', 999), row('SCRL9Z', 2, 1), row('OTHER2', 3)],
        ):
            with self.subTest(rows=rows):
                before = store(rows, b'extra bytes')
                after = stock.sto_add_item(before, 'SCRL9Z', 5)
                offset, count = stock.sale_layout(after)
                actual = [after[i:i + 28] for i in range(offset, offset + count * 28, 28)]
                self.assertEqual(actual.count(row('SCRL9Z', 5)), 1)
                self.assertEqual([r for r in actual if stock.item_name(r) != 'SCRL9Z'],
                                 [r for r in rows if stock.item_name(r) != 'SCRL9Z'])
                self.assertEqual(after[0x9C:offset], b'extra bytes')
                for field, extra in ((0x2C, 0), (0x4C, 4), (0x70, 8)):
                    self.assertEqual(struct.unpack_from('<I', after, field)[0], offset + count * 28 + extra)
                self.assertTrue(after.endswith(b'foreign sections'))
                self.assertEqual(stock.sto_add_item(after, 'SCRL9Z', 5), after)

    def test_empty_zero_offset_sale_array_is_created(self):
        before = bytearray(store())
        struct.pack_into('<II', before, 0x34, 0, 0)
        after = stock.sto_add_item(bytes(before), 'SCRL9Z', 5)
        self.assertEqual(stock.sto_find_item(after, 'SCRL9Z')['amount'], 5)
        self.assertTrue(after[:0x34] == before[:0x34])

    def run_tool(self, root, *args):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            stock.main([str(root), 'ribald.sto', 'SCRL9Z', '5', *args])
        return output.getvalue()

    def write_save(self, root, name, payload):
        folder = root / name
        folder.mkdir()
        path = folder / 'BALDUR.SAV'
        path.write_bytes(payload)
        return path

    def test_apply_ignores_stale_size_and_preserves_first_backup_and_foreign_blob(self):
        with tempfile.TemporaryDirectory(prefix='cbr-save-stock-') as temporary:
            root = Path(temporary)
            original = save(store([row('SCRL9Z', 900, 1)]), usize=1)
            path = self.write_save(root, 'one', original)
            self.assertIn('PATCHED', self.run_tool(root, '--apply'))
            after = path.read_bytes()
            entries = stock.parse_sav(after)
            self.assertEqual(entries[1], stock.parse_sav(original)[1])
            payload = zlib.decompress(entries[0][2])
            self.assertEqual(len(payload), entries[0][1])
            self.assertEqual(stock.sto_find_item(payload, 'SCRL9Z'), {'index': 0, 'amount': 5, 'infinite': 0})
            backup = path.with_name('BALDUR.SAV.bak-cbr101')
            self.assertEqual(backup.read_bytes(), original)
            self.run_tool(root, '--apply')
            self.assertEqual(path.read_bytes(), after)
            self.assertEqual(backup.read_bytes(), original)

    def test_damaged_resources_and_saves_do_not_block_readable_neighbors(self):
        with tempfile.TemporaryDirectory(prefix='cbr-save-stock-') as temporary:
            root = Path(temporary)
            damaged = (b'', b'SAV V1.0\x01', b'SAV V1.0' + struct.pack('<I', 9000),
                       stock.build_sav([['RIBALD.STO', 1, b'bad zlib']]), save(b'too short'))
            for i, data in enumerate(damaged):
                self.write_save(root, str(i), data)
            good = self.write_save(root, 'z-good', save(store()))
            log = self.run_tool(root, '--apply')
            self.assertEqual(log.count('cannot read'), len(damaged))
            self.assertIn('z-good: PATCHED', log)
            self.assertEqual(stock.sto_find_item(zlib.decompress(stock.parse_sav(good.read_bytes())[0][2]),
                                                'SCRL9Z')['amount'], 5)
            for i, data in enumerate(damaged):
                self.assertEqual((root / str(i) / 'BALDUR.SAV').read_bytes(), data)

    def test_scan_exclusion_and_missing_target_do_not_write(self):
        with tempfile.TemporaryDirectory(prefix='cbr-save-stock-') as temporary:
            root = Path(temporary)
            original = save(store([row('SCRL9Z', 0)]))
            path = self.write_save(root, 'one', original)
            other = self.write_save(root, 'interval', original)
            absent = self.write_save(root, 'absent', stock.build_sav([['FOREIGN.STO', 3, b'xxx']]))
            log = self.run_tool(root)
            self.assertIn('amount=0 infinite=0; would write x5', log)
            self.assertEqual(path.read_bytes(), original)
            self.run_tool(root, '--apply', '--exclude', 'interval')
            self.assertEqual(other.read_bytes(), original)
            self.assertFalse(other.with_name('BALDUR.SAV.bak-cbr101').exists())
            self.assertEqual(stock.parse_sav(absent.read_bytes())[0][0], 'FOREIGN.STO')

    def test_failed_publish_leaves_original_and_backup_available(self):
        with tempfile.TemporaryDirectory(prefix='cbr-save-stock-') as temporary:
            root = Path(temporary)
            original = save(store())
            path = self.write_save(root, 'one', original)
            with patch.object(stock.os, 'replace', side_effect=OSError('publish unavailable')):
                self.assertIn('could not write', self.run_tool(root, '--apply'))
            self.assertEqual(path.read_bytes(), original)
            self.assertEqual(path.with_name('BALDUR.SAV.bak-cbr101').read_bytes(), original)
            self.assertEqual(list(path.parent.glob('.cbr-stock-*')), [])


if __name__ == '__main__':
    unittest.main()
