# Original potion effects: opcode and lifecycle evidence

2026-10-09. Offline research only. This expands the direct-effect prototype; it
does not establish game acceptance, full save/load safety, or linked coverage.
The private-SPL replacement prototype remains rejected.

Evidence uses the read-only BG2EE 2.7.3.0 `Baldur.exe` in
`%USERPROFILE%\Games\CBR-TimeStop-2.7.3.0`, SHA256
`b51093a49140b2b8a7c046b4652bb8e535be24ebbc12b1d735e0b94217a14d57`.
Addresses below are RVAs, with image base `0x140000000`. Function names come from
the matching local EEex 1.3 `loader/v2.7.3.0/bg2ee/function_names.db`.

## Direct effects with stable state

`probe_native_potion_stats.py` passes **87 cases** using copied native
ResolveEffect/ApplyEffect instructions in Unicorn. It changes only the original
active effect's expiry, revisits before/after the old deadline, and verifies all
effect bytes remain unchanged during recalculation. Native base OnAdd also runs
with self source IDs and source flags both 0 and 0x400; it changes neither effect
nor actor. Each constructor's real vtable is read and checked, independently of
the synthetic vtable used for ResolveEffect.

| Cases | Native evidence and interpretation |
|---|---|
| Additive mode0: 6,10,15,21,22,27–31,33–37,44,49,59,73,91,275 | Two amounts per opcode. Parameters and Special stay stable; finite application updates actor accumulators. All use non-dice constructor semantics, shared destructor14C8E0, no-op OnAddSpecific1E1E0 and OnRemove1E1E0. |
| Saves33–37 mode3 | First native application consumes firstCall. Subsequent expiry-only extension retains that state. Five tests; this is not permission to reset/recreate the effect. |
| Skill90,91,92,275 modes1/2 | Four set and four percentage cases. All effect fields remain stable. **91 percentage is cumulative**: its finite branch1C6FBE reads current derived trap skill115A, then writes115A at1C6FFB. From50, two120% calls produce60 then72. 90/92/275 instead read base fields and give60 then60. |
| Ability stats6,10,15,44,49 modes1/2 | Ten cases plus STR44 set19–24. Native fields stay stable; repeated setter/percentage calls do not accumulate potency in these cases. STR/DEX mode3 is separate: random rolls mutate amount/firstCall and sometimes Special. |
| State328, Special nonzero | Apply1C6084–1C60A5 calls SetSpellState154020. Unsigned state index0–255 sets one bit in derived stats; parameter1 is unused. Already-set bits do not accumulate. Tests include0,1,68,127,255; Special1 and9 have the same branch. Index256/0xFFFFFFFF and Special0/index68 are inert negative controls. This proves state mechanics, **not beneficial polarity of arbitrary spell-state IDs**. |

The companion tests support owning these finite records inside an HP family;
the repeat decision must include every positive companion, even native setters.
For an ordinary safe family, a native setter can be accounted for explicitly
without recreating it. Arbitrary mixed positive/adverse packages still need
semantic classification; a state ID is not intrinsically a positive bonus.

Base OnAdd1E5500 tests source flags0x400, but self sourceID==targetID skips its
hostility/message branch at1E5544 and reaches the class callback at1E573D. The
reviewed callbacks above are no-ops. There is no hidden duration conversion
between the proposed success boundary and direct stat application. The earlier
`probe_native_potion_opcodes.py` separately passes16 INT19/THAC054/HP18 cases,
including native percentage54(80) and zero-dice HP repeat rejection.

CON10 stays **HP sensitive in every reviewed mode**. Downstream
CheckStatsChange34EAF5–34EC9D applies the derived CON HP-bonus delta to current
and maximum HP and can kill on a reduction. State stability does not justify
removal/reapplication. The selected HP-family policy remains ignore bonuses on
repeat while the old package remains active.

These Apply bodies do not call AddEffect/CheckAdd/AddMessage in the probed paths.
That does not prove general non-reentrancy: outer AddEffect can call
ProcessEffectList38757E, which also processes unrelated existing effects such as
177/146/326. A runtime frame must continue to distinguish its exact incoming
object from nested effects; no actor/time-only inheritance is justified.

## Regeneration and protections: limits of the direct proof

`probe_native_regeneration.py` executes copied Apply98, regenerated-list and
regeneration AIUpdate, native-generated Heal17 constructor/Apply, ClearAll and
RemoveAll instructions. It also executes AddEffect with the candidate admission
callback and the decisive ProcessEffectList scheduling fragments. This is **not
whole ProcessEffectList execution**: the harness explicitly orchestrates its
ClearAll → Resolve98 sequence. Allocator/list-node/UI services and the generated
heal's AddEffect admission are substituted; actual native opcode17 arithmetic
runs, rather than generic healing in the test.

Regeneration98 modes2/3 have no immediate healing grant in Apply1BEC50–1BEE02.
Constructor1A16C0 uses non-dice semantics; its actual vtable593AD0 uses shared
destructor14C8E0, OnAddSpecific1E69D0 and no-op OnRemove1E1E0. Six native OnAdd
cases (modes2/3, timings0/10/4096) leave the effect and current HP unchanged.
The reviewed Apply body does not mutate the original descriptor. Modes0/1 have
amount/current-HP-dependent duration semantics and are not covered.

The cached 0x30-byte regeneration object contains word interval+18, word phase+1A,
tick-counter+1C, word mode+20, amount/remaining+22, word heal amount+24 and signed
remaining ticks+28. Mode2 sets interval1 and heal amount=parameter1; mode3 sets
interval=parameter1 and heal amount1. Apply copies `effect.expiry - now` into
cache+28 at1BED6D–76. It reconstructs phase as
`floor((now - effect[6C])/15) % interval` at1BED97–D2. Field6C is an observed phase
input; these findings do not establish it as a universal creation timestamp.
Extended parameter4+64 and nonzero Special take additional paths not covered by
this ordinary direct-potion probe.

The cached remaining time is independent of the original expiry. The negative
case extends original expiry1017→1100 at worldTime1010, but without a rebuild the
cache still disappears at its old countdown and heals only at1015. Rebuilding
keeps one native source alive and heals at1015,1030,1045,1060. A scheduled
once-per-15 check is insufficient: CheckDuration1CD1F0 returns0 for an unexpired
effect, and ProcessEffectList's second gate3ABF97–3ABFDA can skip the full reload.

**Dirty flag is necessary for this candidate but is not phase-safe in general.**
Accepted AddEffect writes **DWORD actor+4BA4=1** at38744C. Rejection skips that
write, although both paths reach common tail387558: with game+3FA4=0 and the
immediate flag it calls ProcessEffectList38757E. The probe tests adding the same
dirty write alongside the expiry update, then returning through native rejection:

| Boundary | Native result |
|---|---|
| Global3FA4=0, actor4EA4=1, off scheduler phase | Rejection calls ProcessEffectList; dirty bypasses both reload gates and is cleared at3ABFE7. Without dirty the first gate chooses cached-only work. |
| Global3FA4=1 | AddEffect skips the immediate ProcessEffectList call; dirty remains available to the next normal processing pass. |
| Actor4EA4=0 | ProcessEffectList increments the deferred-pass word4EA2 and returns at3ABB14. It does not consume dirty. No reentrant full processing is invoked by the candidate. |

Regenerated-list AIUpdate226500 copies **list+38** into each cache+1C before
calling it, then increments list+38. ClearAll1F8990 → CObList RemoveAll407930
destroys old caches and clears nodes but **preserves list+38**. Native AIUpdate
uses that counter for its 15-tick second boundary; it uses cache phase+1A for
mode3's longer interval. These are two distinct phase inputs.

Twelve cadence comparisons cover modes2/3, list-counter offsets0/7/14 and original
phase-input6C values0/991. An extra double rebuild at the same worldTime1027
causes no immediate healing and produces one cache. All six mode2 comparisons
retain exactly the original native heal ticks and HP. **Two mode3 comparisons
rephase:** with list counter0 at worldTime1000, interval3, control heals at1045
and1090; extra dirty rebuild instead heals at1030 and1075. Both histories finish
with the same HP in that window, but the first pulse is 15ticks early. The probe
asserts this counterexample rather than hiding it as a failed acceptance test.

Therefore neither original-expiry-only nor original-expiry-plus-dirty is a proven
phase-preserving general98 solution. A mode2 refresh's broad dirty rebuild can
also rephase an unrelated mode3 source. A possible next adapter would associate
each original98 with its current cache at Apply's append boundary1BEDE0
(RDI=original, RBX=cache), then preserve or update that exact cache's countdown
without resetting phase; this needs cache lifetime/rebuild/destructor proof.
Do not infer that association from amount/interval alone. Late/deferred cache
ordering, TimeStop, Haste and save/load still require separate validation. No
runtime dirty write, cache hook or98 compiler capability was added here.

Protection101/102/206 inspection finds actor immunity-list/flag construction,
not direct mutation of their effect descriptors. That is insufficient blanket
coverage for all protections: decrementing/consumed shields, duration-bearing
ward companions, unusual filters and native rejection require per-opcode review.
No new protection/regen reader policy was added by this work.

### Portrait icon142 companion

`probe_native_portrait_icon.py` passes10 copied-instruction cases (icons0,16,22,79,
200 with parameter1=0/7). Constructor1A1300 has non-dice semantics; actual
vtable594AA0 uses destructor14C8E0 and no-op OnAddSpecific/OnRemove1E1E0. Apply
1BC5E0 reads only parameter2:79 is an inert special case; others call
AddPortraitIcon349120. That function's original list scan avoids duplicate icons.
It receives the actor/icon ID, not the effect pointer. No first-use flag,
parameter, Special or original expiry is changed by the reviewed path.

Native Resolve/Apply and the icon list duplicate/clear logic run in the probe;
resource/string/render constructors are explicit substitutes. Original effect
bytes stay stable across first/repeated Apply and an expiry extension1450→1900.
ProcessEffectList clears the icon list4CC0 with RemoveAll at3AC4A7 before timed
effects rebuild it. At1900 the native effect is done and no icon is reapplied.

This supports identifying142 as stable **package metadata** and suppressing an
HP package's repeated icon along with its bonuses. An icon's longer duration
must not itself keep HP-family presence active, prevent a new dose after the
actual bonuses end, or decide beneficial polarity. No UI-art acceptance is
claimed, and no source/identity fields need rewriting.

### Exact regeneration cache candidate

`probe_native_regeneration_cache.py` tests a narrower proposal: once one live
native cache is proven to belong to the matched original98, update
`cache.remainingTicks += newOriginalExpiry - oldOriginalExpiry` and the original
expiry. Reject the incoming original effect through its usual native CheckAdd
failure path. Do not set the actor dirty flag, reapply98, change phase, or create
healing effects in the candidate.

**Association is necessary; cache descriptors alone are insufficient.** Native
Apply's successful append return1BEDE5 has RDI=original98, RBX=cache and RBP=sprite.
Cache vtable598B18 has destructor1A4750, AIUpdate1A5CA0 and Copy1DCA40. The cache
does not store the originating effect pointer or item name. Two identical98
records and unrelated sources can therefore have indistinguishable cache fields.

Cache destruction must retire lineage before pointer reuse. ClearAll1F8990 and
normal AIUpdate226500 removal both call destructor1A4750. Native
RemoveAllOfType2265A0 first sets cache+C=1; the subsequent AIUpdate deletes it.
The list's own deleting destructor150E90 also calls ClearAll. Original-effect
destruction/reset must invalidate its lifetime token and all related lookup
eligibility; a raw effect pointer is not a durable identity.

**Copies are another creation path.** Regenerated-list operator=226480 deletes
its destination nodes and calls each source cache's virtual Copy. Derived-stat
operator=14F290 invokes this at14F73C; ordinary AddEffect and ProcessEffectList
copy live derived stats1120 into snapshot1DC8, and character-creation/level-up
paths can restore copied stats. A constructor-only map is incomplete. At
Copy's return boundary1DCAE9, RBX is the source cache and RAX the new copy; its
lineage can inherit the original-effect lifetime token. A snapshot copy counts
only if it later appears in the **actual sprite+1A08 list**, never merely because
it exists. The native Copy retains phase/countdown but leaves heal amount+24 at
constructor default1; the probe records this native behavior without fixing it.
It is another reason not to infer provenance from equal amounts.

The preflight proposal walks the current list read-only and requires exactly one
cache with this verified original lifetime, actual vtable598B18, Done+8=0,
canceled+C=0 and positive signed remaining ticks. It rejects missing/ambiguous
lineage, expired/done originals and arithmetic overflow **before either write**.
The bounded probe tests extensions only (nonnegative expiry delta). The units
are game ticks: AIUpdate subtracts its r8 delta; ordinary sprite processing
passes1. Adding the exact expiry delta preserves any existing one-tick offset
between the cache's last update and the world clock. Setting cache time directly
to `newExpiry-now` would discard that offset and is not this candidate.

Thirty paired native cases cover modes2/3, list-counter offsets0/7/14, refreshes
at1001/1015/1016/1027/1039, and two consecutive admitted repeats at the same
world time. The1039 case is one tick before original expiry1040. Candidate
original/cache state yields exactly the native heal sequence and current HP of
an unchanged control original born with expiry1100. The unrelated regeneration
cache and list bytes are unchanged at commit. Native17 constructor/Apply still
performs the heals. Lifecycle cases cover copy/restore, same-address reuse,
natural expiry, native type cancellation and the missing-cache boundary below;
six negative cases reject before mutation.

AIUpdate stores its decremented remaining time at1A5D1B **before** generating
native17 and calling AddEffect1A5ED6, and does not write that countdown again
later in its body. Its own heal-triggered nested callbacks therefore cannot
overwrite an extension with a pre-callback local countdown. An already-Done
cache is deliberately not revived. Full nested engine/EEex callback handling
and atomic write failure behavior remain runtime responsibilities.

These are **candidate boundary tests**, not installed hooks or whole-actor
processing. Generated native17 admission is bypassed; real accepted AddEffect
would set the actor dirty flag and can cause an ordinary later reload. The
candidate adds no such reload. Association must be established before first
Apply or from a subsequent ordinary rebuild; an existing unassociated cache
must not be guessed or force-rebuilt just to obtain provenance. Native cache
copy/clear/reset hooks, original lifetime validation, guarded two-field commit,
mode/extended-parameter limits, and independent hook-byte verification are still
needed before98 becomes a runtime capability. TimeStop/Haste and full save/load
acceptance remain outside this proof.

**A missing cache can be a legitimate transient state.** Full processing can
Apply98 then call its cache AIUpdate in the same world tick. Applying at1000
with original expiry1017 and ticking at1000 through1016 naturally removes the
cache at1016, while the original remains live until1017. The native probe
reproduces this one-tick gap. A new ordinary repeat in that gap must not be
described as an unsupported potion resource. The current strict prototype
diagnoses the scheduling state before writing; it is not complete98 coverage.
The reviewed ProcessAI Haste/Slow branches change actor counter3A4, while this
regenerated-list update receives delta1. This bounded inspection does not prove
the full Haste/world-time relation, and does not assume every missing cache is
caused by Haste.

Recovery needs a naturally-expired snapshot, not a generic cache copy. The
natural-deadline path marks Done at1A5D40 before its final eligible heal; cache
destructor1A4750 then exposes the final phase/countdown. Cancellation, original
removal and reset must invalidate recovery eligibility. The original must still
be a live exact lifetime, and cache+0xC cancellation must remain distinguished
from natural countdown expiry. To account for subsequent updates, a recovery
record needs the actual regenerated-list counter/pass, not world time alone.
The inline Apply allocation initializes the cache; no dedicated safe callable
constructor/recovery API has been established in this work. Native Copy also
fails to preserve heal amount, as recorded above.

**Appending a recovery during admission is not generally safe.** At226530–34
the list iterator reads the current node's next pointer before invoking its
AIUpdate. Later nodes see changed next links. Two native-iterator negative
controls let the old98 cache expire and emit its final17, then append a modeled
recovery during a later cache's heal callback. If the triggering cache is the
tail, the recovery waits until next pass and the old family heals once. If an
unrelated node follows it, the newly appended tail is visited in this same
list-counter cycle and the old family heals **twice**. The construction/AddTail
service is modeled; actual iterator and native healer instructions demonstrate
the extra pulse. A recovery adapter would need explicit list-pass tracking and
safe deferred insertion after counter increment/iteration exit, plus an elapsed
phase policy. No such recovery implementation or complete safety proof exists.

### Isolated cache bookkeeping module

`CBRPQRegenCache.lua` is a factory with no autoload or native hooks. Its adapter
contract is `ptr(record)`, `original(pointer)` (current owned identity/opcode/
timing/expiry/done), `isCurrentOriginal(sprite, pointer, identity)`,
`currentCaches(sprite)`, `cache(pointer)` (actual vtable, boolean Done/canceled,
signed remaining ticks), `now()`, `writeRemaining(pointer, value)` and an exact
`regenerationVtable`. The adapter must never dereference a retired native pointer
merely to create a fresh identity; native destructor/reset wiring is prerequisite.

Methods `onAppend`, `onCopy`, `onCacheDestroy`, `onOriginalDestroy` and `reset`
maintain exact lifetime lineage. Destruction/reset do no native reads. A snapshot
copy is tracked but only current-list membership makes it eligible. `prepare`
consumes Core refresh updates, including the selected original `identity`, and
validates all98 targets before returning a single-use transaction. The intended
sequence is `prepare(plan.refresh)`, `Core.commit(plan)`, `transaction.commit()`
with no engine method, yield or callback in between. The second commit rechecks
all original/cache identities, membership, new original expiries and old cache
countdowns before writing only the selected remaining-tick fields.

Signed cache countdown-1 is explicitly unsupported, as are nonpositive values,
overflow and missing/ambiguous current lineage. Shortening uses the exact signed
expiry delta only when it leaves a positive countdown. The module does not wrap
arithmetic or invent a broad dirty fallback. Its22 LuaJIT tests include extension,
shortening, sentinel/overflow, original/cache ABA, copies, reset, same-time repeats,
mixed targets and explicit post-write failure. A native write error after Core's
expiry commit or after an earlier cache write has **no rollback guarantee**;
the caller must diagnose and halt, never silently retry. The module's positive
path is implemented; missing-cache recovery and native integration remain open.

### Missing-cache recovery: bounded positional candidate

`probe_native_regeneration_recovery.py` now tests a narrower recovery candidate
for the reproduced normal `originalExpiry - 1` window. This is copied-instruction
research, **not a change to the strict cache module or an installed hook**.

Natural death is observed at regeneration AIUpdate1A5D40 (Done write), followed
by the exact list's pre-removal boundary22655E: RSI=list, RBP=current node,
RBX=cache, RDI=next node. The candidate saves cache bytes after its final native
update and records the ordered cache lifetime tokens before RemoveAt. It retains
no retired node pointer for later dereferencing. A recovery requested inside
that list's update waits for common boundary22658B, after the list counter has
incremented; the remaining native epilogue only restores registers and returns.
The probe orchestrates recovery immediately after that return. Nested updates
of the same list have not been accepted or proved by these cases.

**Deferring and appending alone is insufficient.** Two required negative controls
show unchanged per-source cadence but different full healing order: the restored
cache moves behind unrelated regeneration. This remains a failed-equivalence
result; matching final HP or each source's separate history does not make it an
acceptable recovery strategy.

The bounded positive candidate instead reconstructs at the old position. It
walks the current list anew, validates its lifetime, the original effect's
lifetime, and unchanged order of surviving cache lifetimes. New, reordered,
canceled or reused current members diagnose before reconstruction. Removed
successors are skipped using their retired lifetime tokens. The first surviving
successor supplies a **fresh current node**, passed to native
`CPtrList::InsertBefore`4077F0 (RCX=list, RDX=successor node, R8=new cache). Native
AddTail4075C0 is used only when no original successor remains. Native RemoveAt,
NewNode and InsertBefore/AddTail execute in this probe; the harness supplies a
free node when the pool is empty. Actual free-node address reuse is covered and
does not confuse the successor selection.

Recovery executes the original98 inline cache allocation/initialization fragment
1BEC70–1BECC3, restores the saved cache state, clears only natural Done, and sets
`remaining = savedRemaining + (newOriginalExpiry - oldOriginalExpiry)
- elapsedListUpdates`. The bounded saved remaining is zero, delta is positive,
counter arithmetic does not wrap, and fewer than15 extra list updates are
accepted. Mode3 phase advances across any elapsed native second boundary; past
heals are not backfilled. This preserves the saved native heal amount, including
5HP mode2, rather than using native Copy's observed reset to1. It creates no
CGameEffect98, calls no Apply98 or broad stats rebuild, and emits no healing
during reconstruction. All subsequent pulses use the native regenerated-list
and native17 paths.

The probe passes12 same-pass cases (modes2/3, counters0/7/14, triggering cache
tail/non-tail),9 head/middle/tail and removed-successor cases with **full ordered
emission/healing history equal to an unchanged long-duration control**, and2
elapsed-pass cases with matching future cadence and no backfill. Eleven negative
cases reject original/list lifetime changes, original Done/expiry, new/reordered
cache lifetimes, cache-address reuse, canceled successors, ClearAll/type-cancel
and leaving the proved time window. Rejection adds no reconstruction write.

A real adapter is a separate native capability: the initializer is an inline
fragment, not an identified callable constructor; it also needs allocator-failure
handling, exact list entry/exit/removal/destructor/reset hooks, preserved original
and list lifetimes, and a safe native insertion call. Optional Lua recovery
orchestration is now implemented in `CBRPQRegenRecovery.lua`, but those native
capabilities and lifecycle hooks remain unimplemented. See
`regeneration-recovery-contract.md` for the exact injected adapter and failure
contract. The probe's generated17 admission is substituted
as documented above, so full ProcessEffectList/reentrant side effects, arbitrary
Haste/Time Stop schedules, save/load recovery and allocation failures remain
unproved. These results justify a focused next prototype, not shipping98 support.

The follow-up batch probe passes24 two-original cases with modes2/3 in all four
combinations, initial counters0/7/14, and same/different natural-removal passes.
Per-list removal history retains retired lifetime positions. All replacement
caches are staged before insertion, then restored in reverse logical order;
their new lifetimes are recognized explicitly when recovering earlier positions.
The full ordered emission/healing history and final HP match unchanged native
long-duration controls. The pure module has28 recovery tests, including canceled
middle successors, cancellation of one pending owner, successive deadline
changes, mixed live/missing updates and failure of the second allocation.

## Queued effects, load and save

The ordinary active-game load path has concrete ordering:

1. LoadGame280670 checks game+3FA8. If nonzero it calls DestroyGame272A20 at2806B2.
2. DestroyGame calls ClearMessages209970 at273738.
3. ClearMessages repeatedly RemoveHead4079F0, then calls each non-null message's
   scalar deleting destructor at209998. It never calls Run.
4. LoadGame later calls Unmarshal2930C0 at280F46. The prototype reset hook is at
   this Unmarshal entry; it is **not** a DestroyGame hook.

`probe_native_queue_clear.py` passes an empty queue and a mixed queue containing
ordinary/HP AddEffect messages, an already-empty payload and a null list entry.
Actual ClearMessages, message destructor1551B0, effect destructor14C8E0 and HP
destructor1A45A0 execute. The original effect is destroyed and message+10 is
cleared without Run/AddEffect. List RemoveHead, string teardown and heap release
are explicit service substitutes. This is cancellation evidence, not full load
execution or Lua callback acceptance.

Normal asynchronous processing instead removes a queued message at2050C5,
calls its Run virtual+30 at2050D3, then destroys it at2050DF. A nested enqueue
does not justify discarding all tokens when the first message returns.

The observed `CMessageAddEffect::MarshalMessage`20A1F0 and
`CMessageFireSpell::MarshalMessage`20BDE0 are **network message encoders**, not
the creature V2 save serializer. They encode remote object IDs from sprite+50/54
and packet-specific fields. CMessageHandler::Broadcast calls virtual Marshal+20
at2098A9, then CNetwork::SendSpecificMessage40CB20 at209919; Send does the same
at2198D8 and219A15. The inspected disk SaveGame path instead calls game/area/world
marshal at289ED3/289F4E/289F64; sprite timed effects use list Marshal1E50E0 at361767.
No queued-message disk serialization was found in this bounded save path.

Consequently an already-applied direct effect is restored through V2 effect
records, while a pending local dose on a normal active-game load is canceled
by native queue destruction; a pointer/dose token should not be persisted to
replay it. Native charge handling is left unchanged. This does not establish
all startup, failed-load, direct-Unmarshal, multiplayer or external runtime-reset
paths. If a supported reset occurs with surviving tagged work, diagnose that
condition rather than silently allow an untagged owned message later.

V2 effect serialization retains source type/resref, caster level, semantic
parameters, Special and absolute expiry. It does not retain ability/effect
ordinal, source actor ID, native pointer or HP private+158. The descriptor-based
direct reader therefore remains sourceType2/native caster level10; no field-copy
test is described as a full native save/load test.

## Linked delivery: concrete next adapter boundaries

**146 mode1 is asynchronous.** Apply1A851A–1A8575 constructs CMessageFireSpell,
then queues it at1A859E and marks the parent done. The message contains source/
target IDs and spell name, not the parent potion family/ordinal. Its Run212DD0
calls CGameAIBase::FireSpell16ABC0 at212E84. A dose frame scoped only around the
original Apply cannot cover this path.

A future adapter must tag that exact FireSpell message while the parent item
record and its dose are known, retain the tag until Run/destruction, then bind
the native child-creation loop to it. CGameAIBase::FireSpell creates children at
16AFCB, adjusts duration using original spell rules at16B00D/16B02B, and may queue
AddEffect at16B100, deliver directly at16B1D8/16B252, or attach to a projectile.
These routes must preserve original sourceType1, SPL name, caster level and gates.
Neither source-name merging nor treating every cast of a linked SPL as a potion
is acceptable. Shared children can also be used by spells/equipment.

146 mode2 is synchronous at1A85C0, but its FireSpell1E4570 still has both child
queue1E483D and direct AddEffect1E4863 paths. A scoped parent trace can establish
child creation provenance only until a native message/projectile outlives it;
that child then needs its own exact lifetime tag. Mode0 queues an action and is
another route, not implicitly covered. Opcode326 conditionally calls the same
FireSpell helper after target filtering at1A7270/1A729A; it is not an ordinary
stat effect to extend.

**Existing self206 is meaningful.** Opcode206 builds an immunity entry with
entry+0xC=0 at1B693E. CheckAdd1CCCF6 passes `(sourceType != 1)` to lookup1F8C90;
the lookup skips those entries for nonspell sources at1F8CAC, but compares them
for sourceType1. Thus a same-name potion ITM146 parent can be admitted while the
SPL children are rejected before the success hook (1CCD1E→1CD076). Keeping native
no-repeat semantics must be explicit; a child success hook cannot refresh an
effect it never sees. Do not remove or bypass original wards as a lineage fix.

**177 is a carrier, not a persistent child.** Apply decodes a child at1A6D25,
copies parent timing/deadline at1A6D86–90, checks its admission only while parent
parameter5+68 is zero, directly calls child Apply at1A6E3B, copies selected state
back at1A6E51–69 and destroys the child at1A6E7A. A child rejection marks the
carrier done. Refreshing/rejecting this transient child is the wrong lifetime.
A future narrow adapter could own an original finite item177 carrier for a
proven simple beneficial EFF, extending only that carrier; it must fingerprint
native copied-back state and preserve filters/gates. Nested177/146, HP state,
adverse payloads and conditional admission remain separate constraints.

For146 children, disk persistence loses parent-potion provenance. A save sidecar
would need proof of the exact saved effect subset/order and a verified descriptor
for each restored occurrence; raw live-list ordinal is not yet a valid key.
Existing saves with indistinguishable shared-child effects remain ambiguous.
No linked reader relaxation or new linked hooks were implemented here.

## Verification and remaining scope

- 25 offline LuaJIT reader tests pass, including lazy projectile-class checking
  against the actual pointer-sized vtable `imageBase+59BFF0`, ASLR and replaced
  classes. Existing direct matching/lifetime-token tests remain green.
- 87 native stat/state cases pass, plus the separate16 earlier19/54/18 cases.
- 2 native queue-cancellation cases pass.
- Regeneration probe passes6 scheduling/deferral cases,6 native OnAdd cases,
  12 cadence comparisons (including two required negative phase cases),2 cached
  deadline cases and an ordinary scheduled-skip control.
- Exact-cache candidate passes30 paired cadence cases,5 native lifecycle cases,
  6 no-mutation negative cases and2 immediate-recovery counterexamples.
  Portrait142 probe passes10 cases; isolated cache module passes22 LuaJIT tests.
- Positional missing-cache recovery adds12 same-pass and9 position/removal
  cases,2 elapsed-pass cases,2 required append-order counterexamples and11
  rejecting lifetime/cancellation cases. A further24 native batch cases and28
  Lua recovery tests support the optional orchestration module; there is still
  no native allocation/insertion adapter or installed lifecycle integration.
- These are isolated instruction/model tests; no game process, native DLL,
  installation, save edits or live playtest was used.

Reproduce the instruction probes with Python, an existing pefile/Unicorn library
directory, and the pinned executable via `--exe` and `--python-libs`. Every probe
checks the executable SHA256 before executing copied instructions.


## Regeneration adapter and lifecycle progress (offline follow-up)

The missing-cache candidate now includes concrete inert allocation/insert/dispose
services (`native-regeneration-service-notes.md`) and an inert lifecycle hook
descriptor generator (`native-regeneration-lifecycle-notes.md`). Service code
passed15 ML64/Unicorn cases; lifecycle code passed36 generated-trampoline cases
plus five real-EEex preprocessing checks. The cache/recovery/service/lifecycle
unit set currently has66 tests. Recovery has32 pure tests and the batch probe
now adds8 observed-append cases to its24 two-original cases. No generator has
been installed, and the Lua buffer/token adapter and Runtime composition remain
unconnected. This follow-up supersedes earlier statements that native allocation
and observed append were wholly missing, without changing the earlier negative
controls or claiming live acceptance.
