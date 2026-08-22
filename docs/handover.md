# chriz-bg-rebalance — Handover

Live entry point for anyone (user, future agent) picking up work on this repo.
Mirrors the convention of `chriz-bg-modpack/docs/handover.md`.

## What this is

SCS- and SR-adjacent balance adjustments + spell-behavior fixes as a tail-install WeiDU mod.
Component numbering: 100s SCS / 200s SR / 300s cross-cutting; labels `cbr_*`. Approved design:
`docs/plans/2026-07-02-chriz-bg-rebalance-design.md`. Conventions + landmines: `CLAUDE.md`.

## Status (2026-08-22)

- **Component 407 (EEex spec-APR listener) was LIVE-BROKEN — fixed, shipped as 409.** The
  user saw Branwen's APR cycle 1.5 → 5 while unpaused. Root cause (disassembly of
  `CGameSprite::ProcessEffectList`, `research/07-spec-apr-listener-runaway.md`):
  `EEex_Opcode_AddListsResolvedListener` fires every AI-tick PASS, but the engine rebuilds
  `CDerivedStats` only every 15th pass / on `m_newEffect` — the v0.1.0 relative `+½` write
  accumulated on the unrebuilt struct. Fix = per-rebuild idempotence marker: private
  SPLSTATE bit `CBR_TEMPUS_SPEC_APR` (planned 242) set in `stats.m_spellStates` after the
  bump; `Reload` clears it. Template now stamps kit id + state id; new tail component
  **409** re-ships the listener over a live 407 (never reinstall 407 mid-stack). Design
  addendum in `docs/plans/2026-07-16-tempus-completion-design.md`; TDD suite
  `tests/test_cbrapr_listener.py` (fake-EEex Lua cadence harness) + extended hermetic and
  installer suites. Mod VERSION → v0.2.0.
- **KB:** the ListsResolved cadence is recorded in the bg-modding skill (`eeex-sprites.md`,
  `ie-apr-proficiency.md` (f), `gotchas.md`) — any future EEex stat listener must be
  idempotent per rebuild.
- **Live check still owed by the user after 409 is installed + game restarted:** Branwen
  wielding a 2-pip weapon reads a *steady* 1.5 (stat 8 = 7; 2.5 under Holy Power tier-1),
  no cycling; swapping to a 0-pip weapon drops it within a second.

## Status (2026-07-20)

- **Community-ideas triage: DONE** — Discord backlog (2026-07-12→20) triaged against the
  live WeiDU.log in `docs/plans/2026-07-20-community-ideas-triage.md`. Proposed slots:
  110 dragons (flagship), 310/311 unidentified-item disguise (EEex research required),
  320 weapon dice, 410+ deity weapons per cleric kit; monks/kensai/companions parked.
- **Component 110 (Apex Dragons): research DONE, design pending user levers** —
  `research/05-dragons.md` has the verified installed baseline (new
  `research/scripts/parse_cre.py`, self-checked vs. comp250's Morentherene numbers), the
  full SCS #6540 anatomy (DMWW_dragon_difficulty gating, dw#drahp = 300% HP on Hard+,
  dw#innat, Insane breath accelerator, 6s wing-buffet timer), and the proposal: offense
  not sponge, comp250-style script-delivered tiers keyed to SCS's own difficulty
  variable, optional 111 buffet-cadence relief. Key install fact: the user already plays
  at DMWW_dragon_difficulty=5 (×3 HP active) and still finds dragons weak.

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

0. **Component 110 dragons — design → build**: user lever answers (asked 2026-07-20) →
   `docs/plans/*-dragons-design.md` → implement per `research/05-dragons.md` §5.
   Then the rest of the triage order (310/311 EEex feasibility, 410+ deity weapons, 320
   weapon dice) per `docs/plans/2026-07-20-community-ideas-triage.md`.
1. **SR wishlist session** — *needs the user live*: walk Spell Revisions' changes, collect
   which to keep/revert/re-tune → `research/10-sr-wishlist.md` → design 200-series.
2. **SCS component catalog** — solo-able: from the game install's WeiDU.log (414 entries;
   read-only) catalog the 77 installed SCS components + balance touchpoints; propose 1xx
   candidates. (Scope inherited from chriz-sod-rebalance "Part 3".)
3. **Formal install of comp 100 into the live game** — pending user sign-off; tail-install.
4. **Umbrella / collection** — see `docs/plans/2026-07-03-umbrella-analysis.md`; decision
   pending user, work deferred until 2xx/3xx mature.
