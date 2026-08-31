# SCS ambient readiness implementation plan

> **For Codex:** Execute this plan task by task with `@executing-plans`. Invoke
> `@bg-modding`, `@infinity-engine-spells`, and `@weidu-modding` for component 120;
> add `@eeex-api` for component 121. Use `@test-driven-development` for every behavior
> change and `@verification-before-completion` before each completion claim. Do not use
> multi-agent research or review fan-outs unless the user explicitly lifts the handover's
> no-fan-out instruction.

**Goal:** Ship component 120 to repair the installed SCS/Spell Revisions weapon-protection
semantic mismatch, then ship component 121 as a narrow EEex bridge that gives eligible SCS
casters honest long-duration readiness and one fast, normal first-contact defensive cast.

**Architecture:** Component 120 is an install-time, dynamically resolved WeiDU repair. It
classifies spells by their actual effects, removes only false weapon-protection metadata,
and transforms only allowlisted SCS script blocks whose installed binary shape proves that
they expect weapon immunity. Component 121 compiles a conservative data manifest into one
hot-reload-safe EEex Lua module. Its ambient layer debits one real memorized copy per genuine
spellbook reset and maintains that same buff for free only under safe conditions. Its urgent
layer may replace proven passive work with one normal, interruptible weapon-protection cast
per contact episode. The two runtime layers can be disabled independently or claimed by the
future EEex AI without uninstalling the component.

**Tech stack:** WeiDU 24900 (`.tp2`, `.tpa`, SPL V1, BCS/BAF, IDS, 2DA), Python 3
standard-library `unittest`, PowerShell, Lua 5.3 simulation, EEex v1.2-first APIs, SCS 35.21,
Spell Revisions, BG2:EE + EET.

**Approved design:** `docs/plans/2026-08-27-scs-ambient-readiness-design.md`

**Branch:** `codex/ambient-readiness-121`

> **Correction addendum — 2026-08-31:** Task 6 did not prove its clock. The probe tried two
> nonexistent EEex globals and then silently used `os.clock()`, so its numeric timing claims
> and the original full-runtime acceptance conclusion are withdrawn. The repaired path must
> target official EEex v1.2 first: use
> `EngineGlobals.g_pBaldurChitin.m_pObjectGame.m_worldTime:GetCurrentTime()` as raw 15-Hz
> engine ticks and `EEex_Opcode_AddDeferredListsResolvedListener` as the primary tick hook.
> Runtime capability checks—not WeiDU component numbers—are authoritative. Older listener
> fallback follows only after a successful v1.2 live pass. See `research/11-eeex-v1.2-readiness-compatibility.md`.

**Safety boundary:** The active game at
`C:\Games\Baldur's Gate II Enhanced Edition modded\` is read-only throughout normal
implementation. Tasks may read final resources, mod sources, `WeiDU.log`, and the bundled
Lua interpreter. They must not install or uninstall a component, write `override`, modify a
save, edit `WeiDU.log` / `dialog.tlk`, or copy a probe into the game. Task 6 is a hard gate:
its session-scoped probe may run only after fresh, explicit user authorization in that
conversation. A later live installation is a second, separate checkpoint.

**Sequencing rule:** Component 120 can be completed before the Task 6 gate. Component 121
may receive red tests and a non-persistent probe script before the gate, but production
runtime implementation must wait until the installed EEex APIs and slot-accounting behavior
are proven. If the spike cannot prove a safe primitive, revise the design or leave that
feature disabled; do not substitute an inferred or destructive mechanism.

---

## Task 1: Land the installed evidence and a reproducible read-only audit

**Files:**

- Create: `research/08-ambient-readiness.md`
- Create: `research/09-scs-sr-moment-of-prescience.md`
- Create: `research/scripts/audit_scs_weapon_semantics.py`
- Create: `tests/test_audit_scs_weapon_semantics.py`
- Create: `research/originals/SPWI611.spl.orig`
- Create: `research/originals/SPWI708.spl.orig`
- Create: `research/originals/SPWI808.spl.orig`
- Create: `research/originals/SPWI907.spl.orig`
- Create: `research/originals/dw#mg14.bcs.orig`
- Create: `research/originals/dw#mg144.bcs.orig`
- Create: `research/originals/dw#mg148.bcs.orig`
- Create: `research/originals/scs-ambient-readiness-sha256.txt`
- Modify: `docs/handover.md`

### Step 1: Import and reconcile the existing research

Bring the uncommitted source-checkout findings from
`C:\src\private\chriz-bg-rebalance\research\08-ambient-readiness.md` into this worktree.
Read the current effective resources again before accepting any historical assertion.
Record source paths and modification times, because prior handover material is context rather
than current authority.

Create `research/09-scs-sr-moment-of-prescience.md` with the current binary evidence:

- `SPELL.IDS` maps both `WIZARD_IMPROVED_MANTLE` and
  `WIZARD_MOMENT_OF_PRESCIENCE` to spell number 2808 on this install;
- effective `SPWI808` is Moment of Prescience, not a weapon-immunity spell;
- its false weapon markers are opcode 233 with parameter 1 = 2 / parameter 2 = 128 and
  opcode 328 state 64;
- generic Breach/Dispel priority states 187/188 are a separate fact and remain unless the
  counter-effect audit disproves them; and
- SCS first-round, renewal, and chain-contingency binaries contain the numeric spell id and
  decompile through the newer alias name.

### Step 2: Write the audit tool's red tests

Test a synthetic override tree and a fake WeiDU runner. Require the audit tool to:

- enumerate only `^dw#mg[0-9]+\.bcs$` common mage scripts;
- prefilter candidate binaries by the dynamically supplied decimal spell id;
- decompile into a caller-owned temporary directory, never beside the source BCS;
- identify exact first-round, renewal, and chain-contingency block shapes;
- report unknown blocks separately rather than classifying them by substring alone;
- emit deterministic JSON plus a readable summary; and
- leave every source file byte-identical.

Run:

```powershell
python -m unittest tests.test_audit_scs_weapon_semantics -v
```

Expected initially: `ERROR` because the audit module does not exist.

### Step 3: Implement and run the read-only audit

Implement the smallest standard-library wrapper around repo-owned `weidu.exe`. Require
explicit `--game`, `--override`, `--weidu`, and `--output` arguments. Create all temporary
files below `tempfile.TemporaryDirectory`; reject output paths inside the game directory.

Run it against the active installation read-only. Confirm the current observed count of 585
common mage scripts and record the candidate / recognized / unknown counts without turning
those historical numbers into installer predicates. Include representative decompiled blocks
from `dw#mg14`, `dw#mg144`, and `dw#mg148` in the research document.

### Step 4: Preserve exact originals and prove no game write

Copy only the four final SPLs and three representative BCS binaries into
`research/originals`. Store SHA-256, size, source path, and modification time in the manifest.
Hash the live sources, `WeiDU.log`, and `dialog.tlk` before and after the audit/copy and record
equality. The checked-in originals are evidence and test-fixture donors; production code must
always patch the user's effective installed resources.

### Step 5: Update the handover and commit

Document that dragon work remains out of scope, the approved 120/121 design is authoritative,
and Task 6 is the next live-access gate.

```powershell
git add research docs/handover.md tests/test_audit_scs_weapon_semantics.py
git commit -m "Document installed SCS readiness semantics"
```

---

## Task 2: Lock component 120 behavior with failing binary and script tests

**Files:**

- Create: `tests/test_scs_weapon_semantics.py`
- Create: `tests/weidu/scs_weapon_semantics_harness.tp2`
- Create: `tests/fixtures/scs_weapon_semantics/README.md`
- Create: `tests/fixtures/scs_weapon_semantics/first_round.bcs`
- Create: `tests/fixtures/scs_weapon_semantics/renew.bcs`
- Create: `tests/fixtures/scs_weapon_semantics/chain_contingency.bcs`
- Create: `tests/fixtures/scs_weapon_semantics/unrelated_mop.bcs`
- Modify: `tests/ie_formats.py`

### Step 1: Build live-shaped hermetic fixtures

Derive minimized fixtures from the preserved originals. Keep the exact compiled block shapes
needed for the test, plus sentinel blocks before and after each target. Generate semantic SPL
variants for:

- current SR Moment of Prescience;
- true vanilla/SR-compatible Mantle, Improved Mantle, PfMW, and Absolute Immunity shapes;
- a restored future `SPWI808` that really grants weapon immunity;
- false marker variants; and
- unsupported / malformed spells.

The harness must call production functions against an isolated fixture directory. It must not
load or mutate the active game.

### Step 2: Add semantic classifier and metadata expectations

Tests must prove:

1. current `SPWI808` is not a weapon-protection candidate;
2. each true protection is accepted because of a reachable, self-applicable weapon-immunity
   effect, not its symbolic name;
3. restored/future Improved Mantle makes the mismatch predicate false;
4. only the exact false opcode-233 tier marker and opcode-328 state 64 are removed;
5. Moment of Prescience's AC, saves, duration, school, level, descriptions, headers, and
   unrelated effects are byte/semantically preserved;
6. Breach/Dispel priority states 187/188 remain when their installed counters can remove the
   spell and are rejected only on separately proven counter evidence; and
7. malformed or ambiguous effect graphs fail preflight before mutation.

### Step 3: Add exact SCS block-transform expectations

Cover at least:

1. a first-round block that casts the false candidate and spends `instantprep` is removed so
   the following original Mantle/PfMW block remains eligible;
2. the equivalent renewal block is removed;
3. a chain-contingency block keeps its generated contingency call but replaces the extra false
   cast with the closest lower semantically valid protection in the same SCS branch;
4. unrelated Moment of Prescience uses are untouched;
5. only `dw#mg[0-9]+.bcs` resources are candidates;
6. an unknown target-like block is reported and left byte-identical;
7. an absent SCS tree, absent SR mismatch, and future-restored Improved Mantle all no-op;
8. a second application is byte-identical; and
9. uninstall restores every prior byte in the isolated game fixture.

### Step 4: Run and preserve the intentional RED result

```powershell
python -m unittest tests.test_scs_weapon_semantics -v
```

Expected: failures identify the missing
`chriz-bg-rebalance/lib/scs_weapon_protection_semantics.tpa`, not malformed fixtures.

```powershell
git add tests
git commit -m "Test SCS weapon-protection semantic repair"
```

---

## Task 3: Implement the component 120 semantic and BCS patch library

**Files:**

- Create: `chriz-bg-rebalance/lib/scs_weapon_protection_semantics.tpa`
- Modify: `tests/test_scs_weapon_semantics.py`
- Modify: `tests/weidu/scs_weapon_semantics_harness.tp2`

### Step 1: Implement pure SPL semantic classification

Add namespaced functions that take explicit resource paths/resrefs and return classification
facts. Resolve `WIZARD_IMPROVED_MANTLE`, `WIZARD_MANTLE`,
`WIZARD_PROTECTION_FROM_MAGIC_WEAPONS`, and `WIZARD_ABSOLUTE_IMMUNITY` through the caller's
`SPELL.IDS`. Never infer mechanics from the symbol.

Validate SPL V1 bounds using the empirically correct ability layout (`0x1e` effect count,
`0x20` first-effect index). Inspect every reachable ability and effect, including target,
timing, duration, probability, dispel/resistance, and opcode-120 weapon category semantics.
Return an ordered set of genuine protection candidates for both component 120 and the later
component 121 manifest compiler.

Run the classifier-focused tests and make only those tests green.

### Step 2: Patch false metadata surgically

When and only when the dynamically mapped Improved Mantle spell lacks genuine immunity:

- remove the exact false opcode 233 / parameter 1 = 2 / parameter 2 = 128 marker;
- remove the exact opcode 328 / state 64 `BUFF_PRO_WEAPONS` marker;
- retain generic states 187/188 when the counter audit permits them; and
- reject unexpected duplicates or near-matches rather than broad-deleting opcode classes.

Apply the patch a second time in the test harness and require byte stability.

### Step 3: Implement an allowlisted compiled-block transformer

Vendor only the minimum block-splitting / decompile / recompile algorithm needed from SCS
SFO's `alter_script.tph`, with source/version attribution. Do not include another installed
mod's library at runtime.

For each `dw#mg[0-9]+.bcs`:

- cheaply prefilter for the dynamically resolved decimal spell id;
- split and decompile individual blocks;
- match the complete approved action/trigger shapes, not a token substring;
- delete recognized first-round and renewal false-candidate blocks;
- in recognized chain-contingency blocks, preserve the generated contingency helper and
  substitute the validated lower true-immunity candidate;
- recompile only modified blocks and preserve ordering; and
- count/report recognized and unknown shapes.

Any unknown shape remains untouched. If a required known context is present but no safe
replacement exists, fail the component before committing any mutation.

### Step 4: Separate preflight from mutation

Scan all candidate resources and build the full change plan first. Validate the mismatch,
replacement spell, script shapes, and compileability before copying a single output. Then
apply the plan through normal WeiDU backup-aware writes. This prevents a half-patched install.

### Step 5: Run focused and full tests

```powershell
python -m unittest tests.test_scs_weapon_semantics.ScsWeaponSemanticsTests.test_spell_classification -v
python -m unittest tests.test_scs_weapon_semantics.ScsWeaponSemanticsTests.test_first_round_and_renewal_blocks -v
python -m unittest tests.test_scs_weapon_semantics.ScsWeaponSemanticsTests.test_chain_contingency -v
python -m unittest tests.test_scs_weapon_semantics -v
```

```powershell
git add chriz-bg-rebalance/lib/scs_weapon_protection_semantics.tpa tests
git commit -m "Implement SCS weapon-protection semantic repair"
```

---

## Task 4: Wire and document component 120

**Files:**

- Modify: `setup-chriz-bg-rebalance.tp2`
- Modify: `chriz-bg-rebalance/languages/english/setup.tra`
- Modify: `README.md`
- Modify: `docs/00-project-scope.md`
- Modify: `research/09-scs-sr-moment-of-prescience.md`
- Modify: `tests/test_scs_weapon_semantics.py`

### Step 1: Add the public component

Add component 120 with label `cbr_scs_sr_weapon_protection_semantics`. Require BG2EE/EET,
installed SCS Smarter Mages component 6030, valid `SPELL.IDS`, the mapped spell resources,
and the recognized current mismatch. Use `REQUIRE_PREDICATE` so installs without the target
combination skip cleanly.

Do not require a hardcoded numeric resref or an exact SCS script count. After preflight, print
one concise summary of metadata changes, script blocks changed, unknown blocks skipped, and
the chosen chain-contingency replacement.

### Step 2: Add installer-level tests

Exercise complete fixture installs for:

- current SCS + current SR mismatch;
- SCS absent;
- SCS present / SR absent;
- future restored Improved Mantle;
- unknown SCS shape;
- idempotent reinstall; and
- WeiDU uninstall restoration.

Assert that component 120 never modifies the Moment of Prescience spell's gameplay effects
and never touches non-common-mage scripts such as `bheye.bcs` without a separately approved
evidence expansion.

### Step 3: Update user-facing documentation

Credit DavidW/SCS and Demivrgvs/Gibberlings3 Spell Revisions prominently. Explain that 120
is a compatibility repair, not a redesign of Moment of Prescience, and that it becomes a
no-op if a later SR patch restores genuine weapon immunity.

### Step 4: Verify and commit

```powershell
.\weidu.exe --parse-check TP2 setup-chriz-bg-rebalance.tp2 --nogame
python -m unittest tests.test_scs_weapon_semantics -v
git diff --check
```

```powershell
git add setup-chriz-bg-rebalance.tp2 chriz-bg-rebalance/languages/english/setup.tra README.md docs/00-project-scope.md research/09-scs-sr-moment-of-prescience.md tests
git commit -m "Add SCS weapon-protection compatibility component"
```

---

## Task 5: Build the red fake-EEex suite and the session-scoped probe

**Files:**

- Create: `tests/test_ambient_readiness_listener.py`
- Create: `tests/lua/ambient_readiness_sim.lua`
- Create: `tests/fixtures/ambient_readiness/manifest.lua`
- Create: `research/scripts/ambient_readiness_probe.lua`
- Modify: `research/08-ambient-readiness.md`

### Step 1: Define the stamped runtime contract

The future module is `chriz-bg-rebalance/lua/M_CBRRDY.lua`. Pin these public retirement
controls in tests:

- `_G.CBR_RDY_AMBIENT_ENABLED`: integer `1` by default, `0` disables ambient handling;
- `_G.CBR_RDY_URGENT_ENABLED`: integer `1` by default, `0` disables urgent handling; and
- `_G.CBR_RDY_EXTERNAL_OWNER`: integer bitmask, bit 0 claims ambient responsibility and bit
  1 claims urgent responsibility.

All values are read dynamically inside callbacks. A future AI can therefore retire either
layer after load. The module registers one root-level listener trampoline and replaces only
the dynamically looked-up handler on hot reload.

### Step 2: Build the fake engine surface

Model only APIs the production module will use:

- sprites, stable session ids, settled versus unsettled loaded fields, EA, SCS caster marker,
  visibility, dialogue/cutscene/conscious state, Project Image ownership, and active effects;
- mage/priest memorized records with availability bit 0 and quick-list rebuilds;
- UDAux/marshal primitive tables, save/load, game time, and spellbook reset events;
- current/queued actions, normal `SpellRES` queuing, started-action callbacks, interruption,
  failure-to-start, and one-round loss of sight; and
- fault injection, hot reload, and callback-count instrumentation.

The Python wrapper should stamp a manifest into a temporary copy of the Lua template and run
under `CBR_LUA`, the read-only installed Lua executable, or a system Lua. Never write the
game directory.

### Step 3: Add ambient RED scenarios

Cover at least:

1. only settled, recognized SCS casters are classified;
2. baseline grade 1, grade 0, sparse include, sparse exclude, and reserved higher grades;
3. only actually memorized allowlisted self-defenses of at least 2400 seconds qualify;
4. first confirmed application consumes exactly one available record;
5. maintenance refresh before reset consumes zero further copies;
6. natural expiry may refresh only out of combat with no party visible;
7. early removal suppresses refresh until a real spellbook reset;
8. elapsed time, save/load, area transition, and party rest without caster refresh do not
   reset the ledger;
9. a proven engine spellbook reset clears the charge and permits one new debit;
10. SCS's initial sight-prebuff pass cannot double-charge the exact managed spell;
11. unrelated combat casts and renewals are never reimbursed;
12. transaction failure restores safely or disables that caster/spell without looping;
13. marshal state contains only versioned primitive values and no userdata/object id; and
14. disable/ownership flags, hot reload, and an injected exception leave the listener inert
   and log at most one full traceback per disabled layer.

### Step 4: Add urgent RED scenarios

Cover at least:

1. hostile `See([PC])`, conscious state, no existing immunity, and a real available slot are
   all required;
2. candidates are ordered Absolute Immunity, genuine Improved Mantle, Mantle, then PfMW,
   filtered by actual protection semantics;
3. Moment of Prescience is rejected on the current manifest;
4. only proven idle, wander, and ordinary movement states with a safe relevant queue may be
   cleared;
5. casts, attacks, tactical actions, dialogue, cutscenes, and uncertain queues are untouched;
6. Project Image owner-lock uncertainty skips acceleration;
7. the selected spell uses a normal self-cast, real slot/aura/casting time, and can be
   interrupted;
8. the attempt is spent when the cast starts, even when interrupted;
9. a cast that never starts receives at most one bounded retry;
10. continuous sight never retriggers; and
11. one full round without seeing any party member rearms the contact episode.

### Step 5: Create a non-persistent probe script

The probe must be safe to send as session-scoped remote-console Lua and must not write a game
resource. It may register only process-lifetime callbacks behind a root guard that teardown
makes inert; nothing may persist across game exit. It should timestamp and log:

- hostile contact / `See([PC])` recognition;
- SCS prep and cast start;
- current and relevant queued action ids;
- memorized-record availability before/after a controlled debit and quick-list rebuild;
- normal cast queue, started-action callback, interruption, and effect activation; and
- neutral-to-hostile, already-casting, Project Image, dialogue, and cutscene gates.

It must expose one explicit teardown function that removes/neutralizes session state as far
as the append-only API permits. Root guards make any surviving callback inert.

### Step 6: Run and commit the intentional RED suite

```powershell
python -m unittest tests.test_ambient_readiness_listener -v
```

Expected: failures identify the absent `M_CBRRDY.lua`; the simulator and probe themselves
must parse successfully.

```powershell
git add tests research/scripts/ambient_readiness_probe.lua research/08-ambient-readiness.md
git commit -m "Test EEex ambient readiness behavior"
```

---

## Task 6: Obtain authorization and run the installed EEex timing/API spike

**Files:**

- Create after authorization: `research/10-ambient-readiness-spike.md`
- Modify after authorization: `research/08-ambient-readiness.md`
- Modify if evidence changes requirements: `docs/plans/2026-08-27-scs-ambient-readiness-design.md`
- Modify if evidence changes tests: `tests/test_ambient_readiness_listener.py`
- Modify if evidence changes probe: `research/scripts/ambient_readiness_probe.lua`

### Step 1: Stop and request explicit live-probe authorization

Do not interpret approval of this implementation plan as approval to write a throwaway save
or execute remote-console code in the active game. Ask separately. State the exact selected
throwaway save, that no component will be installed, and that all game resources remain
read-only.

If authorization is withheld, mark component 121 blocked at this task. Component 120 may
still be completed and reviewed.

### Step 2: Establish rollback and read-only evidence

After authorization, use a disposable copy/new throwaway save only. Hash `WeiDU.log`,
`dialog.tlk`, the relevant override SPL/BCS resources, and the EEex Lua loader files before
and after. Do not copy `ambient_readiness_probe.lua` into `override`; send it through the
already installed remote-console mechanism for the current session.

### Step 3: Measure the unmodified SCS baseline

First prove the exact clock source. On EEex v1.2, log
`m_worldTime:GetCurrentTime()` directly, confirm that it advances in raw 15-Hz gameplay
ticks, and reject the probe if any fallback clock would be used. Then, for controlled
caster/contact cases, record those engine ticks and separately sourced wall-clock timestamps
for:

- first normal hostile `See([PC])`;
- SCS's preparation block;
- selected defensive cast start; and
- protection activation.

Include neutral-to-hostile transition, caster already occupied, and a fast ranged rush. This
is evidence, not a benchmark promise; preserve raw logs.

### Step 4: Prove or reject every risky primitive

The spike must establish on the installed EEex version:

- the exact documented world-time accessor, its 15-tick-per-gameplay-second unit, and
  fail-closed behavior when it is unavailable;
- registration through the v1.2 deferred lists-resolved listener in a fresh game process;
- how to recognize a settled SCS caster, preferably the `caster_label_ini` local;
- exact availability-bit mutation and `CheckQuickLists` behavior for mage and priest records;
- the observable fingerprint of a genuine engine spellbook reset;
- exact cosmetic-free SCS `_PREBUFF` delivery and active-effect detection;
- whether the narrowly scoped initial-prebuff reimbursement can be proven without masking a
  genuine cast;
- current and queued action inspection sufficient to prove passive-only interruption;
- normal `SpellRES` queueing, start confirmation, aura/slot behavior, and interruption;
- one-round visibility loss / re-engagement timing; and
- Project Image owner behavior.

Do not rerun a token-mutating slot experiment on the same actor unless the prior state is
independently restored or the throwaway save is reloaded.

### Step 5: Record the decision and update tests first

For each primitive, record `proven`, `unsupported`, or `ambiguous` with raw evidence. Any
unsupported or ambiguous primitive defaults to no action at runtime. Update the approved
design only if user approval is needed for a behavior change; otherwise refine the RED tests
to the proven API contract before production Lua is written.

```powershell
git add research/08-ambient-readiness.md research/10-ambient-readiness-spike.md research/scripts/ambient_readiness_probe.lua tests/test_ambient_readiness_listener.py docs/plans/2026-08-27-scs-ambient-readiness-design.md
git commit -m "Record EEex ambient readiness timing spike"
```

---

## Task 7: Implement the component 121 install-time manifest compiler

**Files:**

- Create: `chriz-bg-rebalance/data/ambient_readiness_spells.2da`
- Create: `chriz-bg-rebalance/data/ambient_readiness_overrides.2da`
- Create: `chriz-bg-rebalance/lib/ambient_readiness.tpa`
- Create: `tests/test_ambient_readiness_installer.py`
- Create: `tests/weidu/ambient_readiness_harness.tp2`
- Modify: `tests/fixtures/ambient_readiness/manifest.lua`
- Modify: `tests/ie_formats.py`

### Step 1: Add RED manifest/compiler tests

Test fixture variants for current SCS/SR, missing spell symbols, missing SCS prebuff clones,
short duration, non-self target, non-defensive effects, no memorized delivery, duplicate
overrides, and future restored Improved Mantle. Require the compiler to fail before writing
on malformed required data and to skip optional unsupported candidates with a diagnostic.

Run:

```powershell
python -m unittest tests.test_ambient_readiness_installer -v
```

Expected initially: missing production library failures.

### Step 2: Define conservative data tables

`ambient_readiness_spells.2da` stores symbolic spell identity, minimum grade, minimum duration
2400 seconds, and the proven detection/prebuff metadata needed at runtime. Populate only the
installed, researched grade-1 baseline: Stoneskin, Ironskins, Mage Armor, Non-Detection,
Impervious Sanctity of Mind, and Mind Blank where their actual installed spell and SCS clone
pass validation. Do not add one- or two-hour spells.

`ambient_readiness_overrides.2da` provides sparse actor include/exclude/grade overrides.
Ship no speculative narrative curation; schema support is enough for the first release.

### Step 3: Resolve and validate the installed resources

The WeiDU library must:

- resolve every spell symbol through the installed `SPELL.IDS`;
- resolve the cosmetic-free delivery spell through the installed SCS
  `weidu_external/data/stratagems/instant_prebuff_spells.2da` mapping rather than naming a
  clone by convention;
- validate final SPL target, duration, effect reachability, and detection state;
- import component 120's genuine weapon-protection candidate classifier/order;
- validate override rows and stable resrefs; and
- stamp a deterministic Lua manifest with no unresolved WeiDU placeholders.

### Step 4: Make generation deterministic and idempotent

Sort emitted records by stable semantic key, emit only ASCII/LuaJIT-5.1-compatible syntax,
and verify the generated file in a second `BUT_ONLY` pass. A second application to the same
fixture must be byte-identical.

### Step 5: Run tests and commit

```powershell
python -m unittest tests.test_ambient_readiness_installer -v
git diff --check
```

```powershell
git add chriz-bg-rebalance/data chriz-bg-rebalance/lib/ambient_readiness.tpa tests
git commit -m "Compile ambient readiness runtime manifest"
```

---

## Task 8: Implement the ambient one-slot-per-reset runtime

**Files:**

- Create: `chriz-bg-rebalance/lua/M_CBRRDY.lua`
- Modify: `tests/test_ambient_readiness_listener.py`
- Modify: `tests/lua/ambient_readiness_sim.lua`
- Modify: `chriz-bg-rebalance/lib/ambient_readiness.tpa`

### Step 1: Add the hot-reload-safe, fail-closed shell

Implement one root-level registration sentinel and a dynamic trampoline. Keep current
handlers and state tables in namespaced `_G` entries so reloading replaces logic without
adding an active duplicate. Check enable and external-owner flags inside every callback.

Wrap each layer separately with `xpcall`. On the first fatal error, disable that layer and
log one full traceback. Do not let repeated AI ticks produce repeated exceptions. Make the
shell/retirement tests green and commit:

```powershell
git add chriz-bg-rebalance/lua/M_CBRRDY.lua tests
git commit -m "Add ambient readiness runtime shell"
```

### Step 2: Implement settled-load eligibility and O(1) caching

Classify only after the installed-field-settling rule proven in Task 6. Eligibility uses the
proven SCS caster marker plus sparse overrides; current EA does not by itself exclude neutral
or allied SCS-scripted casters. Cache only primitive session identity and classification.
Never retain sprite userdata between callbacks or persist an engine object id.

After classification, normal per-tick work must be O(1). Re-resolve and validate the current
sprite each callback. Make classification/grade tests green and commit.

### Step 3: Implement versioned marshal ledger and reset recognition

Persist per-spell records containing only schema version, normalized resref, charged integer,
expected-expiry number, and suppression integer. Migrate or safely discard recognized older
schemas; disable only the actor/spell on malformed state.

Reset charges only from the exact engine spellbook-refresh signal/fingerprint proven in Task
6. Elapsed time, load, area transition, or party action alone is not a reset. Make save/load
and real-reset tests green.

### Step 4: Implement checked first application and debit

For each eligible manifest record:

1. revalidate one available memorized record;
2. apply the validated cosmetic-free SCS prebuff delivery;
3. confirm the managed active effect using the proven detection path;
4. debit exactly one availability bit and rebuild quick lists through the proven API; and
5. commit the ledger record only after both effect and debit are confirmed.

Use the safe ordering/rollback method proven by the spike. If exact restoration cannot be
confirmed, stop maintenance for that actor/spell and report once. Never retry/debit every
tick and never leave a silently unlimited maintained buff.

Make first-debit and transaction-failure tests green, then commit.

### Step 5: Implement maintenance, suppression, and duplicate-charge guard

Maintenance runs on a cheap cadence, only out of combat with no party visible. Natural expiry
may receive a free refresh before the next reset. Materially early disappearance marks the
record suppressed until reset.

Implement SCS double-charge prevention only if Task 6 proved the complete fingerprint: exact
managed resref, charged ledger record, active managed effect, and initial-prebuff window.
Reimburse only that exact availability transition. If any condition is uncertain, do
nothing. Never reimburse later combat casts or renewal.

Make the remaining ambient tests green and commit:

```powershell
python -m unittest tests.test_ambient_readiness_listener.AmbientReadinessListenerTests -v
git add chriz-bg-rebalance/lua/M_CBRRDY.lua tests
git commit -m "Implement honest ambient spell readiness"
```

---

## Task 9: Implement the urgent first-contact reaction

**Files:**

- Modify: `chriz-bg-rebalance/lua/M_CBRRDY.lua`
- Modify: `tests/test_ambient_readiness_listener.py`
- Modify: `tests/lua/ambient_readiness_sim.lua`

### Step 1: Implement contact episodes and hard gates

Use ephemeral per-session primitive state only. Require proven hostile EA, normal party
visibility, consciousness, no dialogue/cutscene handling, no existing genuine weapon
immunity, a semantically valid memorized candidate, and an unspent contact episode.

Track continuous visibility and rearm only after one full round without seeing any party
member. Loading never restores contact state. Project Image owner ambiguity skips the attempt.
Make gate/debounce tests green.

### Step 2: Implement effect- and slot-based candidate selection

Read the install-time candidate manifest in this order:

1. Absolute Immunity;
2. genuine Improved Mantle, if installed;
3. Mantle; and
4. PfMW.

At runtime, filter by genuine available memorization and absence of a current true immunity.
Do not include Moment of Prescience unless its installed effects were changed into genuine
weapon immunity before component 121 was installed.

### Step 3: Implement fail-closed action safety

Allow interruption only for the exact idle, wander, or ordinary movement action ids proven
in Task 6, and only when every relevant queued action can also be inspected and classified
safe. Any unknown action or queue representation is unsafe.

Never clear a cast, attack, tactical action, dialogue action, cutscene action, or Project
Image-owner work. If a safe proof is unavailable on the installed EEex version, leave the
urgent layer inert and log the unsupported capability once.

### Step 4: Queue one normal cast and confirm start

Only after passing safety checks, clear the proven passive work and queue
`SpellRES("<resolved-resref>",Myself)` with
`EEex_Action_QueueResponseStringOnAIBase`. Do not apply the spell directly and do not edit a
memorized bit manually. The engine must own slot use, aura, casting time, visuals, and
interruption.

Disarm the episode from the started-action callback when the selected cast actually begins,
even if later interrupted. If it never starts, permit one bounded retry after the proven
timeout; then spend/close the episode until normal rearm. Queue success alone is not start
confirmation.

### Step 5: Run the full fake-runtime suite and commit

```powershell
python -m unittest tests.test_ambient_readiness_listener -v
git diff --check
```

```powershell
git add chriz-bg-rebalance/lua/M_CBRRDY.lua tests
git commit -m "Add urgent first-contact defense bridge"
```

---

## Task 10: Wire and document component 121

**Files:**

- Modify: `setup-chriz-bg-rebalance.tp2`
- Modify: `chriz-bg-rebalance/languages/english/setup.tra`
- Modify: `README.md`
- Modify: `docs/00-project-scope.md`
- Modify: `docs/handover.md`
- Modify: `research/08-ambient-readiness.md`
- Modify: `tests/test_ambient_readiness_installer.py`

### Step 1: Add the public component and prerequisites

Add component 121 with label `cbr_eeex_ambient_readiness`. Require BG2EE/EET, installed SCS
Smarter Mages component 6030, `M_*.lua` autoload support, and the SCS instant-prebuff mapping.
Do not hardcode EEex component numbers: v1.2 moved Main to component 1 and LuaJIT to 8, and
the runtime does not itself use a LuaJIT-only primitive. Use `REQUIRE_PREDICATE` for missing
mod prerequisites; use explicit preflight diagnostics for malformed recognized installs.

A successful Task 6 capability profile is a development acceptance gate, not an installer
predicate that can be rediscovered safely on another user's machine. Stamp the v1.2 target
profile into the module and recheck required API entry points and world-time access at runtime;
if they are absent, the affected layer disables itself with one diagnostic.

Component 121 may be installed with or without 120, but it imports the same classifier so its
candidate manifest is always truthful. On the current SR install, recommend installing 120
first so native SCS paths are repaired too.

### Step 2: Stamp and ship one runtime module

Call the manifest compiler and copy only the verified stamped `M_CBRRDY.lua` into the fixture
or game override through WeiDU's normal backup-aware install. Assert that no placeholders,
unsupported Lua syntax, machine-specific paths, or debug/probe hooks remain.

### Step 3: Add full installer tests

Cover SCS absent, EEex absent/unsupported, current SCS/SR, restored Improved Mantle, missing
optional ambient candidates, malformed required mapping, deterministic reinstall, and
uninstall restoration. Assert that component 121 does not patch SCS combat scripts or spell
mechanics and that 120 does not depend on EEex.

### Step 4: Document ownership and non-goals

Explain the one-slot-per-reset rule, natural-refresh versus dispel suppression, normal urgent
cast, baiting counterplay, separate layer flags, external-owner bitmask, and temporary bridge
status. State clearly that offensive AI, target selection, sequencers, later-round defenses,
and the future full EEex AI are out of scope.

### Step 5: Verify and commit

```powershell
.\weidu.exe --parse-check TP2 setup-chriz-bg-rebalance.tp2 --nogame
python -m unittest tests.test_ambient_readiness_installer tests.test_ambient_readiness_listener -v
git diff --check
```

```powershell
git add setup-chriz-bg-rebalance.tp2 chriz-bg-rebalance/languages/english/setup.tra README.md docs/00-project-scope.md docs/handover.md research/08-ambient-readiness.md tests
git commit -m "Add EEex ambient readiness bridge component"
```

---

## Task 11: Run final offline verification and two-pass local review

**Files:** Review all branch changes since `ae71422`.

### Step 1: Review against the approved design

Without spawning a reviewer unless the user explicitly authorizes it, perform a fresh local
requirement-by-requirement review. Confirm:

- 120 changes only the proven false semantic contexts;
- Moment of Prescience itself is not redesigned;
- 121 spends one slot once, never maintains after early removal, and never direct-applies an
  urgent protection;
- unsafe/unknown queue state always skips;
- each runtime layer retires independently;
- no dragon or broader AI work leaked into the branch; and
- no live-game mutation occurred outside an explicitly authorized Task 6 probe.

Fix every mismatch with a focused test first.

### Step 2: Review failure handling and install transactions

Do a second pass focused on SPL bounds, BCS block matching, dynamic IDS resolution, preflight
before mutation, WeiDU backup/uninstall behavior, LuaJIT syntax, append-only listeners,
marshal primitives, sprite lifetime, retry bounds, callback error fuses, and per-tick cost.

### Step 3: Run the complete clean-process verification

```powershell
.\weidu.exe --parse-check TP2 setup-chriz-bg-rebalance.tp2 --nogame
python -m unittest discover -v
git diff --check
git status --short
git log --oneline ae71422..HEAD
```

Re-run the read-only audit and compare its report with the checked-in evidence. If Task 6 was
authorized, compare the recorded before/after live hashes. Component 121 is not shippable if
Task 6 has no proven capability profile, even when all fake tests pass.

Commit review fixes with narrow messages. Do not call the branch complete until the commands
above have fresh successful output.

---

## Task 12: Prepare—but do not perform—the live deployment checkpoint

**Files:**

- Create: `docs/plans/2026-08-27-scs-ambient-readiness-live-checklist.md`

### Step 1: Define the rollback/evidence bundle

The checklist must preserve timestamped bytes/hashes of:

- every `SPWI611` / `SPWI708` / `SPWI808` / `SPWI907` effective spell used by classification;
- every `dw#mg*.bcs` binary component 120 plans to change;
- the shipped `M_CBRRDY.lua` target if it already exists;
- SCS's instant-prebuff mapping;
- `SPELL.IDS`, `WeiDU.log`, and `dialog.tlk`; and
- the selected throwaway acceptance-test save.

Never uninstall an existing WeiDU.log entry. Rollback of a newly appended component must use
the separately approved plan appropriate to the live playthrough, not manual log/source edits.

### Step 2: Define staged acceptance

After separate explicit installation approval:

1. install/verify 120 first and test native SCS first-round, renewal, and chain-contingency
   choices;
2. install/verify 121 on a throwaway save;
3. test hostile rush, neutral-to-hostile, already casting, attack/tactical queue, dialogue,
   cutscene, Project Image, interruption, bait/re-engagement, and one bounded retry;
4. test each ambient baseline spell for one debit, natural refresh, dispel suppression,
   save/load, real rest/reset, and SCS prebuff double-charge prevention; and
5. set each retirement flag/owner bit live and prove the associated layer becomes inert.

Record actual engine observations separately from automated coverage.

### Step 3: Stop at the deployment boundary

Do not install either component, modify `override`, alter a real playthrough save, or edit
`WeiDU.log` / `dialog.tlk` as part of this implementation plan. Report the exact verified
branch/commit and wait for explicit live-install authorization.

```powershell
git add docs/plans/2026-08-27-scs-ambient-readiness-live-checklist.md
git commit -m "Add SCS ambient readiness live checklist"
```
