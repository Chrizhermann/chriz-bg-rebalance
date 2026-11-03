# Flail of the Ages: bounded item rebalance (2026-09-29)

Christopher approved implementation for the next CEBG release: retain +5 Free
Action while allowing Haste/Improved Haste, and give the on-hit Slow a save versus
breath at -2/+3, -4/both +4 versions, and -6/+5. Do not alter proc probability,
duration, damage, lower tiers, other Free Action sources or the global Slow spell.

## SCS without SR — 2026-11-03 (unreleased)

A CEBG install of BG2:EE/EET 2.7.3.0 with SCS 35.21 and without Spell Revisions
rolled back at 302: `BLUN14.SPL mixes Slow with other effects, additional saves,
or a different recipient/projectile`. The pre-302 override resources of that
install were captured and read; they are not committed (third-party data).

### Provenance

The layout comes from SCS's spell tweak `haste_cancels_slow` ("Haste and Slow
effects cancel; slow always gives AC and THAC0 penalties", `spelltweaks.2da`
compatibility `not_sr,ee`), installed by SCS component 2000 ("Install all spell
tweaks", the only SCS spell-tweak component in that WeiDU.log). Its source
(`stratagems/spell/haste_cancels_slow.tpa`, `lib/bg/slow_fixes.tph`,
`sfo2e/lib_opcode.tph` in SCS 35.21):

- `slow_fixes` gives every listed Slow, BLUN14/BLUN30/BLUN30C/BLUN30D included, a
  -4 THAC0 penalty by cloning the opcode-40 effect into opcode 54 (same timing,
  duration and probability). Its comment: the penalties of Slow "are because of
  being slowed, not additional to it". `opcode_secondary_effects` associates
  opcodes 0, 54, 158 and 240 with opcode 40.
- `process_slow_file` moves the Slow into an instantly cast helper SPL
  (`opcode_extract`, secondary type `dw_persistent_40`), adds the Slow-removes-
  Haste opcode 221 next to the item's opcode 146, and prefixes the helper with an
  own-type refresh (221), a feedback branch (326 → `dw_neg16`, "Haste cancelled by
  Slow") and an opcode-318 self-block, both under SPLPROT 138 (STATEBITS) with
  STATE_HASTED. A hasted target therefore loses Haste instead of being slowed.
- `process_haste_file` does the mirror image for Haste (`dw_persistent_16`
  payloads) and guards every Haste and payload with opcode 324 under SPLPROT 110
  (SPLSTATE=n) for HASTE_IMMUNITY; Improved Haste's payload sets HASTE_IMMUNITY.

### Binary evidence (captured install; fixture observations)

- MSECTYPE rows 24 `dw_persistent_16` and 25 `dw_persistent_40`. SPWI305 and
  SPWI613 keep generic type 13 (Non-combat) and cast SPWI305A/SPWI613A (type 24);
  SPWI312 keeps type 11 (Disabling) and casts SPWI312A (type 25). SPWI312 removes
  24; SPWI305/SPWI613 remove 25; the payloads refresh their own type.
- SPWI312A applies op40, op0 -4 and op54 -4 with one timing and duration, all with
  the spell's save, plus feedback (141, 61, 139, 142 icon 41, 240 icon 38).
- BLUN14/30C/30D/30 on hit: SCS troll riders and damage, then in one 0..32 window
  op324 SLOW_IMMUNITY (BLUN14 only), op146 helper and op221 p2=24. BLUN30C/BLUN30
  add op318 SPLPROT 55/77 checks naming the helper. Helpers (type 25, one ability,
  target 1, projectile 1, no saves): op221 p2=25, op326/op318 as above, op54 -4,
  op40 and op139 14000, op54 and op40 both timing 0 for 20 s.
- `dw_neg16`: one op139 (target 2), ability target 0, projectile 0.
- BLUN30 equipped: op328 mode 1 for spell states 139, 138, 133, 132 and 131
  (138 = HASTE_IMMUNITY in SPLSTATE.IDS; 139 again later), beside the blockers 302
  already removed (op101/op337 p2=16, op169/op240 p2=38, op267 14023).

### Three gaps and their repair

1. **Pure Slow package.** The classifier treated three Slow companions as other
   behaviour. Now part of the package, so the parent save covers them:
   - opcode 0/54 with a negative modifier whose `opcode:mode` the installed
     WIZARD_SLOW applies with its own opcode 40 at the same timing and duration
     (derived from the spell and its opcode-146 payloads, not a blanket rule),
     and whose timing and duration equal an opcode 40 of the same effect list.
     A penalty that outlasts the Slow stays foreign. A direct item-level Slow
     shares its save with such a penalty in its window on the same terms.
   - opcode 221 removing an installed Slow type (refresh).
   - opcode 326 whose parameters equal an opcode 318/324 self-block of the same
     list and whose payload is presentation only (61, 139, 141, 142, 174, 215,
     240; projectile 0/1, which opcode 326 treats as None per IESDP).
   Damage, other conditions, extra inner saves, non-instant projectiles and
   other recipients still reject with the existing message.
2. **Haste/Slow secondary types.** They were read from the header byte of
   SPWI305/SPWI312, which is 13/11 here. Now each spell's effective
   implementation (own type plus opcode-146 payloads on the target, bounded at
   depth 32, each resource once) is walked. A type counts as Haste if Haste or
   Improved Haste carries it and Slow removes it, and as Slow if Slow carries it
   and Haste removes it. Result: SCS 24/25. On SR 4.19 reference data the same
   rule gives 20/21 (SR Haste removes k1#Slow, SR's Slow payload SPWI312D removes
   k1#Haste). Generic 13/11 never count. Several types are allowed.
3. **+5 Haste allowance.** The Haste spells' opcode 318/324 checks on their own
   resources are resolved through SPLPROT.2DA by meaning (STAT 0x112, RELATION 1,
   VALUE or Parameter 1). An equipped mode-1 opcode 328 setting such a state is
   removed only when SPLSTATE.IDS names it HASTE_IMMUNITY. If it does not, the
   install fails and rolls back, because removing it could drop another
   protection. A HASTE_IMMUNITY state that the installed Haste spells do not
   check is kept, with a log line. Every other opcode 328 (SLOW, HOLD, WEB,
   ENTANGLE immunities) is kept.
4. **Innate Haste (SPIN572).** SPIN572 is the innate "Haste" behind the Potion
   of Haste and Haste rings. The +5 is immune to it (op206). In SCS's layout
   SPIN572 has no op16 of its own: op324 HASTE_IMMUNITY self-check, op146
   SPIN572A, op221 removing type 25. SPIN572A (type 24) holds the Haste: op324
   self-check, op221 removing 24, op326 → `dw_neg40` paired with an op318 self-block
   under STATE_SLOWED, op16 48 s, op93 fatigue. The Haste-identity check now
   follows opcode 146 (bounded, each resource once, each its own owner) and
   judges the payloads as one Haste. It accepts the same companions as above:
   typed op221, own-resource guards, and a feedback-only op326 paired with a
   same-condition self-block. Anything foreign still keeps the immunity with the
   existing message. A missing or unreadable linked payload keeps it too, with
   its own message.
5. **Spell states of every Haste the +5 lets through.** Before anything is
   removed, the +5's op328 decision collects the spell states that the wizard
   Haste and Improved Haste refuse themselves under. It also collects those of
   each op206 target judged pure Haste (own op318/op324 `SPLSTATE=n` guards,
   payloads included). Same HASTE_IMMUNITY confirmation and same failure for an
   unconfirmed state as in 3. An innate Haste that mixes in another effect keeps
   its op206 and does not contribute its states; the op328 then stays unless
   another allowed Haste checks it. In SCS the state (138) is already checked by
   the wizard spells. In SR 4.19 only SPIN572 checks it: SR's SPIN572 is a direct
   op16 Haste (type 20, op221 removing 21, op93) with an op324 HASTE_IMMUNITY
   self-check. Before this change the +5 lifted op206 SPIN572 but kept
   HASTE_IMMUNITY there, so Potion of Haste and Haste rings stayed blocked on SR.
   Fixed: SR now drops HASTE_IMMUNITY as well.

The save still goes only on the item's parent delivery (op146 and the Slow-
removes-Haste op221 in its window); helper bytes and resrefs are unchanged and
nothing is cloned. Immunity checks (op324/op318) get no save. The roll model is
unchanged: one probability roll per effect-list application, saves of one type
sharing a roll per application.

### Tested scope and limits

- `tests/test_flail_of_ages_scs.py` rebuilds the SCS-not-SR layout synthetically
  from the field values above (four items and helpers, `dw_neg16/40`, Haste,
  Improved Haste and Slow with payloads, SPELL.IDS, SPLSTATE.IDS, SPLPROT.2DA,
  MSECTYPE.2DA). It asserts -2/-4/-6 on op146 and op221 p2=24, unsaved immunity
  checks and riders, removal of only the HASTE_IMMUNITY op328 and the known
  blockers, unchanged helper bytes, reapplication and exact uninstall, mixed
  helpers (damage, inner save, outlasting penalty, AoE projectile, non-feedback
  cancel branch), an unconfirmed spell state, an unchecked HASTE_IMMUNITY, and a
  direct Slow with its penalty and refresh. SPIN572/SPIN572A are part of the
  fixture (the +5's op206 SPIN572 is removed); variants with damage in SPIN572A
  and with SPIN572A missing keep the immunity and say why.
- The SR fixtures now model SR 4.19's mutual cancellation (Haste removes k1#Slow,
  Slow removes k1#Haste), as the reference SR install has it. An SR version
  whose Slow does not remove Haste leaves an on-hit Haste removal unsaved, with
  the existing diagnostic.
- Real inputs: the component ran on copies of the captured override files
  (SPIN572A included) in a disposable game. The four items gained the save on
  op146 and op221 p2=24 only (-2/-4/-4/-6). BLUN30 lost exactly the
  HASTE_IMMUNITY op328, op206 SPIN572, op101 and op337 p2=16, op169 and op240
  p2=38 and op267 14023 (53 → 46 equipped effects, others in order). Uninstall
  restored every file byte for byte.
- SR reference copies (SR 4.19, read only): the on-hit result equals the
  existing SR contract. BLUN30 goes 53 → 46 and loses the HASTE_IMMUNITY op328,
  op206 SPIN572, op267 14023, op240 and op169 p2=38, op337 and op101 p2=16.
  Before item 5 HASTE_IMMUNITY was kept there (53 → 47).
- Vanilla (base KEY/BIF extracts of the same game, read only): BLUN30 has no
  op328, and SPIN572 is a bare op16 + op93 without a state check. Item 5 adds
  nothing there.
- `tests/test_flail_of_ages_haste.py` covers the SR case: a pure SPIN572 with the
  check lifts both; with damage it keeps both; with damage plus a wizard Haste
  that checks the state, the op206 stays and the op328 goes.
- No live-game, combat or save-game result is claimed. No game was changed.

## Compatibility repair — 2026-10-08 (unreleased)

This section supersedes the original narrow preconditions described below.
The community report failed on `BLUN14.ITM` with “expected one direct melee Slow
effect.” The reporter's actual resource is not available; this is a repair of
the source-proven assumption, not a claim to have reproduced their exact mod list.

The old code authenticated one captured layout: one ability, exactly one direct
Slow, and one recognizable English description line. The transformation now:

- Iterates actual melee abilities and all victim-targeted Slow effects. It gates
  corresponding feedback/Haste removal by their target and probability window,
  not whichever match was last. Unrelated secondary-type removals are retained.
- Uses effect-slice indexes, tolerates unused records/padding, and separates a
  shared slice before editing it so equipped or non-melee deliveries stay intact.
- Follows opcode 146/177/326 into read-only SPL/EFF V2 resources with bounded,
  cycle-aware traversal. A proven single-recipient, no-extra-save Slow-only helper
  gets a save on the weapon's parent delivery; every helper byte and resref stays
  unchanged. Separate EFF feedback/Haste-removal companions are recognized too.
- Does **not** clone shared spells. That would change resource-specific immunity
  and refresh identity. It also does not put a save on mixed Slow-plus-damage
  helpers, area/caster delivery, or payloads with additional inner saves. Those
  require an adapter; otherwise installation rolls back with the actual reason.
  Non-instant projectiles currently also need a delivery-specific adapter.
- Preserves an item with no identified on-hit Slow, with an explicit diagnostic
  and no false Slow-description update. It does not invent a replacement effect.
- Updates recognizable Slow rule lines, leaving other prose intact. If no safe
  English line is recognized, appends a concise rule note instead of failing.
  The appended English note is not a translation of the entire old description.
- Retains genuine format/bounds checks. +5 movement immunity conflicts are based
  on actual canonical Haste payloads (including linked helpers), not presence of
  a secondary-type label. Noncanonical immunity matching ignores unused records
  and keeps protection against mixed Haste-plus-damage spells.

### Focused evidence

**33 tests passed** across `test_flail_of_ages`, `test_flail_of_ages_variants`,
`test_flail_of_ages_safety` and `test_flail_of_ages_haste` using real WeiDU 249 in
disposable synthetic games. This includes subcases for SR/non-SR, captured vanilla
and CEBG inputs, multiple abilities/proc windows, shared slices, SPL/EFF chains,
external resource immunity, original helper bytes, reapplication, exact uninstall,
malformed-input rollback, mixed/AoE/extra-save rejection, localization and lore.
Tests assert resulting records and retained data, not merely exit status.

Full regression also completed with exit 0: 560 tests in 451.995 seconds,
536 passed and 24 skipped because private dragon/bracers captures were absent.
All FoA tests ran. Evidence is saved in `work/foa-full-regression-20261008`;
the Bard guard diagnostics in stdout are expected negative-test output.

Review rejected an intermediate private-helper design before release; it is not
part of this implementation. Source reasoning follows IESDP's resource identity
and delivery rules: [206](https://gibberlings3.github.io/iesdp/opcodes/bgee.htm#op206),
[321](https://gibberlings3.github.io/iesdp/opcodes/bgee.htm#op321),
[177](https://gibberlings3.github.io/iesdp/opcodes/bgee.htm#op177).
No live-game/saved-game compatibility result is claimed. No game was changed.

## Provenance and inspected inputs

All reads were against `~/Games/Chriz Easy BG/game`; no game file was
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

Each captured item has one melee ability, one opcode-40 Slow lasting 20 seconds and a
matching opcode-139 Slowed message (BG2 string 14000). The BIF probability window
is 0..33; effective EEFP/SR inputs use 0..32. Preserve the bytes, not an assumed
percentage. SR adds a matching opcode-221 Haste-secondary-type removal; that
removal and the Slowed message must receive the same save as Slow, so a successful
save neither strips Haste nor says Slowed. Damage and unrelated per-hit riders
must not gain a save. Existing resource immunities remain untouched.

SR allocates the Haste secondary type through `MSECTYPE.2DA` (`k1#Haste`, row 20
in the inspected install), not an IDS symbol. Resolve `WIZARD_HASTE` from the
installed `SPELL.IDS`; do not assume row 20. (Superseded 2026-11-03: the types
come from the effective Haste/Slow implementations, see "SCS without SR".) The same symbol lookup resolves Improved Haste. An unresolved
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
