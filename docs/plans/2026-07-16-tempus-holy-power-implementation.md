# Cleric of Tempus Holy Power Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers-extended-cc:executing-plans to implement this plan task-by-task.

**Goal:** Ship mutually exclusive WeiDU components 401-403 that replace the installed Cleric of Tempus Holy Power with the approved five-tier martial burst, cap its uses at five, make it mutually exclusive with the installed Divine Power in both casting orders, and interoperate with either true-doubling or Spell Revisions-style additive Improved Haste.

**Architecture:** Keep the live game read-only during development. A small namespaced WeiDU library performs a complete semantic preflight, patches final installed resources with `COPY_EXISTING`, builds private helper SPL/EFF resources, and allocates collision-free SPLSTATE/SPLPROT entries only for the additive bridge. Python `unittest` creates isolated SPL/2DA/IDS fixtures, invokes the same production patch functions through a `--nogame` WeiDU harness, and parses the output binaries to verify progression, compatibility branches, casting-order graph, and idempotency. The three public components share one implementation body and differ only in automatic, forced-doubling, or forced-additive semantic selection.

**Tech Stack:** WeiDU 24900 (`.tp2`, `.tpa`, SPL V1/EFF V2/2DA/IDS binary patching), Python 3 standard-library `unittest`, BG2:EE/EET Infinity Engine opcodes 1/18/44/54/97/272/321/326/328, Git worktree branch `feature/tempus-holy-power`.

**Approved design:** `docs/plans/2026-07-16-tempus-holy-power-design.md`

**Safety boundary:** All commands in Tasks 1-8 run from the isolated worktree. They may read the active installation but must not write its `override`, saves, `WeiDU.log`, `dialog.tlk`, IDS, or 2DA files. Task 9 prepares a rollback/deployment handoff; an actual live install is a separate explicit checkpoint.

---

## Task 1: Preserve exact resource evidence and document the live layout

**Files:**

- Create: `research/04-tempus-holy-power.md`
- Create: `research/scripts/extract_key_resource.py`
- Create: `research/originals/OHTMPS1.spl.orig`
- Create: `research/originals/OHTEMPUS.2da.orig`
- Create: `research/originals/SPPR412.spl.orig`
- Create: `research/originals/SPWI613.spl.orig`
- Test: `tests/test_extract_key_resource.py`

### Step 1: Write a failing KEY/BIF extraction test

Create a tiny synthetic KEY/BIF pair in a temporary directory. Assert that the extractor:

- resolves a resource by case-insensitive resref and type;
- selects the BIF from the high locator bits in the KEY entry;
- uses `locator & 0xFFFFF` as the BIF variable-resource table ordinal, regardless of the
  entry's serialized locator dword;
- writes only to the caller-provided output path; and
- fails cleanly on an out-of-range ordinal or payload-size mismatch.

Run:

```powershell
python -m unittest tests.test_extract_key_resource -v
```

Expected initially: `ERROR` because `research/scripts/extract_key_resource.py` does not exist.

### Step 2: Implement the read-only extractor

Implement the smallest standard-library parser needed for KEY V1 and BIFF V1 variable resources. Require explicit `--key`, `--game-root`, `--resref`, `--type`, and `--output` arguments. Refuse to overwrite an existing output unless `--expected-sha256` matches the bytes to be written.

Run the test again and expect all extractor tests to pass.

### Step 3: Capture the exact effective resources into the repository

Use the repo-owned extractor for biffed `OHTMPS1`; use `Copy-Item` only from final override resources into the worktree for the other three files. Do not use the live WeiDU executable and do not extract into the game directory.

Known evidence to assert before accepting the copies:

- `OHTMPS1.spl`: KEY entry 33414, locator `0x01000035`, `DATA/PATCH25.BIF`, payload offset `0x5EAA08`, size 13394, SHA-256 `abd47abfa923196f7c25332a5bc9518ceb08458b0a0bfa25a85fa3be1e1d70ef`.
- `OHTEMPUS.2da`: SHA-256 `84fc365814c45d323220ad9760b6bbf45f0d9072f583899ab879ba06f2600d98`.
- effective `SPPR412.spl`: SHA-256 `c2db73888707428cb8f0abb68faa1f6393b98ec37fa0ac814a36428a72cf7062`.
- effective `SPWI613.spl`: SHA-256 `67443841399a7e67020cc5e02fb87d198caa582ea88dc23dca6f60fe2e07e028`.

Record the source path, modification time, size, hash, symbolic spell resolution, and parsed effect/header summary in `research/04-tempus-holy-power.md`. Explicitly note that SR exposes Divine Power through `CLERIC_HOLY_POWER`, not a nonexistent `CLERIC_DIVINE_POWER` symbol.

### Step 4: Prove the live installation remained unchanged

Hash `dialog.tlk`, `WeiDU.log`, and the three effective override resources before and after capture. Record equality in the research document; do not commit machine-specific absolute save paths or volatile timestamps as requirements.

### Step 5: Commit

```powershell
git add research tests/test_extract_key_resource.py
git commit -m "Document installed Tempus Holy Power resources"
```

---

## Task 2: Build the isolated fixture harness and lock the behavior with failing tests

**Files:**

- Create: `tests/__init__.py`
- Create: `tests/ie_formats.py`
- Create: `tests/weidu/tempus_holy_power_harness.tp2`
- Create: `tests/test_tempus_holy_power.py`

### Step 1: Build minimal fixture writers and parsers

In `tests/ie_formats.py`, add only the SPL V1, EFF V2, 2DA, IDS, and effect/header fields required by these tests. Prefer parsing the preserved effective binaries where useful, but generate semantic variants rather than checking in copies for every case.

The harness must copy a fixture into an isolated output directory and call production `cbr_*` functions from `chriz-bg-rebalance/lib/tempus_holy_power.tpa`. It must never use `COPY_EXISTING` or load a game in test mode.

### Step 2: Add behavior tests

Cover at least:

1. additive Improved Haste: one timed cumulative opcode 1 with APR key 1, and no true-Haste effect;
2. doubling Improved Haste: timed opcode 16 or 317, type 1, and no additive signature;
3. mixed, missing, probabilistic, conditional, and header-inconsistent Improved Haste rejection;
4. auto versus forced compatibility modes;
5. exactly 30 Holy Power headers with required levels 1-30, with the level-30 header serving all later levels;
6. durations 18/24/30/30/30 seconds for levels 1/7/13/19/25;
7. Strength floors 18/00, 18/00, 19, 20, 21 that never lower a higher current value and are restored after a stronger temporary Strength effect expires;
8. fighter THAC0 `max(0, 21 - level)`, temporary HP `min(level, 30)`, and cumulative APR keys 6/1/7 for +1/2, +1, +1.5;
9. preservation of installed state 9, state 68, opcode 282, visuals, icons, and unknown sentinel effects;
10. removal of only `GA_OHTMPS1` cells 26/31/36/41/46 from `ABILITY1`, preserving levels 1/6/11/16/21, level-25 `AP_CDHLYSYM`, every other row, and sentinel columns;
11. reciprocal first-effect opcode 321 cleanup between `OHTMPS1` and the dynamically resolved `CLERIC_HOLY_POWER` resource;
12. collision-free/reusable private SPLSTATE allocation and append-only semantic SPLPROT reuse/allocation;
13. immediate conditional kicks for both casting orders plus one-second non-stacking heartbeat refresh at the resource-graph level;
14. binary/semantic equality after a second application; and
15. no `SAY`, `STRING_SET`, `RESOLVE_STR_REF`, `dialog.tlk`, or TLK-writing operation in components 401-403.

### Step 3: Run the red test suite

```powershell
python -m unittest tests.test_tempus_holy_power -v
```

Expected: tests fail because `chriz-bg-rebalance/lib/tempus_holy_power.tpa` and generated resources do not yet exist. Confirm the failures concern missing production behavior, not malformed fixtures.

### Step 4: Commit the red tests

```powershell
git add tests
git commit -m "Test Tempus Holy Power component behavior"
```

---

## Task 3: Implement namespaced preflight, semantic classification, and allocation utilities

**Files:**

- Create: `chriz-bg-rebalance/lib/tempus_holy_power.tpa`
- Modify: `tests/test_tempus_holy_power.py`

### Step 1: Add pure patch functions

Implement namespaced functions with explicit inputs and returned values:

- `cbr_validate_spl_v1`
- `cbr_classify_improved_haste`
- `cbr_validate_tempus_clab`
- `cbr_find_or_allocate_splstate`
- `cbr_find_or_append_splprot`
- `cbr_add_basic_self_ability`
- `cbr_clone_final_spell_header`

Vendor only the minimum algorithms needed, with inline attribution to the SCS/SR/Artisan patterns researched in `research/04`. Do not include files from another installed mod at runtime.

### Step 2: Enforce semantic rules

Classification must inspect all reachable caster-level headers and accept only a consistent shape:

- `double`: timed opcode 16/317 with parameter 2 equal to 1, no recognized additive signature;
- `additive`: exactly one reachable timed cumulative opcode 1 with parameter 1 equal to 1 and parameter 2 equal to 0 per applicable header, no true-Haste signature;
- anything else: fail with the resref, header index, opcode counts, and selected mode.

Forced mode chooses the compatibility branch but still validates the minimum patchable structure. It must not rewrite Improved Haste mechanics.

### Step 3: Make allocation idempotent and collision-safe

For SPLSTATE, reuse the exact private symbol if it maps uniquely; otherwise select a free numeric state in 0-255, append, and `CLEAR_IDS_MAP`. Reject a duplicate symbol with conflicting values or a number already shared by another symbol.

For SPLPROT, implement a generic semantic `(STAT, VALUE, RELATION)` lookup/append helper. Use it for the active-SPLSTATE test (`STAT=0x112, VALUE=-1, RELATION=1`) and the Strength/exceptional-Strength comparisons needed by the floor helpers. If a row is absent, append it at the tail and return the new zero-based row index. Never insert or hardcode current row numbers such as 110, 124, or 125.

### Step 4: Separate preflight from mutation

Expose a common action-phase preflight that validates BG2EE/EET, resources, symbolic spell mappings, OHTMPS1 layout, exact Tempus grant shape, helper resref collisions, SPLSTATE/SPLPROT structure, and compatibility mode before any append/create/patch operation. A validation `COPY_EXISTING ... ~override~ ... BUT_ONLY` block may read and `PATCH_FAIL`, but must perform no writes.

### Step 5: Run focused tests and commit

```powershell
python -m unittest tests.test_tempus_holy_power.TempusHolyPowerTests.test_improved_haste_classification -v
python -m unittest tests.test_tempus_holy_power.TempusHolyPowerTests.test_state_and_splprot_allocation -v
```

Commit only after both pass and the remaining feature tests still fail for missing Holy/bridge transformations.

```powershell
git add chriz-bg-rebalance/lib/tempus_holy_power.tpa tests/test_tempus_holy_power.py
git commit -m "Add Tempus Holy Power compatibility preflight"
```

---

## Task 4: Implement the Holy Power progression and five-use CLAB cap

**Files:**

- Modify: `chriz-bg-rebalance/lib/tempus_holy_power.tpa`
- Modify: `tests/test_tempus_holy_power.py`

### Step 1: Extend rather than replace the installed spell

Accept either the recognized original 20-header layout or the exact already-patched 30-header layout. Clone installed header 20 ten times to create levels 21-30, then normalize all 30 headers. Preserve unrelated/mod-added effects; remove only recognized legacy Holy Power mechanics and prior `CBR` effects. Preserve Detectable Spells state 9, buff-enhancement state 68, opcode 282, visuals, icons, sounds, and self-replacement behavior.

Use installed resources as the base. Never copy the stored evidence binaries or SR source SPLs into a user's override.

### Step 2: Apply per-level mechanics

For each header level 1-30, write:

- required level equal to the header level;
- duration 18 seconds at levels 1-6, 24 at 7-12, and 30 at 13+;
- flat fighter THAC0 `max(0, 21 - level)` via opcode 54;
- temporary maximum/current HP `min(level, 30)` via opcode 18;
- Holy APR cumulative key: none at 1-6, key 6 at 7-12, key 1 at 13-24, key 7 at 25+;
- administrative opcode 321 removal of the resolved Divine Power resource before timed Holy effects; and
- timing/dispel/MR fields matching the installed spell: timed mechanics `resist_dispel=3`, administrative removals immediate/non-dispellable.

### Step 3: Implement Strength as a real floor

Create private strength helpers for 18/00, 19, 20, and 21. Use an immediate conditional application and a one-second Holy-duration heartbeat that removes the previous helper then reapplies it only when current Strength is below the tier floor. For 18/00, distinguish Strength below 18 from Strength exactly 18 with exceptional value below 100; use a nested conditional helper if necessary so a 19+ character with a zero exceptional-Strength stat can never match the latter case. This ensures Holy Power never lowers a stronger value and restores its own floor if a stronger external Strength buff expires first.

All helper resrefs must use the `CBR` prefix and be at most eight characters.

### Step 4: Cap CLAB uses surgically

Patch only `OHTEMPUS.2DA` row `ABILITY1`, clearing exact `GA_OHTMPS1` grants at columns 26, 31, 36, 41, and 46. Fail if the expected original or already-cleared shape is not present. Do not touch the level-25 domain helper or other ability rows.

### Step 5: Run progression tests and commit

```powershell
python -m unittest tests.test_tempus_holy_power.TempusHolyPowerTests.test_progression -v
python -m unittest tests.test_tempus_holy_power.TempusHolyPowerTests.test_strength_floor -v
python -m unittest tests.test_tempus_holy_power.TempusHolyPowerTests.test_clab_cap -v
python -m unittest tests.test_tempus_holy_power.TempusHolyPowerTests.test_preserves_foreign_effects -v
```

```powershell
git add chriz-bg-rebalance/lib/tempus_holy_power.tpa tests/test_tempus_holy_power.py
git commit -m "Implement Tempus Holy Power progression"
```

---

## Task 5: Implement casting-order-safe Improved Haste bridging and Divine Power exclusion

**Files:**

- Modify: `chriz-bg-rebalance/lib/tempus_holy_power.tpa`
- Modify: `tests/test_tempus_holy_power.py`

### Step 1: Add the additive Improved Haste marker

Only in the additive branch, clone the final recognized timed `opcode 1, parameter1=1, parameter2=0` effect to opcode 328 with `special=1` and the dynamically allocated private Improved Haste state. Preserve target, power, timing, duration, probability, dispel, resistance, caster-level, and header placement. Delete an identical prior private marker before adding it so reinstall is idempotent.

### Step 2: Mark Holy APR tiers

Allocate separate private Holy states for +1/2, +1, and +1.5 APR. Add the appropriate state to each applicable Holy header for exactly that header's duration. Level 1-6 needs no APR-tier state.

### Step 3: Create non-stacking bridge helpers

Create one helper SPL and one conditional EFF per APR tier:

- APR keys 6, 1, and 7 respectively;
- helper effect order begins with opcode 321 removing the same helper resref;
- the duplicate APR effect is cumulative, lasts one second, and has no magic-resistance check;
- the EFF uses opcode 326 against the private Improved Haste SPLSTATE via the semantically resolved SPLPROT row; and
- Holy headers carry opcode 272 with `parameter1=1`, `parameter2=3` for one pulse per second and only for the Holy header's duration.

Do not lengthen the helper to two seconds without separate user approval; the approved design requires expiry within one engine tick.

### Step 4: Make both casting orders immediate

- Holy cast second: add an immediate opcode 326 check in each Holy APR tier that applies its helper when the Improved Haste state is already active.
- Improved Haste cast second: add one immediate opcode 326 kick per Holy tier to the same header as the matched +1 APR effect. Each kick checks its Holy tier state and applies the corresponding helper.

The heartbeat is continuity/cleanup insurance, not the sole casting-order trigger.

### Step 5: Close Divine Power stacking in both orders

Resolve `CLERIC_HOLY_POWER` through `SPELL.IDS`. Ensure each Holy header begins with removal of the resolved spell and each header of that installed spell contains an early opcode 321 removal of `OHTMPS1`. Preserve all other Divine Power effects, including SR helper EFFs, Detectable Spells states, and later-mod compatibility additions.

### Step 6: Run bridge/exclusion/idempotency tests and commit

```powershell
python -m unittest tests.test_tempus_holy_power.TempusHolyPowerTests.test_additive_bridge_graph -v
python -m unittest tests.test_tempus_holy_power.TempusHolyPowerTests.test_doubling_needs_no_bridge -v
python -m unittest tests.test_tempus_holy_power.TempusHolyPowerTests.test_divine_power_exclusion -v
python -m unittest tests.test_tempus_holy_power.TempusHolyPowerTests.test_idempotent_second_application -v
```

```powershell
git add chriz-bg-rebalance/lib/tempus_holy_power.tpa tests/test_tempus_holy_power.py
git commit -m "Bridge Tempus Holy Power with Improved Haste"
```

---

## Task 6: Wire components 401-403 and user-facing documentation

**Files:**

- Modify: `setup-chriz-bg-rebalance.tp2`
- Modify: `chriz-bg-rebalance/languages/english/setup.tra`
- Modify: `README.md`
- Modify: `docs/00-project-scope.md`
- Modify: `research/04-tempus-holy-power.md`

### Step 1: Add the 4xx family

Extend the numbering comment with `400-499: class and kit revisions`. Add one `SUBCOMPONENT` family with:

- 401: automatic semantic detection, recommended;
- 402: force true-doubling compatibility;
- 403: force additive compatibility.

Use labels from the approved design. Each component sets only the compatibility mode then invokes the same implementation body. `SUBCOMPONENT` enforces mutual exclusivity.

### Step 2: Add predicates and diagnostics

Add translated component/group/subcomponent names and actionable failure strings. Predicates must guard BG2EE/EET, OHTEMPUS, OHTMPS1, symbolic Divine Power, and symbolic Improved Haste. Do not add game-facing strings or write the TLK.

### Step 3: Document install-order and save behavior

README/scope must state:

- install after SR, SCS, Artisan's Kitpack, and other spell/kit changes;
- component 401 is the normal choice;
- existing characters automatically use the patched `OHTMPS1` resource;
- Branwen at level 13 already has the intended three uses and needs no save edit for this component;
- characters already above level 25 may retain previously granted excess uses in their saved creature and require a separately controlled save repair;
- no weapon-training, Chaos of Battle, Divination, or EEex APR-cap changes are included.

### Step 4: Parse-check and run all fixture tests

```powershell
.\weidu.exe --parse-check TP2 setup-chriz-bg-rebalance.tp2 --nogame
python -m unittest discover -v
git diff --check
```

Expected: parse success, all tests pass, no whitespace errors.

### Step 5: Commit

```powershell
git add setup-chriz-bg-rebalance.tp2 chriz-bg-rebalance/languages/english/setup.tra README.md docs/00-project-scope.md research/04-tempus-holy-power.md
git commit -m "Add Tempus Holy Power WeiDU components"
```

---

## Task 7: Record the deferred EEex APR-cap experiment

**Files:**

- Create: `research/05-eeex-apr-cap.md`

### Step 1: Record the supported conclusion

Document:

- the current playthrough uses EEex 0.11 and has no supported public attack-scheduler/cap hook;
- writing `m_nNumberOfAttacks` may change derived/displayed APR but is not proof of scheduled attacks;
- EEex 1.0 adds opcode 342 parameter2 5 combat-round bitmap overrides, making real 6-10 attack schedules plausible;
- this is unverified above five attacks and is not part of components 401-403; and
- upgrading EEex in the active playthrough is explicitly out of scope.

### Step 2: Define a future isolated prototype matrix

Require real hit-count instrumentation with cosmetic attacks disabled, melee/ranged/dual-wield/off-hand/half-APR cases, casting-order interaction with opcode 16/317, UI, save/reload, multiplayer parity, and performance. If custom RNDBASE schedules fail, the fallback is a dedicated OneSwing/Swing scheduler hook, not a derived-stat write.

### Step 3: Commit

```powershell
git add research/05-eeex-apr-cap.md
git commit -m "Document deferred EEex APR-cap prototype"
```

---

## Task 8: Independent specification and code-quality review

**Files:** Review all branch changes since `c967c18`.

### Step 1: Specification review

Give a fresh reviewer the full approved design and this plan. Require a requirement-by-requirement report, including explicit confirmation that no Chaos/Divination/weapon/EEex feature leaked into the component and no live game writes occurred. Fix every mismatch, then rerun the reviewer until approved.

### Step 2: Code-quality review

After spec approval, give a separate fresh reviewer the diff and test output. Require scrutiny of WeiDU transaction ordering, offset/header indexing, effect timing/dispel semantics, state collision handling, helper non-stacking, idempotency, diagnostics, and fixture fidelity. Fix every important issue and re-review until approved.

### Step 3: Final verification

From a clean process:

```powershell
.\weidu.exe --parse-check TP2 setup-chriz-bg-rebalance.tp2 --nogame
python -m unittest discover -v
git diff --check
git status --short
git log --oneline c967c18..HEAD
```

Expected: parse success, all tests pass, no whitespace errors, and only intentional tracked changes.

Commit any review fixes with focused messages.

---

## Task 9: Prepare—but do not perform—the live deployment checkpoint

**Files:**

- Create: `docs/plans/2026-07-16-tempus-holy-power-live-checklist.md`

### Step 1: Define the rollback bundle

The checklist must preserve timestamped copies/hashes of effective `OHTMPS1`, `OHTEMPUS.2DA`, resolved Divine Power, resolved Improved Haste, SPLSTATE.IDS, SPLPROT.2DA, `WeiDU.log`, and `dialog.tlk` before installation. It must never uninstall an existing WeiDU component.

### Step 2: Define the controlled in-engine matrix

After a separately approved live install, test Branwen at level 13 for three charges, axe/sword/crossbow usability already handled separately, both Holy/IH casting orders, both Holy/Divine Power orders, expiry, dispel, save/reload, Slow, APR equipment, ranged/melee attacks, and actual attack counts. Include a rollback condition for any unexpected resource or save behavior.

### Step 3: Stop at the deployment boundary

Do not copy files to the active override, run the component against the live game, alter a save, upgrade EEex, or touch `dialog.tlk` in this task. Report the exact tested branch/commit and wait at the explicit live-install checkpoint.

```powershell
git add docs/plans/2026-07-16-tempus-holy-power-live-checklist.md
git commit -m "Add Tempus Holy Power live deployment checklist"
```
