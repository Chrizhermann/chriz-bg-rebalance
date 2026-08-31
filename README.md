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
| 121 | SCS adjustments | EEex ambient caster readiness + one honest first-contact defense | ✅ implemented for EEex v1.2; pending live acceptance |
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
6030, EEex's `M_*.lua` autoload bootstrap, and the final SCS prebuff map. The current runtime
targets EEex v1.2.0: it uses the deferred lists-resolved listener and the documented world
timer's raw 15-Hz engine ticks, and it rechecks every required API before acting. It does not
hardcode EEex WeiDU component numbers or impose a component-specific LuaJIT requirement.
Missing prerequisites skip cleanly; malformed recognized data fails before the override
transaction is retained. Component 120 is independent, but installing 120 first is
recommended on the currently researched SR setup. The v1.2 path is source- and
simulation-verified; a fresh v1.2 gameplay pass is still required.

The ambient layer considers only recognized, settled SCS casters and conservative installed
self-buffs lasting at least 2,400 seconds. A caster must really have the spell memorized. The
first confirmed application spends exactly one memorized copy; only an actual engine
spellbook reset (normally rest) opens that charge again. Natural expiry may be maintained for
free while the caster is safe, out of combat, and cannot see the party. Dispel, early removal,
or suspicious early loss suppresses maintenance until the next real reset. Save/load, area
change, and elapsed time are not treated as rests, and the narrow initial SCS-prebuff
reimbursement prevents a second charge for the same managed spell.

The urgent layer gives a hostile caster one fast but ordinary self-cast on clear first
contact. It may replace only proven idle/wander/movement work, never attacks, casts,
dialogue, cutscenes, tactical/unknown queues, or Project Image actors. The engine owns the
slot, aura, casting time, visuals, and interruption. Candidates are Absolute Immunity,
genuine Improved Mantle, Mantle, then Protection from Magical Weapons, filtered by installed
opcode-120 semantics and actual memorization. The episode is spent when casting starts and
rearms only after a full round without seeing the party. Players can therefore bait or
interrupt the response, but continuous sight cannot farm repeated casts.

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
