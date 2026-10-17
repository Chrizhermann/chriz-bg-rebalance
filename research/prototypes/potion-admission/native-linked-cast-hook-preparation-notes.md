# Inert original-mode1 cast transport preparation

2026-10-09. `CBRPQCastTransport.lua` prepares guarded hooks only when its caller
explicitly invokes `install`. It is not loaded by M_, wired into the lab/runtime,
installed into a game, or a claim that linked potion support is complete.

Public API: `validate(api, config, watchdog)` and
`install(api, config, watchdog)`, matching the other prototype modules.
`config.callbacks` contains the nine global Lua callback names below. The
existing scoped `CBRPQWatchdog` helper is mandatory when EEex's watchdog is on.
The external lab preflight must verify `expectedExecutableSha256`; this module
checks in-memory native sites/contexts and message vtable slots, not a disk hash.

Input is the pinned BG2EE2.7.3.0 / EEex1.3.0 executable documented in
`native-linked-cast-lineage-notes.md`. All sites are image-relative. Every child
callback additionally checks `[RBP+B8] == imageBase+212E89`, preserving the
original flags and RAX on both paths. Runtime must also correlate the exact
FireSpell frame with the tracked Run-entry frame; the return check alone cannot
establish a dose owner.

| Callback | Arguments | Hook RVA / replay |
|---|---|---|
| parentQueued | parent effect userdata RSI, message pointer R14, target sprite userdata R15 | 1A8594 / 7 bytes |
| castEnter | message pointer RCX, original Run-entry RSP | 212DD0 / 6 bytes; entry alignment8 |
| castLeave | message pointer RBX | 212E89 / 5 bytes |
| castDestroy | message pointer RCX | 165200 / 5 bytes; entry alignment8; actual vtable590D90 filter |
| childCreated | nativeFireFrame, effect userdata RBX, ordinal EDI, selected ability `[nativeRSP+50]`, caster userdata R14, target userdata RSI | 16B047 / 5 bytes |
| childDirectEnter | nativeFireFrame, effect pointer RDX, numeric noSave R9D | target1:16B24A; target2:16B1D0 / 8 bytes each |
| childDirectLeave | nativeFireFrame | target1:16B258; target2:16B1E7 / original JMP destination16B331 |
| childQueued | nativeFireFrame, message pointer RDX, effect userdata RBX, ordinal EDI | 16B0F9 / 7 bytes |
| childProjectile | nativeFireFrame, effect userdata RBX, ordinal EDI, actual projectile pointer R13 | 16B1EC / 6 bytes |

`nativeFireFrame` means **original FireSpell entry RSP = RBP+B8**, not RBP.
The selected ability capture uses the original native stack, accounting for
callback saves and EEex shadow space. Userdata is synchronous/borrowed. Correlate
an owned invocation before reading sprite fields: generic unowned Run callers
may use other AI types. Unowned Run invocations still need nesting sentinels.

`childProjectile` deliberately reports the actual pointer even for an unsupported
class. Runtime must validate the original instant-class capability and retire or
reject unsupported pending ownership. Suppressing this callback on class mismatch
would leave a childCreated tag without a class decision. Resource projectileID1
alone is insufficient because existing EEex type mutators can replace it.

Original CALLs at1A859E,212E84,16B252,16B1D8,16B1E2,16B100 and16B1F2 remain at
their native addresses. This preserves the Run→FireSpell return-address proof
and EEex's projectile caller decoding. Direct target2 leave runs after its native
CString cleanup (AddEffect returns16B1DE; cleanup ends16B1E7). The direct context
therefore spans that cleanup; the inspected native string-cleanup path has no
effect dispatch. Runtime still must require the exact incoming effect lifetime.

The two leave JMPs are re-emitted to their original absolute destination after
the watchdog exits. Their relative instruction bytes are not blindly copied to
JIT code. All other displaced instructions are position-independent native
instructions. No native call outputs or arguments are replaced.

Preparation saves/restores all volatile GPRs, XMM0..5 and full flags around Lua;
the scoped watchdog decoration protects the same volatile state around the real
watchdog templates and reports original native RSP. No ignore mask is weakened.
Lua error paths restore state and continue native execution. Runtime callbacks
remain responsible for invalidating transient prototype state/reporting errors.
Partial native patch failure has no claimed rollback; the module forbids retry
or double-arm. Validation also rejects a changed cast vtable destructor/Run slot.

## Verification

New tests:

- `tests/test_potion_cast_transport_preprocessor.py`: actual EEex1.3 Lua macro
  expansion, both watchdog settings, all site/context/vtable mismatch guards,
  stack/branch paths, preserved original CALL locations, no double-arm and
  protected cleanup after injected partial preparation failure.
- `tests/test_potion_cast_generated_trampoline.py`: real generated text assembled
  by local ML64 and executed in Unicorn. All eleven sites run with successful
  and failing Lua services; eight caller/class rejection paths also run. Actual
  Lua arguments include original RSP, nativeFireFrame, ability1337 and ordinal17.
  Every result is compared with independently executed displaced native bytes,
  including GPRs, XMM, flags and the original stack. Watchdog/native Lua service
  doubles deliberately clobber volatile state.

Combined old admission/item-transport and new cast suites: **25 tests pass**
(2026-10-09; 19.389s). No game or EEex/native Lua DLL was executed. Actual EEex
macros/templates run in offline LuaJIT; only generated instructions run in Unicorn.
Generated source/object artifacts retained at
`%USERPROFILE%\AppData\Local\Temp\cbr-potion-cast-generated-gido0gw3`.

The separately saved native construction probe reports62 passing cases; the
lineage probe reports27 native-base cases plus27 explicitly synthetic alternate-
mapping cases. These do not prove runtime registry integration, persisted linked
provenance, arbitrary hook coexistence, remote serialization or native exception
unwinding. Active profiler patches at the guarded Run/destructor entries fail
preflight rather than being overwritten.
