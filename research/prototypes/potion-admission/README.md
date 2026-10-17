# Original-effect potion admission lab

2026-10-09. Local prototype; **not a public component or native acceptance result**.
Both policies are represented: `unique` and `except_genius`. The latter exempts
the actual Intelligence potion, not every potion with an Intelligence effect.
Heroism/Power families ignore repeated bonuses while any owned family bonus is
still active. The original item-use path remains responsible for consuming the
dose and delivering unrelated records.

## What is implemented

The prototype keeps each original native ITM effect. After `CheckSave` succeeds,
before `OnAdd`, a safe repeat changes only the active effect's absolute expiry
and rejects the incoming duplicate through native `CheckAdd` failure. An HP
repeat rejects the new record without writing the old effect. This preserves
source identity, native caster/dispel level, opcode state and first-application
behavior. It does not remove/recast bonuses or manufacture helper spells.

| File | Responsibility |
|---|---|
| `build_manifest.py` | Read-only compiler for explicit loose ITM inputs; semantic family/key registry, ability ordinals and multisets; diagnostics for unsupported/ambiguous payloads. |
| `CBRPQCore.lua` | Pure admission plan and expiry-only commit. First-dose siblings remain distinct; each old effect is assigned once per dose. |
| `CBRPQMessages.lua` | Opaque token per native item-use invocation; queued-message, nested-frame, cancellation and reset bookkeeping. |
| `CBRPQNative.lua` | Read-only native field matching and timed-list traversal, with effect lifetime identities independent of native pointer reuse. |
| `CBRPQRuntime.lua` | Connect the compiler, native reader and message callbacks. Diagnose unsupported state and disable the lab on callback failure. |
| `CBRPQHook.lua` | Signature-guarded admission hook after successful native checks. |
| `CBRPQTransport.lua` | Signature-guarded item-loop/message/destruction/load hooks. Preserve native arguments and the original indirect `AddEffect` call. |
| `CBRPQLab.lua` | Explicit composition: `prepare()` validates; only a separate `arm()` patches code. No autoload or public installer. |
| `probe_native_potion_bridge.py` | Actual manifest/compiler/Lua decisions at copied native admission instructions, with explicit service and transport test doubles. |

Dose identity is an invocation token, not a timestamp or actor counter. UseItem
and FireItem have separate frame namespaces. Messages are tagged before
`AddMessage`, including possible synchronous dispatch. Each native Run brackets
its AddEffect call with enter/leave; untagged and `noSave=true` messages hide an
outer frame. Cancellation destroys the tag. No native pointer is serialized.

At the first successful owned admission, the core records the old family. HP
suppression is latched for that dose, so its first HP record cannot suppress its
own THAC0 sibling. Safe records are matched one-to-one. If an old record was
removed, a new live equivalent can be refreshed; otherwise the admitted original
fills the missing bonus. Native effect lifetime tokens prevent an old snapshot
from aliasing a reused address. Current native fields are read again before the
one expiry write; list links and engine iterator cursors are never written.

## Exact target and evidence

The inspected local files are BG2EE **2.7.3.0** and EEex **1.3.0**. These are
pinned evidence inputs, not a claim about an uninspected future latest release.

- `Baldur.exe` SHA256:
  `b51093a49140b2b8a7c046b4652bb8e535be24ebbc12b1d735e0b94217a14d57`.
- `EEex.dll` SHA256:
  `cc06e13f3376557c6966442f5c6989d299f97c48c30999515c064373f9e9b882`.
- `function_names.db` SHA256:
  `c5e957b9f63b1a945ccc837b827bad37f209f99412d791d4a749503fc6c25823`.
- EEex `EEex_Assembly.lua` SHA256:
  `6a10e2d6a0cfd880768f81ac381e715c3ae49f3b0aa04e833f35799f831e7dc1`.
- EEex `EEex_Assembly_x86-64.lua` SHA256:
  `eb7c8e9307b1a150f1cd57ac91b3c497d1102454f1495083c4395cc28e606d62`.

All addresses are RVAs. `CheckSave` call `1CD1A4`, test `1CD1A7`, conditional
failure `1CD1A9`, success `1CD1AF`, OnAdd `1CD1CF`, Resolve in AddEffect `387478`.
The hook executes only the original branch's successful fallthrough. Failed
probability, immunity, CheckEffect and save checks cannot refresh an old effect.
Existing opcode403 is earlier and is not used as the commit point.

Direct item construction `1FB4DF–1FB517` supplies sourceType2, item resref,
school/secondary/source flags and casterLevel10. A specialist school can adjust
saveBonus by -2 at `1FB55F`; self delivery supplies flags bit3, and item
identification supplies bit31. These are the only corresponding matching
normalizations. HP18's saved Special bit0 changes on first use; it is normalized
for active identity without resetting it. Rolled HP changes parameter1 and is
excluded from this reader.

The native constructor matters: `19DD1C–19DD4F` moves only raw timing bits8/9
into runtime flags1/2. The remaining high timing bits are not ordinary flags.
At `19DD72–19DD90`, HP18 uses dice fields, while19/54/90/92 interpret the raw
dice-count/size slots as maxLevel(+58)/minLevel(+54). Their runtime dice fields
remain zero. The compiler and reader represent this distinction; the native
minLevel>65535 normalization is outside this lab's accepted registry.

Lifetime cleanup needs two native paths:19/54/90/92 use destructor `14C8E0`,
whereas HP18 uses `1A45A0` with separate inlined cleanup. Both entry hooks retire
the pointer without reading the dying object. The ordinary entry hook does not
overlap EEex's existing cleanup hook at `14C900`. `CInfGame::Unmarshal` entry
`2930C0` resets transient state before loading; the existing EEex session-destroyed
listener also clears it. These are source/guarded-generation checks, not proof
that every possible effect subclass or native unwind path is covered.

Native timing0 converts seconds to 15 ticks at `1E84A5–1E84E6`; timing10 adds
ticks at `1E84F3–1E850E`; timing4096 expires at unsigned `now >= expiry` at
`1E8460–1E8487`. The lab diagnoses signed/clamped or wrapping duration cases
instead of pretending ordinary arithmetic preserves them.

V2 marshal `1E53B0–1E543D` saves effect bytes +08..+10F, including expiry and
source metadata. It does not preserve original ability ordinal/duration or
runtime pointers. Consequently the compiler rejects fingerprints that become
ambiguous after loading. This is static format evidence, not save/load acceptance.

[Native admission notes](native-admission-notes.md) distinguish actual copied
engine instructions from substituted predicates/services. The opcode follow-up
probe covers 19/54 expiry-only recalculation and zero-dice percentage18 repeat
suppression. `noSave=true` is a reproduced negative control: AddEffect overrides
CheckAdd failure and grants another bonus. The runtime deliberately excludes it.

## Bounds before any game test

The replacement is still being expanded and is **not coverage of every potion**.
Reviewed direct stats now extend beyond the initial 19/90/92/54/18 subset, with
CON treated as HP-sensitive and complete reviewed HP companions owned together.
Instant projectile delivery is being integrated for Heroism's target-2 record.
Conclusive unowned links stay native; linked bonuses, regeneration phases,
network-reconstructed effects and remaining opcodes still need adapters.
The compiler reports these capability gaps; it does not silently promise the
all-potion policy for them. Different canonical potion types remain distinct.

Known limitations remain visible:

- No generated trampoline has run in the game. Real EEex preprocessing and
  copied native instruction tests do not establish the complete native Lua ABI.
- Nested owned AddEffect calls are diagnosed and disable this lab. Ordinary
  unrelated nesting is bracketed, but arbitrary engine/Lua mutation reentrancy
  has not received native acceptance.
- Existing stacks beyond one legal multiset are diagnosed, not migrated.
  Resources changed between registry creation and use must be recompiled.
- The watchdog can remain enabled. Pass `parts.watchdog` loaded from
  `CBRPQWatchdog.lua` to the composition module. Scoped template decoration
  protects XMM/flags around the original checks and preserves their original
  stack snapshots and register masks. Generated machine code now runs offline
  with deliberately clobbering external-call doubles; native DLL execution
  remains untested.
- An installation error can leave inert trampolines. Callbacks are disabled;
  restart is required. No automatic rollback/retry or hook-conflict chaining is
  claimed. Signature guards reject previously patched sites.
- Whole-package atomicity after selective native rejection is not invented.
  Each original record still undergoes its native checks. Instant healing,
  adverse records and permanent operations remain outside repeat suppression.
- The transport/lifetime callbacks touch general engine paths. Their overhead
  has not been measured on a heavily modded game; production may benefit from
  a small native filter or focused EEex extension even though Lua can express
  this lab. No performance or universal hook-compatibility claim is made.

## Offline verification and next native acceptance

Earlier checkpoint: **106 module/preprocessor tests passed with no skips**, plus
**44 connected Lua/native-instruction cases**. The separate opcode probe passes
16 bounded cases. See the [handover](../../../docs/handovers/2026-10-09-potion-uniqueness.md)
for current work, command/log context and the retained rejected-draft failures.
Those historical totals are not the completed component's acceptance result.

Run the `tests.test_potion_admission_*`, `test_potion_message_lifecycle`,
`test_potion_native_reader`, `test_potion_lab_composition` modules. Set
`EEEX_LUA_DIR` to the pinned `EEex_scripts` directory to enable the actual
preprocessor tests. Native probes require an explicit `--exe` and optionally
`--python-libs`; they hash the input and execute copied instructions in Unicorn.
They never launch a game or change a game/save file.

The connected bridge probe replaces the earlier supplied Python matching
decision with this actual compiler, native reader, message lifecycle and Lua
core. Native admission/Resolve/Apply instructions run in Unicorn. Native
construction, predicates, list allocation and full stat rebuild are still
substituted; transport callbacks are deliberately invoked by the harness.
It complements the separate hook-generation tests and does not execute their
assembled trampolines.

The three failing private-SPL draft methods in
`tests/test_potion_uniqueness_installer.py` remain ordinary failures and are
retained as rejected-architecture evidence. They are not hidden by skips or
expected-failure annotations. Normal packages exclude both research prototypes.

After separate authorization for a disposable native lab, coordinate the game
process slot with other agents; do not terminate or attach to another test.
Start with one actor and direct Master Thievery-style potion, then Genius and
Heroism/Power. Record these acceptance results separately:

1. First and second use: one safe potency, second-dose expiry, unchanged
   native source/caster level/flags, dose consumed normally; different potion
   types and unrelated spell/equipment bonuses retain native interactions.
2. Probability/immunity/save rejection leaves old expiry untouched; self-use,
   canceled messages, same-tick uses and unrelated nested messages balance.
3. Wounded/full/near-zero HP: repeated Heroism/Power causes no heal, clamp or
   extension. Check both canonical/SCS orders and partial package removal.
4. Full dispel/expiry allows a new original dose; selective removal, new native
   replacements and pointer reuse never resurrect or modify a dead object.
5. Save/load active bonuses in a fresh test save, reload during pending delivery
   if supported, then use again. Verify no persisted pointers/tokens or stale
   guards. Existing-playthrough safety remains a separate decision.
6. Only after these pass, broaden SR/non-SR/SCS and IR/IRR payload coverage with
   explicit linked and HP-sensitive adapters, preserving unrelated records.

No game launch, live installation, save edit, collection integration or
publication was performed during this work. Wish remains a separate design note;
Time Stop/Haste remains deferred.
