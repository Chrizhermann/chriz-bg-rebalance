# Regeneration composition adapter — inert offline draft

`CBRPQRegenAdapter.lua` returns a factory:

```lua
adapter = factory(api, cacheFactory, recoveryFactory)
transaction = adapter.prepare(corePlan, sprite)
Core.commit(corePlan)
transaction.commit()
```

No module load/factory call installs hooks, exposes Lua globals, JITs code or
executes a native service. `prepare` reads and validates; it performs no native
allocation or effect/cache write. The existing Core remains responsible for all
original expiry writes. The transaction is one-use and performs exact countdown
changes or missing-cache recovery through the existing real Cache/Recovery
modules. It must run immediately after Core without yielding or another engine
operation. Root Runtime/Lab/Core were not changed.

## Required injected capabilities

All functions use numeric native pointers unless stated otherwise. Missing
capabilities fail factory construction; ownership98 must not silently enable
only the live-cache subset. Native service functions must come from the separately
byte-validated `CBRPQRegenServices` plan and its calling wrapper.

| API | Contract |
| --- | --- |
| `imageBase` | Exact numeric base of the pinned executable. |
| `ptr(object)` | Resolve the sprite/effect object passed to `prepare` or Core record. No identity inferred from userdata equality. |
| `now()` | Current unsigned world tick. |
| `original(pointer)` | Fresh owned effect descriptor or nil: `{identity,opcode,timing,expiry,done}`. The identity must be the same authoritative original lifetime token used by Core. No retained freed userdata reads. |
| `isCurrentOriginal(spritePointer,originalPointer,identity)` | Fresh proof that this exact effect/lifetime is currently in that sprite's timed list. |
| `spriteIdentity(spritePointer)` | Authoritative opaque table lifetime token, or nil for an unowned/unknown sprite. This is explicitly required; this adapter does not invent a token from native objectID/address. Native sprite lifetime wiring remains unproved here. |
| `readPtr/readU32/readI32/readU16(pointer)` | Exact native scalar reads. Signed countdown uses I32, flags/counts use U32, phase/amount use U16. |
| `readBytes(pointer,length)` | Immutable Lua string of exactly length bytes. |
| `writePtr/writeU32/writeU16(pointer,value)` | Exact native scalar writes, with ordinary synchronous failure semantics. |
| `writeBytes(pointer,string)` | Exact scratch-buffer write. |
| `allocScratch(length)`, `freeScratch(pointer)` | Caller-owned scratch allocation. Engine never adopts these buffers. Null allocation diagnoses; retain ownership on a thrown free. |
| `services.allocate/insert/dispose(requestPointer)` | Bound raw service calls returning the documented DWORD status. They use the engine heap for cache/pool allocations. They may synchronously invoke only the precisely recognized observation hooks below. |
| `report(message)` | Record a structural failure. Callback wrappers protect even an erroring reporter; first failure is retained by `status`. |

All current list traversals check vtable58F528, count/head/tail consistency, both
node directions, duplicate pointers/cycles, bounded count/counter and positive
native pool block count. Regeneration-only fields are read only after its exact
vtable598B18 check. Unrelated cache classes can be only0x20 bytes; their common
Done/Cancel fields are sufficient for successor checks and are not overread.

The adapter creates cache tokens on first proved observation and retires them on
the five native destructor callbacks. List tokens are tied to the authoritative
sprite token, retired by explicit list/sprite destruction or reset. It rejects a
sprite address reused without retirement. No token or pointer is serialized.

## Lifecycle interface

`adapter.callbacks` has exactly the names/arguments documented in
`native-regeneration-lifecycle-notes.md`: updateEnter/updateExit, naturalDeath,
beforeRemove, clear/removeType/replace/listDestroy, cacheDestroy/copy,
appendOwned/append. These are functions to register later, not registered globals.

Every update gets a stack frame or an unowned sentinel. Exact entryRSP and list
must match the most recent exit. Known sprites require native delta1; unknown
invocations are paired without arbitrary sprite memory reads. Reset invalidates
old frames but retains their comparison-only sentinels for late exits. It does
not treat a later exit as permission to inspect old native memory.

Generic AddTail notification with returnAddress=imageBase+1BEDE5 is deferred to
appendOwned. That callback binds original98 lineage and updates logical ordering
once. Other genuine appends to a known current sprite list update order normally.
Copy creates lineage and a new token; it is not an append event.

Also call `adapter.onOriginalDestroy(pointer)` before original retirement,
`adapter.onSpriteDestroy(pointer)` before retiring the authoritative sprite token,
and `adapter.reset()` at the separately proved reset boundary. These explicit
methods throw if misused and must be protected by the outer native callback
bridge. The generated lifecycle callback wrappers themselves catch/report errors,
return false and halt this adapter; false is not a native control-flow decision.

## Native service observation and ownership

The adapter retains each0x40 request and0x30 snapshot scratch allocation as soon
as it exists. A successful service allocation registers its cache token while
still detached. Insertion rechecks exact list identity/counter and current
successor node before invoking the service. After insertion it checks the returned
adopted node and current membership before releasing scratch buffers.

During a native service, only these callbacks are tolerated:

- An AddTail completion for the **exact staged cache and target list** during its
  insert call. Fresh list/node/counter/tail checks must pass. It does not invoke
  ordinary recovery append bookkeeping; Recovery records its known replacement.
- A destructor for the **exact detached cache** during its dispose call. Only
  the token is retired; it does not recursively call recovery lifecycle methods.

All other lifecycle reentry halts and reports, including copying another cache,
changing lists, or an unrelated append during the service. No broad busy-flag
suppression or native stats rebuild is used. A callback error cannot be hidden
merely because the raw native service later returns success.

`status()` returns `{halted,error,pending}`. Pending entries retain request/cache
addresses plus adopted/uncertain flags. `cleanupDetached()` can dispose only
known detached allocations (including service allocation status4 ownership) or
scratch allocated before any engine call. It never frees adopted/uncertain
cache/pool memory and does not resume a halted feature. A service exception may
have occurred after native mutation; it marks ownership uncertain. Reset refuses
to forget unresolved allocation handles.

Allocation and native insert failures remain possible after Core expiry writes.
There is no rollback promise: the original may already have a new deadline.
An error after adoption may retain scratch buffers for diagnosis; it must not
free the engine-owned cache. Recovery may have earlier successful cache writes
or insertions in the same batch. The outer Runtime must stop the feature and
surface this state, not retry or claim atomic success.

## Verification scope

`tests/test_potion_regen_adapter.py` currently has24 passing tests using the real
adapter, Cache, Recovery and Core Lua modules, with byte-addressed native memory
and explicit native-service doubles. It covers live/immediate/deferred and
multi-original paths, order/phase, deduplicated and unrelated appends, small
unrelated cache headers, frame sentinels, cancel/replace/type/reset, cache reuse,
sprite reuse rejection, malformed native lists/pool bounds, failures before/after
adoption, retained cleanup ownership and forbidden service reentry.

Separately, the actual generated native services passed15 copied-instruction
ML64/Unicorn cases and the generated lifecycle trampolines passed36 cases.
Combining the adapter tests with those proofs is still not executing their
native services and real Lua callbacks together inside a game/JIT environment.
Authoritative sprite lifetime hooks, full composition, live-game behavior and
full save/load remain outstanding. The adapter adds no permission to activate
or install the research prototype.
