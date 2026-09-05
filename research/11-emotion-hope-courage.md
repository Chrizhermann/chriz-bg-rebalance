# Research 11 — Emotion, Hope and Courage exclusivity

**Date:** 2026-08-30 · **Status:** delivery and mutual exclusion live-verified; status-list
correction automated-verified, manual retest pending · **Production game:** read-only

This note records the effective spell and scroll resources that component 301 must replace,
the installed IWDification/SCS provenance, and the standalone-resource boundary. The active
installation at `C:\Games\Baldur's Gate II Enhanced Edition modded` was used only as a read
source. No live WeiDU command was run and nothing was written to either installed game.

## Findings that determine the component

- `WIZARD_EMOTION_COURAGE` and `WIZARD_EMOTION_HOPE` are install-allocated symbols. They
  resolve here to `SPWI428` and `SPWI429`, but component 301 must resolve the live symbols and
  must not hardcode those resrefs.
- The effective Courage spell has a relocation defect: its intended self-remover became a
  second `SPWI430` (Emotion, Fear) remover. Courage can consequently stack with itself.
- Hope correctly removes itself, but neither beneficial spell removes the other. Both need
  canonical self and reciprocal opcode-321 removers created only after both final resrefs are
  known. The most recently applied beneficial Emotion then wins per recipient.
- Installed Fear removes Courage. Installed Emotion, Hopelessness and Symbol, Hopelessness
  remove Hope. Their removal/save domains differ and must be preserved.
- SCS component 5900 added detectable-spell opcode-328 markers for Hope and Courage. Replacing
  the spells without recreating those markers would make SCS AI observability regress.
- The IWD presentation is a resource graph, not two self-contained SPL files. Existing valid
  IWD assets are retained in place. The standalone branch packages the required original IWDEE
  game assets extracted from a pristine user-owned installation, publishes their dependency
  graph under private CBR resrefs, and does not copy IWDification or SCS binaries.
- The corrected standalone spells initially had no opcode 142 and published no portrait-status
  resources. Real casts therefore applied every mechanical effect but could not show a Courage
  or Hope entry on the character sheet. Each standalone spell needs a private native IWDEE heart
  BAM, a dynamically allocated `STATDESC.2DA` row, and one matching timed opcode 142. Provider
  spells retain their existing raw opcode-142 record and status table instead.
- SCS and IWDification both create the new scrolls and shadow stores that carry a designated
  donor scroll. The standalone CBR branch should mirror those dynamically discovered store
  entries: Enchanted Weapon is the Courage donor and Emotion, Hopelessness is the Hope donor.
  It should not copy IWDification's optional fixed campaign scatter.

## Installed provenance and preserved hashes

`WeiDU.log` lines 195–196 install IWDification v11 components 30 (arcane spell pack) and 40
(divine spell pack). SCS v35.21 component 5900 is installed at line 296. SCS component 1500,
its own IWD spell installation, is absent. The effective spells are therefore IWDification
resources subsequently annotated by SCS's detectable-spell initialization.

The metadata below is the UTC read-only evidence snapshot used by this audit. Paths without a
drive prefix are relative to `C:\Games\Baldur's Gate II Enhanced Edition modded`.

| Input | Bytes | Last modified (UTC) |
|---|---:|---|
| `WeiDU.log` | 43,923 | `2026-08-23T15:30:45.8267161Z` |
| `override/SPELL.IDS` | 33,232 | `2026-02-12T16:51:58.6602708Z` |
| `override/SPLSTATE.IDS` | 4,498 | `2026-08-23T12:30:54.3731233Z` |
| `override/PROJECTL.IDS` | 8,426 | `2026-02-12T16:51:57.6596415Z` |
| `override/STATDESC.2DA` | 11,770 | `2026-07-08T16:39:50.1328231Z` |
| `override/SPWI428.SPL` | 922 | `2026-02-12T16:12:29.6496501Z` |
| `override/SPWI429.SPL` | 778 | `2026-02-12T16:12:29.6008575Z` |
| `override/CDIA428.ITM` | 418 | `2026-06-06T22:21:22.8102400Z` |
| `override/CDIA429.ITM` | 418 | `2026-06-06T22:21:22.8122932Z` |
| `override/IDPRO407.PRO` | 768 | `2026-02-11T17:13:46.7620428Z` |
| `override/#GENENCH.VVC` | 492 | `2026-02-11T17:12:44.8448550Z` |
| `override/ENCHANX.BAM` | 236,071 | `2026-02-11T17:12:44.8469261Z` |
| `override/#ARE_M21.WAV` | 40,161 | `2026-02-11T17:12:44.8418557Z` |
| `override/#EFF_E03.WAV` | 19,028 | `2026-02-11T17:14:19.6772997Z` |
| `iwdification/iwdspells/data/iwd_arcane.2da` | 4,281 | `2026-02-11T17:12:04.3593529Z` |
| `iwdification/iwdspells/lib/move_spell_resources.tph` | 46,521 | `2026-02-11T17:12:04.4195212Z` |
| `iwdification/sfo/lib_spl.tph` | 56,397 | `2026-02-11T17:12:05.0433727Z` |
| `iwdification/iwdspells/custom/cd_scroll_placement.tpa` | 14,155 | `2026-02-11T17:12:04.3488381Z` |
| `iwdification/iwdspells/iwdspells_arcane.tpa` | 3,016 | `2026-02-11T17:12:04.6699195Z` |
| `iwdification/readme-iwdification.html` | 66,551 | `2026-02-11T17:12:04.7383197Z` |
| `iwdification/sfo/data/spell_styles_iwd.2da` | 2,117 | `2026-02-11T17:12:04.7725844Z` |
| `iwdification/sfo/data/spell_styles_bg.2da` | 2,001 | `2026-02-11T17:12:04.7715843Z` |
| `stratagems/setup-stratagems.tp2` | 80,477 | `2024-11-20T15:07:16.5210879Z` |
| `stratagems/iwdspells/data/iwd_arcane.2da` | 4,281 | `2022-07-10T05:32:04.8211497Z` |
| `stratagems/iwdspells/lib/move_spell_resources.tph` | 46,521 | `2024-11-03T09:06:06.2164526Z` |
| `stratagems/iwdspells/iwdspells_arcane.tpa` | 3,016 | `2024-11-03T07:04:39.5615998Z` |
| `stratagems/sfo2e/lib_spl.tph` | 56,397 | `2024-06-29T22:31:48.9571861Z` |
| `stratagems/ds/ds_iwd.tpa` | 2,213 | `2023-09-02T13:47:02.6180212Z` |
| `C:\Program Files (x86)\Steam\steamapps\common\Icewind Dale Enhanced Edition\chitin.key` | 532,346 | `2026-08-18T11:49:28.5686601Z` |
| `C:\Games\Icewind Dale Enhanced Edition\chitin.key` | 532,346 | `2026-08-18T11:49:28.5686601Z` |

The final `override/SPELL.IDS` mappings are:

| IDS value | Symbol | Effective resref |
|---:|---|---|
| 2428 | `WIZARD_EMOTION_COURAGE` | `SPWI428` |
| 2429 | `WIZARD_EMOTION_HOPE` | `SPWI429` |

The generated IWDification registry at
`weidu_external/iwdspells/generic_arcane.tpa` records `SPWI428`/`CDIA428` and
`SPWI429`/`CDIA429`. `SETUP-IWDIFICATION.DEBUG` lines 28170–28210 and 28283–28323 record the
source-to-final copies and scroll generation.

| Read-only resource | Size | SHA-256 |
|---|---:|---|
| `override/SPWI428.SPL` | 922 | `869EDD92E6760B6D03D5C4594613126EBE506A0581212E3F6D79946CB8E7F5F2` |
| `override/SPWI429.SPL` | 778 | `25A4DFE9EB8EDCBECF8D4EB4C98041B6EE2288988BA6FDFEE9DF3F8A551B7858` |
| `override/CDIA428.ITM` | 418 | `960225A47DFBF271516CBC0A4D0664F1D1A7AC596420144021701E7811D39D76` |
| `override/CDIA429.ITM` | 418 | `D1A1AE79FAA53DD9DD825B651F815F90D5A91ADE4326A4BB12C91EFEF248A570` |
| `iwdification/iwdspells/copyover/wizard_emotion_courage/SPWI427.SPL` | 874 | `65FABF10505B6D5BEF41A1E7AC8F0E8ED4D516C4A9988E926A5CD824F412B250` |
| `iwdification/iwdspells/copyover/wizard_emotion_hope/SPWI429.SPL` | 778 | `35B070A4CD1889285AFEE55DF40403F48A5B3ED34540387BE735F365E20D9BF0` |

The source-tree hashes above are provenance evidence only; IWDification's copies are not
repository fixtures or implementation inputs.

The publication boundary distinguishes mod work from game assets. Installed IWDification's
`readme-iwdification.html` lines 391–394 asks users not to host or redistribute that mod without
the authors' permission, so no IWDification or SCS binary or source file is copied. Component
301 uses clean-room WeiDU code and independently extracted original IWDEE game resources for
the blue icons and presentation graph. Their provenance and exact hashes are recorded in
`chriz-bg-rebalance/resources/emotion_iwdee/README.md`.

## Decoded live beneficial spells

Both resources are level-four Enchantment spells with one visual-range, point-targeted area
header, casting time 4, an IWD-derived area projectile, and a 300-second timed package. The
following tables are a complete reproduction-oriented decode of the live SPL headers and
recipient slices. Offsets use the empirical SPL V1 layout (`nFx @ ability+0x1E`,
`firstFxIdx @ ability+0x20`).

### Spell headers

| Field | Courage | Hope |
|---|---|---|
| Effective resref | `SPWI428` | `SPWI429` |
| Name / description strref | 350327 / 350328 | 350329 / 350330 |
| Completion sound | `CAS_M05` | `CAS_M05` |
| Flags / spell type / exclusion flags | 0 / 1 (wizard) / `0x800` | 0 / 1 (wizard) / `0x800` |
| Casting animation / minimum level | 11 / 0 | 11 / 0 |
| Primary / secondary type | 4 (Enchantment) / 7 | 4 (Enchantment) / 2 |
| Spell level / unknown word at `header+0x38` | 4 / 1 | 4 / 1 |
| Spell icon (`header+0x3A`) | `SPWI428C` | `SPWI429C` |
| Ability offset / count | `0x72` / 1 | `0x72` / 1 |
| Effect offset | `0x9A` | `0x9A` |
| Casting-effect first / count | 0 / 0 | 0 / 0 |

### Ability headers

| Field | Courage | Hope |
|---|---|---|
| Type / flags / location | 2 / 0 / 2 | 2 / 0 / 2 |
| Ability icon (`ability+0x04`) | `SPWI428B` | `SPWI429B` |
| Target / target count / range | 4 / 0 / 50 | 4 / 0 / 50 |
| Minimum level / casting time / uses | 1 / 4 / 0 | 1 / 4 / 0 |
| Dice size / count / bonus; required word at `ability+0x1C` | 6 / 0 / 0; 1 | 6 / 0 / 0; 1 |
| `nFx` / `firstFxIdx` | 16 / 0 | 13 / 0 |
| Charges / depletion | 1 / 1 | 1 / 1 |
| Stored projectile word (`ability+0x26`) | 569 | 569 |

The stored projectile word is **one greater than the `PROJECTL.IDS` index**. Thus stored 569
maps to `override/PROJECTL.IDS` entry 568, `IDPRO407`. Entry 569 is `IDPRO255`; treating the
stored word as the IDS index is the off-by-one trap and would select the wrong projectile.
Conversely, `IDPRO255` would be encoded as stored value 570.

For both effect tables below, every row has target 2, power 4, probability 100/0, dice 0/0,
save type 0, and save bonus 0. Those common values plus the displayed columns account for
every field in each 48-byte embedded effect. `dr` is the packed `resist_dispel` byte; rows
not explicitly showing a resource have an empty resref.

### `SPWI428` — Emotion, Courage

The sole header has 16 effects. Its opening two records are both instant opcode 321 against
`SPWI430`. There is no remover for `SPWI428`, so the installed spell does not prevent its own
timed bonuses from stacking. The remaining material includes the BG-style Enchantment casting
package, SCS detectable-state marker 195, portrait icon 327, +1 THAC0, +3 damage, +5 temporary
hit points, fear-state cleanup, and additional removers for `SPWI205` and `SPIN105`.

The duplicate `SPWI430` is explained by the installation sequence. The source donor is
`SPWI427`; its self-remover names `SPWI427`, while the source Fear remover names `SPWI428`.
Relocating Courage first rewrites the self-reference to `SPWI428`. A later old-Fear
`SPWI428` → final-Fear `SPWI430` rewrite then matches both records. This is why component 301
must not perform chained global resref replacement: it must resolve all symbols first and then
write explicit final remover resources.

| # | Opcode | p1 | p2 | Timing | dr | Duration | Resource | Special |
|---:|---:|---:|---:|---:|---:|---:|---|---:|
| 0 | 321 | 0 | 0 | 1 | 0 | 0 | `SPWI430` | 0 |
| 1 | 321 | 0 | 0 | 1 | 0 | 0 | `SPWI430` | 0 |
| 2 | 141 | 0 | 10 | 1 | 3 | 0 | — | 0 |
| 3 | 174 | 0 | 0 | 1 | 3 | 0 | `EFF_M05` | 0 |
| 4 | 61 | 509245440 | 1638400 | 1 | 3 | 0 | — | 0 |
| 5 | 328 | 1 | 195 | 0 | 3 | 300 | — | 1 |
| 6 | 142 | 0 | 327 | 0 | 3 | 300 | — | 0 |
| 7 | 54 | 1 | 0 | 0 | 3 | 300 | — | 0 |
| 8 | 174 | 0 | 0 | 4 | 3 | 300 | `#EFF_E03` | 0 |
| 9 | 73 | 3 | 0 | 0 | 3 | 300 | — | 0 |
| 10 | 18 | 5 | 0 | 0 | 3 | 300 | — | 0 |
| 11 | 23 | 20 | 1 | 0 | 3 | 300 | — | 0 |
| 12 | 240 | 0 | 36 | 1 | 3 | 0 | — | 0 |
| 13 | 321 | 0 | 0 | 1 | 3 | 0 | `SPWI205` | 0 |
| 14 | 321 | 0 | 0 | 1 | 3 | 0 | `SPIN105` | 0 |
| 15 | 161 | 0 | 0 | 1 | 3 | 0 | — | 0 |

Rows 11–15 are one fear/morale-cleansing package and must be retained with their decoded
fields. In particular, row 11 is opcode 23 with `p1=20`, `p2=1`, timing 0, `dr=3`, duration
300, and special 0. [IESDP identifies opcode 23 as morale
handling](https://gibberlings3.github.io/iesdp/opcodes/bgee.htm#op23), but its EE mode 0
hardcodes a flat morale value of 10 and marks the effect done immediately; it may also remove
morale-based panic. Therefore the serialized `p1=20` is not a maintained +20 morale bonus.
Here it is a morale normalization step within Courage's fear cleanse. Row 12 is opcode 240
with portrait icon 36, which [removes the matching special-effect
icon](https://gibberlings3.github.io/iesdp/opcodes/bgee.htm#op240); rows 13–14 remove the
Horror spell sources; and row 15 is [opcode 161 Cure:
Horror](https://gibberlings3.github.io/iesdp/opcodes/bgee.htm#op161). The player-facing
description should summarize this package simply as "ends fear and morale failure."

The live `SPWI205` and `SPIN105` references correspond to `WIZARD_HORROR` and
`INNATE_HORROR` on this installation. They are evidence, not constants: component 301 must
resolve both symbols dynamically before constructing Courage's cleansing removers.

### `SPWI429` — Emotion, Hope

The sole header has 13 effects. Its first three records remove `SPPR734` (Symbol,
Hopelessness), `SPWI411` (Emotion, Hopelessness), and itself (`SPWI429`). It has no Courage
remover. Its timed package includes the BG-style Enchantment casting material, SCS
detectable-state marker 194, portrait icon 328, +2 to all saving throws, +2 morale, +2 THAC0,
and +2 damage.

The effective English descriptions explain the individual bonuses and adverse-Emotion
interaction, but neither description says Hope and Courage are mutually exclusive.

| # | Opcode | p1 | p2 | Timing | dr | Duration | Resource | Special |
|---:|---:|---:|---:|---:|---:|---:|---|---:|
| 0 | 321 | 0 | 0 | 1 | 0 | 0 | `SPPR734` | 0 |
| 1 | 321 | 0 | 0 | 1 | 0 | 0 | `SPWI411` | 0 |
| 2 | 321 | 0 | 0 | 1 | 0 | 0 | `SPWI429` | 0 |
| 3 | 141 | 0 | 10 | 1 | 3 | 0 | — | 0 |
| 4 | 174 | 0 | 0 | 1 | 3 | 0 | `EFF_M05` | 0 |
| 5 | 61 | 509245440 | 1638400 | 1 | 3 | 0 | — | 0 |
| 6 | 174 | 0 | 0 | 4 | 3 | 300 | `#EFF_E03` | 0 |
| 7 | 328 | 1 | 194 | 0 | 3 | 300 | — | 1 |
| 8 | 142 | 0 | 328 | 0 | 3 | 300 | — | 0 |
| 9 | 325 | 2 | 0 | 0 | 3 | 300 | — | 0 |
| 10 | 23 | 2 | 0 | 0 | 3 | 300 | — | 0 |
| 11 | 54 | 2 | 0 | 0 | 3 | 300 | — | 0 |
| 12 | 73 | 2 | 0 | 0 | 3 | 300 | — | 0 |

The exact current presentation dependencies are now explicit. The SPL header completion sound
is `CAS_M05`; recipient chrome is opcode 141 parameter 2 = 10, opcode 174 `EFF_M05`, and
opcode 61 parameters 509245440/1638400. The timed audio is `#EFF_E03`. The projectile chain
is stored 569 → `PROJECTL.IDS` 568 → `IDPRO407.PRO` → `#GENENCH.VVC`, `ENCHANX.BAM`, and
`#ARE_M21.WAV`. The SPL spell/ability icons are respectively `SPWI428C`/`SPWI428B` and
`SPWI429C`/`SPWI429B`. Portrait icon parameters 327/328 resolve through `STATDESC.2DA` to
`SPWI428D`/`SPWI429D`; the A icons exist in the imported package but are not referenced by
these SPL headers.

## Adverse interaction audit

The user's expectation is broadly correct for the installed paired adverse spells:

- `WIZARD_EMOTION_FEAR` resolves here to `SPWI430`. All nine recipient headers contain one
  opcode-321 `SPWI428` remover. It shares Fear's save-vs-spell domain and per-header save
  adjustment, so a creature that resists Fear does not lose Courage.
- `WIZARD_EMOTION_HOPELESSNESS` resolves to `SPWI411`. All nine recipient headers begin with
  an unconditional opcode-321 `SPWI429` remover; the hostile Hopelessness effects that follow
  retain their own saves.
- The effective `SPPR734` Symbol, Hopelessness has eight recipient headers, each with one
  `SPWI429` remover in the symbol's save domain.

Component 301 should preserve these pairwise semantics and normalize duplicates, not turn all
positive and negative Emotions into one universal exclusion family. Only the beneficial
self/reciprocal Hope-Courage removers are timed-effect transitions: target 2, power 4,
timing 1, parameter 2 = 2, no save, and magic-resistance bypass. Beneficial cleansing of
dynamically resolved Fear, Horror, Innate Horror, Emotion: Hopelessness, and Symbol:
Hopelessness sources uses parameter 2 = 0, no save, and magic-resistance bypass. This second
shape removes the source effects completely rather than only their timed effects. Both kinds
of remover precede the timed buff package in every recipient header.

## SCS detectable-state evidence

The final `override/SPLSTATE.IDS` maps `EMOTION_HOPE` to 194 and `EMOTION_COURAGE` to 195.
The installed Hope and Courage contain one opcode-328 marker each with parameter 1 = 1,
parameter 2 set to that state, and special = 1. SCS's
`stratagems/ds/ds_iwd.tpa` associates the two wizard symbols with those state symbols for AI
checks.

The numeric values are allocation-specific evidence, not constants for component 301. The
installer must look up the live `SPLSTATE.IDS` symbols and add exactly one marker when each
symbol exists.

## Upstream allocation and scroll behavior

The bundled IWDification and SCS source trees use parallel resource-moving pipelines. For
each IWDification path below, the corresponding SCS path is obtained by replacing the root
`iwdification/` with `stratagems/`, except that SCS's SFO library is under `sfo2e/`:

- `iwdification/iwdspells/data/iwd_arcane.2da` and
  `stratagems/iwdspells/data/iwd_arcane.2da`, rows 8–9: Courage designates
  `ENCHANTED_WEAPON` as its `scroll_shadow`; Hope designates `EMOTION_HOPELESSNESS`;
- both `iwdspells/copyover/arcane_resrefs.txt` files, rows 8–9, and their
  `copyover/wizard_emotion_*` folders: nominal donor spell resources;
- both `iwdspells/lib/move_spell_resources.tph` files, lines 489–509: resolve or allocate final
  spell resrefs before copying; lines 632–647: generate the scroll and record the donor-scroll
  mapping; lines 698–717: clone each matching donor entry in every STO resource, changing only
  the cloned scroll resref;
- `iwdification/sfo/lib_spl.tph` and `stratagems/sfo2e/lib_spl.tph`, lines 704–719: generated
  wizard scroll names use the `SPWI` → `CDIA` convention;
- both `iwdspells/iwdspells_arcane.tpa` files, lines 45–62: invoke the resource pipeline,
  including IWD-to-BG casting-style conversion and any supplied custom includes.

The exact SCS component path is `stratagems/setup-stratagems.tp2` lines 124–132: component
1500 calls SFO `run` with `file=iwdspells_arcane location=iwdspells` and no version argument.
That reaches `stratagems/iwdspells/iwdspells_arcane.tpa`: line 1 defines the action, line 6
copies the empty version to `custom_includes`, and lines 45–62 pass it to
`install_spell_resources`. Thus SCS 1500 executes spell allocation, scroll construction, and
donor-store shadowing, but not `custom/cd_scroll_placement.tpa`.

On this install, the donor scrolls resolve to `SCRL6M` for Enchanted Weapon (`SPWI417`) and
`SCRL5H` for Emotion, Hopelessness (`SPWI411`). The effective donor-shadow store scan found:

| New scroll | Donor | Stores whose donor entries are mirrored |
|---|---|---|
| Courage (`CDIA428`) | Enchanted Weapon (`SCRL6M`) | `25SPELL`, `25SPELL2`, `BPDING01`, `BSHOP01`, `C0LEANNE`, `RIBALD`, `SHOP08`, `TRCAR04`, `TRMER04`, `TYPE2` |
| Hope (`CDIA429`) | Emotion, Hopelessness (`SCRL5H`) | `25SPELL`, `25SPELL2`, `BDBELEG3`, `BPDING01`, `SCROLLS`, `SHOP08`, `TYPE1`, `ULGOTH` |

These exact store names describe this modded installation; they are not a fixed CBR placement
list. The component must discover the two donor scrolls from their live spell symbols and
clone the live donor entries wherever found. This preserves store-specific quantities,
charges, flags, and ordering without assuming a particular campaign or mod stack.

IWDification component 30 instead passes
`custom/cd_scroll_placement.tpa custom/cd_arcane_spell_use.tpa` from
`iwdification/setup-iwdification.tp2` lines 1024–1027. In
`iwdspells/custom/cd_scroll_placement.tpa`, the relevant fixed additions are:

- lines 13–33, guarded by `GAME_IS ~eet bgee tutu tutu_totsc bgt~`: Courage goes to the
  BG1 Iron Throne level-4 area (`BG0614` on this EET mapping), `Container8`;
- lines 48–57, additionally guarded by `GAME_INCLUDES sod`: Hope goes to `BD2100`, `chest`;
- lines 155–171: `AERIE6`, `AERIE7`, `AERIE9`, `AERIE10`, `AERIE11`, and `AERIE12` gain
  Courage only when the CRE exists, class byte is 14, and mage level at `0x235` is greater
  than 6 (inside the broader greater-than-2 spell grant);
- lines 237–251: `JAN8`, `JAN10`, `JAN11`, `JAN12`, and `JAN15` gain Courage only when the
  CRE exists, class byte is 13, and mage level at `0x234` is greater than 6.

There is no Hope known-spell CRE grant. There is also **no random-table distribution for
either Hope or Courage**: lines 8–10 alter `RNDSCROL.2DA` only to replace a duplicate Grease
entry with Expeditious Retreat. The two beneficial Emotions are distributed only through
donor-store shadowing and the fixed container/CRE additions above.

The CBR fallback therefore mirrors the common dynamic store behavior only. Reproducing the
IWDification-only campaign scatter would duplicate content on existing installs and make
standalone behavior depend on fixed areas or saved CRE state.

## IWDEE provenance and standalone visual boundary

Two pristine IWDEE installations were checked read-only:

- `C:\Program Files (x86)\Steam\steamapps\common\Icewind Dale Enhanced Edition`;
- `C:\Games\Icewind Dale Enhanced Edition`.

Their 532,346-byte `chitin.key` files are byte-identical, SHA-256
`2C16C07B3DE69BCEA935C2C68CAFC01F08D85DC74056EC5D40E4A2AA24013461`.
Packed IWDEE `SPWI427` and `SPWI429` match the IWDification/SCS copyover donors exactly:

| IWDEE resource | Size | SHA-256 |
|---|---:|---|
| Courage `SPWI427` | 874 | `65FABF10505B6D5BEF41A1E7AC8F0E8ED4D516C4A9988E926A5CD824F412B250` |
| Hope `SPWI429` | 778 | `35B070A4CD1889285AFEE55DF40403F48A5B3ED34540387BE735F365E20D9BF0` |

Every file in the two IWDification/SCS Hope/Courage copyover folders matches its packed
IWDEE counterpart. Selected graph resources include:

| Resource | Role | SHA-256 |
|---|---|---|
| `IDPRO407.PRO` | area projectile chain | `B4725639B39D11DE292932EFC59693C6B6B2D32925472E63A353087FACF1E6BE` |
| `#GENENCH.VVC` | projectile visual | `670B8A6AC5A403263DC2CB64BCCA126BFDF77C9DB87F258E6FA4393DA42F9D8A` |
| `ENCHANX.BAM` | visual animation | `730E330EF9390EDF139C77EC01730630D89D1D4030CA86A1E450B7F155C6C33B` |
| `#ARE_M21.WAV` | projectile audio | `46BDF9F2E7631AA717B2ADA6870B2F6A6D7DE71CA7BC5480B1AD6DE654EBE3B2` |
| `#EFF_E03.WAV` | delayed effect audio | `634DFE623FA34E096637F82487373B382CF290CB80E56D5D5DC8DE67EB61DC1F` |

The unmodded BG2EE KEY contains none of the selected IWD graph resources: `SPWI427`,
`SPWI429`, their A/B/C icons, `#ARE_M21`, `#EFF_E03`, `#EFF_M05`, `#GENENCH`, `ENCHAH`,
`ENCHANX`, and `IDPRO407` are all absent. The original IWDEE spells use missile 434
(`PROJECTL.IDS` 433, `IDPRO407`) through `#GENENCH.VVC`/`ENCHANX.BAM` and `#ARE_M21.WAV`,
plus `ENCHAH`, `#EFF_M05`, `#EFF_E03`, and an IWD glow.

IWDification's style conversion at `iwdspells/iwdspells_arcane.tpa` lines 54–55, using
`sfo/data/spell_styles_iwd.2da` and `spell_styles_bg.2da`, already substitutes the
BG-native Enchantment casting package: opcode 141 parameter 2 = 10, `EFF_M05`, and BG glow
parameters 509245440/1638400. The final spells retain the imported projectile chain and
delayed `#EFF_E03`; their A/B/C icons are still exact IWDEE assets. Pristine IWDEE has no named
`SPWI427D`, `SPWI429D`, `PI_COURAGE`, or `PI_HOPE` resource. Its status artwork instead lives in
the monolithic `STATES.BAM`: Hope is cycle 251/frame 177 and Courage is cycle 252/frame 178;
both frames are 13x13 with center `(0,13)`. IWDification's generated `pi_hope` is an exact copy
of frame 177, while its `pi_courage` shifts frame 178 one pixel right and one pixel up.

Accordingly, component 301 retains valid installed presentation references for provider spells.
Its standalone branch keeps the BG Enchantment casting package and `CAS_M05`, but packages the
six original blue IWDEE A/B/C icons, two unmodified heart frames extracted independently from
pristine IWDEE, and the exact IWDEE Emotion delivery graph. The standalone status BAM hashes are
`6156D0716907E4DD3195CCBF957B061F97A68051CE20FF9CE9C64A04422DFBCC` for Courage and
`4045A535EAF4BD0B90E377B232D7EE8964AE9A09CAD50BC01D7BB523FF00E93E` for Hope. At install time
the graph is collision-safely remapped as:

```text
CBR301P.PRO -> CBR301V.VVC -> CBR301A.BAM + CBR301W.WAV
standalone SPL opcode 174 -> CBR301E.WAV
```

`CBR301P.PRO` is based on `IDPRO407.PRO`. Its area flag word at `0x200` is `0x04C0`: the
faction filter is enabled, allies are selected, and the VVC is drawn. This is the crucial
difference from BG2's enemy-only `HOLD.PRO`. The PRO dependency at `0x21C` and the VVC
dependencies at `0x08`/`0x78` are rewritten to the private names. The installer does not read
either sibling IWDEE path; all required source assets are packaged with verified hashes.

## Component 301 installation contract

The implementation must:

1. resolve or allocate both level-four wizard symbols before writing any cross-reference;
2. rebuild Hope and Courage deterministically with exactly one self-remover and one reciprocal
   remover at the start of each recipient header;
3. preserve/normalize the established adverse removers: Fear and Symbol, Hopelessness share
   their hostile mechanic's save/MR domain, while Emotion, Hopelessness removes Hope
   unconditionally before its separately saved hostile effects;
4. retain Courage's decoded opcode-23 morale normalization, opcode-240 panic-icon removal,
   and opcode-161 Cure Horror package without describing it as a maintained +20 morale bonus;
5. preserve valid installed presentation records, but use the privately namespaced IWDEE
   Emotion projectile/animation/sound graph and original blue icons in the standalone branch;
6. preserve a provider's existing raw opcode-142 status entry, while each standalone spell
   receives a private native-IWDEE heart BAM, a distinct free `STATDESC.2DA` row at 200 or above,
   and exactly one target-2, power-4, 300-second opcode 142 referencing that row;
7. recreate SCS opcode-328 markers by symbolic `SPLSTATE.IDS` lookup, never by observed
   numbers 194/195;
8. reuse existing learn-scrolls when present and, only for a newly allocated beneficial spell,
   construct a clean two-ability IWDification-style CBR scroll (point target, range 50,
   opcode 148 at caster level 10, then opcode 147 learning);
9. dynamically discover the Enchanted Weapon and Emotion, Hopelessness donor scrolls, then
   clone their current store entries for standalone Courage and Hope respectively;
10. avoid fixed area, CRE, save, or spellbook mutation; and
11. publish original CBR English descriptions that disclose beneficial-Emotion exclusivity.

Tests must cover relocated symbols, the observed duplicate-Fear regression, SCS marker
preservation, one/both symbols absent, repeated application, provider status-entry preservation,
standalone dynamic status rows/icons, donor-store discovery, existing scroll reuse, and exact
synthetic uninstall restoration.

## Implementation and automated verification

Component 301 (`cbr_emotion_hope_courage_exclusion`) is implemented in
`setup-chriz-bg-rebalance.tp2` and delegates the deterministic binary transformation to
`chriz-bg-rebalance/lib/emotion_hope_courage.tpa`. The public installer resolves every spell,
state, projectile, scroll, and store relationship from the target game's final resources;
it carries no observed live-install resref or store list as a production constant.

Automated verification covers two independent layers:

- `tests/test_emotion_hope_courage.py` checks the transformer contract, malformed-resource
  preflight, exact beneficial/adverse effect shapes, descriptions, scroll publication, and
  byte-stable repeat application;
- `tests/test_emotion_hope_courage_installer.py` runs component 301 under WeiDU against a
  synthetic BG2:EE KEY/BIF/override/TLK layout. Its matrix covers both symbols present, neither
  present, Courage-only, and Hope-only installations; symbolic allocation and optional SCS
  markers; dynamic donor-scroll store mirroring; forced reinstall; transactional failure; and
  forced uninstall restoration. Synthetic resources, IDS files, scrolls, stores, and
  `STATDESC.2DA` restore exactly on uninstall. The four base translated strings plus only the
  status labels needed for newly allocated spells follow WeiDU's append-only TLK behavior and
  remain allocated rather than truncating `dialog.tlk`.

### Corrections found by a real standalone install

The first disposable-clone install was intentionally allowed to exercise real game resources
rather than fixtures. It rolled back with zero published files when the validator rejected
vanilla `SPWI411`. Four fixture-masked assumptions were then captured as failing regression
tests before the installer was corrected:

1. vanilla `SPWI411` has 14 ability headers with 21 effects each and no opcode-45 donor; an
   unconditional adverse remover must not require a save-domain donor;
2. real `SPELL.IDS` maps `3105 INNATE_HORROR` to `SPIN105`; 3000-series innate IDs require
   WeiDU's `RES_NUM_OF_SPELL_NAME` mapping rather than the compatibility rule for nonstandard
   100–999 innate rows;
3. real `MISSILE.IDS` stores `190 HOLD`, but `HOLD.PRO` filters for enemies and is not a valid
   beneficial Emotion delivery projectile; and
4. native `SCRL6M` casts with actor-target opcode 146. Cloning it made Courage impossible to
   target on the ground. IWDification instead constructs a fresh point-target scroll with
   opcode 148 and a separate opcode-147 learning ability.

A final independent review also hardened scroll discovery itself. Candidate items now need
exact one-owner coverage of every global/ability effect, so malformed matching resources are
ignored rather than creating false donor ambiguity. Donors remain distribution anchors in this
initial implementation; their item bytes do not shape the generated scroll.

The exact pristine `SPWI411` used for that regression is 14,786 bytes with SHA-256
`068C19B7A09D677D39621A61C883DD13356CE2D1A37A10586F1FD0EAE66AA7A8`.
It was byte-identical across the pristine Steam game and the checked development clones.

### Superseded first fallback audit

The earlier fallback build was installed with WeiDU 25100 into the isolated clone
`C:\Games\Baldur's Gate II Enhanced Edition modded - CBR301 DISPOSABLE TEST 20260830 R2`.
The clone allocated `2422 WIZARD_EMOTION_COURAGE` (`SPWI422`) and
`2426 WIZARD_EMOTION_HOPE` (`SPWI426`); the existing `3105 INNATE_HORROR` resolved to
`SPIN105`. The production installation was not used for installation or runtime testing.

That audit established the following structure, but the later UI test proved its delivery
choices were wrong:

- Courage and Hope each had one ability, used the `HOLD` stored projectile word 190, and had
  exactly one self-remover plus one reciprocal beneficial remover at the start of the recipient
  slice;
- Courage's administrative source removers are `SPWI422`, `SPWI426`, `SPWI205`, and
  `SPIN105`; Hope's are `SPWI426`, `SPWI422`, and `SPWI411`;
- all 14 vanilla `SPWI411` headers begin with exactly one unconditional `SPWI426` remover;
- `CBRCRGSC` inherited actor-target opcode 146 from `SCRL6M`; `CBRHOPSC` inherited opcode 148
  from its unrelated donor; and
- the donor scan found 22 rows across 16 stores. Installation produced exactly 22 adjacent
  clones with the donor row's complete stock tail preserved: `25SPELL`, `25SPELL2`, `BSHOP01`,
  `GARLENA1`, `OHBMHSM2`, `OHNMHSM2`, `RIBALD1`, `SAHPR1`, `SCROLLS1`, `SHOP08`,
  `SUELF10`, `TRCAR04`, `TRMER04`, `TYPE1`, `TYPE2`, and `UDDROW25`.

A forced uninstall/install cycle completed in one WeiDU process. The override and TLK snapshot
was byte-stable; only `WeiDU.log` changed because WeiDU records the expected commented
`Recently Uninstalled` history line.

### UI failure and corrected fallback

The later manual UI test supplied decisive negative evidence:

- both fallback spell icons were red donor icons instead of the blue IWD icons;
- neither spell applied any effect or buff to the clustered party;
- Courage could not target the ground at all.

Binary comparison against pristine IWDEE and IWDification identified two independent root
causes. The fallback SPLs used `HOLD.PRO`; byte `0x200 = 0x50` enables the faction filter for
enemies, so a beneficial preset-target payload cannot reach allied party members. The Courage
scroll was cloned from Enchanted Weapon and therefore retained LivingActor/touch targeting and
opcode 146 instead of IWDification's PointWithinRange/range-50/opcode-148 contract. Direct EEex
feature-block application in the earlier runtime test bypassed both the scroll and projectile,
so it proved the buff mechanics but never proved real spell delivery.

Regression tests were added in the failing state before correction. The corrected standalone
path now:

- publishes the private IWDEE allies-only projectile graph and verifies the private PRO/VVC
  links plus `PROJECTL.IDS + 1` stored value;
- publishes byte-identical blue IWDEE A/B/C icons under each dynamically allocated spell name;
- constructs each 322-byte scroll from scratch with two abilities, point targeting, range 50,
  opcode 148/caster level 10, and opcode 147 learning; and
- keeps donor scrolls only as dynamic store-distribution anchors.

The corrected installer matrix, reinstall/uninstall cycle, asset hashes, projectile flags,
scroll layout, and publication allowlist pass automatically. Later real UI casts from the R2
host verified delivery, the complete stat sequences, and Hope/Courage replacement. They also
exposed a separate presentation omission: neither fallback spell contained opcode 142, so no
Courage or Hope entry could appear in the character-sheet status list. The status-entry
correction described below is automated-verified; the final manual status-list retest remains
pending.

### Corrected-build installation audit

The corrected component was first installed with WeiDU 24900 into a fresh disposable copy:

`C:\Games\Baldur's Gate II Enhanced Edition modded - CBR301 CORRECTED TEST 20260830`

Its source was the separate 3.54 GiB `dev clean install`, which had no `WeiDU.log`. The failed
UI-test copy was not uninstalled or overwritten, and the production installation remained
read-only. The corrected install allocated `2422 WIZARD_EMOTION_COURAGE` (`SPWI422`),
`2426 WIZARD_EMOTION_HOPE` (`SPWI426`), and projectile registry row `346 CBR301P`; these spell
resrefs match the failed copy, so the isolated test save remains compatible.

Post-install parsing of the actual override resources established:

- both SPLs are level-4 Enchantment spells with Invoker exclusion `0x800`, point target 4,
  range 50, stored projectile 347, and their dynamically renamed `B`/`C` icons;
- both spell descriptions state that Courage and Hope are mutually exclusive, and each
  ability begins with exactly one self-remover and one reciprocal remover before its mechanics;
- `CBR301P.PRO` has flags `0x04C0`, links to `CBR301V`, and has SHA-256
  `86E6DCFD8583774898B3D26F8ED3AB307E05F53778FD51BD98836BF232328282`;
- `CBR301V.VVC` links to `CBR301A` and `CBR301W`, with SHA-256
  `332054F1C378E1DAE16444BD4DABD32D0BD28A2DE535395B11814ADBE7A4C03F`;
- all six installed dynamic `A`/`B`/`C` BAMs are byte-identical to their packaged original
  IWDEE Courage/Hope icons; this pre-status R2 build had no corresponding `D` BAMs or opcode-142
  effects, which explains the later missing status-list rows;
- `CBRCRGSC.ITM` and `CBRHOPSC.ITM` are each 322 bytes with exactly two abilities: a
  PointWithinRange/range-50 opcode-148 cast at caster level 10 and a caster-target opcode-147
  learning ability; and
- dynamic store mirroring placed Courage in 11 stores and Hope in 10 stores on this clean game.

After the independent review correction for the `0x800` exclusion field, the focused 43-test
component suite and the full 182-test repository suite both passed at that revision. This audit
proved the installed resource graph and payload shape. The later real UI casts supplied the
separate engine-delivery evidence and exposed the status-entry omission.

The first attempted UI load from that clean clone crashed before a spell could be exercised.
This was a test-host error, not evidence against component 301. The old `bfbt-test` save was
created under EEex/BuffBot and contains EEex `X-BIV1.0` auxiliary marshal records on all 23
GAM creatures plus 32 saved-area actors. It also names the ad-hoc BuffBot test spells
`BFBT01`, `BFBT02`, `BFBT11`, and `BFBT12`. The clean corrected clone had neither the EEex
unmarshal hook nor those resources and was launched directly through `Baldur.exe`. Without the
hook, the vanilla effect reader reaches the auxiliary payload bytes `Buff` as an invalid effect
opcode during save loading. The save predates component 301 and contains no references to
`SPWI422`, `SPWI426`, `CBRCRGSC`, or `CBRHOPSC`.

A second fresh compatible host was therefore built without uninstalling any component:

`C:\Games\Baldur's Gate II Enhanced Edition modded - CBR301 CORRECTED UI TEST R2 20260830`

Its WeiDU order exactly matches the previously load-capable environment: EEex 0/1, BuffBot
0/1, EEex Remote Console 0, then corrected component 301. It uses the English TLK, has the
same InfinityLoader/EEex runtime hashes, carries the four exact ad-hoc BuffBot spell fixtures,
and sets `engine.lua` to the isolated `CBR301 UI Test 20260830` profile. A post-build preflight
and a repeat parse of both corrected SPLs, both 322-byte scrolls, all six A/B/C IWDEE icons, and
the private PRO/VVC graph passed. The isolated `BALDUR.gam` and `BALDUR.SAV` hashes remained
unchanged before testing. This R2 host was launched through its own `InfinityLoader.exe`; the
subsequent load and real UI cast sequence completed without a new save.

The status-entry revision was installed, again without uninstalling any prior clone, into a
third fresh compatible host:

`C:\Games\Baldur's Gate II Enhanced Edition modded - CBR301 STATUS UI TEST R3 20260830`

Its WeiDU order is EEex 0/1, BuffBot 0/1, EEex Remote Console 0, then component 301. It has an
independent copied profile named `Baldur's Gate II - Enhanced Edition - CBR301 Status UI Test R3
20260830`; the copied `bfbt-test` `BALDUR.GAM` and `BALDUR.SAV` hashes are unchanged from the R2
source. The install again allocated `SPWI422` Courage and `SPWI426` Hope. Installed-resource
auditing established:

- Courage has exactly one 300-second opcode 142 referencing `STATDESC.2DA` row 207; that row's
  TLK text is `Courage` and its BAM is `SPWI422D`;
- Hope has exactly one 300-second opcode 142 referencing row 208; that row's TLK text is `Hope`
  and its BAM is `SPWI426D`;
- both effects use recipient target 2, power 4, timing 0, dispel/resistance byte 3, and no save;
- each D BAM is one 13x13 frame and exactly matches its independently extracted native IWDEE
  hash; and
- both point-target scrolls still use opcode 148 with range 50, while both SPLs retain their
  self and reciprocal timed-effect removers.

The current focused feature suite passes 44 tests, the full repository suite passes 183 tests,
and all three relevant WeiDU TP2/TPA parse checks pass. Only the visible in-game status-list
result remains unverified.

### Runtime behavior

The earlier clone was launched through its own `InfinityLoader.exe` and an isolated user profile. A
duplicate of a prior development save was loaded; the original save was never opened for
writing, and no save was created by this test. The installed SPL ability blocks were applied
directly through EEex to the protagonist and the engine was allowed to process effect-list
ticks. These results validate the recipient-effect mechanics only; they bypassed delivery.

- Courage produced exactly its three persistent mechanical effects (opcode 18 +5 maximum Hit
  Points, opcode 54 +1 THAC0, and opcode 73 +3 damage). Maximum Hit Points changed 70→75 and
  THAC0 14→13. Reapplication left exactly three effects and unchanged bonuses.
- Hope produced exactly its three persistent mechanical effects (opcode 54 +2 THAC0, opcode 73
  +2 damage, and opcode 325 +2 to every save). THAC0 changed 14→12 and saves
  8/10/9/10/11→6/8/7/8/9. Reapplication refreshed expiry without stacking.
- Hope followed by Courage left zero Hope and three Courage effects; Courage followed by Hope
  left zero Courage and three Hope effects.
- Hope followed by the installed `SPWI411` remover lost Hope and returned to baseline. A real
  timed `SPWI411` feature followed by Hope left zero `SPWI411` and the Hope package active.
- Real timed panic features sourced from `SPWI205` and `SPIN105` were both removed by Courage,
  leaving the Courage package active.

The standalone clone did not contain `WIZARD_EMOTION_FEAR` or Symbol, Hopelessness, so their
reverse adverse-to-beneficial directions remain installer/transformer-tested rather than live
in that clone. Horror and Innate Horror are deliberately cleanse-only inputs; component 301
does not rewrite them to remove Courage.

Queued `UseItem`/`UseItemPoint` actions were not valid casting evidence. The subsequent user-run
UI tests supplied two stronger results. The first exposed the broken HOLD/donor-clone fallback
described above. The second used the corrected point-target scrolls and allies-only projectile:
both real casts applied, every expected stat change appeared, and the Hope/Courage sequence
replaced the earlier benefit as intended. However, neither cast produced a character-sheet
status entry. Binary inspection then confirmed that both R2 fallback SPLs had zero opcode-142
effects and the clone had no CBR status rows or D-icon resources.

The correction packages the two unmodified 13x13 native IWDEE heart frames as source `D` BAMs.
For each missing spell only, the installer allocates a distinct free `STATDESC.2DA` row at 200
or above, writes the localized `Courage` or `Hope` label and `<resolved spell>D` BAM name, and
adds exactly one recipient-targeted, power-4, dispellable/bypass-resistance opcode 142 lasting
300 seconds. Existing provider spells preserve their raw opcode-142 effects and do not publish
fallback D assets or status labels. Automated installer tests cover standalone, mixed-provider,
provider-only, reinstall, and uninstall paths. The remaining live gap is the visible status-list
retest of this corrected revision.

### Reinstall, uninstall, and restoration

After the runtime process was closed, WeiDU uninstalled component 301 and reported 23 restored
files. There is no active component-301 log entry, all allocated spell/scroll and patched
spell/store/IDS overrides are absent exactly as in the pristine source clone, and both clones'
`chitin.key` files retain SHA-256
`EAEF6ADE748ACFABE940220CFF6791CBA745FEE090115B129DF5ED77962491E5`.
WeiDU's commented `Recently Uninstalled` log line and append-only TLK strings are expected
installer history, not active resources.

Publication checks restrict output to the resolved spell/adverse/scroll/store/IDS resources,
`STATDESC.2DA`, the five private presentation resources, and four dynamic icons per newly
allocated spell. They leave unrelated BIF and override resources unchanged. The repository
contains original installer code and text plus the thirteen independently extracted IWDEE
presentation assets; it contains no copied IWDification or SCS binaries.

## Evidence boundaries

The production installation at `C:\Games\Baldur's Gate II Enhanced Edition modded` and its
active saves remained read-only. Controlled installation and runtime work occurred only in the
explicit disposable clone and isolated profile above. The production store lists earlier in
this note are a snapshot of one heavily modded EET installation; the implementation predicate
is dynamic donor-entry discovery, not equality with that snapshot. Real UI delivery and mutual
replacement are verified; the immediate manual gap is the final Courage/Hope character-sheet
status-list retest. Live directions involving adverse resources absent from the standalone clone
also remain unverified.
