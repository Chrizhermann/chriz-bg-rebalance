# Inert regeneration lifecycle descriptors — pinned offline evidence

`CBRPQRegenLifecycle.lua` supplies `validate(api, config, watchdog)` and
`prepare(api, config, watchdog)`. It has no install/JIT entrypoint, automatic
loading, callback registration or engine write. `prepare` returns
`{base, watchdog, descriptors}`; each descriptor is
`{key,address,restoreSize,stackMod,labels,assembly}`. A future composer must pass
these through the existing EEex BeforeRestoreWithLabels machinery **inside**
`CBRPQWatchdog.withPreservation`. Preparation requires all configured global
callbacks already to exist, validates every pinned code/vtable byte first, then
builds assembly. No hook is installed here.

Evidence is the SHA256-pinned BG2EE2.7.3.0 executable
`b51093a49140b2b8a7c046b4652bb8e535be24ebbc12b1d735e0b94217a14d57`
and local EEex1.3.0 assembly/Watchdog scripts. All locations below are image RVAs.
The hook bytes are platform capability guards, not assumptions about potion data.

## Exact callback contract

All pointers are numeric synchronous keys, all callback returns ignored. Each
callback must catch/report its own bookkeeping errors and invalidate transient
feature state; the generated error branch restores native state and continues.
No borrowed effect userdata is introduced here.

| Config callback | Native point | Arguments / required meaning |
| --- | --- | --- |
| `updateEnter` |226500 before prologue| `(list,sprite,delta,entryRSP)`. Observe unowned invocations too; use a sentinel so nested exit pairing remains exact. Only a validated actual sprite/list association may enter recovery. |
| `updateExit` |22658B after both counter-increment paths| `(list,entryRSP)`. Current native RSP+56 equals the entry key. The bridge retrieves the opaque recovery frame saved at entry. No iterator from this invocation remains active. |
| `naturalDeath` |1A5D40 before Done=1| `(cache)`. Candidate only; final phase/heal may still occur. |
| `beforeRemove` |22655E before RemoveAt argument setup| `(list,cache,currentNode)`. Final native AIUpdate completed; capture only when natural marker, Done/Cancel/remaining, identity and original window agree. Original RemoveAt CALL226564 remains in place. |
| `clear` |1F8990 entry| `(list)`. Cancel pending/snapshots before any cache destruction. |
| `removeType` |2265A0 entry| `(list,low16Type)`. Only type5 is regeneration cancellation; other types must not cancel owned regeneration. |
| `replace` |226480 entry| `(destinationList,sourceList)`. Destination cleanup is inlined and does not call ClearAll; it separately invalidates pending work. |
| `listDestroy` |150E90 entry| `(list)`. Cancel and retire list lifetime. The wider embedded-list lifetime authority still needs integration review, not pointer equality. |
| `cacheDestroy` |1A46C0/F0,1A4720/50/80 entries| `(cache)`. Retire cache lifetime before memory reuse. Twelve pinned persistent-cache vtables598A40..598B48 map to these five bodies; this includes unrelated successor anchors. |
| `copy` |1DCAE9 before epilogue| `(oldCache,newCache)`. RBX/RDX are still valid; RAX also equals newCache. Lineage only: no adoption/order event yet. Native Copy does not preserve heal amount, so is not a recovery constructor. |
| `appendOwned` |1BEDE5 after original98 AddTail| `(original,cache,sprite)` from RDI/RBX/RBP. Original AddTail CALL1BEDE0 stays in place. |
| `append` |4075F0 nonempty /407608 empty AddTail completion| `(list,cache,node,nativeReturnAddress)`. Both tail/head fields are updated. An assembly vtable check filters out other list classes before Lua. A validated sprite association is still required; snapshot lists share the same class. |

The generic tail callback precedes `appendOwned`. The bridge can use its exact
native return address `imageBase+1BEDE5` to defer notification to `appendOwned`:
`cache.onAppend` already invokes `onNativeAppend`, including for an unowned
original. Never send duplicate append events. Other genuine ordinary appends use
`onNativeAppend` after translating validated list identity to sprite.

Recovered allocations are a separate explicit category. The service's AddTail
can trigger `append`, and its detached disposal can trigger `cacheDestroy` after
these hooks are installed. The bridge must recognize its own staged allocation,
retain the recovery module's ordered replacement bookkeeping, and permit only
pure token retirement for detached destruction while `recovery.busy`. Feeding
these back as ordinary native recovery events would cause false reentry. There
is no Runtime integration claiming this behavior yet.

Existing original-effect destruction/reset transport remains required. This
module does not duplicate it. List replacement/destruction, reset, copy and
unknown cache lifetimes must use opaque lifetime tokens; node/address equality
alone is insufficient. Replacements in an update and nonlocal native unwinding
need exact failure behavior from the future bridge.

## Preservation and evidence

Each trampoline saves flags, all volatile GPRs and XMM0..5 around the Lua call.
The existing scoped Watchdog wrapper preserves flags/XMM around its own native
checks too. The generic list-class filter preserves flags/RAX on match and skip.
All overwritten instructions are position-independent loads/stores or stack
operations replayed byte-for-byte. No relative CALL or branch is moved.

Five preprocessing tests use real local EEex Lua expansion with read-only native
bytes and capture-only JIT stubs. They check all signatures/vtables, capability
errors, balanced normal/error paths and scoped Watchdog preservation.
Two native test methods execute36 generated ML64 trampolines under Unicorn:
17 sites with callback success/error, plus both mismatched-list skip paths.
Clobbering Lua/Watchdog service stubs verify exact callback arguments, native
GPR/XMM/flags, original stack and replay behavior against the original bytes.
They do not execute Lua DLLs or a game process.

Together with cache/recovery/service planning,66 current tests pass. Separate
native service15, batch24+8, recovery and cache probes retain their explicit
Windows allocation, message/heal admission and bookkeeping substitutes.

## Remaining integration proof

The concrete hook sites and generated trampolines are tested independently.
They have not yet been composed with the native allocation service, Lua request
adapter and actual recovery module in one full native update/admission sequence.
That composition must verify sentinel pairing on empty/nonempty/nested lists,
cancellation/replacement during an update, staged allocation callback filtering,
all embedded-list lifetimes, and cleanup after callback errors without a retry.
No native write-error rollback, general engine reentry, complete linked-effect
coverage, full game save/load or live-game acceptance is claimed.
