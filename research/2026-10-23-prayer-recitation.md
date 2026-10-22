# Prayer and Recitation: not cumulative

Status: decided by Christopher on 2026-10-23; a part of component 340 (Chris
Revisions). Builds on the [first batch](2026-10-23-aid-luck-chaotic-commands.md)
and the [October 11 review](2026-10-11-general-spell-balance-design.md).

## Decision

Christopher: "Nur Prayer und Recitation schließen sich gegenseitig aus, Bless
und Chant stapeln weiter wie bisher."

He rejected the broader rule "only the strongest of Bless, Chant, Prayer and
Recitation counts", because Recitation would make Chant worthless. Only the two
area prayers now exclude each other:

| Situation | Result |
|---|---|
| Recitation reaches a creature with Prayer's bonus | Recitation's +2 to attack and saves replaces Prayer's +1 to attack, damage and saves |
| Prayer reaches a creature with Recitation's bonus | No Prayer bonus on it while Recitation lasts |
| The same with the penalties on enemies | Recitation's −2/−2 replaces Prayer's −1s; Prayer adds no penalty while Recitation's lasts |
| Bonus from one side, penalty from the other | Both apply, as before |
| Bless, Chant, Aid, Luck, Emotion: Hope | Unchanged; they still stack with Prayer or Recitation |

The stronger spell wins for each kind, whichever was cast first: Recitation is
the level-4 spell with +2. "The newer replaces the older" was rejected: a later
Prayer would downgrade Recitation, and AI casters could replace each other's
buffs in turn.

## Binary evidence

Read-only from Christopher's CEBG game (BG2:EE 2.7.3.0 with EET, Spell
Revisions v4.21-chriz.5, SCS, Bardic Wonders). Prayer and Recitation come from
IWDification v11, component 40 (IWD Divine Spell Pack, DavidW's iwdspells
library, which SCS also bundles). The 2.6.6.0 reference install has the same
structure. Third-party binaries are not copied into this repository.

| Resource | Size | SHA-256 |
|---|---:|---|
| `SPPR327.SPL` (Prayer, `CLERIC_PRAYER` 1327) | 250 | `503B1AB27CFF9ED505745707F141328FCDF3077D566074F7F1E4ECAF019770CD` |
| `SPPR422.SPL` (Recitation, `CLERIC_RECITATION` 1422) | 250 | `236505747AC90FA1A00673F5F73E1B2D156BD42F57ECCA058DA45E4D6E268F8A` |
| `#PRAYERG.SPL` (Prayer's bonus) | 9970 | `D6E86F9067F44DC78EB9BF083E8C296901495262F2F4CD3789CD655D70B1B437` |
| `#PRAYERB.SPL` (Prayer's penalty) | 8530 | `E313B33A53D64D688B32D8D2EB07EF77E9C4FFF94137F26A6A60D9CB1128FF5D` |
| `#RECITEG.SPL` (Recitation's bonus) | 8066 | `5D8274BB1E358026D1793572A500985F401ABA1B39289EDB48B628F10F40BE22` |
| `#RECITEB.SPL` (Recitation's penalty) | 6818 | `7F8DE5835E2B889BC388C04CA89926D28A49D929238AE2AC34A564E7D24B9627` |
| `CDID327.ITM` (Prayer scroll) | 218 | `16649DDF48663159995B8BBFF12019D60F8B48D565208BF3257B2A5A4ED58C6A` |
| `CDID422.ITM` (Recitation scroll) | 218 | `E3CA6D29FE5F32CDD01BE277BA1A0FDF0F730DEE53F2AF4473407F3EAD49AFFF` |

- `SPPR327` and `SPPR422` have one ability with two opcode-146 effects on the
  caster: they cast the bonus sub-spell (projectile 337, allies) and the
  penalty sub-spell (projectile 338, enemies).
- `#PRAYERG`: 16 abilities (levels 1, 6–20). Each starts with an opcode-321
  refresh of itself, then a visual, sounds and a feedback string, and +1 to
  attack (opcode 54), damage (73) and all saves (325), the spell states
  `BENEFICIAL_PRAYER` (12) and `BUFF_ENHANCEMENT` (68), icon 336, a glow and an
  end sound, all for `6 * max(level, 5)` seconds. Power 3, dispellable,
  ignores magic resistance (resist/dispel 3).
- `#PRAYERB`: the same with −1 and no spell states, resist/dispel 1. Its
  casting effects, added by SCS to hostile spells, reset the caster's
  invisibility animation (opcode 146 `DW#BLHDA`, opcode 321 `DW#HDANI`).
- `#RECITEG`: 14 abilities (levels 1, 8–20) with +2 to attack and all saves,
  `BENEFICIAL_RECITATION` (14) and 68, power 4, for `6 * max(level, 7)` seconds.
  `#RECITEB`: −2/−2, resist/dispel 1, with the same SCS casting effects.
- Recitation's description ends with "Recitation does not nullify a Prayer
  spell—the two can be cast in tandem, and the effects are cumulative."
  Prayer's says nothing about Recitation.
- `CDID327` and `CDID422` are IWDification's priest scrolls: they cast the spell
  (opcode 146) and show the spell's own description string.
- No other resource casts the four sub-spells. Other mods only remove or block
  `SPPR422` or remove `SPPR327` from spell lists (`BDCONSTR`, `K#REST`,
  `OHSMODE1`/`4`, `C0BAR#05`, `C0PY071`, `OHTYR1`, `C0BG#S2`); they stay as
  they are.
- SCS's priest AI (`priest/ssl/combatblocks/group_buffing.ssl`) casts Prayer
  when the nearest enemy lacks `BENEFICIAL_PRAYER` and Recitation when it lacks
  `BENEFICIAL_RECITATION` (`TargetBlock(VillainsInOrder)` is `[ENEMY]`).

## Component design

1. Resolve `CLERIC_PRAYER` and `CLERIC_RECITATION` through SPELL.IDS. Without
   either (no IWD divine spells installed) the part is skipped.
2. Find each spell's payloads: the spell and the spells it casts (opcode 146 or
   148), two levels deep, each visited once. A payload has timed opcode-54 or
   opcode-325 type-0 modifiers; positive ones make it a bonus, negative ones a
   penalty. Removing and blocking work per resource, so a resource with both is
   ambiguous and the part is left unchanged with a warning.
3. Pair each Recitation payload with Prayer's payloads of the same kind. A
   Prayer payload whose abilities cast other spells is not blocked, because the
   block would also stop those; the part is left unchanged with a warning.
   Casting effects, which reach only the caster, do not count.
4. Every ability of a paired Recitation payload gets, per Prayer payload of its
   kind, an opcode-321 removal and an opcode-206 block for the ability's bonus
   duration, without a feedback string (parameter 1 = −1, as SCS's own blocks).
   - They are delivered like the ability's first bonus effect (target, power,
     resistance, probability, saving throw). So they reach exactly the
     creatures the bonus reaches, and are resisted or saved against with it.
   - They follow the payload's own refresh, which would otherwise remove them at
     once.
   - Existing removals and blocks are reused, and a block's duration follows
     the bonus. A second run changes nothing.
   - An ability whose bonus effects have different durations is ambiguous, so
     the part is left unchanged with a warning.
5. Prayer's spells are not changed: the block on Recitation's targets covers
   both casting orders.
6. Spell states stay as they are. SCS tests `BENEFICIAL_PRAYER` on the caster's
   enemies. Copying the state to Recitation's bonus would stop hostile priests
   from casting Prayer whenever the party has Recitation, although their
   Prayer still works fully then. AI decisions therefore stay as before.
7. Descriptions: Recitation's "cumulative" sentence is replaced with @3411.
   Prayer gets @3412 as a paragraph. Other English wording gets the note at
   the end, and Recitation also warns that its sentence was not found.
   Untranslated text stays unchanged, with a warning. Items that show exactly
   the old description text, such as IWDification's priest scrolls, show the
   new one.

## Consequences

- Prayer's +1 damage ends when Recitation replaces its bonus, because
  Recitation has no damage bonus.
- Recitation wins even when it will run out sooner than the Prayer it replaces:
  a 42-second Recitation from a level-7 priest replaces a level-20 Prayer with
  120 seconds left. When it ends, Prayer can be cast again.
- Prayer cast during Recitation still blesses creatures without Recitation's
  bonus and curses enemies without its penalty.
- A creature under Recitation's penalty that casts Prayer itself may also be
  blocked from SCS's invisibility-animation reset on `#PRAYERB`. That reset is
  cosmetic, and the case needs an enemy priest who has been cursed by
  Recitation.

## Verification

- `tests/test_chris_revisions.py` (`PrayerRecitationTests`, `CombinedTests`):
  real WeiDU on synthetic games shaped like the files above. It covers the
  exact records added to both Recitation payloads, unchanged Prayer files, SCS
  casting effects, both descriptions and the scrolls (same string and same
  text). It also checks a refresh in second place, an existing block with
  another duration, saving throws copied to the added records, ambiguous
  payloads, Prayer payloads that cast other spells, uneven bonus durations,
  other and untranslated wording, missing symbols, a second run (no change)
  and uninstall.
- On 2026-10-23 component 340 was installed on scratch copies of the CEBG
  resources and on copies of the 2.6.6.0 reference install, each with its
  `dialog.tlk`. Both Recitation payloads gained exactly the removal and the
  block per ability, with the bonus durations (42–120 seconds). Every old
  record was kept. Prayer's files changed only their description strings,
  and both scrolls showed the new texts. Uninstalling restored every file. With
  the BIFF originals (no IWD divine spells) the part was skipped.

## Limitations

- Not yet checked in a running game. A lab check should cast Prayer then
  Recitation and the reverse on one party, and both from opposing casters.
- Effects already running in a save keep stacking until they expire.
- Descriptions are patched in English only.
- Prayer or Recitation copies with their own payloads (for example kit
  abilities) are not covered.
