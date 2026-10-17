# Regeneration native services — pinned offline evidence

Build: BG2EE2.7.3.0, executable SHA256
`b51093a49140b2b8a7c046b4652bb8e535be24ebbc12b1d735e0b94217a14d57`.
All addresses below are RVAs. No game/EEex DLL was executed and no hook installed.

`CBRPQRegenServices.lua` now generates concrete inert Win64 service assembly and
an optional EEex Lua C-function wrapper. `plan(api)` checks pinned native bytes
using `EEex_GetImageBase`/`EEex_ReadU8`, then returns assembly; it performs no JIT,
native call, registration or patch. `generate(base)` only generates text and is
used by the offline probe. Runtime integration must use the validated plan.

## Heap, class and initialized state

Opcode98 allocates0x30 bytes at1BEC70–1BEC75. The inline initializer1BEC8A–1BECBE
sets the following fields and makes no calls after allocation:

| Offset | Native initialization |
| --- | --- |
|00 QWORD|vtable `imageBase+598B18`|
|08 DWORD|Done0|
|0C DWORD|Canceled0|
|12 WORD|cache type5|
|14 DWORD|−1|
|18 QWORD|1: interval1, phase0, update counter0|
|20 DWORD|`FFFF0000`: mode0, amount-remainingFFFF|
|24 WORD|heal amount1|
|28 DWORD|remaining0|

Bytes10–11,26–27 and2C–2F remain allocator contents. The generated initializer
matches **all48 bytes** of the copied native initializer for prefill00/7F/A5,
including untouched padding. The allocation service restores the complete48-byte
natural-death snapshot, changing only Done08, phase1A and remaining28. Thus it
preserves every scalar and padding byte without invoking native Copy (which
resets heal amount), Apply98, an effect constructor, or healing.

Native scalar destructor1A4750 changes only the vtable to598A40 and, when its
flag's bit0 is set, calls delete45E690. That chain reaches free-base51E414. The
cache contains no separately owned pointer/resource requiring another destructor.

Native operator new4F7A88 can invoke new-handler51A7EC and throw. NewNode407890
can reach the same path through CPlex::Create407AF0. The generated service avoids
both paths. CRT initialization52A3DC calls imported GetProcessHeap and stores
the result at34B8590. Malloc-base51E486 calls HeapAlloc via IAT58A1B0 with that
exact handle and flags0. Free-base51E41E calls HeapFree via IAT58A1B8 with the
same handle and flags0. The service uses those same heap imports and handle
directly, so null allocation does not invoke the CRT new-mode/new-handler path.
Native destruction later frees the adopted cache and node pools on the same heap.

## Reserved node pool and adoption

The native node size is0x18; CPlex header size0x10. Its first QWORD links the prior
pool. Nodes use next00, previous08, data10. The list fields are head08, tail10,
count18, free-head20, pool-chain28, block-count30. Pool count is the actual positive
native list block count, not a potion-record limit. The generated service uses
64-bit size arithmetic for `0x10 + count*0x18`.

Allocation stages both a detached cache and a detached pool before any live-list
write. At insertion:

- If the list already has a free node, the unused reserve is freed first.
- Otherwise the reserve is linked as a native CPlex pool and the free-node chain
  is built using the exact native descending-node order.
- Native InsertBefore4077F0 or AddTail4075C0 then calls native NewNode407890.
  A free node is guaranteed, so NewNode takes its nonallocating path.

The only calls on the generated insertion path are the optional HeapFree and
the pinned native list routines. They contain no effect application, virtual
gameplay dispatch or Lua callback. The probe treats any entry into operator-new,
CPlex::Create or new-handler as failure. Windows heap implementation/instrumentation,
heap-corruption exceptions and additional patched hooks are outside that proof.

Native ClearAll plus CObList RemoveAll successfully destroys the adopted caches
and frees every adopted pool in the probe. A detached allocation instead uses
the native cache destructor and frees its still-detached reserve. Actual lifecycle
hooks may therefore run during detached destruction; they must permit ordinary
unowned lifetime retirement without attempting gameplay or recursive recovery.

## Exact raw service ABI

Every generated function takes RCX pointing to a caller-owned64-byte request,
preserves Win64 nonvolatile registers, uses aligned call stacks and returns a
status DWORD in EAX. Buffers/list/node pointers must already be validated by the
Lua adapter. The request layout is:

| Offset | Field |
| --- | --- |
|00 QWORD|immutable48-byte snapshot buffer pointer|
|08 DWORD|positive replacement signed countdown|
|0C WORD|replacement phase, less than positive signed interval|
|10 DWORD|actual positive list pool block count|
|18 QWORD|detached cache output; initially0|
|20 QWORD|detached pool output; initially0|
|28 QWORD|target native list pointer|
|30 QWORD|fresh successor node;0 means tail|
|38 QWORD|adopted node output; initially0|

`allocate(request)` returns0 on success;1 invalid request/snapshot/heap state;
2 cache allocation failure;3 pool allocation failure with cache cleanup complete;
4 cleanup failure with the detached cache explicitly retained at18. It never
changes a live effect or list. The output pointers are not hidden on failure.

`insert(request)` returns0 on adoption;1 invalid request/current pool-size mismatch;
2 failure freeing an unused reserve. On success both detached output fields are
zero and38 contains the native adopted node. The list now owns the cache and
any pool linked into its chain. No throwing allocator is used during insertion.

`dispose(request)` invokes the native scalar cache destructor for any remaining
detached cache and frees any remaining detached pool. It returns0 on success,
1 invalid request,2 pool-free failure. Successfully released fields are zeroed.
Never pass it an uncertain possibly adopted pointer after an unrelated failure.

`luaWrapper(serviceAddress)` generates a Lua C-function wrapper: one validated
numeric request-buffer pointer in argument1, one integer status returned. It uses
the existing EEex `Hardcoded_lua_tointegerx`/`Hardcoded_lua_pushinteger` labels.
EEex_Assembly.lua399–402 supplies JITNearAsLuaFunction/ExposeToLua for such a wrapper;
no new compiled EEex API is required by this calling convention. No wrapper has
been JIT-created or exposed here.

## Mapping to the recovery module

`api.recovery.allocate(state, changes, listContext)` now receives the freshly
validated list context as a third argument. A future Lua native adapter can read
the list block count, allocate scratch request/snapshot buffers through EEex,
call the generated allocate service, and return
`{pointer=cachePointer, identity=registeredFreshToken, request=ownedRequestHandle}`.
Scratch buffers are never adopted by the engine and may use EEex's own allocator;
cache/pool memory must use the service's game heap. The adapter must retain explicit
ownership of status4 failures rather than lose the request while throwing.

`api.recovery.insert(listPtr,listToken,allocation,successorNode)` fills request28/30,
checks the service status and retains enough handle state to distinguish adoption.
The orchestration module checks the exact resulting native list order/lifetimes.
`api.recovery.dispose(allocation)` uses the retained request only while detached,
then frees scratch storage. Registration/retirement of opaque cache tokens is a
separate lifecycle operation; allocation must not impersonate Apply98's append
callback. The inert Lua buffer/token composition is now implemented in
`CBRPQRegenAdapter.lua` and tested with explicit native-service doubles; see
`regeneration-adapter-contract.md`. It remains unconnected to Runtime/JIT.

Immediate calls can occur while Runtime.admitting is true; no Runtime wiring was
changed. Allocation/insertion have no gameplay/Lua-dispatch calls on the pinned
path above. Native destructor hooks and the chosen EEex buffer/call wrappers must
still be checked as a whole before enabling that path. The existing no-rollback
warning after Core expiry writes remains applicable.

## Observed native appends

An unexplained new list member still diagnoses. A **proved AddTail observation**
can now extend the logical order safely through
`cache.onNativeAppend(spritePointer, cachePointer)`. It verifies the new lifetime
is the current tail and every prior live member remains in recorded order, then
adds it after all previous logical positions, including retired ones. This also
handles a reused cache address when the destruction/creation authority supplies
a fresh lifetime token. A forged middle-insert notification or another unexplained
mutation is rejected.

Existing `cache.onAppend(original,cache,sprite)` invokes this internally even if
the original is unowned, before deciding whether to bind owned98 lineage. Do not
send a second onNativeAppend for the same event. The original98 append point is
1BEDE5, after AddTail; it exposes RDI=original, RBX=cache, RBP=sprite. Other native
append routes need their own genuine observations, not an inferred source match.

## Verification and next native lifecycle probes

-15 generated-service cases pass after ML64 assembly and Unicorn execution:
  byte-exact initializer, two-mode restore/adopt/free, real native middle/tail and
  pool exhaustion, both allocation failures, cleanup ownership, invalid requests,
  detached native destruction and Lua C-function ABI. Windows heap/Lua C API are
  explicit service substitutes; no game/native DLL executes.
-5 pure planning tests verify inert generation, signature drift and relocation.
-32 recovery plus22 live-cache Lua tests pass.
-24 two-original native batch cases remain green;8 more cases prove observed
  native append before/between removal passes preserves full ordered healing.

The next isolated hook generator/probes must cover exact list entry/exit pairing,
natural death versus cancellation, pre-removal capture after final phase change,
ClearAll/type5 cancel/list destruction, original/cache destruction and Copy,
and real append observation. Verify register/flag/XMM preservation and watchdog
behavior at every site, including errors. Those hooks and the Lua buffer/token
adapter remain inactive until the separately reviewed integration step.
