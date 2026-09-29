# Flail of the Ages: bounded item rebalance (2026-09-29)

Christopher approved implementation for the next CEBG release: retain +5 Free
Action while allowing Haste/Improved Haste, and give the on-hit Slow a save versus
breath at -2/+3, -4/both +4 versions, and -6/+5. Do not alter proc probability,
duration, damage, lower tiers, other Free Action sources or the global Slow spell.

## Provenance and inspected inputs

All reads were against `C:/Users/chris/Games/Chriz Easy BG/game`; no game file was
written. `research/originals/flail-ages/vanilla` contains exact KEY/BIF extracts:
`BLUN14` originates in base BG2 `data/Items.bif`, and `BLUN30`, `BLUN30C`,
`BLUN30D` originate in ToB `data/25Items.bif`. The matching `cebg` directory
contains effective override copies from the default EET/SR/SCS/Artisan install.
These captures are local research fixtures, not mod runtime payloads.

| Resource | Tier | Original SHA-256 |
|---|---|---|
| BLUN14 | +3 | 33e673d8c4c16f6b622d4923526e972dc12471209bca9cf5efa48c5a34caa6d2 |
| BLUN30C | +4 poison | 891c5d9fe52a0559036fcfcd75a544fc012e5fa4f5cf83de07dc0d69b1a5bbbd |
| BLUN30D | +4 electricity | 822fdd0159e8e5159c739ad8968b0287391585219feefa10d0259ed1083ad062 |
| BLUN30 | +5 | 19e8a5aa7065e1e620e445e4b2e90d7e478378940e7ef95ff8cc22a78ead9806 |

Read-only `UNINSTALL.*` records and the actual WeiDU order identify EE Fixpack 0,
UB 20 (ToB descriptions), Spell Revisions 0, Artisan 20000 (item usability), SCS
5900 (+5 detection markers) and finally SCS 8130 (troll riders) as relevant owners.
Ascension 0 also touches BLUN30. Final SCS troll damage helpers and Artisan opcode
319 usability restrictions must survive byte-for-byte. No change-log command was
run against the live game.

Each item has one melee ability, one opcode-40 Slow lasting 20 seconds and a
matching opcode-139 Slowed message (BG2 string 14000). The BIF probability window
is 0..33; effective EEFP/SR inputs use 0..32. Preserve the bytes, not an assumed
percentage. SR adds a matching opcode-221 Haste-secondary-type removal; that
removal and the Slowed message must receive the same save as Slow, so a successful
save neither strips Haste nor says Slowed. Damage and unrelated per-hit riders
must not gain a save. Existing resource immunities remain untouched.

SR allocates the Haste secondary type through `MSECTYPE.2DA` (`k1#Haste`, row 20
in the inspected install), not an IDS symbol. Resolve `WIZARD_HASTE` from the
installed `SPELL.IDS`, then read the effective SPL secondary byte at 0x27; do not
assume row 20. The same symbol lookup resolves Improved Haste. An unresolved
secondary type with a matching opcode-221 Slow rider fails before a partial
package can be installed.

## Free Action

The +5 item explicitly blocks opcode 16 and Haste spell resources and suppresses
the Haste icon/message; effective inputs also remove existing opcode-16 effects.
Its Hold/Slow/Web/Entangle immunities and movement protection are separate records.
IESDP confirms opcode 163 itself only removes certain movement-rate reductions,
not Haste: https://gibberlings3.github.io/iesdp/opcodes/bgee.htm#op163 .
Preserve it and harmful-impairment protections. Remove only the equipment-side
Haste blockers/removers and the neutral 100% movement reset. Preserve opcode-126
immunity: native Haste is opcode 16, and inspected SR Haste/Improved Haste use
opcode 176 for beneficial movement plus opcode 1 for APR. Both work without any
global spell patch. Unknown conflicting movement-immunity layouts are not an
invitation to broaden this component.

Klatu's `lib/freeAction.tpa` is useful prior art but is intentionally not reused:
it sweeps all ITMs/SPLs/CREs and repartitions movement opcodes globally. That is
beyond the approved item-only scope. This component uses original narrow code.

## Delivery and text contract

Component 302 (`cbr_flail_of_ages_rebalance`) is a late BG2EE/EET item patch; no
EEex requirement. Install after SR, SCS, item overhauls and description changes.
All four items must exist. Keep prior descriptions, replacing only the Slow line's
obsolete No Save wording and adding the save penalty; clarify +5 Free Action.
Allocate replacement descriptions locally through WeiDU and repoint only each
ITM's identified-description field, never STRING_SET shared strings or copy TLKs.

No save editing or hotpatch promise. Equipped effects can be baked into a save;
existing-save deployment needs separate review. This work is source/fixture
verification only until released and integrated.

## Verification (2026-09-29)

`python -m unittest tests.test_flail_of_ages -v`: **13/13 passed**, using the real
WeiDU 249 production TP2/component against disposable synthetic games:

- SR and non-SR; captured original BIF items and effective default CEBG items.
- Equipment-first and hit-first effect storage; exact byte-for-byte uninstall.
- Signed save penalties of −2/−4/−6 on Slow, its feedback and SR Haste removal;
  extension save flags preserved; all damage and unrelated hit effects unchanged.
- Every non-Haste equipment record preserved, including harmful-condition
  immunities, magic resistance, SCS detection and Artisan item usability.
- Lower tiers, foreign items, KEY/BIF and source SPLs unchanged.
- Repeat application under a second synthetic TP2 identity produces identical
  item and TLK bytes. Old TLK entries remain unchanged: new description references
  are allocated through `RESOLVE_STR_REF`, not shared-string overwrite.
- Missing items skip; ambiguous descriptions, unresolved SR Haste-removal type
  and unreviewed movement-immunity layouts reject with normal WeiDU rollback.
- Both native English and UB's `(No Save)` / `(no saving throw)` wording are
  replaced; the original lore and unrelated statistics remain untouched.

A separate disposable install used all four full current descriptions read from
the reference TLK, not just synthetic text, and passed the same preservation and
effect assertions. The source game was read-only. Both production TP2 and TPA
also pass WeiDU parse checks. No live-game combat, existing-save migration or
general third-party item-overhaul compatibility is claimed.

The current CEBG tail has no global Free Action tweak. Its later CDTweaks
2310/2311 modify SPL resources (including 2311's SPIN692 exception), not these
items; Klatu's selected armor-thieving component is unrelated. Therefore 302 fits
the existing late Rebalance run after EET_end/SCS. The owner must still package
and release this source before CEBG pins it.
