# chriz-bg-rebalance

Personal SCS- and SR-adjacent balance adjustments and spell-behavior fixes for
**BG2:EE / EET** installs. Sibling of
[chriz-bg-modpack](https://github.com/Chrizhermann/chriz-bg-modpack) (fix consolidation) and
[chriz-sod-rebalance](https://github.com/Chrizhermann/chriz-sod-rebalance) (SoD remix + companions).

**Status:** active component development. See `docs/00-project-scope.md`.

## Credits — stand on the shoulders of giants

This mod grew out of three outstanding open-source mods, and many components are designed to be
installed on top of them. Component 301 can also supply its own Hope and Courage spells on a
plain BG2:EE/EET spell set:

- **[Sword Coast Stratagems (SCS)](https://github.com/Gibberlings3/SwordCoastStratagems)** by
  DavidW — the gold standard for Infinity Engine AI and tactics. Install it. This mod merely
  files down a few rough edges.
- **[Spell Revisions (SR)](https://github.com/Gibberlings3/SpellRevisions)** by Demivrgvs & the
  Gibberlings3 team — a thoughtful, comprehensive spell rebalance. Most of its changes are
  excellent; this mod adjusts the handful that don't fit my table.
- **[IWDification](https://github.com/Gibberlings3/iwdification)** by CamDawg and contributors —
  the established Icewind Dale spell port whose spell allocation, detectable-state, and
  donor-scroll distribution precedents informed component 301.

Code patterns in this repo are frequently adapted from SCS (open source). Component 301 uses
original CBR code and English text informed by the PnP/IWD spell concepts and read-only study of
the installed IWDification/SCS implementations. Its standalone presentation files are original
IWDEE game assets extracted from a pristine user-owned installation and credited in
`chriz-bg-rebalance/resources/emotion_iwdee/README.md`; no IWDification or SCS binary was copied.
Bugs found here are reported upstream first (see `research/02-upstream-scs-report-draft.md`).

## Components

| # | Group | Component | Status |
|---|-------|-----------|--------|
| 100 | SCS adjustments | Telekinetic Storm: restore save vs. spell for half damage (+ bypass Mirror Image) | ✅ implemented |
| 101 | SCS adjustments | Restore five Freedom scrolls to the Adventurer's Mart | ✅ implemented |
| 2xx | SR adjustments | Cherry-picked Spell Revisions tweaks | 📋 planning (`docs/00-project-scope.md`) |
| 301 | Cross-cutting audits | Emotion, Courage / Emotion, Hope: mutually exclusive beneficial emotions | ✅ implemented and automated-verified; delivery/mutual exclusion live-verified, status-entry retest pending |
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

### Component 301 — Emotion, Courage / Emotion, Hope

Component 301 owns the final level-four wizard spells at their dynamically resolved
`SPELL.IDS` slots. The last beneficial Emotion applied wins on each creature, while recasting
the same spell refreshes it. Courage grants +1 THAC0, +3 damage, and +5 Hit Points and ends fear
and morale failure. Hope grants +2 morale, +2 THAC0, +2 damage, and +2 to all saving throws and
ends Emotion, Hopelessness and Symbol, Hopelessness. Fear and Symbol, Hopelessness remove their
matching benefit in the hostile mechanic's save/MR domain. Emotion, Hopelessness retains its
established unconditional Hope removal before its separately saved hostile effects.

**Compatibility notice:** Component 301 deliberately overwrites the effective Emotion,
Courage and Emotion, Hope mechanics and English descriptions. Install it after IWDification,
SCS, Spell Revisions, and other spell, scroll, or store overhauls. A spell mod installed later
can overwrite component 301 again.

When the symbols already exist, the component retains their allocated slots, valid installed
visual/audio references, and existing learn-scroll placement. When either symbol is missing,
it allocates the missing spell dynamically in a normal level-four wizard slot and creates a
private CBR learn-scroll. The standalone spells use the original blue IWDEE A/B/C icons,
independently extracted 13x13 IWDEE heart status icons, and a privately namespaced copy of
IWDEE's allies-only Emotion projectile, VVC, animation, and sounds. Each fallback receives a
dynamic `STATDESC.2DA` row and one 300-second opcode-142 entry, so `Courage` or `Hope` appears
in the character-sheet status list. The scrolls are constructed cleanly from the same contract
as IWDification: point targeting, range 50, opcode 148 at caster level 10, followed by a
separate opcode-147 learning ability.

The dynamically discovered Enchanted Weapon and Emotion, Hopelessness scrolls are distribution
anchors only; their item abilities, icons, and other bytes are not cloned. Component 301 mirrors
their store entries while preserving each store's quantities, charges, flags, and ordering.
Those donor scrolls remain guarded requirements for the initial standalone distribution path;
a missing or ambiguous donor aborts the WeiDU transaction. An existing spell with no
discoverable learn-scroll is left without one in this initial compatibility pass. The component
does not add fixed area, creature, save, or spellbook edits, so a store already cached in an
active save may not acquire a new entry without separate save work.

The first disposable UI pass exposed an enemy-only HOLD projectile and a donor-cloned Courage
scroll in the earlier build; that build could not apply either buff and was discarded. The
corrected UI test then confirmed real spell delivery, the complete stat sequences, and
Hope/Courage replacement, but exposed one remaining presentation defect: the fallback spells
had no character-sheet status entry. Regression tests now require the IWDEE allies-only
projectile, blue icons, point-target scroll contract, dynamic STATDESC rows, D-icons, and
opcode 142. A final manual status-list retest remains. Full binary evidence, provenance, and
the controlled-test boundary are in
`research/11-emotion-hope-courage.md`.

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
./Setup-chriz-bg-rebalance.exe --force-install-list 401 301 --language 0 --no-exit-pause
```

Use `100`, `101`, `301`, or exactly one of `401`/`402`/`403` as appropriate. The example selects
the recommended Tempus mode and installs component 301 last, after every spell overhaul.

Always tail-install: append after the current last WeiDU.log entry. Never uninstall.

## The bigger picture

Long-term, this repo is one building block of a manifest-driven collection ("install my whole
setup, configurably") — see `docs/plans/2026-07-02-chriz-bg-rebalance-design.md`, section
"Umbrella architecture".

## License

MIT (see LICENSE). Third-party mods are **not** redistributed here.
