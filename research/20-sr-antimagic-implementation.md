# SR anti-magic: approved changes and implementation evidence

Date: 2026-10-06. Owner: BG Rebalance SR adjustments, components **210/211**.
Version: `v0.8.1-dev`, unpublished. The user explicitly approved implementation
after choosing the mechanics below. Entropy Shield remains deferred.

The [source comparison](2026-10-06-sr-antimagic.md) identifies the original problem:
SR Pierce Magic sets MR to zero for two rounds, while SR Spellstrike adds a full
round of guaranteed normal spell failure followed by 50%. Pierce Shield has no
MR modifier on this installation and is not part of the change.

## Approved behavior

- **210, `cbr_sr_pierce_magic`:** let M be current nonnegative MR. On the first
  successful hit choose `min(M, max(10, min(40, ceil(M/2))))` percentage points,
  applied as a fixed additive subtraction for **30 seconds / five rounds**.
  Examples: 100 -> 60, 80 -> 40, 60 -> 30, 21 -> 10, 10 -> 0, 0 -> 0.
  Repeated successful casts refresh the **same amount** for another five rounds;
  they do not compound or recalculate it. Other MR changes can coexist, including
  Lower Resistance. After the effect expires, a new cast measures MR again.
- **211, `cbr_sr_spellstrike`:** one 15% failure effect for arcane spells and one
  for divine spells, each **12 seconds / two rounds**. Recasts refresh rather than
  self-stack. Other sources of spell failure retain their normal additive behavior.
- Both retain original protection removal, Spell Shield interception and any
  existing SCS invisible-targeting flag. Neither changes Pierce Shield, Lower
  Resistance, Entropy Shield, spell levels, casting times or projectiles.

## Why component 210 uses EEex

Opcode166 supports additive and SET operations; a native percentage mode is not
documented. Native opcode326/stat bands could choose a subtraction, but removing
an old reduction and immediately testing MR does not establish that derived stats
were rebuilt. That could turn MR60 ->30 on first cast into MR45 on recast.

The implemented callback `CBRPM` reads the impact stat once and creates an ordinary
timed166 effect with private source identity `CBRPM`, plus a matching portrait
icon. Subsequent casts locate that native effect and extend its absolute expiry,
leaving its amount and all foreign effects alone. Normal active effects serialize
through the engine, without storing their amount in transient Lua state.

EEex's `EEex_Sprite_GetStat` delegates to `GetActiveStats`, whose documented
purpose is to avoid the work-in-progress stats structure during effect-list
processing. Source: the inspected game's
`EEex/copy/EEex_scripts/EEex_Sprite.lua:535-584`. It chooses `m_tempStats` in that
case intentionally. Do not replace it with a direct in-progress derived-stat read.

If an expired or done owned166 is still linked at impact, measurement waits until
the native effect-list-resolved hook has removed that stale record. It retains
the impact's original expiry deadline and uses scalar pending data only. There
is no arbitrary one-second delay. Reentry clears pending work before effect
application. The callback validates ownership, amount, additive mode and absolute
timing, and rejects duplicate/malformed owned records rather than stacking again.

The callback checks that the engine accepted the new166 before displaying its
icon; an opcode immunity must not leave misleading successful feedback.

Source/API references:

- [Opcode166 modes](https://gibberlings3.github.io/iesdp/opcodes/bgee.htm#op166).
- Installed `EEex_Opcode_Patch.lua:876`: opcode402 calls `FUNC(effect,sprite)`.
- Installed `EEex_GameObject.lua:279-456`: application arguments and
  `immediateResolve`, normal saving/immunity checks retained.
- Installed `EEex_Utility.lua:105`: CPtrList iteration.
- Installed `override/BfBotExe.lua:151`: game-time accessor.

## Installer ownership and compatibility

`sr_antimagic.tpa` resolves WIZARD_PIERCE_MAGIC and WIZARD_SPELL_STRIKE via
`spell.ids`, accepts direct SR resources or follows actual target2 opcode146
links, and requires one unambiguous effect-bearing payload. It does not assume
native slot numbers or the usual B suffix. Both spell-table layouts and donor
mechanics are validated before description allocation; WeiDU owns rollback.

For Pierce Magic the402 callback replaces the SET0 effect and runs before the
stripper to take its impact snapshot. The old12-second icon and expiry sound
are removed; the runtime owns the30-second refreshing icon. Other visual effects
and mechanics stay intact. Component210 requires EEex and reserves CBRPM across
SPL/EFF/ITM plus M_CBRPM.lua, rejecting foreign collisions.

`sr_spellstrike.tpa` collapses the owned failure effects while preserving donor
metadata, and inserts a timed-effects-only opcode321 against the actual payload
resref. It leaves casting features, unrelated effects and permanent administrative
effects intact. It needs no runtime helper or EEex dependency.

Both require SR main component0, not SR65. The main and standalone installers
block duplicate installation of each component across families. Existing-install
instructions append the standalone patch; they never reinstall SR or existing
Rebalance components. Descriptions receive private strings, retaining the SCS
invisible-targeting note only when the actual flag is present.

## Evidence and remaining boundary

- 13 real-WeiDU Spellstrike transformation tests: donor validation, effect-slice
  order/casting offsets, foreign-byte preservation, idempotence and malformed input.
- 13 Lua behavioral test methods, including every input MR0-150, odd rounding,
  same-frame recasts, other MR modifiers, zero snapshot, simulated native-effect
  serialization, expiry/done deferral, immunity rejection and malformed ownership.
- 24 public installer/packaging tests exercise main/tail, independent selections, dynamic
  slots/arbitrary child names, direct SR, namespaces, descriptions, prerequisites,
  rollback, synthetic reinstall/uninstall and archive contents.
- Combined focused suite including Hardiness and physical-resistance integration
  regressions: **102 tests passed** (100 together, then the two new packaging
  checks against the unchanged implementation).
- Both main and tail210+211 passed against copies of the effective CEBG parents,
  B/C children and protection resources in temporary synthetic games. Original
  game files were only read, with unchanged hashes rechecked afterward.

These checks do not validate the native engine. First-hit synchronous linking
and conversion to absolute effect timing4096 after ApplyEffect, direct expiry
serialization, expiry-boundary stat rebuilding and protection interception require
separate live acceptance. See the [tail checklist](../live-patch/CBR_SR_ANTIMAGIC/README.md).
No game, save or collection recipe was modified and nothing was published.
