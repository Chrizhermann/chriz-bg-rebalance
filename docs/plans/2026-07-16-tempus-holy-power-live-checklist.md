# Tempus Holy Power — Live Deployment Checklist (Prepared, NOT Executed)

This checklist prepares the controlled deployment of components 401–403 into the active
playthrough at `C:\Games\Baldur's Gate II Enhanced Edition modded`. Nothing in this document
has been performed against the live game. Deployment is a separate, explicitly approved
checkpoint.

**Tested state:** branch `feature/tempus-holy-power` at commit `4020de0` ("Tolerate vanilla
star rows in SPLPROT lookup"). 75/75 tests green (`python -m unittest discover`, including the
hermetic synthetic-game install/uninstall byte-exactness suite), `weidu.exe --parse-check`
clean, and both independent Task 8 reviews APPROVED (specification review; code-quality review
after its Critical SPLPROT star-row finding was fixed in `4020de0`). If deployment happens from
a later commit, re-verify and update this line first.

**House rules that bind this deployment:**

- Never uninstall any existing WeiDU.log entry — not even to "fix" a bad install. Recovery is
  file restoration from the rollback bundle below.
- Tail-install only: component 401 must append to the current end of `WeiDU.log`.
- `dialog.tlk` must be byte-identical before and after (the component writes no strings).
- The game and `InfinityLoader.exe` must be fully closed for every file operation.

## 1. Rollback bundle (before any install)

Create `C:\Games\Baldur's Gate II Enhanced Edition modded - safety backups\cbr-tempus-401-<yyyyMMdd-HHmmss>\`
and copy, then SHA-256 hash, each of:

| Artifact | Source |
|---|---|
| `WeiDU.log` | game root |
| `dialog.tlk` | `lang\en_US\dialog.tlk` (and game-root copy if present) |
| effective `OHTMPS1.SPL` | override if present, else extract via `research\scripts\extract_key_resource.py` |
| effective `OHTEMPUS.2DA` | override |
| effective `SPPR412.SPL` (resolved `CLERIC_HOLY_POWER`) | override |
| effective `SPWI613.SPL` (resolved `WIZARD_IMPROVED_HASTE`) | override |
| effective `SPLSTATE.IDS` | override |
| effective `SPLPROT.2DA` | override |
| newest manual save directory | EET user dir (`OneDrive\Documents\Baldur's Gate - Enhanced Edition Trilogy\save\...`) |

Confirm before proceeding:

- [ ] `SPELL.IDS` resolves `CLERIC_HOLY_POWER` to `SPPR412` and `WIZARD_IMPROVED_HASTE` to
      `SPWI613` (Near Infinity or IDS dump). If either differs, record the actual resrefs —
      the installer resolves dynamically, but the rollback bundle must cover the real files.
- [ ] None of the 19 reserved helper resrefs exist in override:
      `CBRST18/19/20/21`, `CBRSC18/19/20/21`, `CBRSE18/19/20/21`, `CBRSX18`,
      `CBRAPR6/1/7`, `CBRAPC6/1/7` (any extension). If any exists, STOP — investigate first;
      the preflight would refuse anyway, but nothing may be deleted to "make it pass".
- [ ] Current `WeiDU.log` tail recorded (entry count and last line) so the post-install diff
      is provable.

## 2. Install procedure (requires explicit user approval to execute)

1. Copy `chriz-bg-rebalance\` and `setup-chriz-bg-rebalance.tp2` from the tested commit into
   the game root (overwrite the copies already there from components 100/101).
2. Ensure `Setup-chriz-bg-rebalance.exe` exists (copy of the WeiDU v24900 template, e.g.
   `Setup-Branwen.exe`).
3. Run exactly:
   `./Setup-chriz-bg-rebalance.exe --force-install-list 401 --language 0 --no-exit-pause`
   (401 = automatic semantic detection; expected to classify SR's Improved Haste as additive
   and activate the bridge).
4. The installer must NOT prompt to reinstall components 100/101; if it does, abort with `q`
   and investigate — do not answer "uninstall".

## 3. Post-install file verification (before launching the game)

- [ ] `WeiDU.log` gained exactly one line: `#0 #401` for `SETUP-CHRIZ-BG-REBALANCE.TP2`;
      every prior line is byte-identical.
- [ ] `dialog.tlk` hash unchanged.
- [ ] Override gained/changed exactly this set (additive semantics):
      changed/staged: `OHTMPS1.SPL`, `OHTEMPUS.2DA`, `SPPR412.SPL`, `SPWI613.SPL`,
      `SPLSTATE.IDS`, `SPLPROT.2DA`; created: the 13 Strength helpers and 6 APR bridge
      resources listed above. No `SPELL.IDS` and no `*.IDS.INSTALLED` may appear.
- [ ] `SPLSTATE.IDS` gained exactly four `CBR_TEMPUS_*` states. `SPLPROT.2DA`: every existing
      row byte-identical (including the vanilla `43_SOURCE` / `44_!SOURCE` / `63_EVASIONCHECK`
      rows with `*` cells) and only tail-appended `CBR`-labeled rows added. On this install a
      2026-07-16 read-only probe against the live file showed three of the four needed
      semantics already exist and are reused; the expected append is exactly one row:
      `CBR_TEMPUS_STR_BONUS_LT 37 -1 2`.
- [ ] `weidu_external\backup\chriz-bg-rebalance\401\` exists and contains the pre-images
      (WeiDU's own transactional record — part of the rollback story, never to be replayed
      via uninstall).

## 4. Controlled in-engine matrix (new manual save first, original untouched)

Load the newest manual save via `InfinityLoader.exe`. Branwen (OHTEMPUS, level 13) expected
in slot 2 — verify before using any console command.

- [ ] Charges: exactly 3 Holy Power uses at level 13 (levels 1/6/11 grants; 16/21 pending).
- [ ] Tier: cast Holy Power → 5-round duration, THAC0 8 (21−13), +13 temporary HP,
      Strength floor 19 (does not lower a higher buffed/item value), +1 APR visible on the
      character sheet during the burst.
- [ ] Casting order A: Holy Power, then SR Improved Haste on Branwen → 4 total APR during
      the overlap (base 1 + Holy +1 + SR Improved Haste +1 + bridge duplicate +1), applied
      within one second; count actual attack rolls in the combat log over one round.
- [ ] Casting order B: Improved Haste first, then Holy Power → identical result.
- [ ] Bridge expiry: when either buff ends, the duplicated APR disappears within ~1 second.
- [ ] Divine Power order A: Holy Power then SR Divine Power → Holy Power's timed effects
      (THAC0/HP/APR/Strength floor) are removed; Divine Power's own effects apply.
- [ ] Divine Power order B: Divine Power then Holy Power → reciprocal removal.
- [ ] Recast: casting Holy Power again refreshes (no stacking of HP/THAC0/APR).
- [ ] Slow: under Slow, the Strength floor and bridge continue (gap of at most ~1–2 seconds
      is the documented portable limitation, not a failure).
- [ ] Dispel: dispelling Holy Power removes the burst and its Strength setter within one
      pulse; no lingering `CBR` icons or stats after ~2 seconds.
- [ ] Save/reload mid-burst: effects and remaining duration survive a save/load cycle.
- [ ] CLAB cap: a test level-up past 25 (console XP on a scratch save) grants no additional
      Holy Power uses beyond five total.
- [ ] Save into a NEW manual slot; the pre-install save stays untouched.

Rollback condition: any unexpected resource diff in section 3, or any matrix failure that
indicates resource corruption (as opposed to a documented limitation) → close the game,
restore the section-1 bundle files into override/game root byte-for-byte, delete the 19
created `CBR*` helper files, restore `WeiDU.log`, and re-verify hashes. Never run
`--uninstall`.

## 5. Boundary

Executing sections 2–4 requires the user's explicit go-ahead in a session where the game is
confirmed closed. This document's preparation (Task 9) deliberately stops here.

## 6. Addendum (2026-07-16): combined install with components 400 / 404 / 405

The completion pass (see `2026-07-16-tempus-completion-design.md`) turns the single-component
deployment above into ONE combined tail run. Everything in sections 1–5 still applies, with
these deltas:

**Install command (one run, ascending order):**
`./Setup-chriz-bg-rebalance.exe --force-install-list 400 401 404 405 --language 0 --no-exit-pause`

**Rollback bundle additions (section 1):** also copy+hash the effective `WEAPPROF.2DA`,
`C0PR#C4.SPL`, `OHTMPS2.SPL` (BIF-extract; no override copy exists), `OHTMPS2D.SPL`,
`OHTMPS2E.SPL` (override copies — EE Fixpack + SCS shaped), and `STATS.IDS`. Confirm none of
the additional reserved resrefs exist in override: `CBRTMG2/CBRTMG2L/CBRTMG2X`,
`CBRCHT1D/1E/2D/2E/3D/3E`, `CBRTMDV`, `CBRTMD0`–`CBRTMD9` (any extension). The dead 2026-07-14
`CBRTMIG.SPL` override orphan MAY exist — it is expected, unrelated, and must not be deleted
without explicit user sign-off (optional cleanup, section 4).

**dialog.tlk rule change (404 only):** the tlk is NO LONGER byte-identical — component 404
appends exactly three strings ("Tide of Battle: Onslaught!/Bulwark!/Fortune!"). Record entry
count before/after: +3 exactly, all preexisting entries byte-identical (WeiDU appends only).
Components 400/401/405 remain TLK-neutral; a tlk delta other than those three strings is a
rollback condition.

**Expected resource delta (section 3 additions):**
- 400: `WEAPPROF.2DA` + `C0PR#C4.SPL` byte-identical (already live-hotfixed); SPLPROT gains
  up to 3 rows (`CBR_TEMPUS_C0LS_LE0 204 0 0`, `CBR_TEMPUS_PROFLS_LE0 90 0 0`,
  `CBR_TEMPUS_PROFXB_LE0 103 0 0` — semantic reuse may reduce the count); new
  `CBRTMG2/CBRTMG2L/CBRTMG2X.spl`.
- 404: `OHTMPS2.SPL` materialized to override (window dispatcher, 9 effects); new 6
  `CBRCHT*.spl`; `OHTMPS2D/E.SPL` staged but byte-identical.
- 405: `OHTEMPUS.2DA` gains the `CBR_DIVTOLL` row (all 50 levels `AP_CBRTMDV`); new
  `CBRTMDV.spl` + `CBRTMD0..4.eff` (expected discovery on this install: SPPR104 Detect
  Alignment, SPPR205 Find Traps, SPPR209 Know Opponent, SPPR415 Farsight, SPPR505 True
  Seeing — verify the actual list in the install transcript).

**In-game migration (once, after install, game restarted, save loaded):**
- 405 book strip: `C:Eval('ReallyForceSpellRES("CBRTMDV",Branwen)')` — quoted NPC names work.
- 400 pips: `C:Eval('ReallyForceSpellRES("CBRTMG2",Branwen)')` — grants longsword permission
  + longsword/crossbow starter pips only where missing; recasting is harmless.
- 404 needs no migration (same `OHTMPS2` resref; her existing innate charges use the new
  behavior; at level 13 she has 2 casts/day and tier-3 magnitudes N=3 / Luck 1).

**Acceptance additions (section 4):**
- [ ] Chaos of Battle cast → exactly ONE announce line in the log; every party member gets the
      SAME tide buff; enemies get the mirrored debuff; recast replaces the previous tide.
- [ ] Fortune tide shows Luck ±1 (tier 3).
- [ ] Branwen's priest book after CBRTMDV: no Detect Alignment / Find Traps / Know Opponent /
      Farsight / True Seeing (memorized instances gone or cleared after rest); Viconia (or any
      other cleric) still has them.
- [ ] CBRTMG2 after-cast: longsword + crossbow show 1 pip and are equippable per Artisan's
      gates; recast changes nothing; axe stays at its current pips.
- [ ] Level-up smoke (console XP scratch save): newly unlocked Divination spells vanish within
      ~1 second (op272 pulse) or at latest on the next CLAB application.
