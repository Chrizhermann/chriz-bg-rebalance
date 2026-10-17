# Potion uniqueness — diagnosis and implementation contract

October 9, 2026. Local work starts from released BG Rebalance `v0.8.1`,
commit `09db97dc5cbd14f1b8bf7fe3af64f69bee313585`, in the isolated
`codex/potion-uniqueness-20261009` worktree. The older primary checkout and
Time Stop/Haste work are deferred and remain separate.

**Current status: replacement admission prototype implemented locally.** Native review rejected the private-SPL
implementation described below. It is retained only under
`research/prototypes/potion-uniqueness/`, outside the normal installer and package.
330/331 are research fixture identifiers, not delivered components. Resource
preservation/model checks do not establish preservation of engine-created fields.
The replacement [original-effect prototype](prototypes/potion-admission/README.md)
has bounded offline validation. It does not yet establish a general, installable
potion component or native acceptance. See the
[handover](../docs/handovers/2026-10-09-potion-uniqueness.md) for verification,
retained failures and the remaining test boundary.

## Settled behavior and owned fields

Two mutually exclusive choices are required: unique temporary bonuses per potion
type, or the same with actual Potions of Genius retaining their normal stacking.
Different potion types remain distinct even when they affect the same statistic.
Native rules may already prevent particular overlaps; this component must not
force them. Equivalent SCS/mod copies belong to their originating potion family.
Names, English descriptions and a shared stat opcode are not sufficient identity.

Christopher explicitly selected the HP-safe exception on October 9: **an extra
dose's bonuses are ignored until the existing HP-changing potion expires; other
safe potion types refresh**. A dose is still consumed normally. There is no
new heal, subtraction, duration extension or removal of the existing HP package.
This includes Heroism/Power and semantically equivalent HP packages such as Item
Revisions Fortitude. Both variants use this rule.

Owned behavior is only repeat application of the same temporary potion bonus.
Preserve charges, ability targets, native values/durations, probability/saves/MR,
instant healing/cures, permanent gains, adverse effects, quest behavior and
unrelated records. Spells, equipment and kit effects do not enter a shared
per-stat cap. Existing correctly non-stacking deliveries require recognition,
not automatic removal of their protections.

The implementation must retain real format/bounds and ambiguity checks while
accepting normal reordered/additional effects, multiple abilities, SR/non-SR,
and supported linked payloads. Any private child identity needs explicit handling
of original source protections/removals; cloning alone does not preserve them.

## Why remove-and-recast is unsafe for HP

Offline inspection used BG2:EE 2.7.3.0, executable SHA256
`b51093a49140b2b8a7c046b4652bb8e535be24ebbc12b1d735e0b94217a14d57`,
with EEex 1.3.0 function labels. No engine process was launched.

EEex's local `EEex.tp2:3` declares `v1.3.0`. SHA256 inputs:
`function_names.db` = `c5e957b9f63b1a945ccc837b827bad37f209f99412d791d4a749503fc6c25823`;
`EEex_Opcode_Patch.lua` = `d82cb2fec583b953ce46ca459b0693da4b2430ca9c6ed55f153eac926de5a9e4`;
`EEex_Projectile_Patch.lua` = `a763130cd02dc293d5ad4cc053573361eedb1a6485555748e4cbe7ffe1ece651`.
These identify the inspected inputs; no claim about every newer binary follows.

| Native location (RVA) | Observation |
|---|---|
| `1B5600` | `CGameEffectHitPoints::ApplyEffect` |
| `1B58FC–1B5929` | Percentage mode adds `(parameter1-100) * base maximum / 100` to rebuilt maximum HP |
| `1B593F–1B5971` | Initial processing may add the increase over previous derived maximum to current HP |
| `1E6C20`, especially `1E6C26–1E6C66` | `OnRemove` can clamp current HP; it does not use special bit 0 to suppress this |
| `1E7766–1E776F` | Opcode321 calls removal handlers immediately |

Four offline Unicorn assertions executed these functions against synthetic actor
memory. With base maximum100 and current80/110, a modeled removal/reapplication
order ended at **90/110** after the next rebuild: potency was unique but wounds
were healed. With the maximum rebuilt downward before removal, suppressing the
replacement's initial HP update instead left **100/110** from an original110HP.
These are function-level counterexamples to an unconditional safety claim, not
complete item-use or live-engine acceptance tests.

[IESDP opcode18](https://gibberlings3.github.io/iesdp/opcodes/bgee.htm#op18)
documents current-HP updates and the processed special bit. Mode6 is not a
per-potion grouping mechanism and would alter other HP-source interactions.
The apparent EFF non-stacking flag from TobEx is also unsuitable: EE's save-type
bit25 has different semantics.

Additional inspection of the same executable rules out a generic direct-effect
to timed-op177 conversion. At `1A6D25` op177 creates a fresh child; saved Special
is restored only when FirstCall is zero (`1A6D9F–1A6DB7`). Op18 uses Special bit0
and its separate runtime field at `+158`, without clearing FirstCall. Three more
bounded native assertions showed additive HP being granted again on a second
stat build, while percentage HP did not regrant on an unchanged build but could
regrant after another maximum-HP change. Existing op177 deliveries must retain
their native structure; this is not a safe new carrier for arbitrary HP effects.

CON also needs HP review: `CGameSprite::CheckStatsChange` (`34EAF5–34EC9D`)
calculates the CON HP bonus and applies its change to current and maximum HP.
An intervening CON loss can even reach the death path at `34EB9E`. Leaving an
already non-accumulating flat CON setter native avoids introducing that removal
step; cumulative CON bonuses need the HP-safe repeat policy.

Regeneration98 modes2/3 have a different lifecycle. `1BEC50–1BEE02` creates a
persistent regeneration record, and `1A5CA0` schedules native healing17 later.
No immediate HP grant was found in ApplyEffect or finite OnAddSpecific. Native
POTN42 uses mode3; IR/IRR use mode2. Refresh may reset the next tick's phase;
persistent-list cleanup, replacement ordering and save/load still need gameplay
acceptance. Modes0/1 require their own review.

Private SPL helpers are not identity-neutral: `CSpell::GetAbilityEffect` writes
the helper's resource and sourceType1 at `24EEEA–24EF20`; admission checks inspect
that identity at `1CC90B–1CC93D`. Original source-specific wards and removals need
explicit preservation or a concrete diagnostic. New delivery/guard opcodes also
add admission checks. A read-only scan of the inspected default override found
no immunity to146/321, but did find immunity to177 on several resources and a
brief immunity to206 in SPWI525. That observed collision informs the guard
design; it is not a universal assertion about other mod combinations.

## Native counterexamples that block the draft

All addresses below use the same pinned BG2EE executable and EEex labels above.
These are substantive compatibility failures, not requests for extra live tests
to certify an otherwise complete implementation.

| Invariant | Native evidence and failure |
|---|---|
| Original dispel level | `CItem::GetAbilityEffect` writes effect `+C8=10` at `1FB517`. `CSpell::GetAbilityEffect` calls actor `GetCasterLevel` at `24EF83`, then writes the result at `24EF8B`. Moving an item effect into a private SPL changes this field. Dispel reads it at `1B1FFD/1B20BD` and scales removal chance at `1B2005–1B2026`. |
| A genuine level override | Op146 mode2 passes parameter1 to ability-header selection (`1E4690–1E46C8`); its constructor independently receives the target actor (`1E4740–1E474B`). Full `1E4570–1E4C3E` inspection found no temporary actor-level override or later `+C8` rewrite. Mode1's message passes no fixed-level override (`212E51–212E84`). SPL types0/4/5 use class level (`39CDB5–39CDE9`). Setting parameter1 to10 is not a proven fix. |
| Original duration scaling | `CGameAIBase::FireSpell` selects op99 scaling by mage/priest/song SPL type at `16ACA5–16ACF7` and multiplies duration at `16B02B–16B044`. The draft's innate helpers suppress that original scaling. Changing to op146 mode2 also changes this path. |
| Removal of HP guards | The draft emits undispellable318 guards even when the original HP bonuses are dispellable. A successful dispel can leave a guard that rejects another dose after the bonus is gone. Copying eligibility alone would still leave the caster-level mismatch. Mixed eligibility/lifetimes require a package design. |
| Complete alias guards | `AddEffect` checks each incoming effect (`387406`). CheckAdd consults318 source immunity (`1CCCEF–1CCD1E`);318 registers the match at `1B6ACC`. A self-source guard can block later alias guards in the same helper. The original model checked once at spell entry and missed this. Its per-effect correction exposes the draft's ordering defect. |

Guard ordering must put the current source last, but that isolated repair would
not solve the architecture's dispel, source-identity and duration failures.
Other retained draft gaps include zero-count table bounds, complete numeric
flat-set classification, casting effects, conditional delivery, linked HP/EFF
first-use state, and existing-save admission. They are not waived by isolation.

Native98 review was also tightened: a completed `ProcessEffectList` rebuild
calls `CDerivedStats::Reload` (`3AC4F8`), whose `ClearAll` (`153DDF` → `1F8990`)
destroys old persistent regeneration objects before rebuilding them. Finite98
admission normally triggers the rebuild (`387553–38757E`), including queued
`CMessageAddEffect` with argument5=1 (`20FE56`). Global/reentrant deferral paths
(`387566–38756D`, `3ABAFC–3ABB14`) remain unresolved. This closes the claim that
an old full-duration tick object must always survive refresh; it does not prove
all replacement/tick ordering safe.

## Alternatives and the next narrow proof

**Original ITM source controls:** keeping the original item effects preserves
fixed level10 and native sourceType2. A timed-list-only321 (`p2=2`) can refresh
a pure direct bonus source; finite318 markers can block a pure HP source, with
all aliases covered and the current source last. However321 compares only the
eight-byte source name (`1E7752–1E7755`) and calls matching removal handlers. It
would also remove adverse/maintenance/other-ability timed effects, or collide
with a same-name SPL/EFF parent.318 blocks every effect from the source,
including legitimate instant healing, cures, permanent and adverse effects.
That is a restricted candidate for simple direct potions, not a general solution
for the agreed mixed-payload and potion-plus-spell preservation requirements.

**Existing EEex:** local1.3.0 `EEex_Projectile_Patch.lua` hooks
`CProjectile::AddEffect`, but self-target item effects can instead queue
`CMessageAddEffect` directly (`3BBB27–3BBB7D`); a projectile mutator misses this
path. Op403's hook at CheckAdd's final probability branch (`1CC744`,
`EEex_Opcode_Patch.lua:974`) does see that incoming native effect. It runs before
later source/opcode/resource immunity and save checks. Blocking a proven HP
repeat there is promising; removing/refreshing an old safe package there is too
early because the replacement may subsequently be rejected.403 also requires
an attached registration effect and a save/load/rehydration design. These facts
do not establish that an engine fix is impossible.

Prefer a narrowly scoped EEex prototype that retains each original effect and
acts after native admission but before first application. Prove hook coverage,
ownership and reentrancy before replacing the draft or introducing an EEex
dependency. The handover records the candidate site and minimum experiments.

The bounded native trace identified that candidate precisely: CheckSave is called
at `1CD1A4`; failure branches at `1CD1A9`, and success falls through at `1CD1AF`.
RDI holds the original effect and R14 the target. This precedes OnAdd (`1CD1CF`),
DisplayString (`1CD1DB`) and subsequent ResolveEffect (`387478`). A callback only
after CheckAdd returns would already be after the first two callbacks.
`EEex_HookConditionalJumpOnFailWithLabels` and `EEex_GenLuaCall` can construct a
new callback at that branch using the existing hook machinery. A compiled EEex
DLL change has **not** been established as necessary. Exact pattern/byte guards,
register/stack preservation and runtime proof are still required.

The first prototype must remain limited to direct self ITM delivery with
`noSave=false`: other callers may override rejection, and must not inherit a
single global rejection flag. Never free the incoming effect from Lua; native
AddEffect owns it. Safe manipulation of existing effect lists during this call
is unresolved because removal handlers can cause nested delivery or rebuilds.
Linked children need source/transaction correlation; a source name or equal game
timestamp alone is insufficient. Save data must never persist native pointers.

For op403 registration, the inspected official
[InfinityLoader source](https://github.com/Bubb13/InfinityLoader/blob/f14a00527286f819b8034411bc92ca719cfe3c86/EEex-Core-Shared-Files/source/EEex.cpp#L4578)
uses per-actor screening lists. That source is supporting evidence; the local
EEex DLL was fingerprinted, not independently rebuilt from that commit.

## Source inventory and prior art

Read-only audit results: 83 pristine Steam category9 resources; 146 effective
category9 resources in each inspected current default and non-SR fixture; 51
loose Item Revisions Beta10 resources and 53 IR Revised1.3.900 resources. These
counts describe the inputs, not future installer requirements. All explicitly
supported SPL/EFF graph edges resolved in those audit runs. This does not classify
all graphs as safe to transform.

| Family | Native/default payload anchors | Important variation |
|---|---|---|
| Heroism (`POTN09`) | op18 percentage HP and op54 | IR delivers a linked SPL; preserve first-use HP semantics |
| Power (`POTN41`) | op18, op54 and thief-skill bonuses | Separate family from Heroism despite shared effects |
| Genius (`POTN29`) | Timed op19 +4 Intelligence | IR/IRR repurpose this resource into Vocalize: op48 and immunity to silence, with no INT bonus; it is **not** exempt |
| Master Thievery (`POTN36`) | op90/op92 +40 | IR linked spell already has self-immunity |
| Mind Focusing (`POTN37`) | Timed op15/op19 +3 | Not Genius; IR changes the resource to restoration behavior |
| Perception (`POTN39`) | op90/op91/op59/op92 +20 | Distinct from Master Thievery |
| Regeneration (`POTN42`) | Native op98 | Keep native periodic healing; no generic replacement damage/healing |
| Fortitude (`POTN28`) | Native CON modification | IR linked spell instead includes op18 percentage HP and needs HP-safe repeat handling |

SCS35.21 `stratagems/potion/potion_shared.tph:85–96` explicitly creates
`DW#PTNnn` copies from the corresponding potion and makes them undroppable.
That provenance is stronger than guessing from a filename or display name.
Other copies need a unique semantic match to a known family; ambiguous matches
must not merge distinct potion types.

The category also contains mixed healing/bonuses (Myconid Soup), delayed/repeated
Clairvoyance delivery, permanent gains, harmful potions, thrown items, quest
consumables and shipped unused resources such as `BTEST1`. Category9 alone is
therefore not an instruction to remove every timed effect.

Prior art is useful but not a substitute:

- Tweaks and Tricks `tnt/components/potions_no_stack/{main,macro}.tpa` wraps17
  potion resources into hidden spells, removes their private secondary type and
  recasts. It also changes protection scrolls and copies op18 unchanged; neither
  its scope nor HP behavior meets this contract directly.
- Rogue Rebalancing10 covers only two potions, bundles other changes, skips under
  an Item Revisions marker and blocks repeats. It is not the requested feature.
- CDTweaks2640 is potion mixing, with unrelated risks.

## Reproducible read-only audit

`research/scripts/audit_potion_payloads.py` reads effective KEY/BIFF plus override,
or loose fixture directories. It emits JSON to stdout only. It follows explicit
SPL/EFF links with cycle, depth, node and bounds checks; retains raw effect and
ability bytes; and reports timing/HP/conditional-delivery concerns. It does not
guess potion identity, favorable/adverse meaning or runtime behavior.

```powershell
python -B research/scripts/audit_potion_payloads.py --game-root '<read-only game>'
python -B research/scripts/audit_potion_payloads.py --resources '<loose fixtures>'
python -B -m unittest tests.test_potion_payload_audit -v
```

Fourteen audit tests passed, including reordered/multiple slices, direct/linked
payloads, shared children, malformed/cyclic/missing links, repurposed Genius,
raw-data preservation and KEY/override precedence. This is parser/audit evidence,
not component or in-game acceptance. Implementation and integration results are
recorded separately in the final owner handover.
