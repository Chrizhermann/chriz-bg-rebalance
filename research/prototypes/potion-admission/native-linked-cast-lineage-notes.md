# Original opcode 146 mode 1: queued cast and child lineage

Research only, 2026-10-09. No linked-cast transport hooks were implemented or
installed. Native source and a copied-instruction probe support a narrow
original-effect route: transfer an opaque potion-dose token to the exact native
cast message, then to its original child effects. Keep the child's native SPL
source, caster level, target, duration, probability and admission checks.

This is a prerequisite for linked-potion support, not that support's completion.
Logical potion owner/child metadata, saved provenance, native opcode 206 policy,
hook generation/integration and live acceptance remain separate work.

## Inputs and evidence level

- Executable: `%USERPROFILE%\Games\CBR-TimeStop-2.7.3.0\Baldur.exe`, BG2EE
  2.7.3.0, SHA256
  `b51093a49140b2b8a7c046b4652bb8e535be24ebbc12b1d735e0b94217a14d57`.
- Function names: the same lab's
  `EEex\loader\v2.7.3.0\bg2ee\function_names.db`.
- EEex 1.3.0 source: the same lab's `EEex_scripts`, especially
  `EEex_Projectile_Patch.lua` and `EEex_Projectile.lua`.
- All addresses below are RVAs, with native image base `0x140000000`.
- Reusable probe: `probe_native_linked_cast.py` in this directory. It reads and
  hashes the executable, copies its instructions into Unicorn, and never loads a
  game/EEex DLL or touches game state.
- Full FireSpell disassembly:
  `%USERPROFILE%\AppData\Local\Temp\cbr-potion-inventory-20261009\native-linked-FireSpell-disassembly.txt`.
- Result:
  `%USERPROFILE%\AppData\Local\Temp\cbr-potion-inventory-20261009\native-linked-cast-result.json`.

The probe executes original `CGameEffectCastSpell::ApplyEffect`,
`CMessageFireSpell::Run`, its actual destructor, `CGameAIBase::FireSpell` through
ability selection and its child loop, direct/queued native `AddEffect`, native
`CheckAdd` control flow, `ResolveEffect`, op90, and instant-projectile original
pointer delivery. Resource loading/child construction, allocation, lookup,
admission predicates and scheduling are explicitly listed test doubles.

At `16B348` the probe deliberately omits FireSpell's feedback, trigger and area
registration tail and uses its real balanced epilogue `16ADDF..16AE18`.
Projectile Fire is invoked explicitly after this omitted scheduling tail. Thus
this is not a complete emulation of a spell cast or the game scheduler.

## Parent to cast-message ownership

`CGameEffectCastSpell::ApplyEffect` starts at `1A84B0`.
Its nonzero/non-2 branch is asynchronous; require p2 **equal to 1** for the
proposed capability, rather than treating all other values as equivalent.

At `1A851F` it allocates a 0x20-byte message. It sets vtable `590D90`, source
actor ID from original effect `+110`, target actor ID from the passed sprite,
and an owned CString for original effect resource `+30`:

| Message offset | Native value |
|---|---|
| `00` | vtable `imageBase+590D90` |
| `08` | source/caster actor ID |
| `0C` | target actor ID, base message routing field |
| `10` | owned CString spell resource |
| `18` | target actor ID used by Run |

There is **no parent effect pointer or dose token** in the message. Native
sourceID=-1 fallback to targetID occurs at `1A84ED..1A84F0`; leave it native.
The parent becomes done at `1A886E`. Its destruction must not cancel ownership
already transferred to a live cast message.

Proposed observation before `1A8594` restores the seven bytes
`48 81 C1 68 17 00 00` (`add rcx,1768h`). Here RSI=original parent,
R14=cast message and R15=target sprite. The original call `1A859E`
(`E8 1D C9 05 00`) remains at its native address. Register the exact message
identity before that call can synchronously reject, destroy or reenter.

Source-only queue trace: `AddMessage 204EC0`, commtype1, R8=0, tailcalls
`Send 219810` through `204F27`. The local path at `219A77..219A7D` adds the
**same** message pointer to the queue. Source lookup failure can delete the
message. Remote paths serialize it and can delete the original: a pointer
sidecar does not survive that serialization, so remote lineage is unproved.

Vtable `590D90` slot0 is `165200`. The symbol DB names it another message's
scalar destructor because this body is shared/code-folded. Its entry bytes are
`48 89 5C 24 08`; it destroys CString `+10`, changes to the base vtable and
deletes 0x20 bytes when requested. An entry observer must only retire known
cast-message identities, checking the pre-destruction class where appropriate.
Other messages sharing this body are unrelated. The cancellation probe executes
this destructor with no Run and proves no children are produced.

## Run and an exact FireSpell frame

`Run 212DD0` entry bytes are `40 53 48 83 EC 60`: push RBX, subtract 0x60.
RBX becomes the message. Run requires both IDs to be valid, resolves each
object with `GetDeny 276700`, and checks object type. All ordinary early exits
join `212E89` (`48 8B 4C 24 58`), so entry/leave observers can be balanced.

At `212E84` the original bytes `E8 37 7D F5 FF` call `FireSpell 16ABC0`.
Arguments are caster RCX, original resref RDX, target R8, R9=0; stack arguments
are -1, null optional parameter block, 1, 1. Native return address is
`imageBase+212E89`.

For original Run entry RSP=S, FireSpell entry RSP is **S-0x70**. FireSpell's
seven pushes and RBP setup make its entry RSP **RBP+0xB8**. The child boundary
can require both:

1. `RBP+0xB8 == currentTrackedRun.originalEntryRSP-0x70`;
2. `[RBP+0xB8] == imageBase+0x212E89`.

Use a nested stack of tracked Run invocations, keyed by the exact message
lifetime, not a single global active dose, same-tick time or spell name.
An unrelated FireSpell executing while a tracked Run exists must fail the exact
frame/caller pair. The probe executes such a nested cast on a separate native
stack frame and confirms its child remains unowned.

The pinned executable's PE base-relocation directory RVA and size are both
zero. The native proof is at its actual fixed base. A second probe mapping at
0x180000000 explicitly fixes up the selected instant-projectile vtable as a
synthetic address-arithmetic test; it is **not** proof of OS ASLR loading.
Still express expected addresses through the verified module base/labels.

Copying the `212E84` CALL into a trampoline changes the return address pushed by
the CPU. An executed negative control demonstrates that the same frame relation
then fails the native-return-address guard while the native effect still applies.
Keep this CALL in place, or deliberately support the exact generated return
address with new evidence. Entry/restoration hooks that return to the original
caller instructions need not move this CALL.

## Original child boundary and dispatch

At `16AFCB`, `CSpell::GetAbilityEffect 24EE30` constructs the original child.
Native code then writes caster/target points, IDs, optional parameter-block
adjustments and caster duration scaling. Proposed boundary `16B047` restores
`8B 43 14 FF C8` (`mov eax,[rbx+14]; dec eax`) after those adjustments.

The registers/locations verified by the probe are:

| Value | Native location |
|---|---|
| Original child effect | RBX |
| Selected zero-based SPL ability | `[nativeRSP+50]` |
| Zero-based effect ordinal | EDI |
| Caster / selected target sprites | R14 / RSI |
| FireSpell entry RSP / its return address | RBP+B8 / `[RBP+B8]` |
| Decoded projectile, when relevant | R13 |

The child keeps sourceType1, its actual SPL resref and native caster level.
Logical potion owner, native source and path through a linked resource are
different data. Do not replace sourceType1 with ITM type2 to evade opcode206.
The probe supplies native-constructor-shaped child fixtures rather than running
the full resource loader. It executes native source/target and duration writes:
a synthetic 150% duration modifier turns 60 into 90 before the boundary.

Target1 at `16B068` sets resistance flag bit8 **after** child-ready. Preserve and
revalidate that native dispatch mutation at admission. With the null parameter
block supplied by this Run, target1 chooses either direct AddEffect or queues
an original CMessageAddEffect. Queued construction stores original child RBX
at message+10 (`16B0D7`), flags1 at+18 and noSave0 at+1A; queue CALL is
`16B100: E8 BB 9D 09 00`.

Direct calls are `16B252` (target1) and `16B1D8` (target2/self fast path), both
`FF 90 E8 00 00 00`. RCX=actor R14, RDX=child RBX, R9=0, arg5=1.
Their continuations are `16B258` and `16B1DE`. Just before the calls,
`16B24A`/`16B1D0` contain an eight-byte argument write
`C7 44 24 20 01 00 00 00`, a possible entry-observation location preserving
the original CALL. A balanced after-call hook still needs generation and
watchdog verification; this note does not approve a relocation scheme.

Target2 can instead attach original RBX to projectile R13 at
`16B1EC: 48 8B D3 49 8B CD`, before original CALL
`16B1F2: E8 79 F0 0B 00`. Keep that CALL/return address in place: existing EEex
projectile hooks explicitly use its caller return address to recover the caster.
They also allow projectile type mutation. Require the actual instant class,
not merely resource projectile ID1. The existing instant proof and this probe
execute unchanged-pointer transfer to CMessageAddEffect and noSave=false.
Area, copied and other projectile classes remain outside this proof.

## Proposed lifecycle API, not implemented

- `castQueue(parentEffect, messagePointer, targetSprite)`: transfer an existing
  approved parent dose/path to the exact newly constructed cast message before
  native AddMessage. Snapshot needed lineage; do not depend on parent survival.
- `castRunEnter(messagePointer, originalEntryRSP)` and
  `castRunLeave(messagePointer)`: push/pop invocation identity, including empty
  unowned frames so unrelated nested Run calls cannot expose an outer token.
- `castChildReady(fireEntryRSP, callerReturn, childEffect, abilityIndex, ordinal,
  casterSprite, targetSprite)`: require the exact tracked frame/caller and a
  manifest-supported original child. Attach the owner's logical path separately
  from native fields. Do not own unrelated/instant/adverse records implicitly.
- Direct delivery needs a scoped before/after AddEffect context with the actual
  noSave value. Queued delivery can reuse existing Run entry/leave by binding
  the exact pending child lifetime to its CMessageAddEffect identity. Projectile
  attachment must additionally verify the actual supported class.
- `castDestroy(messagePointer)`: remove only the cast-message token. Children
  already transferred to queued messages/projectiles outlive Run and its message.
  Existing effect destruction retires pending children; reset clears all tokens.

Do not carry ownership via resref matching, actor-global last-dose state or
current world time. Message/effect pointer reuse needs the same lifetime-token
discipline already used by the direct prototype. Native exceptions, multiplayer
serialization and provenance across saved active linked effects remain gaps.

## Executed checks and limits

27 cases pass at the native fixed image base; the same 27 pass in the explicitly
synthetic alternate mapping:

- Direct target1, queued target1, direct target2 and instant-projectile target2,
  each with accept, probability failure, opcode immunity, CheckEffect failure
  and save/MR predicate failure: only accepted children reach the proposed
  admission observer/actual op90 Apply, exactly once.
- Canceled cast destructor before Run: no child; parent destroyed before queued
  cast Run: its transferred dose survives.
- Missing caster or target: balanced Run lifecycle and no child.
- Two identical doses at unchanged world time, reverse dispatch: distinct dose
  ownership remains attached to the correct children.
- Adversarial reentrant AddMessage→cast Run→unrelated nested FireSpell: one owned
  and one unowned child, native duration scaling retained.
- Both cast and child messages run during their AddMessage service: one native
  application and balanced nested contexts.
- A CALL executed at a different code address pushes a different return address:
  strict ownership guard rejects it, leaving native application intact.

These are native instructions plus stated services and a sidecar contract model,
not an EEex-linked runtime test. No failed-repro artifacts were deleted:
`native-linked-cast-repro-1.txt` retains the initial Unicorn stale-RET/context
restore diagnostic; `-2.txt` retains the genuine absent-relocation-table
diagnostic. Later result files document the successful corrections.

The local EEex Lua source search found no normal dedicated CMessageFireSpell Run
hook. `profiler.db` does define entry patches at `165200` and `212DD0`; active
profiler collisions must fail signature validation, not be silently overwritten.
No compatibility claim is made for unknown hook writers or native exceptions.
