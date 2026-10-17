# Captured coverage of the original-effect admission prototype

2026-10-09. Read-only resource/compiler evidence, with actual Lua core replays.
This report does **not** reuse the rejected private-SPL draft's captured installer
passes as evidence for the replacement. No game, installer, save, or executable
was written or run. The root's whole-resource runtime fixtures and native probes
provide separate evidence; this report does not claim live acceptance.

## Inputs and reproducibility

- Default SR profile: `%USERPROFILE%\Games\Chriz Easy BG\game`.
- Non-SR profile: `%USERPROFILE%\Games\ChrizEasyBG-No-SR-Test\game`.
- Vanilla BG2EE: `C:\Program Files (x86)\Steam\steamapps\common\Baldur's Gate II Enhanced Edition`.
- IR source corpus: `C:\Games\Baldurs Gate 1 and 2 mods\ItemRevisions\item_rev\itm`.
- IRR source corpus: `C:\Games\Baldurs Gate 1 and 2 mods\ItemRevisions-4b10\ItemRevisions-4b10\item_rev\itm`.

The last two are loose source corpora, not complete installed profiles. All
category-9 resources are counted, including unused/quest items; a source count
is not a count of distinct obtainable player potions. No proprietary bytes are
stored in this repository. Local JSON reports retain resource hashes, parsed
effect fields, order, graph edges, concrete diagnostics and compiler/core hashes:
`%USERPROFILE%\AppData\Local\Temp\cbr-potion-inventory-20261009\admission-capability-current-<profile>.json`.

Run `python -B research/prototypes/potion-admission/audit_admission_capability.py
--game-root <explicit-root>`; use `--resources <explicit-loose-directory>` for
IR/IRR. Output goes only to stdout. Compiler CLI `--format json|lua` likewise
does not write its inputs. The compiler's optional `read_resource` callback is
required to prove linked branches harmless; no game location is inferred.

## What the columns mean

`direct_owned` means owned records use only direct item delivery. `linked_owned`
means at least one owned record has compiled linked-spell provenance; a mixed
source also goes in that column and lists both values in `owned_transport`.
**Linked compilation is not connected Runtime acceptance:** this tool does not
replay linked doses. The separate connected Runtime/Lab exists but remains
unactivated and under review; this inventory does not exercise it.
`native_only` means the inspected resource requires no owned
record: its recognized effects remain native, including instant healing/cures,
permanent operations, adverse effects, harmless linked branches and reviewed
nonaccumulating setters. Neither category is a live-runtime acceptance claim.
`unsupported` includes a concrete capability/identity/lifetime diagnostic.

The initial replacement compiler covered only POTN29/POTN36 (Genius/Master
Thievery) and their SCS copies. Extensions are based on the pinned executable's
constructor, Apply and destruction paths and bounded instruction probes, not on
removing a rejecting guard to make a capture pass.

| Current input | Category-9 sources | Direct owned | Linked owned (compiler only) | Native only | Unsupported |
|---|---:|---:|---:|---:|---:|
| Default SR | 146 | 34 | 2 | 89 | 21 |
| Non-SR | 146 | 34 | 2 | 94 | 16 |
| Vanilla BG2EE | 83 | 21 | 0 | 57 | 5 |
| IR loose source corpus | 51 | 0 | 2 | 28 | 21 |
| IRR loose source corpus | 53 | 0 | 1 | 27 | 25 |

All five complete-profile compilations still diagnose an unsupported resource.
The locally compilable subsets also compile together without an additional
identity error:125/130/78/30/28 sources respectively. A subset pass is not a claim
that the requested all-potion behavior is complete. Under `except_genius`, the
actual POTN29 family is exempted at runtime:2 inspected sources in each SCS
profile and1 in vanilla. IR's historical POTN29 is not granted that exception.

Installed direct-owned canonical families are POTN02,09,11,15,18,22,28,29,31,34,35,36,37,
39,41,46, with both SCS copies, plus OHBPTN01 and OHBPTN11. This includes Heroism09/Power41,
Fortitude28's CON setter, Genius29, Master Thievery36, Mind Focusing37 and
Perception39, Magic Protection34's additive MR166, and Invulnerability46's saves.
Color7 and the reviewed unowned linked AC branch no longer block46. Vanilla
additionally supports direct POTN16, OHNPOTN1 and PTION41;
installed POTN16 and its SCS copy now compile linked ownership. IR POTN16/35
and IRR POTN16 also compile linked ownership. They do not gain a direct replay
or connected Runtime acceptance claim from this change.

The capture was generated with compiler SHA256
`0319fe5256feb57649ab48853585d755ff94b363cc32c2b09468de3542eae336`
and core SHA256
`b63172e734fa822ebaff5f87457d30ada83b2cca109d501eb83eeb6aa8e934a2`.
The compiler tests include reviewed stat modes, alternate effect orders, different
native states, post-family HP companions, inherited177 lifetimes and target2
delivery bounds. Their input bytes remain unchanged.

After the 87/88/89 classification, the selected compiler verification command
passed 185 methods in 11.173s, with all five explicit captured roots enabled
and no skipped capture.
This is one run of `tests.test_potion_admission_manifest`,
`tests.test_potion_linked_manifest`, `tests.test_potion_admission_lua_compiler`,
`tests.test_potion_admission_capability`, `tests.test_potion_linked_quota_bounds`
and `tests.test_potion_opcode_276_277`.
Its log is
`%USERPROFILE%\AppData\Local\Temp\cbr-potion-inventory-20261009\resistance878889-compiler-final-20261009.txt`.
The new resistance test module and native probes are reported separately below;
counts from repeated or overlapping runs are not added together.

The lead separately ran `tests.test_potion_captured_runtime` against the three
game profiles above. The selected canonical09/29/36/37/39/41 and available SCS
copies passed both policies, canonical repeats, both alias orders and retained
V2-field round trips. That fixture connects the actual compiler, Native,
Runtime, Messages and Core Lua modules. Native construction, admission, list
insertion and saved-field copying remain test doubles; this is stronger module
integration evidence than core-only replay, but not native HP, hook execution
or real save/load acceptance. Its result does not extend to the other resources
counted in this table.

## Actual canonical/SCS pairs and policy

The inspected SCS source `stratagems/potion/potion_shared.tph:82–97` implements
`make_undroppable_potions`: it clones existing POTN01..99 to DW#PTN01..99 with
`droppable=>0`. The compiler still checks canonical availability and payload
compatibility; a filename alone is not identity proof. It checks again after HP
ownership is resolved, so a changed companion cannot hide behind an initially
empty quota.

The capability tool tests both dose orders for each compilable canonical/SCS
pair, each ability combination and both policies. These are actual Lua core
direct-record replays with native admission assumed successful. Any pair with
linked owned calls is explicitly `not_replayed`/`LINKED_REPLAY_CAPABILITY`,
including mixed direct/linked sources; it cannot pass by replaying only its
direct ordinals. Zero-owned cases are reported
`native_only`, not counted as repeat-policy success. Native gate rejection,
timed-list readers and transport are not simulated by those core replays.
Each installed profile has64 successful owned-policy replays (16 families ×
2 orders ×2 policies). Default SR has108 zero-owned native-only combinations
(27 pairs) and8 unsupported pairs; non-SR has116 native combinations
(29 pairs) and6 unsupported pairs. Each profile also has four explicitly
unreplayed POTN16 linked combinations (two orders, both policies). No failed core replay is concealed
as a supported result. This includes Power's actual ordered seven-record bonus
package and both canonical/alias orders, not only one supplied fingerprint.

HP-sensitive classification is family-wide. A partial SCS alias inherits the
canonical HP policy before final owned ordinals are selected. Reviewed stat
setters, percentages and duration-bearing support states are included in that
package even when native repetition would not increase their potency. A CON18
setter can lower an actor's preexisting CON20; package ownership does not inspect
or require a reference actor baseline. Explicit additive penalties remain native.

Find Traps (91) percentage mode is a substantive exception: native repetition
can multiply an already-derived value (50→60→72), unlike the reviewed base-derived
percentage branches of Pick Pockets/Open Locks/Hide. It is owned even outside an
HP package. Spell-state328 uses the native Special-nonzero branch and unsigned
state index<256; higher indexes are native no-ops. This does not assert that
every spell state has a positive gameplay meaning in isolation.

Finite HP portrait142 and color7 records now belong to the ignored repeat package. Each
source has `nonBlockingKeys`, identifying those cosmetic keys: an old icon alone
must not block a fresh mechanical dose after the last real bonus expires. Icon
duration and original fields stay unchanged, and a canonical/SCS icon/color difference
does not invalidate gameplay provenance. Permanent/adverse HP or CON operations
do not make a family HP-sensitive: POTN48's permanent CON penalty and poison icon
remain native. Other presentation opcodes are not automatically owned. Proven
boolean immunities101/169/267/296 remain native outside HP; they retain a concrete
HP-companion diagnostic until lifetime/rebuild/removal behavior is supported.
Spell-level102 is boolean for0..9, and is a mechanical HP companion; negative
levels diagnose the native unsafe index, while levels>9 are native no-ops.

The next direct-state batch clears the unnecessary whole-resource blockers for
MISC98, OHBPTN01 and POTN21/23/30 (including their installed SCS copies). It also
clears vanilla POTN10; the installed version still has unreviewed318/linked291
companions. Ordinary Invisibility20 mode0 and Infravision63 are native states
outside HP and finite mechanical companions within HP. Morale-break106 mode1
and valid scripting-state282 are stable native setters, likewise owned only in
HP packages. Feeblemindedness76 remains adverse/native. Morale23 Special0 is a
native one-shot cure even with a stored finite/delayed duration; its cumulative
Special-nonzero branch is explicitly unsupported. No linked owner descriptors
were added to the direct compiler schema.

The projectile/fire-setter batch additionally clears WAND16 in all three game
profiles and POTN38 (plus its SCS copy) in non-SR/vanilla. Opcode83's consumer
lookup is non-consuming boolean membership; it is native outside HP and an
owned mechanical HP companion for valid unsigned16 projectile IDs. SR POTN38
still has206 resource protection. Fire resistance30 mode1 is a signed-low16
setter clamped to[-128,127], which makes the shared SPIN713 branch genuinely
native-only for WAND16. No child ownership or changed source is invented.

POTN45's independent movement126 mode2 and proficiency233 high16-zero setter
are now native-only too. Movement modes0/5 and proficiency high16-nonzero
additive forms retain concrete diagnostics. Valid proficiency setters are HP
package companions; movement HP ownership still diagnoses baseline/wrapping
polarity ambiguity. POTN45's206 policy remains unresolved, so this removes
independent obstacles without changing whole-source coverage by itself.

The final bounded IR batch proves slashing resistance86 mode0 cumulative:
IR20 and IRR25 add to a signed WORD accumulator before its upper cap100.
The compiler owns effective LOW16 amounts1..32667, retains neutral0 and
diagnoses larger positives or negative operands whose wrap can reverse
polarity. Raw fields stay intact. Weapon immunity120 is a nonconsuming native
predicate outside HP and retains an HP-companion diagnostic. These remove
independent blockers from POTN18/11, but both still contain206. Bless130's
first-winner state/morale behavior and206 self-protection policy remain
unclassified. See [native-ir-remaining-notes.md](native-ir-remaining-notes.md)
for pinned source hashes, exact native branches and75 instruction cases.

The subsequent Detect Illusion276 / Set Traps277 review removes another
independent IR/IRR skill obstacle. Finite mode0 owns nominal positive signed
LOW16 bonuses, preserving raw upper bits and adverse operands. Stable native
LOW8 setters and base-derived percentages stay native outside HP and use the
same HP companion policy as Hide275. The native DWORD accumulators can wrap
before final0..255 limits; this classification does not repair that behavior.
See [native-skill-276-277-notes.md](native-skill-276-277-notes.md) for exact
branches, constructor fields, independent overflow controls, lifetime proof and
the11 focused Python/Lua preservation tests. The separate native probe passes174
cases, including275 as a control; these are instruction cases, not live tests.

The fresh five-profile counts remain unchanged. IR/IRR POTN39 now reaches
unreviewed292 at child ordinals2/4, after its276 is classified. IRR POTN36
now reaches206 at child ordinal9, after277; IR POTN36 already stopped at206
ordinal8. Thus these resources are still honestly unsupported. The complete
remaining source diagnostics are in [remaining-capability-blockers.md](remaining-capability-blockers.md).
Whole-profile compilation still fails in all five inputs; no complete potion
is advertised as supported by removing only one obstacle.

The independently reviewed crushing87, piercing88 and missile89 finite mode-0
branches also use WORD addition followed by a signed upper cap of 100. The
compiler now applies the existing slashing86 capability policy to these three
classes: own effective signed LOW16 values 1..32667, keep zero native, and
diagnose negative or larger positive operands because underflow/overflow can
reverse polarity. Input bytes and raw fingerprints stay intact. Finite setters
and percentage modes remain unreviewed. This is explicit unsupported behavior
for rejected operands, not a claim to preserve every adverse potion at runtime.
See [native-resistance-87-88-89-notes.md](native-resistance-87-88-89-notes.md):
96 native instruction cases and 12 focused compiler methods pass in separate
runs. Both IR and IRR POTN18 now reach child206 at ordinal8; complete-source
counts remain unchanged and the self-protection policy is still unresolved.

## Linked/shared resources: distinctions that matter

Shared resources are not automatically a blocker:

- IR/IRR `POTN04.SPL`, shared by POTN04/POTN56, contains finite STR44(21,set1)
  plus icon/visual/sound records. The native setter is nonaccumulating; its branch
  remains native for these safe families.
- `POTN20.SPL`, shared by POTN20/POTN47/POTNMARE, contains instant Cure Poison11,
  color50 and delayed visual/sound records. No finite policy-owned bonus exists.
- The compiler proves such branches with bounded recursion (depth16/nodes256),
  preserves every link, and diagnoses missing/cyclic resources. Opcode177's
  carrier timing/duration overrides child EFF timing during classification.
  Thus timed177→raw-permanent bonus is an owned linked gap; instant177→raw-timed
  stat gain remains a native permanent operation.
- Proven non-HP linked318 guards now remain native when the entire branch has
  no owned bonus. Both native predicate outcomes are retained, so no fixed
  SPLPROT row meaning or0/0 operand requirement is invented. This clears
  BDMISC02 and POTN13/26/27 with SCS copies in both installed captures, plus
  non-SR POTN32 and its copy. The parent family's owned source names are checked:
  a guard that could block a repeat before refresh gets `RESOURCE_GUARD_CAPABILITY`.
  Direct318 and conditional HP branches still diagnose, including POTN10.

The smallest real linked-bonus obstacle is IR `POTN36.ITM` ability0 ordinal1 at
0xDA: opcode146→POTN36.SPL. Its child has finite +20 Hide275, Stealth59, Pick
Pockets90 and Open Locks92 for300seconds, then original self206(POTN36), with
presentation records. IRR changes the ordered skill package and adds277. These
are actual cumulative child bonuses. The compiler now emits a bounded mode1
call registry with separate logical owner and original native spell source,
root-dose quotas and child ability selection. Self206 and unreviewed child
opcodes still prevent those particular skill packages from compiling. Connected
Runtime composition remains incomplete and rejects linked dispatch; the direct
core replay deliberately declines every source containing owned calls.
Those children still require native lineage, stable saved identity and admission/lifetime review;
changing the child resref or manufacturing a new effect would lose the design's
native-delivery guarantees. A shared child that does contain owned bonuses would
also require distinguishing parents without relying on transient saved pointers.

IR/IRR POTN29 is a Vocalize/immunity package, not the actual Intelligence potion;
the Genius exception cannot be inferred from that historical resref. IR/IRR
Heroism/Power contain linked HP and Bless130, skills, casting-level191 and/or
self206 guards. Their unchanged native no-repeat guards are behavior to preserve,
not evidence that the direct original-item adapter already covers those graphs.

## Concrete remaining work

The unsupported count is **not** a count of stacking bugs. Prioritize actual
owned behavior rather than making every harmless category-9 resource compile:

| Priority | Current example | Actual missing behavior |
|---|---|---|
| Linked cumulative/HP bonuses | Installed POTN16 compiles; OHNPOTN1 and IR/IRR36/39/41 still have independent blockers | Compose the registry with child-source admission and saved parent-family provenance; preserve original self206 behavior. |
| Original source removal | POTN60 and its SCS copy | The CHA bonus is reviewed; the original321 changes which active family exists before the bonus arrives. |
| Periodic phase | POTN42, regen98(3,mode3,180s) | Preserve native healing schedule while changing expiry; independent native investigation is in progress. |
| Remaining protections/control and cleanup | Installed POTN10's318/linked291 companions; SR POTN14/32/33's221; SR POTN38/45 resource protection packages | Ordinary states,83 membership and safe126/233 setters are classified.206 policy and conditional HP protection remain separate.221/337 are removal operations, not harmless boolean guards. |
| Consumed capacity | BTEST1's200, level1/count6/BTEST1B | Repeats can replenish derived capacity; every original is debited and may independently dispatch its exhaustion payload. This is not a boolean guard. |

The report deliberately does not turn a likely native protection into a proven
nonaccumulating classification merely to raise a coverage percentage.

The five remaining vanilla sources are BTEST1(200), MISC9Y(206), POTN33(206),
POTN42(98), and POTN45(206).
See [remaining-capability-blockers.md](remaining-capability-blockers.md)
for every remaining source, its first compiler stop and individually audited
direct-record diagnostics in all five inputs. A first stop does not prove the
rest of that linked graph free of additional blockers.

A review removed an unsafe sign-based exception for finite AC0/APR1. Source and
instruction probes then established precise replacements. AC modes0/1/2/4/8
subtract signed LOW16(amount) from their accumulators, so positive effective
amounts are owned bonuses. Mode16 takes the lower of current AC and signed
LOW16(amount); it stays native outside HP packages and becomes an owned HP
companion. APR mode0 uses signed LOW16 encodings1..5 for whole attacks and6..10
for half-step values; only effective1..10 are positive bonuses. Original raw
fields are preserved, including values such as65537 whose low16 is1. Unreviewed
modes retain diagnostics; ordinary raw32 sign is never used as a substitute.

The subsequent width audit corrected the same issue for ordinary finite stats:
additive6/10/15/19/21/22/27–31/33–37/44/49/54/59/73/90/91/92/275 consume signed
LOW16 amounts. Setters and percentages have distinct widths, including Hide275's
unsigned-byte setter and Find Traps91's full32 multiplier. The compiler preserves
all raw fingerprint fields, classifies effective native operands, and diagnoses
the few full32 arithmetic cases that can overflow before clamping. Negative
THAC0 percentages have baseline-dependent polarity and remain an explicit HP
diagnostic. See [native-classification-width-notes.md](native-classification-width-notes.md)
for exact RVAs, the446 operand cases,37 color/immunity/MR cases,107 state/setter
cases (including the Invisibility message handler),29 projectile/fire-setter/
consumed-pool cases,286 movement/proficiency cases,10 linked resource-guard
cases, arithmetic bounds
and test-double limitations. These checks do not prove general actor-stat
overflow handling or complete engine rebuild behavior.

A separate20-case direct-ITM construction probe confirms the shared decoder
normalizes exactly raw DWORD+20=0xFFFFFFFF to0 before the constructor. Both
compilers now predict that native field, including HP dice capability checks,
while preserving source bytes and all other bounds. Sentinel/zero forms are
native-equivalent logical records with separate duplicate quotas. This correction
did not change the captured source counts above.

- Heroism's actual THAC0 effect targets2 even in vanilla. Its ability is type3,
  target5, projectile1. The compiler accepts precisely that reviewed self-use
  delivery class while preserving target2. Native instruction evidence shows
  projectile1's base class transfers the original pointer with noSave=false.
  Runtime actual-vtable and self-target guards remain mandatory because EEex
  projectile mutators can replace the class. Other projectile/target routes
  remain unsupported; compiler eligibility alone does not arm a hook.
- POTN60's original321 removes a family source before the CHA bonus. It is
  diagnosed until canonical/alias removal ordering is handled explicitly.
- Regeneration98 carries periodic schedule state; expiry-only edits need phase
  evidence. Protections, delayed-state and other unreviewed opcodes retain
  concrete diagnostics rather than being silently declared native-safe.
- Arbitrary linked bonuses, projectile subclasses/copies, dynamic resource
  changes, native reentrancy, object lifetime and save/load remain separate
  acceptance obligations. Existing stacks are diagnosed rather than migrated.
- Whole-game consumers outside potion graphs are not enumerated. Neither
  source-corpus success nor core replay proves their runtime interactions.

The rejected architecture's three failing test methods remain unchanged and
visible. No production component or install recommendation follows from this
replacement-specific capability report.

## Portable registry prototype; no product port yet

The existing package builder includes `chriz-bg-rebalance/**` and explicit
installer/license files, leaving `research/**` out. Keep that boundary until the
replacement is ready. Python remains developer research/test tooling; players
should need only the normal WeiDU installer and the supported EEex runtime.

The selected design is read-only WeiDU inventory followed by a pure Lua semantic
compiler reading current effective binary resources before activation. WeiDU
can enumerate category9 ITM names using `COPY_EXISTING_REGEXP - GLOB`; runtime
resource extraction belongs to the lead's separate adapter. The compiler keeps
the family-wide HP pass, canonical/alias checks, linked-unowned proofs and all
ambiguity/capability diagnostics before `prepare` and `arm`. Unknown owned
effects remain an explicit failure, not a partial all-potion registry.

This proposal performs extraction at install time and semantic preflight at
startup. If successful semantic validation is required before WeiDU reports
installation success, it instead needs a real WeiDU semantic-compiler port;
startup validation is not a substitute for that requirement. Bundling a new
Python or standalone Lua runtime is unnecessary for the first design. A Lua
port is compared against the Python oracle with current alternate layouts and
the real captured corpus, including matching failures.

`CBRPQCompile.lua` returns a module exposing
`build({version=1, policy=..., names={...}}, readResource, sha256)`. The explicit
reader takes a resource filename including extension and returns a binary Lua
string. `resolveLinks=false` optionally declares a direct-only reader, matching
the Python compiler's absent linked resolver; ordinary runtime use defaults to
linked reads. `CBRPQHash.lua` supplies pure LuaJIT SHA256 using the runtime's bit
library. No sibling module, game path or resource is loaded implicitly. Manifest
fields and SHA256 keys are identical to Python, including `nonBlockingKeys`.

`tests.test_potion_admission_lua_compiler` compares successful outputs field by
field and failed outputs by diagnostic code. Its final80-method run passed,
including79 synthetic differential/schema/hash tests and one opt-in captured
differential method over all579 category9 inputs in the
five sets above, each policy, each SCS/canonical pair, each complete profile and
each compilable subset. Captured checks include unsuccessful compilations rather
than dropping them. `CBR_POTION_COMPILER_ROOTS` supplies explicit roots separated
by the platform path separator. These tests do not execute native hooks.

Production engine-loaded Lua resrefs need the engine's
eight-character naming limit and an EEex-guarded autoload entry; the present
explicit `dofile` lab filenames are not a finished packaging layout. No startup
loader, installer component or game installation was added here. The semantic
Lua port and hash module remain in the excluded research prototype directory.
