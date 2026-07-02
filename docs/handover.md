# chriz-bg-rebalance — Handover

Live entry point for anyone (user, future agent) picking up work on this repo.
Mirrors the convention of `chriz-bg-modpack/docs/handover.md`.

## What this is

SCS- and SR-adjacent balance adjustments + spell-behavior fixes as a tail-install WeiDU mod.
Component numbering: 100s SCS / 200s SR / 300s cross-cutting; labels `cbr_*`. Approved design:
`docs/plans/2026-07-02-chriz-bg-rebalance-design.md`. Conventions + landmines: `CLAUDE.md`.

## Status (2026-07-03)

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
```

## Work queue

1. **SR wishlist session** — *needs the user live*: walk Spell Revisions' changes, collect
   which to keep/revert/re-tune → `research/10-sr-wishlist.md` → design 200-series.
2. **SCS component catalog** — solo-able: from the game install's WeiDU.log (414 entries;
   read-only) catalog the 77 installed SCS components + balance touchpoints; propose 1xx
   candidates. (Scope inherited from chriz-sod-rebalance "Part 3".)
3. **Formal install of comp 100 into the live game** — pending user sign-off; tail-install.
4. **Umbrella / collection** — see `docs/plans/2026-07-03-umbrella-analysis.md`; decision
   pending user, work deferred until 2xx/3xx mature.
