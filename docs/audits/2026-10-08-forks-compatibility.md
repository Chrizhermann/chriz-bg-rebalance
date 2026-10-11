# Fork compatibility audit — 2026-10-08

Source-only audit following the user's mandatory compatibility rule: patch the
intended behavior, not the exact shape of a reference installation. This report
records follow-up work owned by the individual fork repositories; it does not
move their implementation into `chriz-bg-rebalance`.

No game files were accessed or changed. No installs, automated tests, Git/network
mutations, or implementation changes were performed for this audit. The examples
below are source-proven rejecting branches with plausible valid input variants,
not newly reproduced installation or runtime failures.

## Source snapshots and coverage

| Repository | Inspected checkout/ref | Coverage |
| --- | --- | --- |
| Artisan's Kitpack fork | `C:\src\private\The-Artisan-s-Kitpack-Chriz-Balance-Patch`, HEAD `0798dc4`, release `v4.81a-dev.85928f9-chriz.1` | Our additions and rejection paths, particularly Fighter Modals retrofit, Called Shot, and shifted dialogue; not an exhaustive upstream audit. |
| Bardic Wonders fork | `C:\src\private\Bardic-Wonders-Chriz-Balance-Patch\.worktrees\bardic-progression-release-20260920`, HEAD `7db9861`, release `v2.9c-balance.6` | Finite Abettor HLA integration, standalone tail, producer/caller relationship, relevant existing tests, and progression adapter prerequisites. |
| Aura fork | `C:\src\private\Aura_BG1_BG2_EET-Chriz-Balance-Patch`, HEAD `5f8ca3c` | Recent fork balance changes in `aura_items.tpa`, `aura_bg2.tpa`, and associated history. Existing uncommitted item-use changes were preserved. No release tag was identified in the local tag listing. |
| Item Randomiser fork | `C:\src\private\bgee-itemrandomiser-fix`, HEAD `f4a9dfb`, release `v8.1.1` | Removal-plan, source multiplicity, and precondition checks. Experimental worktrees were located and screened, not exhaustively audited. |

Bardic's root checkout was older (`546dd09`) and dirty, so findings use the clean
release worktree above. Item Randomiser also has experimental worktrees at
`C:\Users\chris\.codex\worktrees\mode1-postinstall-profiles\bgee-itemrandomiser-fix`
(`39b665b`, `codex/mode1-postinstall-profiles`) and
`C:\src\private\bgee-itemrandomiser-fix\.claude\worktrees\randomizer-improvements-expansion-1a3ef3`
(`1151182`, `claude/randomizer-improvements-expansion-1a3ef3`). No claim of complete
coverage of their native-hook prototypes is made. Local refs were inspected;
remote release freshness was not checked.

Line references below are relative to the corresponding inspected checkout.

## Finding 1 — Abettor payload metadata can disable Symphony

Priority: follow-up refactor. Affects the normal finite-song integration and its
standalone repair; the normal integration skips the HLA rather than necessarily
aborting the complete installation.

### Evidence and impact

- `BardicWonders/lib/bardsongtweaks.tpa:118` clones the **existing** song resource
  into a dynamically named payload. It is not necessarily an untouched bundled
  fixture: another component installed between the kit and song tweak may have
  modified it.
- `BardicWonders/lib/abettor_hla_finite.tpa:835-877` subsequently requires exactly
  one ability, zero casting effects, an empty ability icon, particular range and
  dice metadata, `first_effect = 0`, and other fixed header values.
- A nonempty ability icon alone fails that predicate although it does not change
  the payload's finite-song behavior. Additional casting effects or level-specific
  abilities are further variants that need semantic handling rather than blanket
  rejection.
- The library removes the Symphony HLA row before validation (`:774`) and warns
  that it is skipping Symphony when the validation fails (`:1131`). Thus unrelated
  payload metadata can silently cost the user a promised ability apart from the
  install warning.
- The standalone tail repeats the layout restrictions in
  `live-patch/abettor-hla/abettor-hla-rebalance/lib/patch.tpa:667-709`; its aggregate
  rejection at `:1517` aborts that repair component.

### Correct fix and safeguards

Validate the delivery, recipient, and timing semantics actually required by the
opening/finale additions. Stop using unrelated payload presentation metadata as
an identity check. Iterate applicable abilities and indexed effect slices,
preserving casting effects and foreign records. Support valid additional
abilities instead of changing the count guard alone.

Keep checks for invalid bounds, wrong delivery semantics, conflicting controllers,
and reserved-resource collisions. Some nearby validators inspect templates freshly
copied by the same component; those internal producer checks are not automatically
cross-mod compatibility defects. Do not delete every exact check in this file.

### Focused tests

Extend the existing synthetic WeiDU suite under `tests/abettor_hla/` with:

- an otherwise identical payload with a changed/nonempty ability icon;
- an unrelated casting effect that shifts the first ability-effect index;
- an additional valid level-specific ability;
- preservation of foreign records, finite timing, and one intended opening/finale
  pair per relevant controller ability;
- byte-exact standalone-tail undo, plus existing malformed and conflicting-input
  negative cases.

Keep producer-output checks, but supplement them with variations of the cloned
input. Existing tests do not by themselves establish support for these variants.

## Finding 2 — Fighter Modals retrofit rejects values/layout/text unnecessarily

Priority: follow-up refactor. This is the optional standalone retrofit for an
existing game, **not** the normal fresh-install Fighter component. Fresh installs
already contain the requested 2/4 tradeoffs, so this finding is not evidence of
another default CEBG installation blocker.

### Evidence and impact

File: `live-patch/AKCB_FIGHTER_MODALS/setup-AKCB_FIGHTER_MODALS.tp2`.

- `:21` rejects any ability count other than one, reporting invalid SPL offsets
  even if the offsets and extra ability are valid.
- `:71-78` permits only the fixed old/new values and exactly one matching stat
  effect. Other legitimate changes can therefore abort the component.
- `:193-223` ties mechanical success to specific English sentence patterns.
  Translation or harmless prose reformatting can roll back an otherwise valid
  gameplay transformation.
- `tests/test_fighter_modals.py:219-250` explicitly tests the existing rejection
  policy, including changed values, duplicate stats, and unsupported wording.
  Those expectations need to be reconsidered with the implementation; green
  tests currently confirm narrowness rather than compatibility.

### Correct fix and safeguards

Define the owned 2/4 tradeoff behavior and match the relevant modal effects across
abilities while preserving unrelated changes. Distinguish relevant grouped stat
effects from foreign effects. A duplicate contributing stat really can be
ambiguous: removing its guard without changing the transformation could multiply
the intended bonus or penalty. Handle the group explicitly or identify the
concrete ambiguity to the user.

Separate description handling from mechanical identity. Update recognizable owned
text accurately, preserve other prose, and disclose any unhandled description
variation rather than treating English wording as proof of valid mechanics.
Keep format/bounds checks and honest rollback on genuinely unsafe transforms.

### Focused tests

- additional valid ability and reordered effect records;
- unrelated effects with preserved bytes/semantics;
- translated and reformatted descriptions;
- already-correct data and a second application;
- multiple relevant stat records with an explicit intended result, or a genuine
  semantic-ambiguity failure;
- byte-exact uninstall and malformed-input rollback.

## Checks that should not be removed wholesale

### Item Randomiser

`lib/removal_plan.tpa:1736-1754` rechecks size/hash against a plan captured from the
**same installation during that operation**, not a development fixture. It guards
against editing stale locations after the resource changed. Retain this protection.

The source multiplicity logic at `:1059-1101` and `:1492-1508` distinguishes a
single source from an explicit `all_one_unit` duplicate-removal policy. These
checks protect item accounting: blindly relaxing counts could remove independent
items or emit the wrong number. Further compatibility cases need an intentional
source-selection/accounting rule, not guard deletion. No concrete unnecessary
fixture gate was established in these paths during this bounded audit.

### Artisan shifted dialogue

`ArtisansKitpack/lib/shifted_dialogue.tpa` scopes removal to the intended equipped,
self-targeted Talk restriction and preserves other records. The scan did not find
the FoA-style exact-count requirement in this implementation.

### Aura

No comparable fixture-derived rejection was identified in the inspected recent
balance changes. This is limited negative evidence, not a general compatibility
certification. Existing dirty edits were neither changed nor interpreted as
released fixes.

## Next ownership

Fix Finding 1 in the Bardic fork and Finding 2 in the Artisan fork, with their
existing focused test harnesses. Keep FoA's implementation/release work separate.
Do not represent this report as completion of those follow-up refactors or as a
full audit of every upstream subsystem.
