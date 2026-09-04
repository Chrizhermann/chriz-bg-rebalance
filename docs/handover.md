# chriz-bg-rebalance — Handover

Live entry point for anyone (user, future agent) picking up work on this repo.
Mirrors the convention of `chriz-bg-modpack/docs/handover.md`.

## What this is

SCS- and SR-adjacent balance adjustments + spell-behavior fixes as a tail-install WeiDU mod.
Component numbering: 100s SCS / 200s SR / 300s cross-cutting; labels `cbr_*`. Approved design:
`docs/plans/2026-07-02-chriz-bg-rebalance-design.md`. Conventions + landmines: `AGENTS.md`.

## Status (2026-09-04) — v1.2 ambient/urgent PASS; Tempus CLAB compatibility fix ready in v0.3.1

- **Component 401's first clean curated-stack install exposed one narrow validator gap.**
  Artisan's Kitpack legitimately packs `AP_C0PR#CL` into otherwise empty `ABILITY1` cells
  of `OHTEMPUS.2DA`. The test-first fix accepts only that exact permission token
  at ordinary levels and still clears only the five late Holy Power grants. See
  `research/13-tempus-artisan-clab-packing.md`. All 68 Holy Power tests pass, and the
  isolated release candidate installed `401` with no warning/error and verified every
  resulting CLAB invariant. It is included in v0.3.1, the successor release the public
  collection should pin instead of v0.3.0.

- **The approved v1.2 laboratory now exists:**
  `C:\Games\Baldur's Gate II Enhanced Edition modded - CBR Ambient Readiness v1.2 Test`
  combines the audited SCS/SR EET snapshot with the exact EEex v1.2 runtime. Components 120
  and 121 are at the WeiDU tail. Its installed `M_CBRRDY.lua` now contains the verified
  accounting and urgent binding corrections (SHA-256 `9957348E...B3D08`) as audited one-file
  lab hotfixes.
  Do not force-reinstall or uninstall 121. The active playthrough
  remains untouched. Recheck `Baldur.exe` and `InfinityLoader.exe` immediately before any
  further lab write rather than relying on an earlier process observation.
- **The first v1.2 pass found a real component-121 blocker.** In the loaded process,
  `type(m_worldTime.GetCurrentTime)` was `nil`, direct `m_worldTime.m_gameTime` returned a
  numeric raw tick value, and the userdata metatable exposed the field but no method. Both
  readiness layers consequently faulted closed before any effect, slot debit, or queued cast.
- **The clock-corrected rerun passed delivery but failed accounting.** The user visually
  confirmed the expected Vigil buffs. A paused read-only diagnostic then found the exact
  `DWSW408` / `DWSP735` effects, but all four memorized counts were unchanged, all component
  ledgers were empty, and every relevant spell had failed. This is a visual delivery PASS and
  one-slot accounting FAIL. The neutral actors did not exercise urgent first-contact casting.
- **The final corrected runtime passed fresh-process ambient acceptance.** In paused `AR3000`,
  exact runtime SHA-256 `EF38A1A0BF942A2B3AB294FAE48DA2548E9413DBD5FE7CB255406C413E06DD3D`
  reported `ambient_faulted=0` and `urgent_faulted=0`. All four subjects were neutral with
  `instantprep=0` and `inafight=0`; every exact marker and schema-2 charged ledger was present,
  with no ambient failure. `SHUGMG01` had one of two `SPWI408` copies available (`[0,1]`),
  while `SHUPOL01` had zero of one `SPWI408` and `SHUGAR01` / `SHUGOD01` each had zero of one
  `SPPR735` (`[0]`). This is the agreed one-slot accounting PASS, not urgent evidence.
- **The corrected neutral-to-hostile urgent path passed.** The first attempt faulted because
  EEex v1.2 requires the Boolean argument to `virtual_ClearActions`; exact binding and engine
  disassembly established `false` as the full-clear branch after the existing passive-only
  action gate. Runtime `9957348E...B3D08` then kept `urgent_faulted=0`. An attack order alone
  correctly did nothing while Brother Pol was neutral; after the first hit made him hostile,
  his exact normal `SPWI708` start spent one contact attempt and the sole Mantle slot, and the
  exact opcode-120 effects were active. The generic mage's non-passive action 22 was not
  displaced. This accepts the primary current-version path, not every broader matrix row.
- **The corrected current-version contract uses one scheduler and one confirmation observer.**
  EEex v1.2 registers one deferred callback as the sole scheduler and one synchronous
  lists-resolved callback as an ambient-only pending-confirmation observer (`1/1`, total 2).
  Legacy registers only one synchronous full scheduler (`0/1`, total 1). If the synchronous
  observer API is missing on v1.2, ambient fails closed while urgent may remain on the
  deferred scheduler. Both modes read direct `m_worldTime.m_gameTime` raw ticks.
- **Opcode-146 delivery does not explain away an SCS action 181.** Exact BG2EE 2.6.6
  disassembly proves `dwFlags=1` publishes the child through `CMessageFireSpell` /
  `CGameAIBase::FireSpell` and does not create action 181. Therefore an exact SCS `181 -> 147`
  sequence during first-delivery pending can supply the one charge after a later callback
  observes its exact slot loss and marker. After an ordinary component debit, schema 2 keeps
  the exact locator/original/debited flags so one later exact SCS pair can restore only that
  component-debited record, again only after post-action delta proof.
- **Persisted accounting survives gameplay retirement.** Existing ledger export/import and a
  real quick-list reset run independently of enable, external-owner, and fault gates. Generic
  callbacks require an existing session, but exact action 181 plus known delivery may rebuild
  ephemeral state from an existing valid charged/reimbursable schema-2 UDAux ledger, without
  allocating UDAux, so save/load or hot reload before the first deferred tick cannot defeat
  reimbursement.
- **The staged lich route was wrong.** The save's `AR3019` one-time spawn locals are already
  exhausted and neither lich exists in any saved area. The staged lab save is in `AR3000`, where
  the Vigil group provides better subjects: the generic mage and Brother Pol have ambient
  Stoneskin plus urgent PfMW/Mantle respectively. While neutral (`EA=128`) their urgent layer
  is correctly inactive; deliberately making the group hostile gives a visible urgent test.
- **Automated and live evidence are deliberately split:** the earlier `68 focused / 228 repository`
  result proves only the clock-field correction. The accounting redesign now has 76 focused
  tests and all 253 repository tests passing. The fresh-process ambient delivery/accounting
  rerun and the later corrected neutral-to-hostile urgent path now pass. Full legacy live
  acceptance and the unexercised rows of the broader current-version matrix remain explicit.
- **Existing-lab deployment used audited direct override hotfixes.** With both game processes
  absent, the disposable lab's clock-only runtime (`42191F62...`) was preserved, the reviewed
  accounting candidate (`870B4C6F...`) was preserved, and the verified ambient runtime was
  deployed as `EF38A1A0...`; the later one-line urgent binding correction produced final
  stamped runtime `9957348E...B3D08`. `WeiDU.log` remained byte-identical at `6C988DE3...`;
  the final runtime parses with the bundled Lua interpreter and matches the production suffix
  exactly.
  Evidence is under `C:\Users\chris\Documents\Codex\2026-09-02\cbr-ambient-v12-accounting-hotfix-20260902-215413`.
  This avoided uninstalling an entry or relying on `--force-install-list 121`, which is a
  silent no-op for an already installed component. Ambient accounting and the primary urgent
  path have cleared their live gates; do not deploy into the active playthrough without
  separate explicit approval.
- **Transient lifecycle ambiguity is bounded and fail-closed.** Reset/import or sprite
  replacement discards pending delivery. A narrow boundary can leave one already-queued
  finite child effect without debit or ledger; the generic marker cannot prove ownership, so
  it is not retroactively charged and never receives free maintenance. If a queued component
  child instead arrives after an SCS-paid ledger commit, it is likewise a bounded redundant
  finite effect and causes no debit or new entitlement.
- **Older EEex remains second priority.** Its one synchronous callback is the full scheduler,
  it shares the direct clock field, and v0.11 inactive/faulted/external-owner no-ledger
  marshal exports normalize to `{}` while valid existing ledgers remain tables. Corrected
  legacy live acceptance remains separately pending.

See `research/11-eeex-v1.2-readiness-compatibility.md` and
`research/12-eeex-legacy-readiness-fallback.md` for provenance, official references, and
RED/GREEN evidence.

## Status (2026-08-30) — superseded original offline implementation checkpoint

- **Dragon work is being handled elsewhere and is out of scope for this branch.** Do not
  resume component 110 from this handover.
- **Historical claim, superseded by the v1.2 accounting failure above:** components 120 + 121
  were considered approved, implemented, and fully reviewed offline on branch
  `codex/ambient-readiness-121`. The authoritative design is
  `docs/plans/2026-08-27-scs-ambient-readiness-design.md` (commit `ae71422`); the executable
  plan is `docs/plans/2026-08-27-scs-ambient-readiness-implementation.md` (commit `b68b22c`).
- **120 fixes a verified SCS / Spell Revisions semantic mismatch.** This install maps both
  `WIZARD_IMPROVED_MANTLE` and `WIZARD_MOMENT_OF_PRESCIENCE` to spell 2808, but effective
  `SPWI808` is Moment of Prescience and has no weapon-immunity effect. The read-only audit
  found 585 SCS common-mage scripts, 98 numeric-2808 candidates, 77 first-round blocks,
  80 renewal blocks, 82 chain-contingency blocks, and zero unknown target-containing
  shapes. Exact resources and hashes are in `research/09-scs-sr-moment-of-prescience.md`
  and `research/originals/`.
- **121 is a deliberately retireable interim hybrid**, not the final AI architecture. The
  user is separately developing an EEex AI overhaul that may eventually claim either
  runtime layer. Ambient readiness starts with actually memorized 8-hour-plus self-buffs,
  curated for hostile/neutral/allied SCS casters, consumes one real slot once per proven
  spellbook reset, and maintains natural expiry for free only when safe. Urgent readiness
  allows one fast but normal, interruptible weapon-protection cast per contact episode.
- **The separately authorized Task 6 capability spike is complete and cleaned up.** It used
  a disposable save, installed nothing, wrote no save, and ended with Baldur/InfinityLoader
  closed and every hashed game input unchanged. The two-pass Task 11 review tightened
  component 120 to every installed canonical BCS family, protected EEex session caches from
  recycled object IDs, required complete effect-list visibility, and replaced the stock
  Project Image resref assumption with final-`SPELL.IDS` resolution. WeiDU parse-check and
  all 216 repository tests passed in a clean process. Task 12's approval-gated procedure is
  `docs/plans/2026-08-27-scs-ambient-readiness-live-checklist.md`. At this checkpoint no live
  component install had yet been authorized; the later disposable-lab result and correction
  are superseded by the 2026-09-02 status above.

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
5. **No multi-agent research or review fan-outs unless the user explicitly asks.** Keep the
   ambient-readiness implementation sequential and land evidence/tests/components as durable
   work.

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

0. **Current-version ambient accounting and the primary urgent path are accepted; legacy
   gameplay remains.**
   Offline verification is green (76 focused / 253 repository), and the fresh-process `AR3000`
   ambient test passed exact markers, one-slot deltas, and schema-2 ledgers on all four Vigil
   casters. Brother Pol's corrected neutral-to-hostile path also passed exact normal-cast start,
   contact, slot, effect, and fuse checks. The broader unrun matrix and the corrected legacy
   path remain optional later acceptance work. The full procedure is in
   `docs/plans/2026-08-27-scs-ambient-readiness-live-checklist.md`. No additional install,
   launch, save mutation, or deployment follows from this handover without the required
   approval for that exact step and target.
1. **SR wishlist session** — *needs the user live*: walk Spell Revisions' changes, collect
   which to keep/revert/re-tune → `research/10-sr-wishlist.md` → design 200-series.
2. **SCS component catalog** — solo-able: from the game install's WeiDU.log (414 entries;
   read-only) catalog the 77 installed SCS components + balance touchpoints; propose 1xx
   candidates. (Scope inherited from chriz-sod-rebalance "Part 3".)
3. **Formal install of comp 100 into the live game** — pending user sign-off; tail-install.
4. **Umbrella / collection** — see `docs/plans/2026-07-03-umbrella-analysis.md`; decision
   pending user, work deferred until 2xx/3xx mature.
