# Original-effect admission and expiry-only refresh: offline prototype

2026-10-09. Research evidence, **not a shipped component or live-game acceptance**.

The narrow expiry-only operation is supported for one exactly identified,
already-active, direct additive skill effect (opcode 90 or 92): after the new
effect passes native admission, update the old object's absolute expiry and
reject the new object. This avoids removing the old effect, calling its OnRemove,
replacing its source metadata, or applying its benefit a second time.

## Inputs and reproducibility

- Executable: `%USERPROFILE%\Games\CBR-TimeStop-2.7.3.0\Baldur.exe`.
- BG2EE 2.7.3.0 SHA256:
  `b51093a49140b2b8a7c046b4652bb8e535be24ebbc12b1d735e0b94217a14d57`.
- Names: that lab's EEex 1.3.0
  `EEex/loader/v2.7.3.0/bg2ee/function_names.db`.
- All native addresses below are RVAs relative to `0x140000000`.
- [probe_native_admission.py](probe_native_admission.py) requires `pefile` and
  `unicorn`; it copies and executes bounded native instructions in Unicorn. It
  does not start Baldur.exe, attach to a process, install anything, or write any
  game/save/resource file. Exact PE hash and six instruction signatures are
  checked before emulation.

Example, using dependencies already present in this lab:

```powershell
python -B research/prototypes/potion-admission/probe_native_admission.py --exe '%USERPROFILE%\Games\CBR-TimeStop-2.7.3.0\Baldur.exe' --python-libs '%USERPROFILE%\AppData\Local\Temp\cbr-potion-hp-research-20261009\pylibs'
```

The JSON result names every native service/predicate substituted by the probe.
It does **not** execute an EEex-generated trampoline or a Lua callback. The
proposed callback is a Python test double; its supplied exact active pointer is
not a production identity matcher.

## Admission boundary and ownership

Native self-target item effects use `CMessageAddEffect`, whose ordinary delivery
supplies `noSave=false` and `immediateResolve=true`. The pertinent order is:

1. `CGameSprite::AddEffect` calls `CheckAdd` at `387406`.
2. Probability bounds are checked at `1CC736–1CC744`; EEex's existing opcode-403
   callback runs on the success side of the latter branch, still before later
   admission checks.
3. Native resource/opcode admission and level checks precede the virtual
   `CheckSave` call at `1CD1A4`.
4. `1CD1A7: test eax,eax`; `1CD1A9: je 1CC9A5` rejects a failed check.
   **Success fallthrough `1CD1AF` is the candidate callback location.**
   `RDI` is the incoming effect; `R14` is the target sprite.
5. The subsequent native path calls `OnAdd` at `1CD1CF` and `DisplayString` at
   `1CD1DB`, then returns success. `AddEffect` calls `ResolveEffect` at `387478`,
   leading to the first opcode application.

At the candidate location, redirecting control to `1CC9A5` returns zero through
the native CheckAdd epilogue. With `noSave=false`, `AddEffect` takes
`38740B–387427`: it destroys **the rejected incoming object**, then resumes its
normal bookkeeping. The adapter must not itself destroy this object or retain
its pointer. Old active effects are not destroyed by this rejection branch.

The probe establishes that rejected incoming effects do not receive OnAdd,
DisplayString, ResolveEffect or ApplyEffect. Original failures never reach the
callback and leave the old expiry intact. Probability comparisons run natively;
opcode-immunity, CheckEffect and CheckSave results are injected at their real
callee entries. Thus this proves ordering and control flow for those results,
**not the internal correctness of MR, saves or immunity implementations**.

The negative control matters: `noSave=true` at `387411` overrides CheckAdd
failure. In the probe the candidate refreshes the old timer, but the new effect
still applies and the skill bonus rises from 20 to 40. Such callers need an
additional proven rejection mechanism; they are outside this prototype.

## Native timing conversion

`CGameEffect::ResolveEffect` establishes these exact conventions:

| Incoming timing | Conversion | Evidence |
|---|---|---|
| 0: seconds | `min(signed32(duration), 0x08888888) * 15 + worldTime`, modulo 32 bits; timing becomes 4096 | `1E84A5–1E84E6`, signed min helper `407BC0` |
| 10: ticks | `duration + worldTime`, modulo 32 bits; timing becomes 4096 | `1E84F3–1E850E` |
| 4096: absolute | No conversion; expire when unsigned `worldTime >= duration` | `1E8460–1E8487` |

`worldTime` is the game's dword at `CInfGame+3FA0`; effect timing and expiry are
runtime offsets `+24` and `+28`. Incoming mode 0 is still unconverted at the
candidate admission point. For an ordinary 60-second dose accepted at world
tick 1000, the native new deadline is 1900.

Expiry-only refresh therefore writes **old effect `+28`**, retaining old timing
4096. Native first-call state, power, parameters, save fields, source type/resref,
source flags, school/secondary type and caster/dispel level remain untouched.
In particular, direct item caster/dispel level `+C8=10` is preserved rather than
recomputed through a private SPL. `+11C` is not needed for this computation and
is not written; it must not be assumed to survive save/load. ResolveEffect does
not establish `+6C` as a general creation-time field.

The probe also reproduces zero, large, negative-as-signed and wrapping duration
arithmetic. Those are arithmetic boundary observations, **not permission to
refresh unusual timing records**. An active match must be not-done, timing4096,
and still unexpired. Delayed/permanent effects and revival of expired records
are outside this narrow operation. Overflow/past-deadline handling still needs
an explicit production policy rather than a silently altered native formula.

## Read-only traversal and the tested write

The sprite's equipped/timed lists are at `+49B0` / `+4A00`. Their CObList head is
`+8`; a node contains `pNext` at `+0` and `data` at `+10`.
`CGameEffectList::HandleList` reads that layout at `1E4FA3` and `1E4FD0–1E4FDF`.
Its live iteration cursors at list `+38` and `+40` are updated by HandleList.
Do not modify them from the adapter.

EEex's `EEex_Utility_IterateCPtrList` follows `m_pNodeHead`, `node.data`, then
`node.pNext`; the callback must only read nodes and write the selected effect's
expiry. It must not call effect removal, admission, full processing or any
operation that may invalidate the current or next node.

The probe supplies an unrelated effect, tests both record orders, and leaves
nonzero iterator cursors in the synthetic timed list. Full old-effect byte
comparison permits only the four expiry bytes to differ. List headers, nodes,
links and iterator cursors remain byte-identical. Native removal functions are
trapped; the old effect's OnRemove and destructor are never invoked. This
supports the absence of list-iterator mutation in the narrow operation, not a
claim about all concurrent or reentrant runtime circumstances.

## Verification result and remaining acceptance

The probe passes 12 admission outcomes (six each for op90/op92), two accepted
native baselines, two reordered-list expiry-boundary cases, seven native timing
cases and the noSave=true negative control. At the old deadline1450, a refreshed
effect still contributes its native +20 once to a fresh synthetic bonus
accumulator; at new deadline1900 it is marked done without another application.
This uses the real native op90/op92 instructions. Full stat reload is stubbed,
and this deliberately does not model multiple live engine threads or actions.

Before any broader acceptance, validate the actual EEex trampoline and register/
stack preservation; precise matching of the admitted record to its old active
record; identical records that coexist within one dose; consecutive doses in
one tick; linked/shared SPL/EFF provenance; conditional or partial admission;
save/load; and effect removal/dispel between matching and refresh. Do not use
source resref or a game tick alone as a dose identity. No raw effect pointer may
persist beyond the synchronous callback or across save/load.

HP18, Constitution10, regeneration98, maintenance effects and delayed payloads
are not covered by the op90/op92 result. Updating only expiry also retains the
old actor/application attribution and opcode-private state: whether that is the
desired repeat policy must be established per supported effect kind.
