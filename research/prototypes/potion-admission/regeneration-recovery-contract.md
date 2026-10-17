# Regeneration recovery adapter contract — offline draft

The native cache needed by an active opcode98 can naturally disappear one world
tick before the original effect expires. Recovering that state **requires native
allocation and ordered list insertion**. An original-expiry write alone cannot
do it. `CBRPQRegenRecovery.lua` supplies bookkeeping and transaction orchestration;
it does not supply or install that native adapter.

Construct the cache module as `cacheFactory(api, recoveryFactory)`. The optional
second argument is the returned factory from `CBRPQRegenRecovery.lua`.
`cache.recoveryEnabled` reports whether the factory was supplied. Without it,
the earlier strict module still diagnoses missing cache lineage. A runtime whose
manifest owns98 must treat an absent/unverified recovery adapter or lifecycle
hooks as a **startup capability failure**, rather than advertise the live-cache
subset as complete regeneration support. The draft now contains the tested inert raw native service generator
`CBRPQRegenServices.lua` and lifecycle descriptor generator
`CBRPQRegenLifecycle.lua`. The Lua scratch-buffer/lifetime adapter now exists as the independently tested
`CBRPQRegenAdapter.lua`; Runtime/JIT composition remains unconnected and no
recovery hooks are installed. See `regeneration-adapter-contract.md`.

## Existing transaction

The existing sequence remains:

1. `transaction = cache.prepare(corePlan.refresh)` — read-only native inspection.
2. `Core.commit(corePlan)` — writes original effect expiries.
3. `transaction.commit()` — revalidates every target, writes exact live-cache
   countdown deltas, and commits missing-cache recovery tickets as a batch.

For a missing cache outside its list update, step3 allocates all replacement
caches for that list before inserting any. During an update, step3 records the
latest pending deadline; reconstruction runs at that exact list's common
after-counter-increment exit. Repeated doses update the same pending original
without creating another cache. Multiple originals, request order, and overlapping
families use the same per-list ordered batch. Different lists remain independent.

All targets retain original lifetime tokens. A per-list logical order retains
retired cache lifetimes across same-world-time removal passes. Reconstruction
inserts later logical positions first, records its own new lifetime at the old
position, then finds each earlier successor by a fresh current-list traversal.
This handles two missing originals even if the first cache disappeared in an
earlier pass or an intervening successor was removed. It does not infer identity
from equal amounts, phase, resource name or native pointer alone.

The bounded candidate supports only natural remaining0 death for98 modes2/3,
uncanceled originals still alive in the `oldExpiry - 1` world tick, interval1–32767,
nonwrapping bounded list counters and fewer than15 elapsed list updates. Missing
cache shortening is rejected; ordinary live-cache shortening retains its existing
positive-countdown guard. A genuine observed native AddTail can extend logical order, including after a
retired tail. Unexplained new/reordered members and nested updates of the same
list still diagnose because their order/reentrant behavior has not been proved. Different-list nesting is covered. These are explicit prototype
limits, not permission to silently skip unsupported potion records.

## Additional injected adapter

The common cache adapter remains unchanged. `api.cache(pointer)` must additionally
return `mode`, `interval`, `phase` and `amount` for a regeneration cache. The new
`api.recovery` table must have all five functions below; a missing function fails
factory construction.

| Function | Exact contract |
| --- | --- |
| `list(spritePointer)` | Read-only `{pointer, identity, counter, entries}` for the actual regenerated list. `identity` is an opaque table token for the list lifetime. Each dense ordered entry is `{pointer, identity, node}`: cache pointer, opaque **cache lifetime** token, fresh current node address. Include unrelated caches, with valid lifetime authority; do not fabricate identity from pointer equality. |
| `capture(cachePointer)` | Copy exactly48 bytes of the currently live native cache into an immutable Lua string. No retained native userdata or native pointer-backed buffer. |
| `allocate(state, changes, listContext)` | Receive a fresh validated list context and return a detached fresh `{pointer, identity}`. Use the reviewed native initialization, then restore the saved state, changing only Done tofalse, phase and signed remaining countdown from `changes`. Preserve amount and all other native fields. Native Copy is unsuitable: it resets the heal amount. This function must not Apply98, dispatch a spell/effect/heal, rebuild stats, advance the list, or invoke gameplay callbacks. |
| `insert(listPointer, listIdentity, allocation, successorNode)` | Verify the exact list and insert the detached cache before the supplied **current** node, using native InsertBefore; zero means AddTail. No effect/AI processing or callbacks. The module immediately checks exact resulting order, member lifetimes, list identity and counter. |
| `dispose(allocation)` | Destroy/free an allocation known to remain detached after a pre-insertion failure, retiring its lifetime token. Never infer detachment after an insertion error. |

Allocation returns a token already registered with the native lifetime authority.
It must not call `cache.onAppend` as though original98 Apply ran. The module binds
the recovered cache to its original internally after insertion. Ordinary cache
destructor bookkeeping for a detached, unowned allocation is permitted; gameplay
reentry or recovery lifecycle reentry during adapter allocation/insertion is not.
The module detects that latter reentry and diagnoses it. This guard is **not**
proof that an arbitrary native allocator wrapper is safe.

The native candidate uses the pinned inline initializer1BEC70–1BECC3, which is not
an identified callable constructor. A real adapter still needs reviewed heap
allocation, initialization, exception/failure handling and native-call ABI code.
InsertBefore4077F0, AddTail4075C0 and NewNode407890 are separate native calls;
NewNode may need a fresh node pool. The copied-instruction probes substitute those
allocation services. No module currently resolves these addresses or patches them.

## Lifecycle callbacks

Existing `onAppend`, `onCopy`, `onCacheDestroy`, `onOriginalDestroy` and `reset`
remain on `CBRPQRegenCache`. Original destruction cancels pending recovery without
reading freed native memory. Reset invalidates old opaque update frames; a later
exit carrying such a frame returnsfalse without touching the new generation.

When recovery is enabled, the cache module additionally exposes:

| Callback | Native point and meaning |
| --- | --- |
| `frame = onUpdateEnter(spritePointer, listPointer)` | Entry226500 for the actual list invocation. Keep this opaque frame for its matching exit. Different lists can nest; same-list nesting currently diagnoses. |
| `onNaturalDeath(cachePointer)` | At1A5D40 before native writes Done due to countdown expiry. Marks a candidate only; cancellation is not natural death. |
| `onBeforeRemove(cachePointer)` | At22655E, after the final native AIUpdate and before RemoveAt. Captures final phase/remaining/amount, logical order, original expiry and identities. A normal death outside the bounded recovery window creates no recoverable snapshot. |
| `onUpdateExit(frame)` | Exactly22658B, after the native counter increment. Checks the matching invocation and reconstructs any pending batch for this list. No active iterator may see inserted caches in the old pass. |
| `onCancelList(spritePointer)` | Before ClearAll or relevant type5 cancellation. Clears snapshots/pending work so cancellation cannot be turned into restoration. |
| `onListDestroy(spritePointer)` | Clears the same state; the external lifetime authority must also retire the list token. |
| `onNativeAppend(spritePointer, cachePointer)` | A genuine native tail insertion extends logical ordering. Existing `onAppend` already calls this, so never notify the same append twice. |

Destructor and Copy callbacks must cover native cache lifetimes, including
unrelated caches whose tokens serve as successor anchors. A cache at a reused
address is a new lifetime. Node addresses are never retained as recovery identity.
List replacement/ClearAll must invalidate pending work before applying rebuilt
effects. Operator=226480 clears inline and needs its own observation; ClearAll
alone does not cover it. The callbacks are not presently wired into an engine.
`native-regeneration-lifecycle-notes.md` documents the tested inert hook
descriptors, exact frame keys, generic-append filtering and deduplication.

## Reentry, failure and Runtime integration

`prepare`, validation, list reads and snapshot capture do not allocate **native
caches** or invoke native engine methods. They do allocate ordinary Lua data.
`transaction.commit()` may allocate/insert immediately; `onUpdateExit()` may do
the same for deferred work. Native allocation/insertion must have the restricted
behavior above. A generic call through EEex is not enough to prove it.

The root Runtime's `admitting` flag has not been integrated or tested with these
native calls. Immediate reconstruction occurs inside the admission callback,
where that flag may be true. Deferred reconstruction occurs at a native list
exit, with a different surrounding call stack. The unhooked service path has no gameplay/Lua-dispatch call. Installing the
proposed hooks introduces our own AddTail and cache-destruction observations,
so the bridge must explicitly recognize staged allocations and permit pure
lifetime retirement while excluding ordinary recovery reentry. The Lua adapter
and combined runtime integration remain untested; no general safe-reentry claim
is made.

There is **no rollback guarantee** after Core expiry writes, live-cache countdown
writes, or a native insertion that fails after mutation. Pre-insertion allocation
failure disposes already staged detached caches where possible; disposal failures
are included in the diagnostic. An insertion failure does not blindly free the
possibly inserted cache. The caller must stop the feature and surface the error,
not retry, silently continue or describe this as atomic. Remaining detached
allocations after an insertion failure also require controlled cleanup by a
future native adapter; current orchestration deliberately does not guess which
objects an erroring insertion adopted.

## Evidence

`tests/test_potion_regen_recovery.py` has32 pure LuaJIT tests, alongside the22
existing exact-cache tests. They cover batch order, separate removal passes,
pending deadline changes, cancellation, lifetime reuse, nested different lists,
phase advancement without backfill, adapter absence, wrong allocation output,
and before/after-mutation failures. Native-reader tests run alongside these.

`probe_native_regeneration_batch.py` passes24 two-original copied-instruction
cases: both mode2/3 combinations, counters0/7/14, and same/different removal passes.
Eight additional native cases cover observed append before/between removal passes.
Every case stages both native initialized caches before insertion and matches
the unchanged long-duration control's **full ordered native emission/healing
history and final HP**. The earlier single-recovery probe retains its append-only
ordering failures as required negative controls and its elapsed-boundary
no-backfill case. These probes do not execute full ProcessEffectList, generated17
admission, live hooks, game/DLL processes or a full save/load.
