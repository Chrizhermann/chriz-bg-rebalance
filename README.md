# chriz-bg-rebalance

Personal SCS- and SR-adjacent balance adjustments and spell-behavior fixes for
**BG2:EE / EET** installs. Sibling of
[chriz-bg-modpack](https://github.com/Chrizhermann/chriz-bg-modpack) (fix consolidation) and
[chriz-sod-rebalance](https://github.com/Chrizhermann/chriz-sod-rebalance) (SoD remix + companions).

**Status:** planning phase + first shipped component. See `docs/00-project-scope.md`.

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
| 2xx | SR adjustments | Cherry-picked Spell Revisions tweaks | 📋 planning (`docs/00-project-scope.md`) |
| 3xx | Cross-cutting audits | e.g. generalized save-for-half audit | 📋 planning |

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

## Install

Copy `chriz-bg-rebalance/` + `setup-chriz-bg-rebalance.tp2` into the game dir, then (per the
target install's conventions) copy the WeiDU template as `Setup-chriz-bg-rebalance.exe` and run:

```
./Setup-chriz-bg-rebalance.exe --force-install-list 100 --language 0 --no-exit-pause
```

Always tail-install: append after the current last WeiDU.log entry. Never uninstall.

## The bigger picture

Long-term, this repo is one building block of a manifest-driven collection ("install my whole
setup, configurably") — see `docs/plans/2026-07-02-chriz-bg-rebalance-design.md`, section
"Umbrella architecture".

## License

MIT (see LICENSE). Third-party mods are **not** redistributed here.
