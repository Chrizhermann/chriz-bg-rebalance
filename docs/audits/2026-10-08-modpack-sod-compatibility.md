# Modpack and SoD compatibility-gate audit — 2026-10-08

Status: source-only findings and follow-up work. No fixes are implemented by this
report, and no installer or live-game compatibility result is claimed.

This is central tracking in `chriz-bg-rebalance`; implementation belongs in the
owning `chriz-bg-modpack` or `chriz-sod-rebalance` repository. The separately
handled Flail of Ages work is outside this report.

## Source selection and evidence limits

The audit read current global/project guidance, the shared `bg-modding` skill,
its mandatory `references/compatibility-policy.md`, and relevant CRE/SPL
references. Worktree lists, local logs, cached refs, and status were checked
before choosing source. No fetch or other network operation was performed.

Path aliases below are exact audit roots; a location such as `M/chriz-bg-modpack/...`
means that relative path under the corresponding absolute root.

| Alias | Absolute source root | Source reviewed |
| --- | --- | --- |
| M | `C:\Users\chris\.codex\worktrees\modpack-release-alpha6\chriz-bg-modpack` | Clean `codex/baeloth-known-spells`, HEAD `17233ea76d1c7cfed7d952a293186f988caf7404`, alpha.10 preparation. Cached `public/main` is `210472d98cb0a66fc2003af886ce545af11e8d56`; `git diff HEAD public/main` was empty, so the audited content matches that newer ref. |
| S | `C:\Users\chris\.codex\worktrees\avernus-finale\chriz-sod-rebalance` | `codex/avernus-finale`, HEAD and cached `origin/master` `b2af8328a9c78dfa7ff2fd71f73f2c0ea6738544`, v0.6.12 source; separately inspected uncommitted component 285 work. |
| E | `C:\Users\chris\.codex\worktrees\early-sod-companions\chriz-sod-rebalance` | `codex/early-sod-companions`, HEAD `b2af8328a9c78dfa7ff2fd71f73f2c0ea6738544`; separately inspected uncommitted components 177/198 and the potion-cleanup change. |

The original named checkouts were older: Modpack at `ebdb7424d4155335c2029146c5f29c8693c93bc0`
and SoD at `115e23cf95c3eba5f4ddb5adf40ac8db52147706`. They were not treated as
the newest release source. Modpack's alpha.7 NPC-preset and indexed-dispel-layout
repairs are already present in M. The SoD files cited as committed findings had
no differences from `b2af832` in the inspected newer worktrees.

Evidence consists of source traces, branch/content comparison, and reading
related regression fixtures. The counterexamples below are derived inputs to
exercise, not cases reproduced during this audit. No tests were run, no game
resources were changed, and no mod source was edited. This is a bounded audit,
not a line-by-line certification or a complete compatibility matrix.

## Prioritized remediation tasks

Priority denotes the consequence of the identified path: P1 can silently produce
the wrong behavior; P2 unnecessarily rejects a plausible valid installation.
Every item remains open.

### 1. P1 — Resolve jailbreak buff spells by installed identity

- **Location:** `S/chriz-sod-remix/lib/comp170.tpa:430`, `:445`; consumers at
  `S/chriz-sod-remix/baf/jb116.baf:58`, `:59`, `:60`.
- **Condition:** `csr_find_spell` searches two fixed spell slots using English
  display-name fragments. It initializes the result to the first, SR-era slot
  and returns that fallback when neither candidate's name matches.
- **Plausible valid variant:** non-English spell names on a non-SR installation,
  or a compatible relocation outside those two candidates.
- **Consequence:** the injected script casts the fallback slot's occupant as
  PfMW, Stoneskin, or Luck without establishing that identity. This can silently
  change the encounter instead of rejecting an unresolved spell.
- **Remediation:** resolve `SPELL.IDS` symbols for the intended spells and
  validate their resulting resources. Diagnose missing/unresolved identity;
  never substitute a reference-install slot merely because name matching failed.
- **Acceptance tasks:** SR and non-SR symbol mappings; translated and changed
  display names; a third relocated slot; missing identity; inspection of the
  compiled intended cast resrefs and unchanged unrelated script actions.

### 2. P2 — Remove Aura's install-assigned strref and timer census from ending preflight

- **Location:** `S/chriz-sod-remix/lib/comp290.tpa:559` through `:563`; the exact
  timer count is used again in the mutation at `:622`.
- **Condition:** preflight requires `DisplayStringHead("C0Aura",309305)`, zero or
  one Aura block, and exactly `17 + aura_count` setters of the victory timer.
- **Plausible valid variant:** the same Aura bark gets another TLK index due to
  install order; another companion mod adds a legitimate victory-timer block.
- **Consequence:** component 290 aborts despite an unchanged victory handoff.
- **Remediation:** identify relevant victory blocks and timer convergence by
  their actions/guards. Preserve arbitrary bark strrefs and unrelated actions;
  transform the intended timer uses without treating the observed census as
  the definition of the supported scene. Update both preflight and mutation.
- **Acceptance tasks:** shifted Aura strref, no Aura, another companion block,
  unrelated timers/actions, repeat application, and retained EET/standalone
  handoff invariants. Do not relax the banking or recovery checks.

### 3. P2 — Replace exact actor-coordinate censuses with bounded encounter matching

- **Locations:** `S/chriz-sod-remix/lib/comp200.tpa:23` through `:50`;
  `comp240.tpa:93`; `comp260.tpa:66`; `comp270.tpa:45`, all under the same lib
  directory. Components 240/260 also apply the pattern to additional areas.
- **Condition:** the cut list is keyed by exact `CRE@x@y`, followed by an exact
  number-of-matches requirement.
- **Plausible valid variant:** a previous mod moves an intended west-group
  spider a few pixels or has already removed one intended cut actor.
- **Consequence:** an otherwise applicable encounter component aborts and its
  associated edits/XP delivery cannot install.
- **Remediation:** define the intended encounter group using identities and
  bounded spatial/context information; distinguish already-removed actors from
  unresolved replacement actors. Keep the east spider group, quest actors, and
  third-party additions outside the cut. Preserve consistency between actual
  content changes and the agreed XP ledger.
- **Acceptance tasks:** moved and already-removed targets, unrelated additions,
  overlapping nearby groups, actual ambiguity, repeat application, and ledger
  consistency. Removing the count assertion alone is not sufficient.

### 4. P2 — Stop treating unique actors' and containers' coordinates as identity

- **Locations:** `S/chriz-sod-remix/lib/comp197.tpa:215` and `:221`;
  `S/chriz-sod-remix/lib/comp265.tpa:100`.
- **Condition:** the placed BDSKIE actor must have `x=1605`; the uniquely named
  `Dead_fighter` container must remain at `(4295,1098)`.
- **Plausible valid variant:** an area mod repositions the same actor or loot
  container while preserving its identity and role.
- **Consequence:** Skie's placement handling or the quest-loot repair aborts
  for an irrelevant positional change.
- **Remediation:** bind the intended object by identity and scene context,
  retaining uniqueness and actual ambiguity checks. Treat position as supporting
  evidence where needed, not an unconditional equality requirement.
- **Acceptance tasks:** moved target, real duplicate identities, preserved
  foreign container contents/flags/charges, unchanged unrelated actors, and
  repeat application.

### 5. P2 — Handle transformation repairs per ability instead of requiring one match per spell

- **Locations:** `M/chriz-bg-modpack/lib/cbm_ascension_slayer_eefp_fix.tpa:42`
  and `:75`; `M/chriz-bg-modpack/lib/cbm_scs_shapechange_eefp_fix.tpa:42`
  through `:44`, plus `:96`.
- **Condition:** Slayer requires exactly one old/corrected transformation link
  across all abilities. Shapechange requires one SPINHUMR/opcode-111 pair across
  the whole spell and one revert-removal effect.
- **Plausible valid variant:** two caster-level abilities each implement the
  same intended transformation behavior, with different level requirements or
  otherwise preserved parameters.
- **Consequence:** components 440/450 reject that spell even when every relevant
  ability can be interpreted and repaired independently.
- **Remediation:** inspect each relevant ability's behavior and preserve its
  effect parameters. Support multiple independent applicable abilities, shared
  effect slices where safe, and a mix of old/already-correct links. Distinguish
  genuinely ambiguous duplicate behavior within an ability from valid tiers.
- **Acceptance tasks:** two or more abilities; reordered unrelated effects;
  shared slices; mixed old/new links; unchanged foreign effects; repeat
  application and uninstall restoration. Revisit the overly broad ambiguity
  expectations in `M/tests/test_spell_tail.py:1013` when adding those fixtures.

### 6. P2 — Remove remaining dispel delivery/scaling fingerprints

- **Locations:** `M/chriz-bg-modpack/lib/cbm_yeslick_keldorn_dispel_fix.tpa:77`,
  `:81`, `:115`.
- **Condition:** every ability must contain exactly one direct opcode 58.
  Keldorn additionally requires positive fixed-level mode `(flags BAND 3)=2`,
  even though that branch only changes the projectile and promises to preserve
  the installed scaling.
- **Plausible valid variant:** caster-level dispel semantics, a conditional pair
  of dispel effects, or behavior delivered through a linked resource.
- **Consequence:** component 410 rejects alternate semantic implementations
  despite its now-flexible physical effect-table handling.
- **Remediation:** recognize the intended delivery and scaling behavior first;
  change only the owned projectile/scaling fields. For linked resources,
  establish sharing and clone/retarget when needed. Do not simply remove the
  assertion and rewrite every opcode 58.
- **Acceptance tasks:** native caster-level scaling; conditional multi-effect
  behavior; linked delivery; unrelated effects and shared subspells; existing
  displaced-table/casting-slice regressions; repeat application and rollback.

### 7. P2 — Support both valid CRE embedded-effect formats in Sarah's preset

- **Location:** `M/chriz-bg-modpack/lib/cbm_sarah_archer.tpa:19`.
- **Condition:** embedded effect version 0 is rejected. Sarah's bounds and
  postcondition loops also hardcode the `0x108` version-1 stride.
- **Plausible valid variant:** the same Sarah template serialized using the
  supported 48-byte embedded-effect format.
- **Consequence:** the authored Archer/proficiency preset cannot apply, although
  the shared `cbm_npc_clear_proficiencies` helper already supports both formats
  (`M/chriz-bg-modpack/lib/cbm_npc_build_helpers.tpa:9`).
- **Remediation:** make preflight and postcondition parsing format-aware, keeping
  signature/bounds checks and complete owned proficiency replacement.
- **Acceptance tasks:** both effect formats; absent/duplicate/increment-mode
  proficiency records; preserved foreign effects and stats 109/110; stable
  second application. Existing Sarah fixture construction starts with format 1
  (`M/tests/test_sarah_options.py:56`).

### 8. P2 — Replace English dialogue-text gates with mechanical scene anchors

- **Committed location:** `S/chriz-sod-remix/lib/comp180.tpa:53` requires
  “Waterdeep and Daggerford” in the SAY text.
- **Uncommitted location:** `E/chriz-sod-remix/lib/comp177.tpa:15` through `:17`
  requires “glad to see you well” and “Leave through the main doors”. Component
  177 is working source, not a finding attributed to v0.6.12.
- **Plausible valid variant:** translated or reworded SAY text with unchanged
  triggers, destinations, and actions.
- **Consequence:** mechanically valid council/report scenes abort installation.
- **Remediation:** identify the scene using stable mechanical context and
  validate the actual transition being changed, preserving other replies and
  actions. Text may support diagnosis but must not be the universal gate.
- **Acceptance tasks:** translated/reworded text, additional unrelated replies,
  and a genuinely wrong state/transition target that still fails explicitly.

### 9. P2 — Preserve already-working positive weapon charges in Branwen's repair

- **Location:** `M/chriz-bg-modpack/lib/cbm_branwen_hammer_fix.tpa:28`.
- **Condition:** every ability opcode-111 effect must have charge count zero or
  one; another positive value sets a flag that aborts the component.
- **Plausible valid variant:** an earlier mod intentionally assigns two charges
  to the hammer or another created-weapon effect.
- **Consequence:** component 400 aborts instead of repairing only the broken
  zero-charge delivery and preserving an already-working effect.
- **Remediation:** identify the intended hammer creation, repair zero charges
  where required, and preserve positive counts that already satisfy the intended
  on-hit behavior. Do not globally normalize unrelated opcode-111 effects.
- **Acceptance tasks:** zero/one/two charges, unrelated weapon-creation effects,
  preserved casting hooks, repeat application, and bounded engine acceptance of
  the resulting delivery when a later playtest is authorized.

## Legitimate checks to retain

- Resource signatures, truncated-file detection, table bounds/indexes, genuine
  overlaps, and numeric field-capacity checks.
- Actual required mod/platform resources and capabilities, including runtime
  APIs and native-hook byte/ABI validation. The unidentified-artwork hook checks
  are memory-safety requirements, not arbitrary resource fingerprints.
- Genuine ambiguity in unique bank/container/scene targets and safeguards for
  EET inventory transfer, backups, install history, and recovery.
- Owned configuration schema and algorithm-specific invariants that have a
  concrete semantic justification.
- Explicit diagnosis and rollback when the promised transformation cannot be
  established. No item above recommends silent skipping or blanket opcode edits.

## Coverage and follow-up boundary

Checked installer entrypoints and searched production TPA libraries for rejecting
conditions; traced the listed candidates through their transformations; read
related Modpack fixture tests; scanned Modpack runtime guards; inspected SoD's
285 and 177/198 work in progress. Research data, upstream third-party mod code,
live game resources, and saves were not audited.

Viconia's fixed progression-table dimensions and seven-row priest-memorization
requirement were identified for a separate format-grounded investigation. Their
individual invariants are not asserted as defects here without establishing
which alternate layouts the engine and intended conversion support.

Completion of this report establishes follow-up tracking only. Each remediation
requires implementation and variation tests in its owning repository, followed
by an explicit statement of remaining untested compatibility and live behavior.
