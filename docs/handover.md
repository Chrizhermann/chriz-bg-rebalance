# chriz-bg-rebalance — Handover

Live entry point for anyone (user, future agent) picking up work on this repo.
Mirrors the convention of `chriz-bg-modpack/docs/handover.md`.

## What this is

SCS- and SR-adjacent balance adjustments + spell-behavior fixes as a tail-install WeiDU mod.
Component numbering: 100s SCS / 200s SR / 300s cross-cutting; labels `cbr_*`. Approved design:
`docs/plans/2026-07-02-chriz-bg-rebalance-design.md`. Conventions + landmines: `CLAUDE.md`.

## Status (2026-07-11)

- **Component 101 (Adventurer's Mart Freedom scrolls): SHIPPED + live-installed.** SCS v35
  orphaned its `freedom_scrolls` spell tweak (no `spelltweaks.2da` dispatch row; dead code
  also lost the ribald target); comp 101 restores the Adventurer's Mart 5× scrl9z. Live
  install got the mod tail-installed (`--force-install-list 101`, user-approved 2026-07-11)
  — the mod folder + setup exe now live in the game dir. 34 saves with the store cached in
  `BALDUR.SAV` were patched directly (`research/scripts/patch_sav_store.py`, backups
  `BALDUR.SAV.bak-cbr101`); 4 live `Interval-Save` slots intentionally skipped
  (`research/03` §Live install).
- **Component 100 (SCS Telekinetic Storm save fix): implemented & parse-checked.** NOT yet
  WeiDU-installed into the live game — the live install got an equivalent user-approved
  direct-override hotfix on 2026-07-02 (`research/01`), and comp 100 is idempotent over it.
- **Upstream SCS report: PARKED, will not be filed** (user decision 2026-07-03: the SCS
  author does not react on GitHub). Draft kept for reference in `research/02`.
- Aura save-bug findings parked at `Chrizhermann/Aura_BG1_BG2_EET-Chriz-Balance-Patch` issue #1.

## Hard guardrails (user directives)

1. **The game folder (`C:\Games\Baldur's Gate II Enhanced Edition modded\`) is a READ-ONLY
   reference** — not a testing ground, not a repo (directive 2026-07-03). Read WeiDU.log,
   override files, mod sources freely for research; never write, install, or test there
   without the user's explicit sign-off in that conversation.
2. **Never uninstall any WeiDU.log entry** on any install; new mods tail-install only.
3. **No upstream SCS reports** — fold fixes into this repo instead.
4. **`gh` CLI state is shared across concurrent agent sessions** — another agent may have
   switched the active account. Run `gh auth status` before any gh operation; this repo needs
   `Chrizhermann` (`gh auth switch --user Chrizhermann`).

## Testing reality

The clean test install used by chriz-bg-modpack
(`C:\Games\Baldur's Gate II Enhanced Edition modded - Copy - Copy\`) has **no SCS/SR**, so
most components here will legitimately `REQUIRE_PREDICATE`-skip on it. Until a dedicated
SCS+SR test install exists, verification = WeiDU parse-check + binary-level before/after
diff of the patched resources (scripts in `research/scripts/`) + user-approved deployment
to the live install.

```bash
./weidu.exe --nogame --list-components setup-chriz-bg-rebalance.tp2 0   # parse check
python research/scripts/parse_spl.py <file.spl>                        # inspect effects
python research/scripts/parse_sto.py <file.sto>                        # inspect store stock
python research/scripts/patch_sav_store.py <saveroot> <sto> <itm> <n>  # save-cache surgery
```

Save-cache reality: visited stores live inside each save's `BALDUR.SAV`; override store
patches only reach saves that never loaded that store. EET userdir on this machine is
OneDrive-redirected (`[Environment]::GetFolderPath('MyDocuments')` →
`...\OneDrive\Documents\Baldur's Gate - Enhanced Edition Trilogy`), it is SHARED by every
EET-based install copy, and `Interval-Save` slots may be actively rewritten by a running
session — always `--exclude` them.

## Work queue

1. **SR wishlist session** — *needs the user live*: walk Spell Revisions' changes, collect
   which to keep/revert/re-tune → `research/10-sr-wishlist.md` → design 200-series.
2. **SCS component catalog** — solo-able: from the game install's WeiDU.log (414 entries;
   read-only) catalog the 77 installed SCS components + balance touchpoints; propose 1xx
   candidates. (Scope inherited from chriz-sod-rebalance "Part 3".)
3. **Formal install of comp 100 into the live game** — pending user sign-off; tail-install.
4. **Umbrella / collection** — see `docs/plans/2026-07-03-umbrella-analysis.md`; decision
   pending user, work deferred until 2xx/3xx mature.
