# SR anti-magic: collection integration handover

Owner: `Chrizhermann/chriz-bg-rebalance`, SR adjustments. Date: 2026-10-06.
User approved the following balance choices and implementation. Publication and
game modification remain unauthorized. Entropy Shield remains research only.

| ID | Stable main label | Behavior | Prerequisite |
|---|---|---|---|
| 210 | `cbr_sr_pierce_magic` | Half current MR; 10-40 percentage-point reduction, zero floor, round reduction upward; five rounds; repeat casts refresh the same amount | SR main 0; EEex |
| 211 | `cbr_sr_spellstrike` | 15% arcane and divine spell failure for two rounds; refreshes without self-stacking | SR main 0 |

Both preserve protection-removal effects and Spell Shield wrappers. Component
210 combines with Lower Resistance, and 211 can combine with other sources of
spell failure. Neither changes Pierce Shield, Lower Resistance or Entropy Shield.
No new SR #65 dependency belongs on these components: that is Hardiness's guard.

## Source and packaging

- Worktree: `C:\src\private\chriz-bg-rebalance\.worktrees\sr-antimagic-research`.
- Branch: `codex/sr-antimagic-research`.
- Version: **v0.8.1-dev**, unpublished. Use the final local commit reported by
  this task; do not invent a release URL, tag or artifact metadata.
- Includes the approved Hardiness 200/201/202 source, integrated from `af48f222`,
  and is based on `7777870` (physical-resistance work). This is a combined local
  development snapshot, not a replacement for the published v0.7.1 identity.
- Main entry point: `setup-chriz-bg-rebalance.tp2`.
- Separate existing-install entry point:
  `CBR_SR_ANTIMAGIC/setup-cbr_sr_antimagic.tp2`, same IDs, independent backups.
- Build with `python tools/package_sr_antimagic.py`. It creates the full mod,
  Hardiness tail and anti-magic tail Windows ZIPs plus SHA-256 sidecars in `dist`.

Component 210 intentionally uses EEex opcode 402. Native conditional MR checks
do not establish a reliable restored-stat snapshot immediately after removing
an old reduction. The runtime calculates once, stores a normal timed additive
MR effect, and renews its expiry directly. This avoids silently weakening the
debuff or compounding reductions on recast. Existing effects and their magnitude
survive saves through native effect serialization; no persistent Lua state is
needed for normal active reductions. Launch through InfinityLoader.

## Collection integration still needed

The owning mod alone does not change a collection recipe. On the current
collection worktree, add the eventual **immutable new artifact pin**, the two
component menu entries, semantic features and curation mappings. Adopt actual
archive URL/size/checksum only after separate publication authorization.

- Add `feature:chriz-bg-rebalance:component-210` and `:component-211`, parented
  under `mod:chriz-bg-rebalance`.
- Require SR's main component bundle for both; additionally require the
  collection's effective EEex feature for 210. Resolve that exact existing
  feature identity from the current manifest rather than assuming a name.
- They are independent choices, not a mutual-exclusion group. Recommend both
  for this user's approved SR profile; record the corresponding preset choices.
- Install after SR and SCS's final spell writers, alongside the post-EET-end
  Rebalance run, while retaining any explicitly required order for component302.
- Use the main installer for fresh collection installs. Do not add the standalone
  tail installer as a second recipe run.
- Preserve Hardiness's separate default 200, optional alternative201 and optional
  extra202 policy, gated by SR65. See the Hardiness handover for its exact rules.

Update the artifact/mod manifests, collection feature/run records, recommended
preset, curation map, BG Rebalance/SR component documentation and source-verification
records together. Test both independent selections, both together, SR disabled,
EEex disabled (210 unavailable, 211 still possible), ordering, and that the pin
actually contains IDs210/211. No collection files were edited by this task.

## Evidence boundary

Focused tests exercise the real WeiDU installer on disposable synthetic games,
binary preservation, guards/rollback, public/tail parity and runtime simulations.
There are 102 passing focused/related regression tests, including 24 anti-magic
installer/package tests, 13 Spellstrike transformation tests and 13 Pierce Magic
runtime-model tests. The extracted standalone archive was installed using its
packaged executable with no repository or SR source tree in the fixture.
Actual installed spell bytes are inspected and transformed only in temporary
fixtures. No automated result establishes live gameplay acceptance, save/reload
behavior in the engine, or final SCS tactics. Follow the tail README's acceptance
checklist after separate authorization; do not modify the running stream game.
