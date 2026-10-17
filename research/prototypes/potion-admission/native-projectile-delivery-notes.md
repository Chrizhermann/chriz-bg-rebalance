# Instant projectile delivery prerequisite — 2026-10-09

The pinned ID1 instant projectile can transport a target-2 potion effect without
copying or replacing the native effect object. Accepting this route requires both
the preliminary resource capability (drinker ability target5/projectile1) and a
runtime check of the actual instant class. The recipient must still be the drinker.
This is offline evidence for an opt-in prototype, not live acceptance.

## Inputs and boundaries

- Executable read: `%USERPROFILE%\Games\CBR-TimeStop-2.7.3.0\Baldur.exe`,
  BG2EE2.7.3.0, SHA256
  `b51093a49140b2b8a7c046b4652bb8e535be24ebbc12b1d735e0b94217a14d57`.
- Function names: the same lab's
  `EEex\loader\v2.7.3.0\bg2ee\function_names.db`.
- EEex1.3.0 scripts: the same lab's `EEex_scripts\EEex_Projectile.lua` and
  `EEex_Projectile_Patch.lua`.
- All native addresses below are RVAs; image base is `0x140000000`.
- No game launch, native DLL execution, process attachment, installed writes,
  save changes, installation, publication, or upstream contact occurred.

## Native route and exact ownership

The decoder decrements the requested projectile number at `22BF8F`.
For requested ID1, `22EEBC[0] = 0` selects jump-table entry
`DWORD[22EDDC] = 22BFBC`. That branch allocates `0x1B8` bytes,
calls constructor `226910` at `22BFE1`, then writes vtable `59BFF0`
at `22BFED`. Relevant vtable slots are:

| Slot | RVA | Routine |
| --- | --- | --- |
| `00` | `2280F0` | CProjectile scalar deleting destructor |
| `90` | `1ECE40` | RemoveFromArea |
| `D0` | `231600` | CProjectileInstant::Fire |
| `D8` | `233030` | CProjectile::OnArrival |
| `E8` | `22EFC0` | CProjectile::DeliverEffects |

`Fire` consists of these instructions:

```text
231600 mov rax,[rcx]
231603 mov [rcx+6C],r9d  ; selected target ID
231607 mov [rcx+68],r8d  ; source ID
23160B mov [rcx+18],rdx  ; area
23160F jmp [rax+D8]     ; OnArrival, immediate tail call
```

`OnArrival` invokes the sound/visual cleanup path, calls slotE8 at `2330A6`,
removes the projectile from its area/object array, and normally calls its scalar
destructor at `2330E4`. The sound routine `233320..2333CD` accesses the sound
object and resource fields; it does not traverse the original effect list.

Attachment `CProjectile::AddEffect(22A270)` writes only the native projectile
type to effect `+A0`, then tail-calls `CObList::AddTail(4075C0)` with the original
effect pointer. `AddTail` stores that pointer in node `+10` at `4075DC`.
The list is at projectile `+78`; its head is at projectile `+80`.

For an ordinary sprite recipient without projectile immunity, `DeliverEffects`
does the following for each node, in list order:

- `22F1A0`: loads the original effect pointer into R14 from node `+10`.
- `22F1B0`: allocates a `0x20`-byte **message**, not an effect.
- `22F1D2/22F1D5`: writes target/source IDs to message `+08/+0C`.
  Effect target9 has a different source-target branch and is outside this scope.
- `22F1DB` (`4C897010`): writes the exact R14 pointer to message `+10`.
- `22F1DF` (`C6401A00`): writes `noSave = 0` at message `+1A`.
- `22F1E3..22F1EA`: copies constant word `1` from `58E9A4` to message `+18`.
- `22F206`: queues the message through `CMessageHandler::AddMessage(204EC0)`.
- `22F219`: calls `CObList::RemoveAll(407930)`, relinquishing list ownership.

`RemoveAll` zeroes the node count, free/head/tail pointers and releases node
storage through `CPlex::FreeDataChain(407B40)`. It does not call effect
destructors. The later projectile destructor sees an empty effect list, so
transferred effects belong to their messages. No effect Copy or DecodeEffect
branch occurs on this ordinary ID1 path.

The optional projectile flag `+188 & 0x800000` is handled **after** the original
list has been transferred and cleared. `22F22E..22F31A` creates a separate op61
effect and message; it does not copy any transferred original. Constructor
`226AF2` initializes these flags to zero. Such generated effects have no original
dose tag and must stay native/unowned.

## Targets and cancellation

UseItem passes selected object R12's ID at `3BBD6C/3BBD7D`, the source sprite's
ID at `3BBD79`, and calls Fire at `3BBD9F`. FireItem similarly uses selected
object R15's ID at `16A803/16A81F`, source RBP's ID at `16A815`, and calls Fire
at `16A837`. ID1 itself does **not** force source and target equality. This probe
tests supplied self IDs and a different-target negative control; it does not
emulate the whole action-selection/UI path. Runtime equality checking remains
mandatory even when the resource ability is target5.

- Projectile immunity: `22F0DB` tests the actor's projectile immunity list.
  For effect target2, `22F15A..22F165` invokes the original effect's scalar
  destructor; no message is queued.
- Non-sprite recipient: target2 likewise reaches `22F07A..22F085` destruction.
- Missing recipient: lookup failure branches from `22EFD8` to the return.
  `OnArrival` subsequently destroys the projectile with its original list intact.
- Cancellation before firing: projectile destructor `2280F0` calls base
  destructor `227F20`. Its loop `227F43..227F5C` destroys each retained original
  effect once, then clears the list.
- For tested native classes54/90, scalar destruction reaches `14C8E0`; op18
  reaches `1A45A0`. Both are observed by the existing prototype lifetime hooks.
  Message cancellation after successful transfer is a separate queue probe.

## Why the runtime class guard is necessary

`EEex_Projectile_Patch.lua:17..52` intercepts DecodeProjectile before native
dispatch and can replace the requested projectile type. This applies to UseItem
and FireItem (listed in `EEex_Projectile.lua`'s decode sources). Therefore an ITM
projectile1 value alone does not prove the instantiated class.

Require actual `[projectilePtr] == EEex_GetImageBase() + 0x59BFF0` before retaining
an owned target2 pending tag. No additional projectile field guard is needed for
the original-pointer transfer proven here. Existing effect mutators execute at
the AddEffect entry (`EEex_Projectile_Patch.lua:197..225`), after the prototype's
attachment callback; native effect fingerprint and lifetime validation must still
run when the message is admitted. Unknown classes, copying/area/bounce routes,
and unrelated/generated records receive no uniqueness mutation.

The transport now supplies a fourth **numeric** argument, retaining the previous
first three arguments:

```text
useProjectile(RBP, effectUserdataRDI, ordinalESI, projectilePtr[RBX+4AD8])
fireProjectile(originalRSP, effectUserdataRBX, ordinalEDI, projectilePtrR14)
```

The guarded hooks remain at `3BBBD0` and `16A66F`; their restored instructions
lead to the original AddEffect calls at `3BBBDA` and `16A675`. Those calls and
their return addresses remain native. Callback arguments, flags, registers and
XMM0..5 preservation were rechecked with the real EEex preprocessor and generated
machine-code emulator, with the integrity watchdog enabled.

## Reproducible offline evidence

Run `probe_native_projectile.py` with `--exe` pointing to the pinned executable
and `--python-libs` pointing to a directory containing pefile and Unicorn.
The probe hashes the input and asserts decoder/vtable evidence before execution.
It executes the actual Fire, OnArrival, DeliverEffects, projectile/effect
destructors, AddEffect, AddTail, NewNode, RemoveAll and FreeDataChain instructions.
Synthetic preallocated free nodes avoid the unrelated CPlex allocation path.

All six cases pass:

| Case | Original messages queued | Original effects destroyed |
| --- | --- | --- |
| self recipient, effects54/90/18 | 3 | 0 |
| projectile immune | 0 | 3 |
| recipient missing | 0 | 3 |
| non-sprite recipient | 0 | 3 |
| cancel before Fire | 0 | 3 |
| different selected target | 1, directed to that target | 0 |

The normal case asserts identical pointer/order, noSave0/flags1, source/target
identity, byte-for-byte preservation of the entire `0x160`-byte synthetic effect
allocation after attachment, and zero native writes into those effects during
Fire/delivery. Cancellation asserts each original is destroyed/freed exactly once.
Instruction allowlisting rejects unexamined effect-copy or other native paths.

Saved output:
`%USERPROFILE%\AppData\Local\Temp\cbr-potion-inventory-20261009\native-projectile-probe.json`.
Full original DeliverEffects disassembly is in the same directory as
`projectile-delivery-disassembly.txt`.

The three focused test modules (`test_potion_hook_preprocessor`,
`test_potion_transport_preprocessor`, `test_potion_generated_trampoline`)
pass all17 tests without skips when their documented local dependency variables
are supplied. Latest generated assembly/object artifacts are retained at
`%USERPROFILE%\AppData\Local\Temp\cbr-potion-generated-trampoline-8p_ogard`.

This does not prove live scheduling, EEex mutator interactions, native exception
unwinding, allocation failure, multiplayer/message serialization, or save/load.
Object lookup, message allocation/queue, immunity lookup, audio and base cleanup
services remain explicit test doubles. No complete potion implementation or
current-save safety claim follows from these bounded results.
