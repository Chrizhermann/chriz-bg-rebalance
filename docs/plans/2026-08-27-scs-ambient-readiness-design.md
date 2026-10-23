# SCS ambient readiness and first-contact defense — components 120 / 121

**Status:** Approved by the user on 2026-08-27; corrected against the live EEex v1.2 API,
BG2EE 2.6.6 opcode-146 dispatch, deferred-delivery ordering, and the
`virtual_ClearActions(Boolean)` binding on 2026-09-02. The corrected build has 76 focused
tests and all 253 repository tests passing; fresh-process v1.2 ambient accounting and the
neutral-to-hostile urgent path passed live. Legacy live acceptance remains pending. This is a transitional
compatibility bridge for the current SCS-based install, not the end-state combat-AI
architecture. The user is developing a broader EEex AI overhaul in parallel; this design
must be easy for that future system to retire without uninstalling a WeiDU component.

Evidence base: `research/08-ambient-readiness.md`, the installed SCS 35.21 / Spell
Revisions resources in the read-only game directory, the 2026-08-27 inspection summarized
below, and the separately authorized disposable-session spike in
`research/10-ambient-readiness-spike.md`. No component was installed and no production save
or game resource was changed by the spike.

Compatibility addendum (updated 2026-09-02): the spike's guessed time functions were not EEex APIs,
and its fallback `os.clock()` invalidates every numeric latency claim. Component 121 targets
v1.2 first. It registers one `EEex_Opcode_AddDeferredListsResolvedListener` callback as its
sole scheduler and one `EEex_Opcode_AddListsResolvedListener` callback as an ambient-only,
pending-confirmation observer (`1/1`, total 2). Legacy uses one synchronous full scheduler
(`0/1`, total 1). If the synchronous observer is unavailable on the current path, ambient
fails closed while urgent can remain on the deferred scheduler. Both modes read the direct
`m_worldTime.m_gameTime` field used by EEex itself as raw ticks at 15 ticks per gameplay
second. A live v1.2 probe proved that this userdata has no callable `GetCurrentTime()` method.
The runtime fails closed before mutation when its clock is unavailable. It does not hardcode
EEex component numbers.

The corrected-clock live rerun exposed a second v1.2 boundary: an immediate opcode-146
request resolves its outer effect but queues its child spell after the deferred scheduler
returns, so the delivery marker cannot be required on the same Lua line. Exact BG2EE 2.6.6
disassembly proves that `dwFlags=1` publishes the child through `CMessageFireSpell` /
`CGameAIBase::FireSpell` and does not create action 181. Ambient application therefore uses
a per-spell pending transaction. The deferred scheduler requests once; the synchronous
observer confirms the marker at child-effect resolution, revalidates the original primitive
spellbook locator/flags/count, and only then debits and commits. The same observer confirms
free maintenance. Exact SCS initial-prebuff action interleavings are handled by a bounded
post-action state machine; non-adjacent or ambiguous actions never reimburse.

### Older-EEex fallback addendum (approved sequence, 2026-08-31)

The user selected current-version support first and an older-version fallback second. Three
implementation shapes were considered:

1. **Capability-selected adapter (selected):** prefer the v1.2 deferred scheduler and add the
   synchronous pending observer required by ambient accounting. Only when the deferred API
   is absent, select one synchronous callback as the legacy full scheduler. Both modes read
   the exact `m_worldTime.m_gameTime` field used by EEex itself; legacy mode also normalizes
   inactive no-ledger marshal exports to an empty table for v0.11 while preserving any valid
   existing ledger.
2. **WeiDU version/component detection (rejected):** component numbers changed between
   v0.11 and v1.x, and install metadata cannot prove the live Lua surface.
3. **A separate legacy component/runtime (rejected):** this duplicates behavior and allows
   the old and current paths to drift.

The adapter never registers two schedulers. On v1.2 it deliberately registers both APIs, but
the synchronous callback is confirmation-only and does no classification, scheduling, or
urgent work. A live v1.2 process proved that its embedded
`m_worldTime` userdata has no callable `GetCurrentTime()` method, while EEex v1.2's own
`B3TimeStep.lua` reads `m_gameTime` directly. v1.2 therefore remains the primary listener
path and shares that field with the fallback. Legacy
callback cadence is synchronous and can repeat around effect-list resolution, so all existing
idempotence gates remain authoritative and receive an explicit repeated-callback regression
test. Pre-v1.0 marshal data keeps integer `0/1` values, and an inactive/faulted/externally
owned ambient exporter returns `{}` rather than `nil` because v0.11 rejects nil exporters.

Fallback acceptance is official-source plus fake-runtime behavior for v0.11/v1.0. It is not
a claim that the corrected fallback has passed live gameplay; the existing v0.11 manual pass
ran the broken clock-gated build. Current v1.2 ambient and neutral-to-hostile urgent acceptance
has passed; legacy live acceptance remains a separate later stage.

## 1. Problem and confirmed evidence

The current install already uses SCS's highest preparation tier. SCS's long/medium/short
preparation batches are instant once their script blocks run, but most are gated on
`See()`. The spike observed preparation after visual/hostility state changes, and the user
has observed a vulnerable reaction window, but the old probe did not validly measure its
duration. PfMW, Mantle, and Absolute
Immunity are deliberately excluded from SCS's instant prebuff table and are normal first
combat casts. A caster can therefore die to a fast archer or melee rush before beginning
the defensive cast a competent mage would choose on seeing an attack.

Spell Revisions creates a second, objective compatibility bug. It replaces vanilla
Improved Mantle at `SPWI808` with the level-eight Divination spell Moment of Prescience,
but the installed `SPELL.IDS` symbol remains `WIZARD_IMPROVED_MANTLE`. The installed spell
grants large AC/save modifiers for four rounds and has no weapon-immunity effect. SCS and
SR detectable-spell metadata nevertheless still classify it as Improved Mantle / weapon
protection, and SCS selects it in first-round, renewal, and chain-contingency paths where
it expects weapon immunity. SCS can consequently cast Moment of Prescience, mark its
weapon-defense job complete, and remain physically vulnerable.

The design solves both issues while preserving resource honesty:

- long-duration readiness consumes one real memorized copy per rest cycle;
- urgent protection is a normal, interruptible cast with real aura and casting time;
- baiting and interrupting remain legitimate tactics;
- the bridge does not grow into a general replacement AI.

## 2. Component architecture and retirement boundary

### Component 120 — `cbr_scs_sr_weapon_protection_semantics`

An install-time SCS/SR compatibility repair. It corrects only proven places where SCS
expects weapon immunity from a spell that does not provide it. It has no runtime EEex
state and becomes irrelevant when SCS scripts are no longer used.

### Component 121 — `cbr_eeex_ambient_readiness`

An EEex runtime bridge with two narrow layers:

1. maintain a conservative package of very-long-duration defenses on eligible SCS
   casters; and
2. accelerate one normal weapon-protection cast when a hostile caster first sees the
   party.

The second layer ends its responsibility when that cast starts. It does not choose
offensive spells, targets, sequencers, later-round defenses, or general tactics; SCS
remains authoritative after the first reaction.

The two runtime layers expose separate namespaced enable flags plus an external-ownership
flag, all checked dynamically inside each callback. A future EEex AI can claim either
responsibility and make the installed append-only listener inert without uninstalling 121.
Only ambient slot-accounting state is persisted. Contact/debounce state is ephemeral.

## 3. Component 120: semantic compatibility repair

Component 120 resolves all spell resources dynamically through the installed `SPELL.IDS`.
It never assumes that a symbolic name describes the installed SPL. Its mismatch path
activates only when the resource currently mapped as `WIZARD_IMPROVED_MANTLE` lacks a
genuine weapon-immunity effect in its effective ability.

When the mismatch is present, component 120:

- removes or reclassifies the false SCS detectable-spell markers that make combat scripts
  treat Moment of Prescience as active weapon immunity;
- retains generic Breach/Dispel priority only when binary evidence proves that the
  installed counter can remove the relevant effects;
- corrects the allowlisted SCS mage-defense paths proven to rely on the old semantics:
  first-round protection, weapon-protection renewal, and defensive/mixed chain
  contingencies;
- removes the false candidate from fallback selections and continues through SCS's
  existing order to a genuine protection such as Mantle or PfMW; and
- publishes the same semantically validated candidate order for 121.

The component does **not** change Moment of Prescience's effects, level, school,
description, memorization, or `SPELL.IDS` identity. Those are balance decisions for the
separate Spell Revisions patch. It does not globally replace every SCS use of the symbol:
each patched context must be proven to expect weapon immunity.

Every script or SPL edit is allowlisted, shape-checked, and idempotent. An unknown SCS/SR
shape is left untouched with a clear diagnostic instead of receiving a speculative text
rewrite. If later SR work restores genuine weapon immunity to this spell, the mismatch
predicate becomes false and the compatibility edits naturally no-op.

## 4. Component 121: ambient readiness

### Eligibility and curation

An actor is eligible only after its loaded fields have settled and it carries a recognized
SCS caster combat script. Current EA does not exclude it: hostile, cautious neutral, and
allied SCS-scripted casters may qualify. Narrative exceptions use explicit exclusions.

Curation is data-driven:

- grade 0: no ambient readiness;
- grade 1: memorized defensive self-buffs with an installed duration of at least eight
  game hours;
- higher grades: reserved for later named/high-level/explicitly cautious curation; and
- sparse include/exclude overrides: resolve exceptional creatures without hardcoding the
  general mechanism.

The shipped baseline assigns eligible SCS casters grade 1. The creature must actually
have an available memorized copy, so its spellbook remains the primary statement of what
it knows. Classification is conservative: a candidate must be a defensive self-buff and
have a validated cosmetic-free SCS prebuff delivery spell. One- and two-hour defenses are
not silently promoted into grade 1. Higher grades are schema support only in the first
release.

### One-slot-per-rest accounting

For each managed spell, the first successful ambient application in a rest cycle consumes
exactly one available memorized record. The version-2 ledger stores the charged resref,
expected expiry, suppression state, exact primitive spellbook locator, original and
component-debited flags, and schema version in namespaced marshal data using only supported
primitive values.

Delivery and debit form a cross-callback transaction on EEex v1.2. The deferred scheduler
records only primitive identity and baseline values and requests the cosmetic-free spell
once. When its exact child marker resolves, the synchronous confirmation observer re-resolves
the memorized record and requires the exact original flags, unchanged availability count,
and empty ledger before clearing one availability bit. Missing or ambiguous confirmation
times out without retrying or touching another slot; marker confirmation is checked before
timeout. Engine reset, marshal import, sprite replacement, or changed spellbook state
invalidates the transient transaction.

Subsequent maintenance refreshes before the next genuine spellbook reset are free. This
avoids the waiting exploit in which five or forty real minutes make the caster weaker than
it would have been without the component. A rest is not inferred from elapsed time or a
party-only rest command: the ledger resets only when the actor actually receives an engine
spell-count refresh. The next successful ambient application consumes one newly available
copy.

The runtime must also prevent SCS's sight-triggered prebuff batch from charging the same spell
twice. Because component opcode 146 does not create action 181, an exact SCS action 181 that
starts during first-delivery pending is distinguishable. With `instantprep == 0` and the
baseline unchanged, it arms a candidate; only an immediately following RemoveSpell action
147 with the same resolved spell number advances it. The action-start callback occurs before
the engine mutation, so a later reconciliation must observe both the exact child marker and
an exact one-slot loss. That SCS-paid race commits the ledger without any component debit or
reimbursement. An unchanged count waits only to a bounded deadline; another delta fails
closed. If the component's already-queued child publishes after this SCS-paid commit, it is
a bounded redundant finite effect only: it causes no component debit and creates no new
ledger or maintenance entitlement.

After an ordinary component debit, one later exact SCS `181 -> 147` sequence, with current
`instantprep == 0` at both action starts, may reimburse only the exact component-debited
record stored in ledger schema 2. A later callback must
observe SCS's exact one-slot loss, resolve the same token, require the current flags to equal
the captured debited flags, restore the exact original flags, repair quick lists, and verify
the baseline. Free `_PRECAST` blocks, canceled removals, non-adjacent/unknown shapes, genuine
combat casts, and renewals are never reimbursed.

### Maintenance and counterplay

The initial application occurs only after sprite initialization has settled. Maintenance
uses a cheap out-of-combat cadence and requires no party member to be visible. It never
refreshes in combat; SCS's normal renewal logic remains responsible there.

The ledger distinguishes natural expiry from early removal. A naturally expired managed
effect may be refreshed once conditions are safe. An effect that disappears materially
before its expected expiry, especially after combat or dispelling, is marked suppressed
until the next real spellbook reset. The component therefore cannot undo successful player
counterplay for free.

Save/load preserves a committed ambient ledger and expected expiry, preventing a second
charge. No EEex userdata, transient object ID, or contact state is saved. A narrow lifecycle
boundary after request can leave one already-queued finite child effect after transient state
is discarded. The runtime deliberately does not infer ownership or charge it from the generic
SCS marker, and without a ledger it receives no free maintenance. Eliminating that bounded
tradeoff would require pre-debit plus marshaled pending state, which is outside this design.

Ledger lifecycle bookkeeping is gate-independent. An existing valid ledger is exported and
imported, and a genuine quick-list reset clears its charge, even while ambient gameplay is
disabled, externally owned, or faulted; retirement must neither lose a real charge nor retain
one across a real spellbook reset. Generic confirmation/action callbacks require an existing
session. The sole reconstruction exception is an exact SCS action 181 plus known delivery
against an already-existing valid, charged/reimbursable schema-2 UDAux record. It may rebuild
only ephemeral session state, without allocating UDAux, so a save/load or hot reload before
the first deferred scheduler tick cannot defeat strict reimbursement. All transient pending
transactions remain discarded.

## 5. Component 121: urgent first-contact reaction

On an eligible caster's AI tick, the accelerator requires all of the following:

- the caster is hostile toward the party and can normally `See([PC])`;
- it is conscious, `Infinity_GetInCutsceneMode()` is false, and its exact current/queued
  actions contain no dialogue, cutscene, tactical, or otherwise unproven work;
- no genuine weapon protection is already active;
- at least one semantically valid protection is genuinely memorized and available;
- no accelerated attempt has been spent in the current contact episode; and
- the current action state is safe to interrupt.

The candidate order follows SCS's installed preference order but filters by actual effects:
Absolute Immunity, a genuine Improved Mantle if one exists, Mantle, then PfMW. Moment of
Prescience is not a weapon-protection candidate under the current SR installation.

Only installed-action IDs proven by the spike may be displaced: NoAction/idle,
RandomWalk 85, and ordinary MoveToPoint 23. The runtime inspects `m_curAction` and every
entry in `m_queuedActions`; an existing cast (including SpellRES 31), Attack 3, tactical,
dialogue, cutscene, unknown action, or unavailable queue representation is left untouched
and control stays with SCS. `GetInControlOfDialog()` is not treated as a dialogue-active
boolean because it returned true during ordinary play.

The selected spell is queued as a normal self-cast. The engine consumes its memorized
copy, applies aura and casting time, displays the cast normally, and permits interruption.
The accelerator disarms when casting starts even if the spell is then disrupted. Failure
to start may receive one bounded retry; it cannot become an every-tick loop.

A contact episode rearms only after one full round without seeing any party member. This
deliberately permits players to bait and wait out defenses, at the cost of the mage's real
spell slots. It removes reaction-latency cheese without removing tactical counterplay.

Project Image is excluded structurally. A clone is recognized by active opcode 237 with
parameter 2 equal to 2 and a valid owner `m_sourceId`; its owner is separately excluded by
the engine-disabled state and lock effects whose source is the installed
`WIZARD_PROJECT_IMAGE` identity resolved through `SPELL.IDS` (currently `SPWI703`). Missing
or inconsistent spell identity or ownership information fails closed.

## 6. Runtime safety and failure policy

- Component 120 requires recognized SCS/SR evidence; component 121 requires the EEex
  autoload bootstrap, its v1.2-first runtime capability surface, and recognized SCS caster
  data. Missing prerequisites no-op with one clear diagnostic. WeiDU component numbers are
  not a compatibility contract.
- Each EEex scheduler/observer registers once through its own root-level hot-reload-safe
  sentinel and dynamic trampoline. Reloading replaces handlers without increasing counts.
- Runtime callbacks retain no engine userdata between calls. Object IDs are re-resolved and
  validated and are never persisted across saves.
- Callback errors are contained at the outer boundary. The affected layer is disabled and
  one full traceback is logged; the engine is not subjected to repeated exceptions.
- Marshal state is versioned and uses integer `0/1` flags rather than unsupported boolean
  assumptions.
- Marshal import/export and genuine quick-list-reset accounting bypass gameplay
  enable/owner/fault gates; valid charges survive retirement, and real resets clear them.
- Ambient application and slot debit are treated as a checked transaction. If both cannot
  be confirmed, that caster/spell stops maintenance. Restoration is allowed only for the
  exact persisted token whose current flags equal its captured component-debited flags; the
  original flags and quick-list baseline must then be verified. The system never loops,
  repeatedly charges, or silently maintains an unlimited buff after a bookkeeping failure.
- Per-tick work is O(1) for a previously classified eligible caster. There is no repeated
  area-wide spell or creature scan.

## 7. Verification and acceptance

### Offline binary and WeiDU fixtures

- Classify vanilla/true mantle-family SPLs and SR Moment of Prescience by actual effects.
- Verify false weapon-protection markers are removed or truthfully reclassified without
  changing Moment of Prescience's gameplay effects.
- Exercise every allowlisted SCS script transform against copied live-shaped resources.
- Prove unsupported shapes no-op, a second install is byte-idempotent, and uninstall
  restores the prior bytes exactly.
- Prove SCS-absent, SR-absent, and future-restored-Improved-Mantle predicates no-op.

### Fake-EEex tests

Cover settled-load classification, grade/exclusion selection, synchronous pending
confirmation, first debit, free natural refresh, early-removal suppression, committed-ledger
save/load, the finite-free-effect lifecycle boundary, real spellbook reset, component/SCS
delivery attribution, pre-confirm SCS-paid charging, post-action strict reimbursement,
canceled and non-adjacent removals, external-AI retirement flags, hot reload listener counts,
visibility/contact debounce, safe and unsafe action queues, cast start, interruption, bounded
retry, and rearming.

### Timing and engine-semantics spike

Before shipping 121, use a session-scoped probe on a throwaway save to measure:

1. first normal `See([PC])` / hostile contact to SCS's own prep and cast start;
2. contact detection to queued cast, cast start, and protection activation with 121;
3. exact memorized-record deltas for ambient debit and urgent normal casting; and
4. interruption, bait/re-engagement, neutral-to-hostile transition, already-casting, and
   dialogue/cutscene cases.

The spike must also prove the selected slot-debit/quick-list path and cosmetic-free ambient
delivery on the installed EEex version. Before recording any timing, it must prove that the
clock is `m_worldTime.m_gameTime`, record its raw-tick values, and verify the 15-tick
per gameplay-second conversion. The v1.2 process must report exactly one deferred scheduler
and one synchronous pending-confirmation observer, with no second scheduler. The game must
start in a fresh process so append-only listeners or sticky fault state from a prior runtime
cannot survive. The production game directory remains read-only unless the user explicitly
authorizes the transient probe in that conversation.

### Acceptance criteria

- A safely interruptible hostile caster begins the selected defense within one AI tick of
  clear visual contact.
- A protected or meaningfully occupied caster is not disturbed.
- Urgent defense consumes exactly one correct slot and remains interruptible.
- Each ambient spell consumes exactly one copy per real rest cycle, neither zero nor two.
- Natural waiting cannot permanently strip readiness; dispelling or interruption remains
  meaningful.
- SCS no longer treats current SR Moment of Prescience as weapon immunity in the patched
  native paths or in 121.
- Both runtime layers can be retired independently by the future EEex AI without
  uninstalling component 121.

## 8. Explicit non-goals

- Redesigning or replacing Moment of Prescience; that belongs to the SR patch.
- General offensive, target-selection, sequencer, contingency, or later-round AI.
- Ambient one- or two-hour spell packages in the first release.
- Fighter/rogue potion readiness or non-caster AI.
- Broad, unverified replacement of every SCS `WIZARD_IMPROVED_MANTLE` reference.
- Any installation, test, or mutation in the production game directory without fresh user
  authorization.
