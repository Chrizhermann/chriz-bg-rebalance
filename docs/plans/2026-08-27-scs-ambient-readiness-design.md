# SCS ambient readiness and first-contact defense — components 120 / 121

**Status:** Approved by the user on 2026-08-27; installed EEex primitives validated on
2026-08-30. This is a transitional compatibility bridge for the current SCS-based install,
not the end-state combat-AI architecture. The user is developing a broader EEex AI overhaul
in parallel; this design must be easy for that future system to retire without uninstalling
a WeiDU component.

Evidence base: `research/08-ambient-readiness.md`, the installed SCS 35.21 / Spell
Revisions resources in the read-only game directory, the 2026-08-27 inspection summarized
below, and the separately authorized disposable-session spike in
`research/10-ambient-readiness-spike.md`. No component was installed and no production save
or game resource was changed by the spike.

## 1. Problem and confirmed evidence

The current install already uses SCS's highest preparation tier. SCS's long/medium/short
preparation batches are instant once their script blocks run, but most are gated on
`See()`. Script cadence, an occupied action, and neutral-to-hostile transitions delay that
evaluation. The installed spike observed 0.570 s from first `See([PC])` to the preparation
marker for a hostile-at-load caster and 0.938 s from EA change to that marker for a
neutral-to-hostile caster. PfMW, Mantle, and Absolute
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
exactly one available memorized record. The ledger stores the charged resref, expected
expiry, suppression state, and schema version in namespaced marshal data using only
supported primitive values.

Subsequent maintenance refreshes before the next genuine spellbook reset are free. This
avoids the waiting exploit in which five or forty real minutes make the caster weaker than
it would have been without the component. A rest is not inferred from elapsed time or a
party-only rest command: the ledger resets only when the actor actually receives an engine
spell-count refresh. The next successful ambient application consumes one newly available
copy.

The runtime must also prevent SCS's later sight-triggered prebuff batch from charging the
same already-active ambient spell a second time. Reimbursement is limited to a ledger-paid
spell while `instantprep` was initially 0, its exact manifest delivery effect being active,
and the observed adjacent SCS action pair: delivery action 181 followed by RemoveSpell 147
whose `m_specificID` is the same resolved spell number and whose availability delta is one.
Only the component's own debited record is restored, leaving one net copy spent. Free
`_PRECAST` blocks, non-adjacent/unknown shapes, genuine combat casts, and renewals are never
reimbursed.

### Maintenance and counterplay

The initial application occurs only after sprite initialization has settled. Maintenance
uses a cheap out-of-combat cadence and requires no party member to be visible. It never
refreshes in combat; SCS's normal renewal logic remains responsible there.

The ledger distinguishes natural expiry from early removal. A naturally expired managed
effect may be refreshed once conditions are safe. An effect that disappears materially
before its expected expiry, especially after combat or dispelling, is marked suppressed
until the next real spellbook reset. The component therefore cannot undo successful player
counterplay for free.

Save/load preserves the ambient ledger and expected expiry, preventing a second charge.
No EEex userdata, transient object ID, or contact state is saved.

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

- Component 120 requires recognized SCS/SR evidence; component 121 requires supported
  EEex/LuaJIT APIs and recognized SCS caster data. Missing prerequisites no-op with one
  clear diagnostic.
- EEex listeners register once through a root-level hot-reload-safe trampoline that looks
  up the current handler dynamically.
- Runtime callbacks retain no engine userdata between calls. Object IDs are re-resolved and
  validated and are never persisted across saves.
- Callback errors are contained at the outer boundary. The affected layer is disabled and
  one full traceback is logged; the engine is not subjected to repeated exceptions.
- Marshal state is versioned and uses integer `0/1` flags rather than unsupported boolean
  assumptions.
- Ambient application and slot debit are treated as a checked transaction. If both cannot
  be confirmed, that caster/spell stops maintenance; exact slot state is restored where
  safely possible. The system never loops, repeatedly charges, or silently maintains an
  unlimited buff after a bookkeeping failure.
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

Cover settled-load classification, grade/exclusion selection, first debit, free natural
refresh, early-removal suppression, save/load, real spellbook reset, duplicate SCS charge
prevention, external-AI retirement flags, hot reload, visibility/contact debounce, safe
and unsafe action queues, cast start, interruption, bounded retry, and rearming.

### Timing and engine-semantics spike

Before shipping 121, use a session-scoped probe on a throwaway save to measure:

1. first normal `See([PC])` / hostile contact to SCS's own prep and cast start;
2. contact detection to queued cast, cast start, and protection activation with 121;
3. exact memorized-record deltas for ambient debit and urgent normal casting; and
4. interruption, bait/re-engagement, neutral-to-hostile transition, already-casting, and
   dialogue/cutscene cases.

The spike must also prove the selected slot-debit/quick-list path and cosmetic-free ambient
delivery on the installed EEex version. The production game directory remains read-only
unless the user explicitly authorizes the transient probe in that conversation.

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
