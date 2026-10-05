# SR Hardiness: collection integration handover

Date: 2026-10-06. Owner: `chriz-bg-rebalance`, SR adjustments.

## Decision and source

Christopher's October 6 decision supersedes the earlier plan to retain SR's extra
resistances by default. Recommend the vanilla **resistance profile**: 40% physical
resistance only. Offer 30% physical resistance instead, and offer SR's extra 20%
damage resistances as a separate, unchecked option. These recommendations belong
to the collection installer; they do not make either alternative a different mod.

| Component | Stable label | Effect | Collection recommendation |
|---|---|---|---|
| 200 | `cbr_sr_hardiness_40` | 40% physical resistance; removes SR's extra damage resistances | Default |
| 201 | `cbr_sr_hardiness_30` | 30% physical resistance; removes SR's extra damage resistances | Optional alternative to 200 |
| 202 | `cbr_sr_hardiness_extra_resistance` | Adds 20% acid, cold, electricity, fire, magic damage, magical fire and magical cold resistance | Optional, off by default; requires 200 or 201 from the same installer |

Components 200 and 201 are mutually exclusive. Component 202 is a separate axis
and must run after the selected physical component. Its magic **damage** resistance
does not grant Magic Resistance (the chance to block spells). It grants no poison
resistance. All three components apply to normal and Wish-granted Hardiness and
require SR Revised Warrior HLAs, component 65.

Duration, stacking protections and current Breach behavior are preserved. In
particular, this does not make Wish Hardiness share normal SR Hardiness's changed
Breach classification. Describe 200 as restoring the vanilla resistance profile,
not as restoring every aspect of vanilla Hardiness.

Implementation source:

- Repository: `Chrizhermann/chriz-bg-rebalance`.
- Worktree: `C:\src\private\chriz-bg-rebalance\.worktrees\sr-hardiness`.
- Branch: `codex/sr-hardiness-adjustment`.
- Source version: `v0.8.0-dev`, based on
  `c3f3cc2c084cd25619506ed1fb865af1251a570c` (the v0.7.1 source line).
- Main entry point: `setup-chriz-bg-rebalance.tp2`.
- Diagnosis and revised policy: `research/06-sr-hardiness.md`.

This source is unpublished. There is no new published release URL or release
artifact metadata to pin yet. Local development archives and SHA-256 sidecars
are built under `dist/` with `python tools/package_sr_hardiness.py`; they are not
a published collection source. The existing v0.7.1 release does **not** contain these components. Do not
change the meaning or contents of the v0.7.1 artifact identity. A future published
source needs its own immutable pin and verified archive metadata.

## Current collection state

The current executable collection recipe was inspected read-only at:

`C:\Users\chris\.codex\worktrees\installer-v0-real-alpha\chriz-bg-collection`

Its inspected HEAD is `ef62225` (alpha.19, October 1). This is newer than the
`spell-revisions-integration` worktree and the repository's docs-only primary
checkout. Recheck the current release worktree before editing because other
collection work is active.

The executable recipe pins BG Rebalance `chriz-bg-rebalance-0.7.1` and SR
`spell-revisions-4.21-chriz.5`. It already has a post-EET-end
`chriz-bg-rebalance-bg2` run. Hardiness 200/201/202 and their selection rules are
absent. **Finishing the owning mod does not complete collection integration.**
Until the collection adopts the new source and these choices, its SR HLA
selection continues to receive SR's original 20% physical plus extra-resistance
profile.

The dependency identity is `feature:spell-rev:component-65` (Revised Warrior
HLAs), currently default-on. Gate Hardiness on this exact feature, not merely
`mod:spell-rev` or `feature:spell-rev:mandatory-components`.

## Required collection edits

Paths below are relative to the current collection worktree.

| Path | Required integration |
|---|---|
| `manifest/artifacts/chriz-bg-rebalance-<new-version>.toml` | Add the eventual immutable source, exact version, archive URL, byte length, SHA-256 and verified archive layout. Check archive limits against the new payload. Do not invent release metadata before publication. |
| `manifest/mods/chriz-bg-rebalance.toml` | Point to that new artifact and add components 200, 201 and 202 with their exact menu meanings. Retain the main TP2 path. |
| `manifest/collection.toml` | Add 200/201/202 to the existing Rebalance run in source order and author the three semantic features described below. |
| `manifest/presets/chris-recommended.toml` | Select 200, leave 201 and 202 off, with the SR 65 dependency enforced by feature evaluation. |
| `manifest/curation-map.toml` | Map the three semantic features to `CHRIZ-BG-REBALANCE:200`, `:201` and `:202`. |
| `docs/curation/components/CHRIZ-BG-REBALANCE.md` | Add the menu, recommendation, mutual exclusion, extra-resistance option and dependency. Refresh the stale version summary: it still says v0.7.0 while the inspected executable recipe pins v0.7.1. |
| `docs/curation/components/SPELL_REV.md` | Explain the default Hardiness adjustment when 65 is selected and link to the Rebalance choices. |
| `manifest/evidence/artifact-verification.toml` and `manifest/mod-sources.tsv` | Record actual new source verification when it exists. |

Do not hand-edit `manifest/install-order.tsv`; it is the captured historical
WeiDU log, not the generated recipe.

Use these semantic identities, following the existing component-feature naming:

- `feature:chriz-bg-rebalance:component-200`: `decision = "default"`.
- `feature:chriz-bg-rebalance:component-201`: `decision = "optional"`.
- `feature:chriz-bg-rebalance:component-202`: `decision = "optional"`.

All three use parent `mod:chriz-bg-rebalance` and require
`feature:spell-rev:component-65`. The physical options share a choice group, for
example `sr-hardiness-physical-resistance`, and have symmetric conflicts so the
resolved plan cannot select both. The existing Lightning Bolt 80/81 choices in
`manifest/collection.toml` demonstrate this schema and UI behavior. Selecting
30% must replace the recommended 40% selection.

Component 202 has no physical choice-group membership. Give it
`requires_any = ["feature:chriz-bg-rebalance:component-200",
"feature:chriz-bg-rebalance:component-201"]` in addition to the SR 65 dependency.
It must be unavailable when neither physical component is effective. Turning off
SR, SR 65, or BG Rebalance must remove all three Hardiness components from the
resolved run. A parent toggle or unrelated mandatory bundle must not accidentally
force SR 65 back on.

Recommended UI wording is "Hardiness: 40% physical resistance (recommended)",
"Hardiness: 30% physical resistance", and "Hardiness: extra 20% elemental and
magic damage resistance". Explain the seven affected damage categories in the
last option's description. Do not call this option Magic Resistance or protection
against all damage.

The main components run after SR 65 and final spell patchers. The existing
Rebalance run is already in `post-eet-end`; verify its relative position against
any newly introduced writer of either Hardiness resource. Preserve existing
component order, including component 302's currently intentional last position.
Within the new family use 200 or 201, followed by 202 only when selected. The
recommended effective expansion is `[200]`, with alternatives `[201]`,
`[200, 202]` and `[201, 202]`.

## Existing-install patch boundary

The dedicated tail patch entry point is:

`live-patch/CBR_SR_HARDINESS/setup-cbr_sr_hardiness.tp2`

It uses the same component IDs and policy as the main installer. This is the
separate existing-install route; the collection's fresh-install recipe uses the
main TP2. Never install both the main and standalone Hardiness families in the
same game, and never satisfy standalone component 202's prerequisite using a
physical component from the main installer (or vice versa).

For an existing installation, use the prepared standalone package only after
separate authorization to modify that game. Append the chosen physical component
and optional 202 at the tail. Do not reinstall SR, uninstall existing entries,
or manually edit `WeiDU.log`. Do not turn a profile switch into an automatic
uninstall/reinstall of a running installation. Follow the standalone package's
preflight and backup instructions and report installed-resource verification
separately from live gameplay acceptance.

No running game modification or publication is authorized by this handover.

## Collection acceptance checks

Extend the existing Rebalance recipe checks in
`engine/tests/production_recipe_chriz.rs` and SR checks in
`engine/tests/production_recipe_spell_rev.rs`, plus curation/artifact validation
where their expected inventories change. Required evidence:

1. The new source pin actually exposes the three new menu entries; v0.7.1 cannot
   be selected as their source.
2. Recommended selection with SR 65 enabled resolves 200 only, after SR 65 and
   final spell patchers.
3. Selecting 30% replaces 200 with 201; the UI and resolver never emit both.
4. Extra resistance is unchecked by default and expands to 202 after either
   physical choice when enabled.
5. SR 65 off, all SR off, or BG Rebalance off removes the Hardiness family without
   silently restoring a disabled prerequisite.
6. With no effective physical option, 202 is unavailable and cannot run alone.
7. Labels, curation mappings and recommended preset agree with the resolved plan;
   unrelated Rebalance selections and component 302's order stay unchanged.
8. Only the main installer identity appears in a fresh collection recipe; the
   standalone existing-install patch is not a second recipe run.

Owner-mod automated tests and isolated WeiDU fixture checks establish installer
behavior only. Neither those checks nor collection resolver tests establish live
acceptance in the user's stream game. Record each integration/test result and
remaining release or live-test limitation explicitly.

Owner-mod evidence on October 6: 24 focused automated tests pass using WeiDU
24900, including the four combinations, both spells, public and standalone
installers, prerequisites, cross-family exclusion, malformed-Wish rollback,
description isolation, exact synthetic uninstall and package contents/checksums.
Separate offline checks pass all four profiles on both archived post-SR spells
with their original 15 level headers, including byte-exact repeat application.
The broader unrelated-component suite was not rerun. No live acceptance is claimed.
