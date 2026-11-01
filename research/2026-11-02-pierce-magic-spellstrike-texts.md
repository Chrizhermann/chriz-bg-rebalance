# Pierce Magic and Spellstrike: descriptions that disagree with the effects (210, 211)

Date: 2026-11-02. Reported by Christopher on stream: the Pierce Magic spellbook text
lacks the detailed header and intro that every other Spell Revisions spell has, and the
scroll still describes another mechanic. Diagnosis by the collection coordinator on
copies of the stream game and of the CEBG 0.1.0 final lab (read only); nothing in either
game was changed.

## Findings

Component 210 changes Pierce Magic's mechanic (MR reduced by half for 5 rounds, at least
10, at most 40 points) and 211 changes Spellstrike's (15% arcane/divine spell failure for
2 rounds). Both replaced only the parent spell's description, with a short text that had
no header. Everything else that shows the old mechanic kept Spell Revisions' (or
vanilla's) text:

| Resource | Shows | Stale since 210 / 211 |
|---|---|---|
| `SCRL7L` Scroll of Pierce Magic | SR text: MR "nullified … 2 rounds" | yes |
| `SCRL9M` Scroll of Spellstrike | SR text: "100% … then 50%" | yes |
| `WAND18` Wand of Spell Striking | vanilla charge line "−20% for 2 turns" | yes (already wrong under SR) |
| `C0MK#009` Kitpack monk Spellstrike (spell) | SR text "100% … 50%" | yes |
| `DW#WNDSS` SCS wand spell | SR text | hidden, never shown |
| `SPWI608B/C`, `SPWI903B/C` | SR text | hidden payload spells |
| `IRENPRCE` | own inline MR effects, own text | correct, untouched |

Item and spell links were found by scanning effects (opcodes 146, 147, 148) in the CEBG
0.1.0 lab and in the stream game: both have exactly `SCRL7L`, `SCRL9M`, `WAND18` as items
and `C0MK#009`, `DW#WNDSS` as sibling spells. SR shares one description strref between a
spell, its payload spells and its scroll; that is how the old text is recognized.

## Layout (Spell Revisions' standard)

Name line, then Level, School, Range, Duration, Casting Time, Area of Effect, Saving Throw
(one per line), a blank line, the intro paragraph, the protections list, the remaining
mechanics and a Note about invisible targets. The header values are SR's own for these
spells and match the installed spell data (read from the CEBG lab and the stream game):

| | Pierce Magic `SPWI608` | Spellstrike `SPWI903` |
|---|---|---|
| Level (SPL 0x34) | 6 | 9 |
| School (0x25) | 1, Abjurer = Abjuration | 1 |
| Range (ability range) | 30 = "Long" (SR labels 30 as Long on 69 spells) | 30 |
| Casting time (ability speed) | 6 | 5 |
| Duration | Special (SR's value; the effect lengths are in the body) | Special |

Duration stays "Special" because the spell is instant (protection removal) and the timed
part is carried by the payload; the Garithos tail's Spellstrike text, the model for this
layout, did the same. The protections list is SR's, unchanged: the payload's protection
removal (`op230 8,1`; `op221 9,1`) was not touched by 210/211.

## What changed

- `lib/sr_antimagic.tpa`: both components now write the layout text (`setup.tra` `@2100`,
  `@2110`; the Note paragraph `@2102` only when the spell can target invisible creatures,
  as before), then:
  - **Items that learn or cast the parent** (opcodes 147/146/148) and still show an old
    description get the new strref (identified and unidentified description). "Old" is
    any strref that the parent, the effective payload or its linked spells carried before,
    or any string with the same long text. An item with other text keeps it and the
    installer prints its name.
  - **Wands** that reach the payload through a sibling spell (a spell that casts the family,
    found by the same scan) get a private copy of their text with only this spell's
    `Special:` value replaced, when the entry is recognizable (`<name>` line, then
    `Special:` mentioning the old mechanic). Otherwise the text stays and the installer
    prints the item.
  - **Sibling spells** that cast the family and share an old description are repointed
    (Kitpack's monk Spellstrike).
  - The hidden payload spells keep their old strref on purpose: that is how a later texts-only
    run on an already changed installation finds what is stale.
- `live-patch/CBR_SR_ANTIMAGIC`: new components **212** and **213**, texts only, for an
  installation that already has the changed mechanic from any source (the main installer,
  the 210/211 tail, a private tail). They refuse a payload without the changed mechanic
  (`CBRPM` callback for 212, 15% failure for 213). 213 keeps a Spellstrike text that already
  has the layout and states the 15% (the Garithos tail's), and points scrolls and sibling
  spells at it.

## Evidence

Automated: `tests/test_sr_antimagic_installer.py` (WeiDU on synthetic games): layout of
both strings, scroll sharing the strref, scroll with its own text, scroll with a copy of
the text under another strref, a scroll rewritten by another mod, wand line present,
unrecognizable and absent, items with inline MR effects, unrelated items, sibling spell,
malformed items and spells, second install and uninstall, direct (child-less) SR payloads,
the texts-only components over a private tail and over the main installer, and their
refusal without the mechanic or without Spell Revisions.

Not tested: a localized game (the texts are English, as before), live display in the game,
other languages' wand charge lines (left alone with a note), a chain of more than one
sibling spell between the item and the payload.
