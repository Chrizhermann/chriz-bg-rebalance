# chriz-bg-rebalance

Personal SCS- and SR-adjacent balance adjustments and spell-behavior fixes for
**BG2:EE / EET** installs. Sibling of
[chriz-bg-modpack](https://github.com/Chrizhermann/chriz-bg-modpack) (fix consolidation) and
[chriz-sod-rebalance](https://github.com/Chrizhermann/chriz-sod-rebalance) (SoD remix + companions).

**Status:** active component development. See `docs/00-project-scope.md`.

## Credits — stand on the shoulders of giants

This mod exists *because* of two outstanding open-source mods, and it only makes sense installed
on top of them:

- **[Sword Coast Stratagems (SCS)](https://github.com/Gibberlings3/SwordCoastStratagems)** by
  DavidW — the gold standard for Infinity Engine AI and tactics. Install it. This mod merely
  files down a few rough edges.
- **[Spell Revisions (SR)](https://github.com/Gibberlings3/SpellRevisions)** by Demivrgvs & the
  Gibberlings3 team — a thoughtful, comprehensive spell rebalance. Most of its changes are
  excellent; this mod adjusts the handful that don't fit my table.

Code patterns in this repo are frequently adapted from SCS (open source). Bugs found here are
reported upstream first (see `research/02-upstream-scs-report-draft.md`).

## Components

| # | Group | Component | Status |
|---|-------|-----------|--------|
| 100 | SCS adjustments | Telekinetic Storm: restore save vs. spell for half damage (+ bypass Mirror Image) | ✅ implemented |
| 101 | SCS adjustments | Restore five Freedom scrolls to the Adventurer's Mart | ✅ implemented |
| 120 | SCS adjustments | Repair the SCS/SR false Improved Mantle weapon-protection semantics | ✅ implemented |
| 121 | SCS adjustments | EEex ambient caster readiness + one honest first-contact defense | ✅ implemented; v1.2 ambient + neutral-to-hostile urgent path live accepted; legacy live pending |
| 2xx | SR adjustments | Cherry-picked Spell Revisions tweaks | 📋 planning (`docs/00-project-scope.md`) |
| 3xx | Cross-cutting audits | e.g. generalized save-for-half audit | 📋 planning |
| 401–403 | Class and kit revisions | Cleric of Tempus: revised Holy Power | ✅ implemented; choose one compatibility mode |

### Component 100 — Telekinetic Storm save fix

SCS's *extra arcane spells* component adds Telekinetic Storm (level 8, 1d6/level magic damage,
AoE). Its description promises "Saving Throw: 1/2", and the damage effect carries the
*save-for-half* flag — but no save **type** is set, so the engine never rolls a save and the
spell always deals full damage (16d6–20d6). It also misses the EE-conventional
*bypass mirror image* flag for AoE damage. Sibling spells in the same SCS source file
(Stormbolts, Icy Ray) set both `s_save_vs_spell=1` and `s_bypass_mirror_image=1`; Telekinetic
Storm's author simply forgot them. Still present on SCS master as of 2026-07-02.

The component resolves the spell dynamically via `spell.ids` (`WIZARD_TELEKINETIC_STORM`) and
ORs `save vs. spell (bit 0) + bypass mirror image (bit 24)` into the save-type field of every
save-for-half damage effect, across all level-scaled ability headers. Idempotent.

Full diagnosis: `research/01-telekinetic-storm-save-bug.md`.

### Component 120 — SCS / Spell Revisions weapon-protection compatibility

On the researched Spell Revisions install, both `WIZARD_IMPROVED_MANTLE` and
`WIZARD_MOMENT_OF_PRESCIENCE` resolve to the same level-eight spell. Moment of Prescience
does not grant weapon immunity, but SCS's generated common-mage scripts and detectable-spell
metadata still treat that slot as if it did.

Component 120 dynamically resolves the final `SPELL.IDS`, classifies the installed spells by
their reachable opcode-120 effects, and repairs only three proven SCS contexts: false
first-round and renewal choices are removed, while Chain Contingency keeps its generated
helper and substitutes the closest lower genuine protection. Only the exact false metadata
markers are removed; Moment of Prescience's real AC, saving-throw, duration, school, text,
and other gameplay effects remain unchanged. Unknown script shapes are reported and left
byte-identical.

This is a compatibility repair, not a redesign of Moment of Prescience. If a later Spell
Revisions version restores a genuine Improved Mantle at that mapping, the semantic
classifier makes component 120 a byte-no-op. The compiled-block transformer is a small,
namespaced adaptation of SCS v35.21's `alter_script.tph`; credit for the underlying AI and
script system belongs to DavidW. Spell Revisions and Moment of Prescience are by Demivrgvs
and the Gibberlings3 team.

### Component 121 — EEex ambient readiness bridge

This is an interim bridge for SCS casters, not the eventual full EEex AI overhaul. At install
time it resolves the final `SPELL.IDS`, validates the installed spell effects, and imports
SCS's own cosmetic-free prebuff mapping. It then ships one stamped `M_CBRRDY.lua`; it does
not patch SCS combat scripts or spell mechanics. It requires BG2:EE/EET, SCS Smarter Mages
6030, EEex's `M_*.lua` autoload bootstrap, and the final SCS prebuff map. EEex v1.2.0 is the
primary target. It uses one deferred lists-resolved callback as the sole scheduler and one
synchronous lists-resolved callback as an ambient pending-confirmation observer; the latter
does no classification, scheduling, or urgent work. Legacy EEex instead uses one synchronous
callback as the full scheduler. The expected listener counts are therefore `1 deferred + 1
synchronous = 2` on v1.2 and `0 + 1 = 1` on legacy. If the synchronous observer API is
missing on the current path, ambient readiness fails closed while the urgent layer may keep
using the deferred scheduler. Both modes read the direct `m_worldTime.m_gameTime` field used
by EEex itself as raw 15-Hz engine ticks. The component does not hardcode EEex WeiDU
component numbers or impose a component-specific LuaJIT requirement. Missing prerequisites
skip cleanly; malformed recognized data fails before the override transaction is retained.
Component 120 is independent, but installing 120 first is recommended on the currently
researched SR setup.

The first v1.2 live pass exposed a bad `GetCurrentTime()` assumption. The corrected-clock
rerun delivered the expected Vigil buffs, but a read-only inspection found every memorized
count unchanged and every component ledger empty. Exact EEex v1.2 source and BG2EE 2.6.6
disassembly explain the split result: immediate opcode 146 with `dwFlags=1` resolves the
outer effect, then publishes its child spell through `CMessageFireSpell` /
`CGameAIBase::FireSpell` after the deferred scheduler returns. It does not create action 181.
The accounting correction has 76 focused automated tests passing, and the full repository
suite passes 253 tests. A fresh-process `AR3000` diagnostic against runtime SHA-256
`EF38A1A0BF942A2B3AB294FAE48DA2548E9413DBD5FE7CB255406C413E06DD3D` then passed ambient
delivery and one-slot accounting on all four neutral Vigil casters: every exact marker and
schema-2 charged ledger was present, with the expected `2 -> 1` or `1 -> 0` slot delta and no
ambient failure. The first urgent attempt exposed a second EEex binding correction:
`virtual_ClearActions` requires an explicit Boolean. After changing the passive-only replacement
path to `virtual_ClearActions(false)`, the stamped lab runtime SHA-256
`9957348E7DB69EE24CA149787887B9AD36012B0F34A2D665CE041611F32B3D08` passed the retest.
An attack order alone correctly left the neutral Vigil group ineligible; after the first hit
made Brother Pol hostile, the component started his exact normal `SPWI708` cast, spent its one
contact attempt and one Mantle slot, left the opcode-120 protection active, and kept
`urgent_faulted=0`. A generic mage already executing non-passive action 22 was not displaced.
The legacy fallback still has no corrected live gameplay pass.

The ambient layer considers only recognized, settled SCS casters and conservative installed
self-buffs lasting at least 2,400 seconds. A caster must really have the spell memorized. The
deferred scheduler requests delivery once and retains only an exact primitive spellbook
locator, original flags/count, and deadline. When the child marker resolves, the synchronous
observer revalidates those baselines before spending one copy and committing the ledger.
Only an actual engine spellbook reset (normally rest) opens that charge again. Natural expiry
may be maintained for free while the caster is safe, out of combat, and cannot see the party.
Dispel, early removal, or suspicious early loss suppresses maintenance until the next real
reset. Save/load, area change, and elapsed time are not treated as rests.

Two narrow SCS races are accounted explicitly. If exact SCS action 181 starts while the first
delivery is still pending, the immediately following matching action 147 may supply the one
real charge; a later callback must observe the exact one-slot loss and child marker before the
ledger is committed, without a component debit. After an ordinary component debit, the
marshaled version-2 ledger retains its exact locator plus original/debited flags; one later
exact SCS `181 -> 147` pair, with `instantprep == 0` at both starts, can restore only that
component-debited record, and only after a later callback observes SCS's exact one-slot loss.
Canceled, non-adjacent, renewed, combat, or ambiguous sequences do not reimburse. A queued
component child that arrives after an SCS-paid commit is merely a bounded redundant finite
effect; it does not debit or create another entitlement. Transient delivery state is
deliberately discarded on import/reset or sprite replacement. In the narrow boundary where
a queued child survives that discard, one finite free effect can remain, but it receives
neither a ledger nor free maintenance; retroactively charging from a generic SCS marker would
not prove ownership.

Existing ledger export/import and genuine spellbook-reset bookkeeping remain active even
when ambient gameplay is disabled, externally owned, or faulted, so retirement neither loses
a valid charge nor retains one across a real reset. Generic action/confirmation handling does
not create sessions. Only an exact SCS action 181 plus known delivery may reconstruct
ephemeral state from an existing valid charged/reimbursable version-2 UDAux ledger, without
allocating UDAux, to preserve reimbursement across save/load or hot reload before the first
deferred tick.

The urgent layer gives a hostile caster one fast but ordinary self-cast on clear first
contact. It may replace only proven idle/wander/movement work, never attacks, casts,
dialogue, cutscenes, tactical/unknown queues, or Project Image actors. The engine owns the
slot, aura, casting time, visuals, and interruption. Candidates are Absolute Immunity,
genuine Improved Mantle, Mantle, then Protection from Magical Weapons, filtered by installed
opcode-120 semantics and actual memorization. The episode is spent when casting starts and
rearms only after a full round without seeing the party. Players can therefore bait or
interrupt the response, but continuous sight cannot farm repeated casts. The passive-only
replacement uses `virtual_ClearActions(false)`; the Boolean is required by the EEex binding,
and the call is unreachable unless the current and every queued action passed the conservative
allowlist.

The two layers can be retired independently without uninstalling the component:

- `CBR_RDY_AMBIENT_ENABLED = 0` disables ambient maintenance;
- `CBR_RDY_URGENT_ENABLED = 0` disables the first-contact reaction; and
- `CBR_RDY_EXTERNAL_OWNER` is a bitmask for a replacement AI: bit 1 claims ambient, bit 2
  claims urgent, and value 3 claims both.

Each callback layer also has its own fail-closed fuse. Offensive AI, target selection,
sequencers, later-round defense choices, non-caster potion logic, and the future full EEex AI
are deliberately out of scope.

### Components 401–403 — Cleric of Tempus Holy Power

These mutually exclusive choices install the same five-tier Holy Power redesign. Component 401
uses automatic semantic detection and is the recommended choice. Components 402 and 403 are
advanced overrides that force true-doubling or additive Improved Haste compatibility; they still
validate the final spell before changing it.

Install after Spell Revisions, SCS, The Artisan's Kitpack, and any other mod that changes spells
or cleric kits. The installer resolves Divine Power and Improved Haste through `SPELL.IDS`,
materializes the six effective input resources at their canonical `override` paths inside the
WeiDU transaction, and then runs the same preflight-first transformation the fixture harness
tests. WeiDU itself backs up, rolls back on failure, and exactly removes or restores every
touched file on uninstall. It adds no game-facing strings and performs no `dialog.tlk` write.

Existing characters automatically use the patched `OHTMPS1` resource. Branwen at level 13
already has the intended three uses, so this component needs no save edit for her. Characters
already above level 25 may retain excess uses granted by the old CLAB in their saved creature;
removing those requires a separately controlled save repair.

This component intentionally does not include weapon-training changes, Chaos of Battle,
Divination-school removal, or an EEex APR-cap experiment. Those are separate Tempus design
components.

## Install

Copy `chriz-bg-rebalance/` + `setup-chriz-bg-rebalance.tp2` into the game dir, then (per the
target install's conventions) copy the WeiDU template as `Setup-chriz-bg-rebalance.exe` and run:

```
./Setup-chriz-bg-rebalance.exe --force-install-list 401 --language 0 --no-exit-pause
```

Use `100`, `101`, `120`, `121`, or exactly one of `401`/`402`/`403` as appropriate; the example
selects the recommended Tempus mode. Install component 120 after the final Spell Revisions
and SCS Smarter Mages components so it sees the effective spell and generated-script shapes.
On the researched SCS/SR/EEex setup, install 120 before 121.

Always tail-install: append after the current last WeiDU.log entry. Never uninstall.

## The bigger picture

Long-term, this repo is one building block of a manifest-driven collection ("install my whole
setup, configurably") — see `docs/plans/2026-07-02-chriz-bg-rebalance-design.md`, section
"Umbrella architecture".

## License

MIT (see LICENSE). Third-party mods are **not** redistributed here.
