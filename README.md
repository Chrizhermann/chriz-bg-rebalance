# chriz-bg-rebalance

Personal SCS- and SR-adjacent balance adjustments and spell-behavior fixes for
**BG2:EE / EET** installs. Sibling of
[chriz-bg-modpack](https://github.com/Chrizhermann/chriz-bg-modpack) (fix consolidation) and
[chriz-sod-rebalance](https://github.com/Chrizhermann/chriz-sod-rebalance) (SoD remix + companions).

**Version: v0.5.0.** Kit-specific bard spell progression is available through EEex.
BG2EE/EET passed the user's quick in-game check; IWDEE support is verified offline.
Previously released components retain their documented acceptance status.
See `docs/00-project-scope.md` for the broader project.

## Credits — stand on the shoulders of giants

This mod draws on two outstanding open-source mods. Its Tempus Holy Power components also work
without them; other components declare their own prerequisites:

- **[Sword Coast Stratagems (SCS)](https://github.com/Gibberlings3/SwordCoastStratagems)** by
  DavidW — the gold standard for Infinity Engine AI and tactics. Install it. This mod merely
  files down a few rough edges.
- **[Spell Revisions (SR)](https://github.com/Gibberlings3/SpellRevisions)** by Demivrgvs & the
  Gibberlings3 team — a thoughtful, comprehensive spell rebalance. Most of its changes are
  excellent; this mod adjusts the handful that don't fit my table.
- **[EEex](https://github.com/Bubb13/EEex)** by Bubb — engine extensions used by the optional
  lethal-dragon component and this mod's other EEex integrations.

Code patterns in this repo are frequently adapted from SCS (open source). Bugs found here are
reported upstream first (see `research/02-upstream-scs-report-draft.md`).

## Components

| # | Group | Component | Status |
|---|-------|-----------|--------|
| 100 | SCS adjustments | Telekinetic Storm: restore save vs. spell for half damage (+ bypass Mirror Image) | ✅ implemented |
| 101 | SCS adjustments | Restore five Freedom scrolls to the Adventurer's Mart | ✅ implemented |
| 110 | SCS adjustments | EEex Apex Dragons: lethal claws and bites, with possible permanent death | Optional; released; combat acceptance pending |
| 111 | SCS adjustments | Five dragon encounters: 18-second wing-buffet cooldown | Optional; released; combat acceptance pending |
| 120 | SCS adjustments | Repair the SCS/SR false Improved Mantle weapon-protection semantics | ✅ implemented |
| 121 | SCS adjustments | EEex ambient caster readiness + one honest first-contact defense | ✅ implemented; v1.2 ambient + neutral-to-hostile urgent path live accepted; legacy live pending |
| 2xx | SR adjustments | Cherry-picked Spell Revisions tweaks | 📋 planning (`docs/00-project-scope.md`) |
| 3xx | Cross-cutting audits | e.g. generalized save-for-half audit | 📋 planning |
| 401–403 | Class and kit revisions | Cleric of Tempus: revised Holy Power | ✅ implemented; choose one compatibility mode |
| 420 | Class and kit revisions | Shared EEex bard progression provider | BG2EE/EET 2.7.3 user playtest passed; IWDEE support checked offline |
| 421 | Class and kit revisions | Bard/Jester IWD7; Blade/Skald vanilla6 | Implemented; requires 420 |

### Components 420–421 — Kit-specific bard progression

Supports **Windows BG2EE/EET and IWDEE with compatible EEex**. The native lookup was
verified in both games' **2.7.3.0** executables; BG2EE/EET also passed the user's in-game
check. IWDEE still needs an in-game check. EEex 1.2 and 1.3 supply the required APIs;
the installer checks capabilities and the actual executable instructions instead of
requiring one exact version or file address. Component 420 supplies one engine hook
and shared table registry; 421 selects IWD progression through seventh-level spells
for ordinary Bards and Jesters, and vanilla progression through sixth level for
Blades and Skalds. Other classes and unregistered kits keep their native behavior.
Future builds can use the provider if their lookup remains compatible and uniquely
identifiable; a changed or ambiguous lookup is rejected before installation.

For Artisan's bard kits, install the kits first, then 420, 421, and **Bardic Wonders
Balance Patch component 3010** last. It gives Dancer vanilla6, Kapellmeister and
Darkbloom IWD8, and the other supported bard kits IWD7. Darkbloom is optional and is
skipped when absent. Progression adds no Spell Revisions restriction; Darkbloom's
separate copied-spell issue under SR remains outside this component. Existing extra
slots, slot penalties, caster levels and innate HLAs remain unchanged. Descriptions
update with the chosen policy.

These components work without SCS, SR or the collection. The shared installer API
is `override/CBRSPAPI.TPA`; adapters add numeric class/kit-to-table registrations to
`CBRSPKIT.2DA`. API 1's native hook handles bards only. No duplicate runtime is
needed in downstream mods. Tables come from the BG2EE bard progression and the
IWD/un-nerfed progression documented by **Tweaks Anthology / Gibberlings3**; the
hook uses **Bubb's EEex** infrastructure.

Standalone Bardic Wonders users may install **420 → 3010** without 421, retaining
their existing base Bard and native-kit progression. The collection selects
**420 → 421 → 3010** for the complete policy. No component rewrites CDTweaks'
`MXSPLBRD.2DA`; registered kits use their selected private table, while unregistered
kits retain the shared table. Install after kits and description-changing tweaks.

The normal level-up path applies the new capacities. This first build does not
automatically rewrite existing saved spellbooks on load. See the
[short in-game check](docs/bard-progression-playtest.md) and
[engine evidence](research/09-kit-spell-progression-and-caster-level.md).

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

### Component 110 — Apex Dragons: lethal claws and bites

**Optional difficulty increase. Requires SCS Smarter Dragons (6540) and EEex.**

**A failed saving throw can cause permanent death (chunking). A chunked companion cannot
be raised or resurrected through normal gameplay.** The native engine still honors its
gore, difficulty and permanent-death protection settings; those may convert the result to
ordinary death. This component does not override those settings.

| Dragon | Chance per qualifying melee hit | Save vs. death |
|---|---:|---:|
| Firkraag | 15% | -4 penalty |
| Thaxll'ssillyia | 5% | -2 penalty |
| Nizidramanii'yt | 10% | -2 penalty |
| Saladrex | 10% | -2 penalty |
| Watcher's Keep guardian | 5% | -2 penalty |

The extra attack effect activates at **Hardcore and Insane** in SCS's Dragon difficulty
settings (including the intermediate setting between them). When that setting follows
the game's slider, it activates on Hard and Insane. Lower settings remove the extra effect.

The hit's physical death effect bypasses **Death Ward, death-effect immunity, Stoneskin
and physical damage resistance**. The victim retains their protections against other
attacks and spells. The effect requires a qualifying melee hit: weapon immunity can stop
it, and scripted minimum-HP protection remains intact. The engine resolves the chance and
one death save before EEex applies the death effect; there is no extra damage prerequisite.

This first pass changes neither HP nor auras. It adds no escorts or spells. Adalon and ToB
dragon changes are deferred. Exact actor-identity guards keep other users of the shared
combat scripts and weapons on their existing behavior; the Thaxll'ssillyia donor alias
shares his identity. The separate SR Death Ward correction is not a prerequisite.

Runtime additions are five patched BCS scripts, four private SPLs, three EFFs and one
autoload Lua module in `override`; WeiDU also maintains its normal installation records.
The component recognizes the current SCS configuration-based difficulty scripts and rejects
unsupported variants before publishing. Script reload may reach already-spawned dragons,
but saved-encounter and combat acceptance remain pending. Do not install into an active
playthrough on the strength of fixture tests alone.

Research: [runtime scope](research/14-dragon-runtime-scope.md),
[physical death delivery](research/19-dragon-vorpal-delivery.md).

### Component 111 — Less frequent dragon wing buffet

This independent option increases the wing-buffet cooldown from **6 to 18 seconds** for
the same five dragon identities. It works at all their existing SCS difficulty settings
and **does not require EEex or component 110**. Existing spell conditions, response weights,
and other dragons' behavior are preserved. It does not change the buffet spell itself.

Both components belong after SCS in the installation order. Their installer, resource and
script behavior is covered by isolated automated checks; actual combat acceptance remains
pending. See [wing-buffet research](research/15-dragon-wing-buffet.md) and the
[v0.4.0 release notes](docs/release-notes/v0.4.0.md).

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
suite passes 254 tests. A fresh-process `AR3000` diagnostic against runtime SHA-256
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

Spell Revisions and SCS are optional. Install after either when present, and after The Artisan's
Kitpack and other mods that change spells or cleric kits. The installer resolves Divine Power
and Improved Haste through `SPELL.IDS`,
materializes the six effective input resources at their canonical `override` paths inside the
WeiDU transaction, and then runs the same preflight-first transformation the fixture harness
tests. WeiDU itself backs up, rolls back on failure, and exactly removes or restores every
touched file on uninstall. It adds no game-facing strings and performs no `dialog.tlk` write.
Artisan may pack its exact per-level cleric permission grant `AP_C0PR#CL` into otherwise empty
`ABILITY1` cells; the validator recognizes and preserves that one known layout while keeping
the Holy Power and level-25 cells strict. See `research/13-tempus-artisan-clab-packing.md`.

Improved Haste supports direct additive APR (SR), direct doubling, and a validated single
opcode-146 hop to a doubling spell. Every caster-level header must agree. SCS conditional
message helpers are checked to contain only display-string effects; missing, malformed,
conditional haste, nested, or ambiguous delivery still aborts. Delegated additive effects are
unsupported because their APR bridge needs a different transformation. The original non-SR
Divine Power exclusion is recognized and upgraded to the same cleanup used by the SR branch.
See `research/14-tempus-delegated-haste.md` for captured inputs and isolated test evidence.

Existing characters automatically use the patched `OHTMPS1` resource. Branwen at level 13
already has the intended three uses, so this component needs no save edit for her. Characters
already above level 25 may retain excess uses granted by the old CLAB in their saved creature;
removing those requires a separately controlled save repair.

This component intentionally does not include weapon-training changes, Chaos of Battle,
Divination-school removal, or an EEex APR-cap experiment. Those are separate Tempus design
components.

## Install

Download the Windows release ZIP and extract its contents into your separate modded game
folder. It includes `Setup-chriz-bg-rebalance.exe`; run it to choose components, or use:

```
./Setup-chriz-bg-rebalance.exe --force-install-list 401 --language 0 --no-exit-pause
```

Use `100`, `101`, optional `110`/`111`, `120`, `121`, or exactly one of `401`/`402`/`403`
as appropriate; the example selects the recommended Tempus mode. The two dragon options
require SCS Smarter Dragons (6540) first; 110 also requires EEex. They can be selected
independently and in either order (the normal menu order is 110 then 111).
Install component 120 after the final Spell Revisions
and SCS Smarter Mages components so it sees the effective spell and generated-script shapes.
On the researched SCS/SR/EEex setup, install 120 before 121.

Always tail-install: append after the current last WeiDU.log entry. Never uninstall.

## The bigger picture

Long-term, this repo is one building block of a manifest-driven collection ("install my whole
setup, configurably") — see `docs/plans/2026-07-02-chriz-bg-rebalance-design.md`, section
"Umbrella architecture".

## License

Original project code: MIT (see LICENSE). Third-party mods are **not** bundled in the
release ZIP. The included WeiDU 249 installer is distributed under GPL v2; see
`WEIDU-LICENSE.txt` and [WeiDU source](https://github.com/WeiDUorg/weidu/tree/v249.00).
