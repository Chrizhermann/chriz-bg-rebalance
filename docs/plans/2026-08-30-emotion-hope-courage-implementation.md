# Emotion, Hope and Courage Exclusivity Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers-extended-cc:executing-plans to implement this plan task-by-task.

**Goal:** Ship component 301 so dynamically resolved Emotion, Courage and Emotion, Hope are self-refreshing and mutually exclusive, adverse Emotion spells retain their counter-removals, and both spells exist with learnable scroll resources when neither IWDification nor SCS supplied them.

**Architecture:** A namespaced WeiDU library performs a preflight-first, deterministic rebuild of both beneficial SPL resources after `ADD_SPELL` has retained or allocated their symbolic slots. Existing visual chrome is preserved where available; mechanics, reciprocal opcode-321 removers, descriptions, optional SCS opcode-328 markers, matching scroll text, and standalone scroll resources are CBR-owned. Python `unittest` drives both a `--nogame` transformation harness and a synthetic BG2EE install/uninstall fixture.

**Tech Stack:** WeiDU 24900 TP2/TPA, Infinity Engine SPL/ITM/IDS/STO/BCS binary formats, Python 3 `unittest`, existing `tests/ie_formats.py` fixture helpers.

**Revision after UI test:** The original HOLD-projectile/donor-scroll fallback was disproved
in game. The implemented correction packages the verified IWDEE allies-only Emotion resource
graph and blue icons under private/dynamic names, and constructs fresh IWDification-contract
scrolls. Donor scrolls now serve only as store-distribution anchors. Real corrected UI casts
subsequently verified delivery, the full buff sequences, and mutual replacement, while exposing
the absence of character-sheet status entries. The current correction adds native IWDEE heart
status BAMs, dynamic `STATDESC.2DA` rows, and opcode 142; its final manual status-list retest is
still pending. See `research/11-emotion-hope-courage.md`.

---

### Task 1: Record provenance, mechanics, and distribution evidence

**Files:**
- Create: `research/11-emotion-hope-courage.md`
- Modify: `docs/plans/2026-08-30-emotion-hope-courage-design.md`

**Step 1: Record the effective resources**

Document the live `SPELL.IDS` mappings, installed-component provenance, file sizes, SHA-256
hashes, spell header/ability fields, decoded effect tables, custom projectile mapping, icon
and sound dependencies, and the opcode-328 state symbols. Record paths and modification
times, but do not copy any third-party binaries into `research/originals/`.

**Step 2: Record the relocation regression**

Show that installed Courage contains two opcode-321 references to relocated Fear and no
self-reference. Trace the collision through the original symbolic source slots and the
later allocation rewrite.

**Step 3: Record scroll distribution**

Compare the bundled SCS and IWDification placement sources. List Hope/Courage scroll
resrefs, fixed containers/creatures, campaign guards, NPC known-spell additions, and any
random/store distribution. State exactly which behavior component 301 mirrors for its
standalone path.

**Step 4: Review the design against the evidence**

Update the approved design only where source evidence requires a correction. Keep live game
paths read-only.

**Step 5: Checkpoint**

Run: `git diff --check -- research/11-emotion-hope-courage.md docs/plans/2026-08-30-emotion-hope-courage-design.md`

Expected: exit 0.

### Task 2: Add binary fixtures and failing transformation tests

**Files:**
- Modify: `tests/ie_formats.py`
- Create: `tests/test_emotion_hope_courage.py`
- Create: `tests/weidu/emotion_hope_courage_harness.tp2`

**Step 1: Extend only the fixture formats needed by this component**

Add minimal ITM V1 parsing/building for header name/description fields, ability/effect
partitioning, and opcode-147 spell references. Add helpers for reading SPL header fields not
currently exposed by `SplFile` (spell type, level, school, casting time, range, flags, and
ability target/projectile). Keep this a fixture library, not a general IE SDK.

**Step 2: Build existing-resource fixtures**

Create synthetic Courage/Hope/Fear/Hopelessness SPLs at noncanonical resrefs. Include:

- the observed duplicate-Fear Courage defect;
- a correct Hope self-remover;
- SCS opcode-328 markers at arbitrary fixture state values;
- distinct visual/audio records that must survive;
- a learn-scroll referencing each spell.

**Step 3: Write the desired transformation assertions**

Assert exact header values and ordered effects. Every beneficial ability must begin with
exactly one self and one reciprocal opcode-321 remover with target 2, power 4, timing 1,
parameter 2 = 2, bypass resistance, and no save. Assert canonical buffs, optional markers,
adverse removers, visual preservation, revised string refs, and no stale duplicate Fear
reference.

**Step 4: Write idempotence and failure tests**

Run the production entry point twice and require byte-identical output. Add controlled RED
cases for malformed SPL signatures, wrong spell type/level, invalid final resrefs, malformed
effect partitions, and missing donor resources.

**Step 5: Add the `--nogame` harness**

The harness copies fixture inputs, includes the production TPA, calls a file-based function
with all resolved resrefs/state IDs passed explicitly, and emits a success marker only after
post-transform validation.

**Step 6: Verify RED**

Run: `python -m unittest tests.test_emotion_hope_courage -v`

Expected: FAIL because `chriz-bg-rebalance/lib/emotion_hope_courage.tpa` and its entry point
do not yet exist. The failure must be about the missing feature, not fixture construction.

### Task 3: Implement the deterministic SPL transformations

**Files:**
- Create: `chriz-bg-rebalance/lib/emotion_hope_courage.tpa`
- Test: `tests/test_emotion_hope_courage.py`

**Step 1: Add structural validation and effect-table helpers**

Implement namespaced functions to validate SPL V1 partitions, append raw/canonical effect
records, retain approved visual records, rebuild one recipient ability, and verify the
finished output. Validate all inputs before any file is mutated.

**Step 2: Implement Courage**

Generate explicit self/Hope/Fear cleanup followed by cure-fear behavior, +1 THAC0, +3
damage, +5 maximum hit points, valid presentation records, and the optional resolved
`EMOTION_COURAGE` opcode-328 marker.

**Step 3: Verify Courage GREEN**

Run the Courage-focused tests from `tests.test_emotion_hope_courage`.

Expected: PASS.

**Step 4: Implement Hope**

Generate explicit self/Courage/Hopelessness cleanup followed by +2 morale, +2 THAC0, +2
damage, +2 all saves, valid presentation records, and the optional resolved `EMOTION_HOPE`
opcode-328 marker.

**Step 5: Implement adverse normalization**

Normalize one Courage remover per Emotion: Fear header and one Hope remover per Emotion:
Hopelessness/Symbol: Hopelessness header while preserving each hostile spell's resistance
and save semantics.

**Step 6: Verify full transformation GREEN**

Run: `python -m unittest tests.test_emotion_hope_courage -v`

Expected: all tests PASS, including idempotence and controlled failures.

### Task 4: Add the public component, strings, and scroll behavior

**Files:**
- Modify: `setup-chriz-bg-rebalance.tp2`
- Modify: `chriz-bg-rebalance/languages/english/setup.tra`
- Create: `tests/test_emotion_hope_courage_installer.py`
- Test: `chriz-bg-rebalance/lib/emotion_hope_courage.tpa`

**Step 1: Write the synthetic-game RED tests**

Build minimal BG2EE games for three cases: both symbols/resources exist, neither exists, and
only one exists. Include `SPELL.IDS`, optional `SPLSTATE.IDS`, Emotion: Hopelessness donor,
base scroll donor, hostile pair resources, one existing learning scroll, minimal TLKs, KEY,
BIFF, and BG2EE marker.

Assert dynamic slot retention/allocation, final SPL semantics, scroll discovery/creation,
description strings, publication allowlist, exact reinstall stability, failure rollback,
and uninstall restoration.

**Step 2: Verify installer RED**

Run: `python -m unittest tests.test_emotion_hope_courage_installer -v`

Expected: FAIL because component 301 is not wired.

**Step 3: Wire the component**

Add the TPA to `ALWAYS`, then define component 301 with group `@1300`, label
`cbr_emotion_hope_courage_exclusion`, and BG2EE/EET plus base-donor predicates. Resolve the
four spell symbols and two optional SCS spell-state symbols dynamically. Use `ADD_SPELL`
with `IF_EXISTING` for Hope and Courage, then call the file-based transformer only after both
final resrefs are known.

**Step 4: Add original strings**

Add group/component/failure strings and original CBR spell/scroll names and descriptions.
Resolve them once and pass numeric strrefs into the library. Both descriptions must include
the mutual-exclusion sentence verbatim from the design.

**Step 5: Implement scroll discovery and fallback creation**

Patch existing opcode-147 learning scrolls that target the final resrefs. If no learning
scroll exists for a newly allocated spell, construct a clean two-ability wizard scroll with
point target/range 50/opcode 148 at caster level 10 and a separate opcode-147 learning path.
Use the final spell's blue A icon throughout. Discover Enchanted Weapon and Emotion,
Hopelessness scrolls only as store-distribution anchors and mirror their store entries. Require
exactly one valid anchor for each needed fallback and fail transactionally when it is missing
or ambiguous. Do not duplicate an existing scroll or placement.

**Step 6: Verify installer GREEN**

Run: `python -m unittest tests.test_emotion_hope_courage_installer -v`

Expected: all tests PASS.

### Task 5: Document compatibility and component scope

**Files:**
- Modify: `README.md`
- Modify: `docs/00-project-scope.md`
- Modify: `research/11-emotion-hope-courage.md`
- Create: `tests/test_emotion_hope_courage_docs.py`

**Step 1: Add README component documentation**

Document component 301, mechanics, install order, fallback behavior, and the compatibility
notice: it overwrites the effective Hope/Courage mechanics and descriptions at their
resolved resources; later spell mods can overwrite component 301.

**Step 2: Update the scope ledger**

Reserve 301 under cross-cutting audits without disturbing the candidate 300 save-for-half
audit or reserved 310/311/320 ideas.

**Step 3: Add static documentation assertions**

Assert the component number/label/group, description notice, dynamic symbol names, absence
of hardcoded final SPWI slots/state IDs, and the exact IWDEE asset/provenance allowlist.

**Step 4: Run focused tests**

Run: `python -m unittest tests.test_emotion_hope_courage tests.test_emotion_hope_courage_installer -v`

Expected: all tests PASS.

### Task 6: Parse, regress, review, and report the boundary

**Files:**
- Review: all files changed by Tasks 1-5

**Step 1: Parse every WeiDU source**

Run:

```powershell
.\weidu.exe --nogame --parse-check TP2 setup-chriz-bg-rebalance.tp2
.\weidu.exe --nogame --parse-check TPA chriz-bg-rebalance/lib/emotion_hope_courage.tpa
.\weidu.exe --nogame --parse-check TP2 tests/weidu/emotion_hope_courage_harness.tp2
```

Expected: all exit 0.

**Step 2: Run focused tests**

Run:

```powershell
python -m unittest tests.test_emotion_hope_courage -v
python -m unittest tests.test_emotion_hope_courage_installer -v
```

Expected: all PASS.

**Step 3: Run the complete regression suite**

Run: `python -m unittest discover -s tests -p "test_*.py" -v`

Expected: all PASS with zero failures/errors.

**Step 4: Inspect the diff and publication boundary**

Run:

```powershell
git diff --check
git status --short
git diff --stat
```

Confirm there are no copied SPL/BAM/VVC/PRO/WAV/ITM binaries, no live-game writes, no
hardcoded final spell slots, and no unrelated worktree changes.

**Step 5: Independent reviews**

Give a fresh reviewer the approved design and final diff. First require a
requirement-by-requirement specification review. After every spec issue is fixed and
re-reviewed, require a separate code-quality/safety review. Rerun focused and full tests
after any review fix.

**Step 6: Report honestly**

Report automated evidence and the separately authorized disposable-clone install/runtime/
uninstall evidence. State explicitly that the production installation and active saves stayed
read-only, and list any remaining UI-cast or absent-resource live gaps.
