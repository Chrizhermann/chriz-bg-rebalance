"""Build this lab's QA copy of UI.MENU, so a hidden run can click the game's own buttons.

Usage:
  python -B research/timestop-lab/qa_menu.py describe GAME_DIRECTORY
  python -B research/timestop-lab/qa_menu.py build GAME_DIRECTORY OUTPUT_DIRECTORY

A hidden lab game gets no mouse. The Remote Console queues the normal click of a stock
button with Infinity_ClickItem(nameToItem[...]), which needs a named item, and it only
listens while one of its host menus (START, WORLD_ACTIONBAR) renders. The QA copy:

* names stock items whose menu, kind, identifying property and action all match exactly;
  any other item, and every action, stays as it is;
* adds one inert 1x1 text to START: on 2.7.3 a campaign choice finishes only on the next
  mouse event, which a queued click on it provides;
* adds a 1x1 ``EEexRemote.Poll()`` text to the menus that are on top while a new game is
  created and entered, so console requests are admitted there too.

The input is the stock UI.MENU from the lab's own chitin.key and BIF, read only. The output
is created exclusively; nothing is launched, installed or overwritten. Adapted from
tools/stage_fixture_qa_menu.py of Chrizhermann/bgee-itemrandomiser-fix.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
import stat
import struct
import sys


MENU_TYPE = 0x408  # Enhanced Edition MENU resource type in chitin.key.


class MenuError(ValueError):
    """The input cannot be enhanced unambiguously."""


@dataclass(frozen=True)
class Token:
    kind: str
    value: str
    start: int
    end: int


@dataclass(frozen=True)
class Binding:
    """One stock item to name: its menu, item kind, identifying property and exact action."""

    menu: str
    name: str
    kind: str
    key: str
    modifier: str | None
    value: str
    action: str


COLOR_DONE = """
    SLIDER_color_hair_start = SLIDER_color_hair
    SLIDER_color_skin_start = SLIDER_color_skin
    SLIDER_color_major_start = SLIDER_color_major
    SLIDER_color_minor_start = SLIDER_color_minor
    if (e:GetActiveEngine() == createCharScreen) then
        createCharScreen:OnDoneButtonClick()
    end
    Infinity_PopMenu('CHARACTER_COLOR',0,0)
"""
DIALOG_CONFIRM = """
    if(gameOptions.m_bConfirmDialog == true and (#worldPlayerDialogChoices > 0)) then
        worldScreen:OnDialogReplyClick(worldPlayerDialogChoices[worldPlayerDialogSelection].marker)
        worldPlayerDialogSelection = 0
    else
        worldScreen:StepDialog()
    end
"""

# BG2:EE 2.7.3.0 stock items on the way from the main menu into a new Shadows of Amn game.
BINDINGS = (
    Binding("START", "CBRTSQA_SOA", "text", "bam", None, "LOGOSOA",
            "logoFrame = 0 startEngine:OnSoAButtonClick(true) Infinity_PushMenu('START_MAIN')"),
    Binding("START_MAIN", "CBRTSQA_SINGLE", "button", "text", None, "SINGLEPLAYER_BUTTON",
            "startEngine:SetEngineState(1) Infinity_TransitionMenu('START_SP')"),
    Binding("START_SP", "CBRTSQA_NEW_GAME", "button", "text", None, "NEW_GAME_BUTTON",
            "Infinity_PopMenu(); startEngine:OnNewGameButtonClick();"),
    Binding("CHARGEN", "CBRTSQA_CG_IMPORT", "button", "text", None, "IMPORT_BUTTON",
            "createCharScreen:OnImportCharacterButtonClick()"),
    Binding("CHARGEN", "CBRTSQA_CG_APPEARANCE", "button", "text", None, "APPEARANCE_BUTTON",
            "createCharScreen:OnMenuButtonClick()"),
    Binding("CHARGEN", "CBRTSQA_CG_NAME", "button", "text", None, "NAME_BUTTON",
            "createCharScreen:OnMenuButtonClick()"),
    Binding("CHARGEN", "CBRTSQA_CG_ACCEPT", "button", "text", "lua", "chargenAcceptOrExport()",
            "createCharScreen:AcceptCharacter(-1)"),
    Binding("POPUP_THREEBUTTON", "CBRTSQA_POPUP3_MID", "button", "text", "lua",
            "getUiString(Popup3Button.midText)",
            "Infinity_PopMenu() if (Popup3Button.midFunc) then Popup3Button.midFunc() end"),
    Binding("CHARACTER_SELECT", "CBRTSQA_CS_DONE", "button", "text", None, "DONE_BUTTON",
            "createCharScreen:OnDoneButtonClick() Infinity_PopMenu('CHARACTER_SELECT')"),
    Binding("CHARACTER_COLOR", "CBRTSQA_COLOR_DONE", "button", "text", None, "DONE_BUTTON", COLOR_DONE),
    Binding("CHARGEN_CUSTOMSOUNDS", "CBRTSQA_SOUNDS_DONE", "button", "text", None, "DONE_BUTTON",
            "Infinity_PopMenu(); createCharScreen:OnDoneButtonClick()"),
    Binding("CHARGEN_NAME", "CBRTSQA_NAME_DONE", "button", "text", None, "DONE_BUTTON",
            "Infinity_PopMenu(); createCharScreen:OnDoneButtonClick()"),
    Binding("CHARGEN_DIFFICULTY", "CBRTSQA_DIFF_VENTURE", "button", "text", "lua",
            "getUiString('VENTURE_FORTH')",
            "Infinity_PopMenu() createCharScreen:AcceptCharacter(currentDifficulty)"),
    Binding("CHAPTER", "CBRTSQA_CHAPTER_DONE", "button", "text", None, "DONE_BUTTON",
            "chapterScreen:OnDoneButtonClick()"),
    Binding("WORLD_DIALOG_CONFIRM", "CBRTSQA_DIALOG_CONFIRM", "button", "text", "lua", "dialogButtonText",
            DIALOG_CONFIRM),
    # Saving and loading: the quick save button of the world's left sidebar, Load Game in
    # START_SP and the LOAD screen's Load button (the save is chosen in its variable first).
    Binding("LEFT_SIDEBAR_BOTTOM", "CBRTSQA_QUICKSAVE", "button", "tooltip", "lua", "getTooltipWithHotkey(28,74261)",
            "worldScreen:OnQuickSaveButtonClick(false)"),
    Binding("START_SP", "CBRTSQA_LOAD_GAME", "button", "text", None, "LOAD_GAME_BUTTON",
            "Infinity_PopMenu(); startEngine:OnLoadGameButtonClick()"),
    Binding("LOAD", "CBRTSQA_LOAD", "button", "text", None, "LOAD_BUTTON",
            "loadScreen:LoadGame(gameSaves.files[currentSave].fileName)"),
)
IDLE_MENU, IDLE_NAME = "START", "CBRTSQA_IDLE"
# START and WORLD_ACTIONBAR already host the console's own menu. WORLD_ACTIONBAR polls here
# too, so a host-menu stack quirk cannot leave the console deaf in the world.
POLLED_MENUS = (
    "START_MAIN", "START_SP", "CHARGEN", "POPUP_THREEBUTTON", "CHARACTER_SELECT", "CHARACTER_COLOR",
    "CHARGEN_CUSTOMSOUNDS", "CHARGEN_NAME", "CHARGEN_DIFFICULTY", "CHAPTER", "WORLD_DIALOG",
    "WORLD_ACTIONBAR", "LOAD",
)
POLL = "EEexRemote.Poll()"


def tokenize(source: str) -> list[Token]:
    """Keep DSL strings and backtick Lua opaque, so their braces are never structure."""
    tokens = []
    position = 0
    while position < len(source):
        start = position
        char = source[position]
        if char.isspace() or char == "\ufeff":
            position += 1
        elif source.startswith("--", position):
            long_comment = re.match(r"--\[(=*)\[", source[position:])
            if long_comment:
                close = "]" + long_comment[1] + "]"
                end = source.find(close, position + len(long_comment[0]))
                if end < 0:
                    raise MenuError("Unterminated long comment")
                position = end + len(close)
            else:
                end = source.find("\n", position)
                position = len(source) if end < 0 else end
        elif char in "\"'`":
            delimiter = char
            position += 1
            while position < len(source):
                if source[position] == "\\" and delimiter != "`":
                    position += 2
                elif source[position] == delimiter:
                    position += 1
                    break
                else:
                    position += 1
            else:
                raise MenuError("Unterminated quoted string or Lua block")
            tokens.append(Token("lua" if delimiter == "`" else "string",
                                source[start + 1:position - 1], start, position))
        elif char in "{}":
            tokens.append(Token(char, char, start, start + 1))
            position += 1
        else:
            while (position < len(source) and not source[position].isspace()
                   and source[position] not in "{}\"'`"):
                position += 1
            tokens.append(Token("word", source[start:position], start, position))
    return tokens


def blocks(tokens: list[Token]) -> dict[int, int]:
    stack, ends = [], {}
    for index, token in enumerate(tokens):
        if token.kind == "{":
            stack.append(index)
        elif token.kind == "}":
            if not stack:
                raise MenuError("Unmatched closing brace")
            ends[stack.pop()] = index
    if stack:
        raise MenuError("Unclosed menu block")
    return ends


def direct_tokens(tokens: list[Token], ends: dict[int, int], opening: int) -> list[Token]:
    direct = []
    index = opening + 1
    while index < ends[opening]:
        if tokens[index].kind == "{":
            index = ends[index] + 1
        else:
            direct.append(tokens[index])
            index += 1
    return direct


def property_values(tokens: list[Token], key: str, modifier: str | None = None,
                    words: bool = False) -> list[str]:
    """Values of KEY [MODIFIER] "value"; WORDS also accepts unquoted values (bam GUIOSTUM)."""
    values = []
    for index, token in enumerate(tokens):
        if token.kind != "word" or token.value.lower() != key.lower():
            continue
        value_index = index + 1
        if modifier is not None:
            if value_index >= len(tokens) or tokens[value_index].value.lower() != modifier:
                continue
            value_index += 1
        elif value_index < len(tokens) and tokens[value_index].kind == "word" and \
                tokens[value_index].value.lower() in ("lua", "style", "align", "color", "point"):
            continue
        if value_index < len(tokens) and (tokens[value_index].kind == "string" or
                                          (words and tokens[value_index].kind == "word")):
            values.append(tokens[value_index].value)
    return values


def lua_signature(source: str) -> str:
    """Compare Lua by its code alone: quoted text stays intact, comments and spacing do not count."""
    pieces = []
    pattern = r"--[^\r\n]*|'(?:\\.|[^'\\])*'|\"(?:\\.|[^\"\\])*\"|\s+|."
    for match in re.finditer(pattern, source, re.DOTALL):
        piece = match[0]
        if not piece.startswith("--") and not piece.isspace():
            pieces.append(piece)
    return "".join(pieces)


def _menus(tokens: list[Token], ends: dict[int, int]) -> tuple[dict[str, int], set[str], list[str]]:
    menus, duplicates, all_names = {}, set(), []
    for opening in ends:
        direct = direct_tokens(tokens, ends, opening)
        all_names.extend(property_values(direct, "name"))
        if opening and tokens[opening - 1].value.lower() == "menu":
            names = property_values(direct, "name")
            if len(names) != 1:
                raise MenuError("Menu must have exactly one quoted name")
            if names[0] in menus:
                duplicates.add(names[0])
            menus[names[0]] = opening
    return menus, duplicates, all_names


def _children(tokens: list[Token], ends: dict[int, int], opening: int):
    """(kind, opening index) of a menu's direct item blocks."""
    index = opening + 1
    while index < ends[opening]:
        if tokens[index].kind == "{":
            yield tokens[index - 1].value.lower(), index
            index = ends[index] + 1
        else:
            index += 1


def enhance(source: str) -> tuple[str, dict]:
    """Return the QA copy and a report; an already enhanced input comes back unchanged."""
    tokens = tokenize(source)
    ends = blocks(tokens)
    menus, duplicates, all_names = _menus(tokens, ends)
    needed = {binding.menu for binding in BINDINGS} | set(POLLED_MENUS) | {IDLE_MENU}
    missing = sorted(needed - set(menus))
    if missing:
        raise MenuError(f"Required menu missing: {missing[0]}")
    # A stock UI.MENU may define an unrelated menu twice; the menus used here must be unambiguous.
    if duplicates & needed:
        raise MenuError(f"Duplicate menu: {sorted(duplicates & needed)[0]}")
    newline = "\r\n" if "\r\n" in source else "\n"
    edits, named = [], []
    for binding in BINDINGS:
        candidates = []
        for kind, opening in _children(tokens, ends, menus[binding.menu]):
            if kind != binding.kind:
                continue
            direct = direct_tokens(tokens, ends, opening)
            values = property_values(direct, binding.key, binding.modifier, words=binding.key == "bam")
            if values == [binding.value]:
                candidates.append((opening, direct))
        if len(candidates) != 1:
            raise MenuError(f"Expected exactly one {binding.kind} for {binding.menu}/{binding.name}; "
                            f"found {len(candidates)}")
        opening, direct = candidates[0]
        actions = property_values(direct, "action")
        if len(actions) != 1 or lua_signature(actions[0]) != lua_signature(binding.action):
            raise MenuError(f"Unexpected action for {binding.menu}/{binding.name}")
        names = property_values(direct, "name")
        if sum(t.kind == "word" and t.value.lower() == "name" for t in direct) != len(names):
            raise MenuError(f"Refusing unexpected unquoted name: {binding.menu}/{binding.name}")
        if names and names != [binding.name]:
            raise MenuError(f"Refusing already-named item: {binding.menu}/{names}")
        if all_names.count(binding.name) != (1 if names else 0):
            raise MenuError(f"Name collision: {binding.name}")
        if not names:
            edits.append((tokens[opening].end, newline + f'\t\tname "{binding.name}"'))
        named.append({"menu": binding.menu, "name": binding.name})
    idle_added = False
    if IDLE_NAME in all_names:
        owners = [kind_opening for kind_opening in _children(tokens, ends, menus[IDLE_MENU])
                  if property_values(direct_tokens(tokens, ends, kind_opening[1]), "name") == [IDLE_NAME]]
        if all_names.count(IDLE_NAME) != 1 or len(owners) != 1:
            raise MenuError(f"Name collision: {IDLE_NAME}")
        kind, opening = owners[0]
        direct = direct_tokens(tokens, ends, opening)
        if kind != "text" or property_values(direct, "action") or property_values(direct, "text", "lua"):
            raise MenuError(f"Refusing unexpected {IDLE_NAME} item")
    else:
        edits.append((tokens[ends[menus[IDLE_MENU]]].start,
                      f'\ttext{newline}\t{{{newline}\t\tname "{IDLE_NAME}"{newline}'
                      f'\t\tarea 0 0 1 1{newline}\t}}{newline}'))
        idle_added = True
    added_polling = []
    for menu in POLLED_MENUS:
        existing = any(lua_signature(value) == POLL
                       for _, opening in _children(tokens, ends, menus[menu])
                       for value in property_values(direct_tokens(tokens, ends, opening), "text", "lua"))
        if not existing:
            edits.append((tokens[ends[menus[menu]]].start,
                          f'\ttext{newline}\t{{{newline}\t\tarea 0 0 1 1{newline}'
                          f'\t\ttext lua "{POLL}"{newline}\t}}{newline}'))
            added_polling.append(menu)
    for position, insertion in sorted(edits, key=lambda edit: edit[0], reverse=True):
        source = source[:position] + insertion + source[position:]
    return source, {"bindings": named, "idle_label_added": idle_added, "added_polling": added_polling,
                    "insertions": len(edits)}


def _reject_linked_path(path: Path) -> None:
    for candidate in (*reversed(path.parents), path):
        try:
            metadata = candidate.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(metadata.st_mode) or (
                getattr(metadata, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)):
            raise MenuError(f"linked/reparse path rejected: {candidate}")


def read_key_resource(game: Path, resref: str, resource_type: int) -> tuple[bytes, dict]:
    """One resource from chitin.key and its uncompressed BIFF V1 file; read only."""
    key = (game / "chitin.key").read_bytes()
    if len(key) < 24 or key[:8] != b"KEY V1  ":
        raise MenuError("chitin.key is not KEY V1")
    bif_count, resource_count, bif_offset, resource_offset = struct.unpack_from("<4I", key, 8)
    if bif_offset + 12 * bif_count > len(key) or resource_offset + 14 * resource_count > len(key):
        raise MenuError("chitin.key tables exceed the file")
    hits = []
    for index in range(resource_count):
        name, kind, locator = struct.unpack_from("<8sHI", key, resource_offset + 14 * index)
        if kind == resource_type and name.rstrip(b"\0").decode("ascii", "replace").upper() == resref.upper():
            hits.append(locator)
    if len(hits) != 1:
        raise MenuError(f"chitin.key lists {len(hits)} {resref} resources of type {resource_type:#x}")
    locator = hits[0]
    bif_index, file_index = locator >> 20, locator & 0x3FFF
    if bif_index >= bif_count:
        raise MenuError("Resource locator names a missing BIF")
    _, name_offset, name_length, _ = struct.unpack_from("<IIHH", key, bif_offset + 12 * bif_index)
    if name_offset + name_length > len(key):
        raise MenuError("BIF name exceeds chitin.key")
    relative = key[name_offset:name_offset + name_length].rstrip(b"\0").decode("ascii").replace("\\", "/")
    bif_path = game / relative
    if ".." in Path(relative).parts or Path(relative).is_absolute():
        raise MenuError("BIF path leaves the game directory")
    bif = bif_path.read_bytes()
    if len(bif) < 20 or bif[:8] != b"BIFFV1  ":
        raise MenuError(f"{relative} is not an uncompressed BIFF V1")
    file_count, _, file_offset = struct.unpack_from("<3I", bif, 8)
    if file_offset + 16 * file_count > len(bif):
        raise MenuError(f"{relative} file table exceeds the BIF")
    found = []
    for index in range(file_count):
        entry_locator, offset, size, kind, _ = struct.unpack_from("<IIIHH", bif, file_offset + 16 * index)
        if entry_locator & 0x3FFF == file_index:
            found.append((offset, size, kind))
    if len(found) != 1 or found[0][2] != resource_type or found[0][0] + found[0][1] > len(bif):
        raise MenuError(f"{relative} has no unambiguous {resref} entry")
    offset, size, _ = found[0]
    return bif[offset:offset + size], {"bif": relative, "locator": locator}


def describe(game: Path | str) -> tuple[bytes, dict]:
    """The QA copy's bytes and its JSON description; nothing is written."""
    game = Path(game)
    stock, source = read_key_resource(game, "UI", MENU_TYPE)
    try:
        text = stock.decode("utf-8")
    except UnicodeDecodeError as error:
        raise MenuError(f"Stock UI.MENU is not UTF-8: {error}") from error
    enhanced, report = enhance(text)
    data = enhanced.encode("utf-8")
    return data, {"sha256": hashlib.sha256(data).hexdigest(), "size": len(data),
                  "stock_sha256": hashlib.sha256(stock).hexdigest(), "source": source, **report}


def build(game: Path | str, output_directory: Path | str) -> dict:
    """Write OUTPUT_DIRECTORY/UI.MENU exclusively; the directory's parent must exist."""
    output = Path(output_directory)
    if not output.is_absolute() or ".." in output.parts:
        raise MenuError("Output directory must be an absolute path without '..'")
    _reject_linked_path(output)
    if not output.parent.is_dir():
        raise MenuError("Output directory's parent must already exist")
    if output.exists() and not output.is_dir():
        raise MenuError("Output destination is not a directory")
    data, description = describe(game)
    output.mkdir(exist_ok=True)
    target = output / "UI.MENU"
    if any(entry.name.casefold() == "ui.menu" for entry in output.iterdir()):
        raise FileExistsError(f"Refusing to overwrite {target}")
    with target.open("xb") as handle:
        handle.write(data)
    return {"output": str(target), **description}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("describe").add_argument("game", type=Path)
    build_parser = commands.add_parser("build")
    build_parser.add_argument("game", type=Path)
    build_parser.add_argument("output_directory", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "describe":
            print(json.dumps(describe(args.game)[1], separators=(",", ":")))
        else:
            print(json.dumps(build(args.game, args.output_directory), separators=(",", ":")))
    except (OSError, UnicodeError, MenuError) as error:
        print(f"CBR_QA_MENU_ERROR: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
