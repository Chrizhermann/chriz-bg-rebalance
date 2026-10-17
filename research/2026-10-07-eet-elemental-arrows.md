# EET elemental arrows — public component 130

Component 130 promotes the approved, tested October 3 private repair without
changing its scope. SCS 35.21's elemental-arrows component 3017 has an EET
exclusion; EET v14 keeps the BG1 arrow damage. The captured BG2 ITEMS.BIF
independently established the intended acid 1d3, cold 1d2 and fire 1d2 values.

The public adaptation requires EET and SCS general spell tweaks (2000).
AROW04 becomes 1d3 acid; AROW09 becomes 1d2 cold; AROW08/AROWKC become 1d2
fire and lose their +2 attack/physical-damage bonuses. Fire dice are written
explicitly because upstream SCS's code does not perform that advertised change.
Original save fields, SCS troll helpers and all other bytes except local
name/description pointers remain. Other special arrows, including ARROPHE2,
are outside the allowlist. English descriptions retain surrounding text.

Private source/evidence: collection
`target/work/oct03-current-game-fixes/arrows`, retained locally and not shipped.
That adapter passed real-WeiDU capture installation, idempotence, all old TLK
entry preservation, exact item uninstall and late-failure rollback before its
approved application. Public synthetic tests independently cover the four
transformations, exact byte delta, saves/helpers, exclusions, missing SCS and
malformed-last-item rollback. No new game or save was modified for publication.

This is an EET implementation of the user's chosen SCS balance rule, not a new
global item overhaul or a claim that upstream SCS 3017 now supports EET.

## 2026-10-17: behavior-based matching (audit 2026-10-08, item 3)

The balance values are unchanged; the input matching no longer fingerprints
the captured shape. Per extended header, the elemental package is the opcode-12
record with the component's damage type (param2 high word), normal damage mode
(low word 0) and projectile target (2). Only its dice are owned (1d3 acid,
1d2 cold/fire); fire also owns the to-hit/damage bonus of the headers that
carry the package. Other damage types (an acid rider on a fire arrow),
same-element records with other delivery, helpers and headers without the
package stay byte-identical, whatever their type or order. Two package records
in one header are ambiguous (writing both multiplies damage) and fail the
component; malformed tables still fail. Validation of all four items runs
before any item or TLK string is written. An item without any package is left
unchanged with a warning. Description edits are derived from the old and new
values; text that states other values or uses other wording is left unchanged
with a warning. The reference install's AROWKC text ("+1d2 fire damage", no
THAC0 line) is accepted as already correct apart from the breath save.
Evidence: synthetic real-WeiDU tests in `tests/test_elemental_arrows.py`; no
game or save was used.

## 2026-10-17: owned ability and owned text clauses (review findings A and B)

An independent source review found two defects in the behavior-based matcher.

A. The classifier never checked the ability type, so a separate type-3
activation dealing fire damage was also reduced to 1d2 and lost its bonuses.
The owned ability is now the arrow's own hit only: every ITM extended header
with attack type 2 (ranged, byte 0x00) and launcher 1 (bow, byte 0x10), which
is what the reference AROW04/08/09/KC carry. Activations, melee headers and
ranged headers without the bow launcher keep every byte, in any order and
number. Several bow-fired headers with the package are all patched, as
before. An item whose only package sits on another header warns, names how
many such records were left alone and stays unchanged.

B. The description rewrite stripped every `NdM+K` bonus and changed every
"Save vs. Spell" for the kobold arrow, so a preserved `+1d4+2 acid damage`
rider lost its `+2` and unrelated save claims became Breath. Only the owned
clauses change now: the one "+NdM <element> damage" clause, the save
statement attached to it, the one weapon-damage bonus (riders written as
"+NdM+K" or followed by a non-physical "<type> damage" are never touched) and
the one THAC0 claim. An owned claim stated more than once leaves the text
unchanged with a warning. A "Save vs. Spell" claim elsewhere in a breath-save
arrow's text is kept with a warning. The female string (dialogF.tlk, present
for several EE languages) is rewritten from its own text instead of
receiving the male result; if either string cannot be rewritten, neither
changes. Unrecognized bonus wording can still stay stale (known limitation).
Evidence: `tests/test_elemental_arrows.py`, synthetic real-WeiDU games only.
