# Compatibility audit: Rebalance, SR fork, and BuffBot

Date: 2026-10-08. Status: source-only audit; findings are pending implementation.

## Scope and evidence

Applied the shared BG compatibility policy: patch intended behavior, preserve
unrelated changes, and justify rejecting preconditions by semantics or safety,
not by the shape of a captured installation. Reviewed current locally available
release refs rather than assuming each primary checkout was current:

| Alias | Checkout inspected | Commit / local release tag |
| --- | --- | --- |
| `R` | `chriz-bg-rebalance` worktree `sr-antimagic-research` | `83e51d2727192ebeff5f7a470d58122cdba80735`, implementation at `v0.8.1` |
| `S` | `chriz-spell-revisions-patch` worktree `sr-lightning-release-20260916` | `c8494181c224d22002b5f4ee6fc4411235dd4a9f`, `v4.21-chriz.5` |
| `B` | `bg-eeex-buffbot` main checkout | `5adbe653ff125819f4b541cf2226a9808ceeeee9`, `v1.10.0` |

Paths and line numbers below were rechecked using `git show <commit>:<path>`
against those exact snapshots. Rebalance's `v0.8.1` tag resolves to
`09db97dc5cbd14f1b8bf7fe3af64f69bee313585`; only two handover documents differ
between that release and recorded commit `83e51d2`, not the cited source files.
The SR review focused on
our changes relative to upstream `v4.21`, not a general audit of upstream SR.
Rebalance's FoA source and tests were explicitly excluded: the lead is repairing
them separately. BuffBot review covered its installer and targeted runtime
validation/discovery paths, not every runtime behavior.

No network refresh, game access, implementation changes, or test execution was
performed. These are source-confirmed rejection paths for the concrete variants
described below, not reproduced reports naming a particular third-party mod.
This report does not establish universal compatibility or release acceptance.
Existing worktree changes were left untouched.

## Recommended first follow-ups

After the separately owned FoA repair: Bracers, Emotion, elemental arrows, then
RR migration and Tempus. Cloud resistance ownership needs a small explicit
balance decision. Each item needs a focused refactor and regression tests;
removing guards alone leaves algorithms that still assume the original layout.

### 1. SR Bracers (component 220): unrelated item/spell changes reject installation

**Source:** `R/chriz-bg-rebalance/lib/sr_bracers.tpa:244-246` requires BRAC16 to
have exactly one ability, zero equipment effects, one charge, and specific
targeting. Lines 148-150 require the Improved Haste donor to have one ability
and no casting effects. Lines 171-206 restrict its effects to a fixed opcode
list, targeting/probability, and 60-second timed payload; opcode 326 permits
only named Tempus helpers at lines 191-196.

**Concrete valid variant:** a passive equipment bonus added to BRAC16, with its
existing Haste activation unchanged, fails the zero-equipment-effect check.
An ancillary casting feature on otherwise unchanged Improved Haste also fails.
Neither change inherently makes the intended Haste activation ambiguous.

**Refactor:** locate and replace the Haste activation while retaining other
abilities and equipment effects. Build its private helper from the relevant
effective semantics, distinguishing payload from ancillary effects. Preserve
casting hooks with their correct delivery semantics rather than dropping them.

**Tests:** passive bonus; unrelated extra activation; reordered effects; donor
casting features; multiple donor level headers; changed donor durations; retained
unrelated data and idempotence. Keep rejection of a vanilla double-APR donor
where this explicitly SR-specific component cannot fulfill its promised result.

### 2. Emotion no-stacking (301): unrelated casting time/range is required

**Source:** `R/chriz-bg-rebalance/lib/emotion_hope_courage.tpa:201-214`
requires beneficial spells to be level 4 with one ability, school 4, target 4,
range 50, and casting time 4.

**Concrete valid variant:** Hope or Courage with casting time changed from 4 to
3 still has the same identifiable no-stacking target, but fails with
`CBR_EM_ERR_BENEFICIAL_PARTITION`. A range-only change similarly fails.

**Refactor:** retain unrelated header fields and handle each relevant ability.
Validate the behavior being transformed rather than authenticating the whole
original header. Targeting changes that alter delivery require real analysis;
casting time alone does not.

**Tests:** changed casting time, range, and school; multiple level headers;
reordered effects; preservation, repeat application, and rollback.

### 3. Elemental arrows (130): unrelated damage counts as incompatible

**Source:** `R/chriz-bg-rebalance/lib/elemental_arrows.tpa:38-57` requires
every ability to be a projectile ability, every opcode 12 record to use the
expected element and victim target, and exactly one damage record per ability.

**Concrete valid variant:** an extra acid-damage rider on a fire arrow rejects
the component even though its existing fire damage remains identifiable.
An unrelated additional item ability also fails.

**Refactor:** select the intended elemental on-hit package and retain unrelated
damage/abilities. Define how multiple same-element packets represent the total
before supporting them: setting every packet to 1d2 would accidentally multiply
damage. Keep actual ambiguity and invalid-slice checks.

**Tests:** unrelated damage type, unrelated ability, split intended damage,
reordered records, preserved saves/helpers, and unchanged foreign damage.

### 4. RR/SR adapter: captured spell-copy and script-token counts are mandatory

**Source:** `S/live-patch/SRCB_RR_COMPAT/lib/rr_spell_semantics.tpa:142-164`
accepts only original or already-migrated CREs with the configured exact number
of prepared copies. Calls at lines 361, 382, and 396 use 6, 4, and 2 for
particular RR creatures; lines 368 and 389 require zero for two others.
Lines 214-220 require exact script symbol counts; calls at lines
375, 403, and 407 specify 17, 13, and 12.

**Concrete valid variant:** a creature retaining the same broken Chaos mapping
but one fewer prepared copy fails migration. An otherwise equivalent RR casting
script with an extra affected branch fails solely because its token count is
different.

**Refactor:** migrate the actual affected prepared records, retaining flags,
existing slot budgets, and unrelated known spells. Identify RR's affected
script behavior rather than validating total token counts. Do not blindly
rename genuinely intentional Waves-of-Fatigue additions: mixed old/new
semantics need an explicit classification, not a broader text replacement.

**Tests:** varying prepared-copy counts; already-migrated and mixed records;
extra unrelated script blocks; additional recognized casting branches;
preserved memorization flags and level slot budgets; honest ambiguous cases.

### 5. Tempus helpers: source layout and cosmetic counts remain fixed

**Sources:**

- `R/chriz-bg-rebalance/lib/tempus_weapon_training.tpa:211-220` requires
  C0PR#C4 to have one ability, no casting effects, and ability effect index zero.
- `R/chriz-bg-rebalance/lib/tempus_chaos_tides.tpa:125-148` requires the donor
  to start with opcode 321, permits a small opcode list, and insists on exact
  icon/pulse counts plus one or two visual records.
- `R/chriz-bg-rebalance/lib/tempus_holy_power.tpa:575-619` validates a
  50-level/reference-row CLAB arrangement and particular unrelated cells before
  applying the Holy Power change.

**Concrete valid variants:** an indexed casting-feature prefix before otherwise
unchanged proficiency grants fails the first check; a third opcode 215 visual
or an added marker outside the allowed opcode set on the Chaos donor fails the
second. An unrelated grant in a constrained
CLAB cell can reject a change that should own only Holy Power grants.

**Refactor:** separate these into small tasks. Traverse the indexed effect
slices and preserve ancillary records. Locate the owned CLAB grants by meaning.
For Chaos, redesign the rebuild to carry unowned effects before relaxing its
input checks; the current rebuild does not preserve arbitrary records safely.

**Tests:** casting-first layout; extra harmless visual/marker; different effect
order; additional level header; alternate CLAB row placement and width;
preserved unrelated grants; idempotence and undo.

### 6. Cloud forms (320): previous resistance percentages are fingerprints

**Source:** `R/chriz-bg-rebalance/lib/cloud_forms.tpa:74-75` permits only
100 or 75 for direct physical resistance. Lines 106-108 require every GASFORM4
donor resistance byte to equal 100.

**Concrete valid variant:** an already partly nerfed, identifiable combat cloud
with 80% physical resistance, or a donor whose elemental resistance was adjusted,
fails despite the same transformation identity.

**Decision/refactor:** state whether this component caps defenses at 75 or
authoritatively sets owned defenses to 75. Do not silently strengthen an
already-50% form. Once ownership is explicit, remove old-value fingerprints and
preserve unrelated form data. Additional invulnerability mechanisms remain real
obstacles: leaving them active must not be reported as a successful damageable
cloud transformation.

**Tests:** already-reduced values, partial prior application, unrelated effects,
retained poison/escape behavior, real extra immunity, and private donor ownership.

### 7. SR classic Lightning Bolt: unrelated damage packets are rejected

**Source:** `S/spell_rev/lib/classic_lightning_bolt.tpa:54-82` counts every
opcode 12 record, requires each to be the precise electrical delivery, then
expects two SR packets. The tail option has the matching library under
`live-patch/SRCB_CLASSIC_LIGHTNING/lib/`.

**Concrete valid variant:** adding a non-electrical damage rider to the otherwise
unchanged unsaved/saved electrical pair fails the classic-bolt transformation.

**Refactor:** identify that electrical pair semantically and preserve unrelated
damage. Keep genuine ambiguity checks when several indistinguishable electrical
pairs exist. Existing tests preserve foreign non-damage records but deliberately
reject extra damage, so the tests need to distinguish these cases too.

**Tests:** non-electrical rider; reordered saved/unsaved packets; preserved later
save penalties and casting hooks; multiple ambiguous pairs; repeat application.

## Checks not condemned by this audit

- Native executable-hook signatures, bounds/index checks, genuine missing
  capabilities, helper namespace collisions, and unsafe parallel MR writers are
  not equivalent to reference-install fingerprints. Keep them where justified.
- Hardiness and Spellstrike contain additional effect-count/delivery checks
  worth a focused follow-up. This audit did not establish that every such
  restriction is wrong; multiple effects can change the intended semantics.
- BuffBot showed no confirmed FoA-like gameplay-layout blocker in this bounded
  review. `B/buffbot/setup-buffbot.tp2:40-99` requires exact INI text to detect
  active LuaJIT; lines 237-250 require `[General]` to be the first section before
  changing the loader configuration. Compare that with InfinityLoader's actual parser
  before calling these restrictions defective. EEex capability, mixed-loader,
  and owned-item restoration guards have concrete safety purposes.

The correct outcome is behavior-aware matching plus variation tests, not mass
deletion of `PATCH_FAIL` or an unsupported promise that every mod combination
will install.
