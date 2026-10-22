# Aid, Luck and Chaotic Commands: first Chris Revisions batch

Status: decided by Christopher on 2026-10-23; parts of component 340 (Chris
Revisions). They were first built as components 340, 341 and 350 and merged the
same day at Christopher's request, so that his revisions do not become one
component per spell. Follows the
[October 11 design review](2026-10-11-general-spell-balance-design.md), whose
duration-only recommendations for Aid and Luck were replaced by these
decisions. Prayer and Recitation were decided later that day
([note](2026-10-23-prayer-recitation.md)); Bless is still open.

## Decisions

| Spell | Decision |
|---|---|
| Aid (`CLERIC_AID`) | Hit points only: 1d8 + 1 per caster level (maximum +10). No attack, damage or saving-throw bonus. One turn per level, as in SR. |
| Luck (`WIZARD_LUCK`) | 90 seconds (15 rounds), fixed. Its bonuses are unchanged. |
| Chaotic Commands (`CLERIC_CHAOTIC_COMMANDS`) | Druids may cast it again, at its existing level 5. |

The reasoning: buff stacking (Bless, Chant, Prayer, Recitation, Aid, Luck,
Emotion: Hope) is the real problem, not any single spell. Aid's +1 bonuses
duplicate Bless and feed that stack, so Aid becomes the cleric's distinct
"staying power" spell. Luck should remain worth casting on a thief without
being a buff for every character. Chaotic Commands is the kind of protection
any divine caster should be able to provide.

The same final values apply without Spell Revisions. Without SR, Luck lasts 90
instead of 18 seconds and Aid becomes the same hit-point spell, because the
decided values are the intended spells, not caps on SR's values.

## Binary evidence

Read-only from the owner's CEBG installation: native resources from
`DATA/SPELLS.BIF` via `chitin.key`, effective resources from `override`.
SCS's spell tweaks (component 2000) do not touch any of the three spells.

| Resource | Size | SHA-256 |
|---|---:|---|
| native `SPPR201.SPL` (Aid) | 7634 | `51E3258ACBECD1D83C1B941064A85107674D3774FCF349BDE597CAA1D5CC462D` |
| native `SPWI209.SPL` (Luck) | 1114 | `A9B6EB2A6BCF90954BE7120741C3E4A6DCA31182EF5C7949116812BFA4372B6E` |
| native `SPPR508.SPL` (Chaotic Commands) | 21682 | `486BDC5EB2D5846158A2D060207375FC6A07FABB6A38BF355804A6C18BA2B0E7` |
| effective `SPPR201.SPL` (SR) | 6882 | `062A178DBD34C9466AD7DCD2680048F2397027DFA37D7C49903C896278804585` |
| effective `SPWI209.SPL` (SR) | 1114 | `AD6AA5B0051302A17597B1009D049490931F8628C34D63B2C6F02F20E2F0ECDC` |
| effective `SPPR508.SPL` (SR) | 39762 | `E1ACB54ADDF41D9837F29EB2DBAF883D4E50DC38D7DCA07C3ECC5CD47F570025` |
| effective `C0TRBS2.SPL` (Bardic Wonders) | 6882 | `B5D8233B763C7FCB56CB311330C9C581C6262EEFC58505375E88A038276F298D` |
| effective `SCRL93.ITM` (Luck scroll) | 370 | `3D3A0A7420020BC467A5EAF780918BCA8BAC3B72D4C7BD362FCE23A6BEE5E9BC` |

Third-party binaries are not copied into this public repository; Spell
Revisions asks not to be redistributed. Hashes and the decoded fields below
identify the inspected inputs. Tests use synthetic fixtures.

### Aid

- Native: 20 abilities for caster levels 1-20. Each has opcode 129 (`Aid`,
  amount 1) for `6 * (level + 1)` seconds, plus a glow, an end sound
  (opcode 174, timing 4) and a visual. Opcode 129 grants the amount to
  attack, damage and saving throws plus `amount`d8 current/maximum hit points
  ([IESDP](https://gibberlings3.github.io/iesdp/opcodes/bgee.htm#op129)).
  No self-refresh; opcode 129 itself is non-cumulative.
- SR: 18 abilities (levels 1, 4-20). Each starts with an opcode-321
  self-refresh on `SPPR201`, then opcode 129 (amount 1) and opcode 18 (maximum
  hit points, type 0) for `+min(L, 10)`, both lasting `60 * L` seconds, where
  `L = max(ability level, 3)`. The level-1 ability therefore gives +3 for 180
  seconds; level 20 gives +10 for 1200 seconds.
- Druids are excluded natively and in SR (`0x80000000`).
- Bardic Wonders' Troubadour copies `SPPR201` to `C0TRBS2` at install time,
  changing only the header's spell type and level. Its abilities and effects
  are byte-identical to SR's Aid, including the refresh of `SPPR201`.
- SoD's Bracers of Perseverance cast `SPPR201` at level 10 through `BDBRAC15`;
  its item text only names "the Aid spell".

### Luck

- Native: one ability. Opcode 133 (`Luck`, +1) and +1 to all five saves for
  18 seconds, +5% to seven thief skills, the portrait icon (opcode 142, 32)
  and the end sound (opcode 174, timing 4) on the same duration; an opcode-321
  self-refresh comes first.
- SR: identical bonuses and refresh, 300 seconds; range 20 instead of 15 and a
  one-second glow (opcode 50) that stays unchanged.
- The scroll `SCRL93` teaches `SPWI209` (opcode 147) and shares the spell's
  description string (`Duration: 5 turns`, "for the next hour").
- SoD's Corinth's Bow casts Luck through `BDBOW02`; its text names the spell
  only. The Cloverleaf belt and Bardic Wonders' Cleansing Aria remove or block
  Luck effects by resource; neither copies its payload.

### Chaotic Commands

- Native exclusion flags `0x00000000`; SR's spell and the effective file have
  `0x80000000`. For priest spells the high word at `0x20` selects the classes:
  `0x8000` is cleric/paladin only, `0x0000` is every priest
  ([IESDP exclusion flags](https://gibberlings3.github.io/iesdp/file_formats/ie_formats/spl_v1.htm#splv1_ExclusionFlags)).
- SR also changes range, casting time and duration headers. None of that is
  touched; only the druid exclusion bit is cleared.

## Component design

Component 340 runs its parts one after another. Each part resolves its spells
through SPELL.IDS and is skipped without them. A dry run then checks every file
the part would change. If one cannot be changed safely, nothing of that part is
written, the installation warns and names the resource, and the other parts
still apply. Items that show exactly a changed spell's old description text
show the new one.

### Aid: hit points only

For every ability of the resolved `CLERIC_AID` spell and of each exact copy:

- the recipient's timed opcode-129 payload is removed. An existing timed
  opcode-18 type-0 bonus becomes `min(L, 10)` plus 1d8; without one (native),
  the first opcode 129 is converted in place, keeping its delivery fields;
- `L = max(ability level, 3)`, the cleric's minimum level for a level-2 spell,
  as SR does. Every timed effect that lasted exactly as long as the old payload
  (glow, icon, end sound, SR's bonus) now lasts `60 * L` seconds;
- each ability starts with one opcode-321 refresh per family member: Aid first,
  then its copies in the order WeiDU lists them. The family is the Aid spell
  plus spells whose abilities and effects are byte-identical to it, collected
  before anything changes. Recasting either spell replaces the other instead of
  stacking hit points. The ability's first family refresh is the template;
  otherwise SR's form is used (non-dispellable, ignores magic resistance) on the
  payload's recipient;
- each ability gets its own copy of its effects, so shared effect records are
  split; casting effects stay first, and records no ability uses are dropped;
- an ability with several or mismatched Aid payloads, or none, leaves Aid
  unchanged with a warning that names the resource.

Already converted spells (no opcode 129, one 1d8 hit point bonus) are only
re-synchronized, so a second run is byte-identical.

Descriptions: the bonus sentence and the `Duration:` line of SR's and the
native English text are rewritten. A description that is not recognized is
left unchanged with an installation warning.

### Luck: 90 seconds

For every ability of the resolved `WIZARD_LUCK` spell and its exact copies,
the Luck payload duration is taken from its opcode-133 effect (or an opcode-22
luck bonus without one). Every timed effect lasting exactly that long becomes
90 seconds. Other durations, such as SR's one-second glow, stay. Conflicting
payload durations leave Luck unchanged with a warning.

The spell and every scroll that teaches it get `Duration: 15 rounds` and "for
the next 15 rounds" in place of the old duration phrases.

### Chaotic Commands: druid access

Clears only the druid exclusion bit of the resolved priest spell and keeps the
other flags. A spell already available to druids is left unchanged. A spell no
priest class can learn (both class bits set) is left unchanged with a warning
rather than guessed.

## Verification

- `tests/test_chris_revisions.py` installs component 340 with WeiDU on
  synthetic games: SR and native Aid and Luck, Bardic Wonders' copy, a near
  copy and a spell that only removes Aid (both untouched), relocated SPELL.IDS
  slots, shared effect slices with a casting effect, an opcode-22 Luck bonus,
  the Luck scroll, an item showing Aid's description, unrecognized text
  (warning), ambiguous or missing payloads (that part unchanged with a warning,
  the others applied), missing symbols (skipped), a second run (no change) and
  uninstall.
- On 2026-10-23 all three components were installed on scratch copies of the
  installed resources, once with the effective SR and Bardic Wonders files and
  once with the original BIFF files, each with the installed `dialog.tlk`. Aid
  and `C0TRBS2` changed identically, Luck and `SCRL93` lasted 90 seconds with
  recognized text, and Chaotic Commands lost only the druid bit (the original
  was left unchanged). Uninstalling restored every file. The same checks passed
again for the merged component 340, on copies of the CEBG game and of the
2.6.6.0 reference install.

## Limitations

- Effects already running in a save keep their old values until they expire;
  the next cast uses the new spell.
- Existing druids should receive Chaotic Commands when the game next builds
  their priest spell list, normally at level-up. Not yet checked in the game.
- Descriptions are patched in English. Other wording is reported, not replaced.
- Aid variants that are not exact copies keep their mechanics. Items that cast
  these spells inherit the change; their texts only name the spell.
- Not yet checked in a running game.
