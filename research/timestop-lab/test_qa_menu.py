"""Offline checks of the QA UI.MENU builder; synthetic menus and resources only."""

from __future__ import annotations

from pathlib import Path
import struct
import sys
import tempfile
import unittest

sys.dont_write_bytecode = True
import qa_menu


def item(binding: qa_menu.Binding, action: str | None = None, extra: str = "") -> str:
    key = f'{binding.key} {binding.modifier} "{binding.value}"' if binding.modifier else \
        f"{binding.key} '{binding.value}'" if binding.key == "bam" else f'{binding.key} "{binding.value}"'
    return (f"\t{binding.kind}\n\t{{\n\t\tarea 1 2 3 4\n{extra}\t\t{key}\n\t\ttext style \"button\"\n"
            f"\t\taction \"{action if action is not None else binding.action}\"\n\t}}\n")


def synthetic(overrides: dict[str, str] | None = None, extra_items: dict[str, str] | None = None,
              newline: str = "\n", skip_menu: str | None = None) -> str:
    """A UI.MENU with every menu the builder needs, each binding's item once, plus decoys."""
    overrides, extra_items = overrides or {}, extra_items or {}
    menus = {}
    for menu in sorted({b.menu for b in qa_menu.BINDINGS} | set(qa_menu.POLLED_MENUS) | {qa_menu.IDLE_MENU}):
        menus[menu] = [f"\tlabel\n\t{{\n\t\tarea 0 0 10 10\n\t\ttext \"DECOY\"\n\t}}\n",
                       # A same-text item of another kind and braces inside a string are not structure.
                       "\tlabel\n\t{\n\t\ttext \"DONE_BUTTON\"\n\t\taction \"x = '{' y = '}'\"\n\t}\n"]
    for binding in qa_menu.BINDINGS:
        menus[binding.menu].append(overrides.get(binding.name, item(binding)))
    for menu, text in extra_items.items():
        menus[menu].append(text)
    out = ["`\nfunction unrelated() return '{' end\n`\n",
           "menu\n{\n\tname 'MESSAGE_SCREEN'\n}\nmenu\n{\n\tname 'MESSAGE_SCREEN'\n}\n"]
    for menu, items in menus.items():
        if menu != skip_menu:
            out.append(f"menu\n{{\n\tname '{menu}'\n\tonOpen \"-- {{ not a brace\"\n{''.join(items)}}}\n")
    return "".join(out).replace("\n", newline)


def binding(name: str) -> qa_menu.Binding:
    return next(b for b in qa_menu.BINDINGS if b.name == name)


class EnhanceTests(unittest.TestCase):
    def test_names_each_stock_item_and_adds_idle_label_and_polling_once(self):
        source = synthetic()
        enhanced, report = qa_menu.enhance(source)
        self.assertEqual([b["name"] for b in report["bindings"]], [b.name for b in qa_menu.BINDINGS])
        self.assertTrue(report["idle_label_added"])
        self.assertEqual(report["added_polling"], list(qa_menu.POLLED_MENUS))
        for b in qa_menu.BINDINGS:
            self.assertEqual(enhanced.count(f'name "{b.name}"'), 1, b.name)
        self.assertEqual(enhanced.count(f'name "{qa_menu.IDLE_NAME}"'), 1)
        self.assertEqual(enhanced.count('text lua "EEexRemote.Poll()"'), len(qa_menu.POLLED_MENUS))
        # Nothing else changes: removing the insertions restores the input byte for byte.
        stripped = enhanced
        for b in qa_menu.BINDINGS:
            stripped = stripped.replace(f'\n\t\tname "{b.name}"', "")
        stripped = stripped.replace('\ttext\n\t{\n\t\tarea 0 0 1 1\n\t\ttext lua "EEexRemote.Poll()"\n\t}\n', "")
        stripped = stripped.replace(f'\ttext\n\t{{\n\t\tname "{qa_menu.IDLE_NAME}"\n\t\tarea 0 0 1 1\n\t}}\n', "")
        self.assertEqual(stripped, source)

    def test_second_run_changes_nothing(self):
        enhanced, _ = qa_menu.enhance(synthetic())
        again, report = qa_menu.enhance(enhanced)
        self.assertEqual(again, enhanced)
        self.assertEqual((report["insertions"], report["added_polling"], report["idle_label_added"]), (0, [], False))

    def test_line_endings_are_kept(self):
        enhanced, _ = qa_menu.enhance(synthetic(newline="\r\n"))
        self.assertNotIn("\n", enhanced.replace("\r\n", ""))
        self.assertIn('\r\n\t\tname "CBRTSQA_NEW_GAME"', enhanced)

    def test_comments_and_spacing_do_not_count_but_code_does(self):
        new_game = binding("CBRTSQA_NEW_GAME")
        spaced = item(new_game, "\n\t\t\tInfinity_PopMenu(); -- close\n\t\t\tstartEngine:OnNewGameButtonClick();\n\t\t")
        enhanced, _ = qa_menu.enhance(synthetic({new_game.name: spaced}))
        self.assertIn('name "CBRTSQA_NEW_GAME"', enhanced)
        other = item(new_game, "Infinity_PopMenu(); FLPRUI_NewGame();")
        with self.assertRaisesRegex(qa_menu.MenuError, "Unexpected action for START_SP/CBRTSQA_NEW_GAME"):
            qa_menu.enhance(synthetic({new_game.name: other}))

    def test_quoted_text_inside_actions_is_part_of_the_code(self):
        soa = binding("CBRTSQA_SOA")
        changed = item(soa, soa.action.replace("START_MAIN", "START_SP"))
        with self.assertRaisesRegex(qa_menu.MenuError, "Unexpected action for START/CBRTSQA_SOA"):
            qa_menu.enhance(synthetic({soa.name: changed}))

    def test_missing_ambiguous_and_wrong_kind_items_are_refused(self):
        single = binding("CBRTSQA_SINGLE")
        with self.assertRaisesRegex(qa_menu.MenuError, "found 0"):
            qa_menu.enhance(synthetic({single.name: ""}))
        with self.assertRaisesRegex(qa_menu.MenuError, "found 2"):
            qa_menu.enhance(synthetic(extra_items={single.menu: item(single)}))
        as_label = item(single).replace("\tbutton\n", "\tlabel\n", 1)
        with self.assertRaisesRegex(qa_menu.MenuError, "found 0"):
            qa_menu.enhance(synthetic({single.name: as_label}))

    def test_missing_or_duplicate_required_menu_is_refused(self):
        with self.assertRaisesRegex(qa_menu.MenuError, "Required menu missing: WORLD_DIALOG"):
            qa_menu.enhance(synthetic(skip_menu="WORLD_DIALOG"))
        doubled = synthetic() + "menu\n{\n\tname 'CHAPTER'\n}\n"
        with self.assertRaisesRegex(qa_menu.MenuError, "Duplicate menu: CHAPTER"):
            qa_menu.enhance(doubled)

    def test_existing_names_are_respected_or_refused(self):
        done = binding("CBRTSQA_CHAPTER_DONE")
        same = item(done, extra=f'\t\tname "{done.name}"\n')
        enhanced, report = qa_menu.enhance(synthetic({done.name: same}))
        self.assertEqual(enhanced.count(f'name "{done.name}"'), 1)
        self.assertEqual(report["insertions"], len(qa_menu.BINDINGS) - 1 + 1 + len(qa_menu.POLLED_MENUS))
        other = item(done, extra='\t\tname "ALREADY_THERE"\n')
        with self.assertRaisesRegex(qa_menu.MenuError, "already-named"):
            qa_menu.enhance(synthetic({done.name: other}))
        collision = '\tlabel\n\t{\n\t\tname "CBRTSQA_CHAPTER_DONE"\n\t}\n'
        with self.assertRaisesRegex(qa_menu.MenuError, "Name collision: CBRTSQA_CHAPTER_DONE"):
            qa_menu.enhance(synthetic(extra_items={"CHARGEN": collision}))

    def test_idle_label_must_stay_inert(self):
        active = f'\ttext\n\t{{\n\t\tname "{qa_menu.IDLE_NAME}"\n\t\taction "startEngine:OnQuitButtonClick()"\n\t}}\n'
        with self.assertRaisesRegex(qa_menu.MenuError, "Refusing unexpected CBRTSQA_IDLE"):
            qa_menu.enhance(synthetic(extra_items={qa_menu.IDLE_MENU: active}))
        elsewhere = f'\ttext\n\t{{\n\t\tname "{qa_menu.IDLE_NAME}"\n\t}}\n'
        with self.assertRaisesRegex(qa_menu.MenuError, "Name collision: CBRTSQA_IDLE"):
            qa_menu.enhance(synthetic(extra_items={"CHAPTER": elsewhere}))


def write_key_and_bif(game: Path, entries: list[tuple[str, int, bytes]], key_entries=None) -> None:
    """A KEY V1 with one BIFF V1 holding ENTRIES; KEY_ENTRIES overrides the listed resources."""
    (game / "data").mkdir(parents=True)
    files, payload = [], b""
    for index, (_, kind, data) in enumerate(entries):
        files.append((index, kind, len(payload), data))
        payload += data
    table_offset = 20
    data_offset = table_offset + 16 * len(files)
    bif = bytearray(b"BIFFV1  " + struct.pack("<3I", len(files), 0, table_offset))
    for index, kind, offset, data in files:
        bif += struct.pack("<IIIHH", index, data_offset + offset, len(data), kind, 0)
    (game / "data" / "TEST.BIF").write_bytes(bytes(bif) + payload)
    listed = key_entries if key_entries is not None else [(name, kind, i) for i, (name, kind, _) in enumerate(entries)]
    name = b"data\\TEST.BIF\0"
    bif_table, res_table = 24, 24 + 12
    name_offset = res_table + 14 * len(listed)
    key = bytearray(b"KEY V1  " + struct.pack("<4I", 1, len(listed), bif_table, res_table))
    key += struct.pack("<IIHH", len(bif), name_offset, len(name), 1)
    for resref, kind, index in listed:
        key += struct.pack("<8sHI", resref.encode("ascii"), kind, index)
    (game / "chitin.key").write_bytes(bytes(key) + name)


class ResourceAndBuildTests(unittest.TestCase):
    def test_reads_the_listed_menu_resource_only(self):
        with tempfile.TemporaryDirectory(prefix="cbr-qa-key-") as directory:
            game = Path(directory)
            write_key_and_bif(game, [("UI", 0x3F3, b"not a menu"), ("UI", qa_menu.MENU_TYPE, b"menu bytes"),
                                     ("OTHER", qa_menu.MENU_TYPE, b"other")])
            data, source = qa_menu.read_key_resource(game, "ui", qa_menu.MENU_TYPE)
            self.assertEqual(data, b"menu bytes")
            self.assertEqual(source["bif"], "data/TEST.BIF")
            with self.assertRaisesRegex(qa_menu.MenuError, "lists 0 MISSING"):
                qa_menu.read_key_resource(game, "MISSING", qa_menu.MENU_TYPE)

    def test_ambiguous_or_mistyped_entries_are_refused(self):
        with tempfile.TemporaryDirectory(prefix="cbr-qa-key-") as directory:
            game = Path(directory)
            write_key_and_bif(game, [("UI", qa_menu.MENU_TYPE, b"a")],
                              key_entries=[("UI", qa_menu.MENU_TYPE, 0), ("UI", qa_menu.MENU_TYPE, 0)])
            with self.assertRaisesRegex(qa_menu.MenuError, "lists 2 UI"):
                qa_menu.read_key_resource(game, "UI", qa_menu.MENU_TYPE)
        with tempfile.TemporaryDirectory(prefix="cbr-qa-key-") as directory:
            game = Path(directory)
            write_key_and_bif(game, [("UI", 0x3F3, b"a")], key_entries=[("UI", qa_menu.MENU_TYPE, 0)])
            with self.assertRaisesRegex(qa_menu.MenuError, "no unambiguous UI entry"):
                qa_menu.read_key_resource(game, "UI", qa_menu.MENU_TYPE)

    def test_build_writes_once_and_describe_matches(self):
        with tempfile.TemporaryDirectory(prefix="cbr-qa-build-") as directory:
            root = Path(directory)
            game = root / "game"
            stock = synthetic(newline="\r\n").encode("utf-8")
            write_key_and_bif(game, [("UI", qa_menu.MENU_TYPE, stock)])
            data, description = qa_menu.describe(game)
            result = qa_menu.build(game, root / "out")
            self.assertEqual((root / "out" / "UI.MENU").read_bytes(), data)
            self.assertEqual(result["sha256"], description["sha256"])
            self.assertEqual(result["stock_sha256"], __import__("hashlib").sha256(stock).hexdigest())
            self.assertEqual(stock, (game / "data" / "TEST.BIF").read_bytes()[-len(stock):])
            with self.assertRaises(FileExistsError):
                qa_menu.build(game, root / "out")
            with self.assertRaisesRegex(qa_menu.MenuError, "absolute path"):
                qa_menu.build(game, Path("relative-out"))
            with self.assertRaisesRegex(qa_menu.MenuError, "parent must already exist"):
                qa_menu.build(game, root / "missing" / "out")


if __name__ == "__main__":
    unittest.main()
