# 10 — Time Stop / Haste: engine clock decisions

2026-09-26. **Research only; no prototype implemented or run.** Continues the
[September 25 feasibility report](%USERPROFILE%/.codex/worktrees/installer-v0-real-alpha/chriz-bg-collection/docs/plans/2026-09-25-timestop-haste-feasibility.md).
Game files were read offline. No game/process interaction, save access/editing,
installation, publication, or upstream contact occurred. Unrelated work was preserved.
Upstream work credited here: EEex/InfinityLoader by Bubb; Sword Coast Stratagems by
DavidW; Spell Revisions by Demivrgvs and the G3 contributors.

## Recommendation

**Proceed, when separately authorized, with one engine-hook prototype on the newest
stable Windows game and EEex releases.**
EEex already supplies the necessary patching mechanisms; new interception sites and
clock policy are needed. A new native DLL is **not inherently required**. Ordinary or
deferred effect-list listeners remain too late. Safe execution is not established by
this static research.

The offline **BG2:EE 2.7.3.0** investigation now establishes more than initial feasibility:

- Normal timed effects expire through an identifiable world-time comparison before
  native removal. Frozen actors can still traverse this path.
- Native poison, regeneration, disease and repeated-EFF workers already reject updates
  for Time-Stop-frozen actors. Preserve that protection; these families do not need a
  speculative replacement damage/healing implementation.
- Native Haste changes **actor scheduling frequency**. The periodic list advances with
  those actor passes, explaining the coupling. Decouple selected periodic clocks;
  leave actor scheduling, attacks and movement alone.
- Both native worker rebuilding and a shared subsecond counter affect pulse phase.
  Merely extending an expiry deadline or skipping alternate callbacks is insufficient.
- This SR install's Haste and Improved Haste use movement/APR effects without native
  Haste. Test native and SR-shaped Haste separately.

Keep the first scope to one existing nonimmune actor, one ordinary short buff and one
native regeneration effect. Exclude area objects, delayed effects and maintenance
graphs from that first allowlist. Those exclusions bound the experiment, not the final
desired behavior. Do not promise complete tabletop fidelity or current-save safety.

### Target-version decision — 2026-09-26

Christopher explicitly chose the newest BG and EEex versions as the working baseline
for this free community mod. Target current stable Windows x64 releases; older-version
support, backports and a historical compatibility matrix are outside the present scope.
Start with BG2:EE for the isolated experiment. Supporting BG:EE too would need its own
current-build verification, not an assumption that both games share addresses.

Release check on 2026-09-26: GitHub's live latest-release API identifies
[EEex 1.3.0](https://github.com/Bubb13/EEex/releases/tag/v1.3.0), published September 16,
as the latest stable release. Beamdog's [official 2.7 release announcement](https://forums.beamdog.com/discussion/90724/2-7-baldurs-gate-icewind-dale-ees-update-new-languages-improved-cloud-support-mobile-modding)
and [current Windows x64 debug-file listing](https://files.beamdog.com/) identify the
**2.7.3.0** build family. Use **EEex 1.3.0 / BG2:EE 2.7.3.0** as today's working target;
verify the exact local executable before tracing it. Refresh the release check if the
prototype begins after another release.

This supersedes the earlier proposed BG2:EE 2.6.6.0 / EEex 1.2.0 prototype baseline.
The old disassembly remains useful research evidence, not a supported-version promise.
The selected current executable has now been inspected directly: the relevant decisions
retain the same control flow with relocated addresses. The current map below replaces
the old map for prototype planning. No old-version fallback is required.

Update 2026-10-18: Christopher chose EEex **1.3.1** for everything, and the
[observation lab](timestop-lab/README.md) is re-pinned to tag commit
`a6d21abe44e20509f5d0259ccc6c7e7f9d12b285`. The 2.7.3.0 `function_names.db` and the
`Data-CGameEffect::vftable` pattern are byte-identical in 1.3.1, so the names and
instruction evidence below still apply. The tagged 2.7 `EEex.dll` and `LuaBindings.dll`
changed; their hashes below describe the 1.3.0 audit.

Update 2026-10-20: the lab's first engine run, in a disposable 2.7.3.0 copy with EEex 1.3.1,
passed the startup and hook-integration smoke test. At the fresh main menu, `CBRTS.Inspect()`
confirmed the image base, the resolver and regeneration vtables and the original bytes at all
eight sites; `CBRTS.Install()` installed the eight disarmed hooks. Two lab defects that only a
real run could show were fixed first: a nonexistent `GetActiveEngine` binding in the
fresh-menu check, and a preflight that refused the loader's own address cache. Nothing was
armed or measured; the native timing questions below remain open. Details are in the
[lab README](timestop-lab/README.md#engine-smoke-test-eeex-131-2026-10-20).

## Evidence identity and method

The current executable inspected was
`C:\Program Files (x86)\Steam\steamapps\common\Baldur's Gate II Enhanced Edition\Baldur.exe`:

| Property | Inspected value |
|---|---|
| File/product version | **2.7.3.0**, Windows x64; Steam build ID `23534562` |
| Size | 7,202,696 bytes |
| SHA-256 | `b51093a49140b2b8a7c046b4652bb8e535be24ebbc12b1d735e0b94217a14d57` |
| Preferred image base | `0x140000000`; all addresses below are **RVAs**, not live addresses |
| PE timestamp | `0x6A18D73D` |
| Audited EEex | **1.3.0**, commit `9e8098ee696ca4b0bc055e7ff74b283704a8c02e`; source/tag assets, not a runtime version claim |
| Tagged 2.7 EEex.dll | 1,294,848 bytes; `cc06e13f3376557c6966442f5c6989d299f97c48c30999515c064373f9e9b882` |
| Tagged 2.7 LuaBindings.dll | 6,499,328 bytes; `728465fddc091ff5d7817b3f33f4d735af51031a753ab1568490bf1a9a22348f` |

[Current instruction excerpts, bytes and extraction metadata](evidence/10-timestop-haste-2.7.3.0.txt)
were decoded directly with Capstone 5.0.9 and pefile 2024.8.26. Names come from EEex 1.3's
[`2.7.3.0/bg2ee/function_names.db`](https://github.com/Bubb13/EEex/blob/9e8098ee696ca4b0bc055e7ff74b283704a8c02e/EEex/loader/v2.7.3.0/bg2ee/function_names.db).
Instructions and callers corroborate those labels. Structure declarations come from
InfinityLoader commit `f14a00527286f819b8034411bc92ca719cfe3c86`, versioned 2.7 header;
this source snapshot is not proof it built a particular release DLL.

The 26 core excerpts retain the earlier instruction sequences, with relocated code/data
references. Selected whole-function comparisons also preserve the relevant branches and
arithmetic after address normalization. Embedded jump tables were distinguished from
instructions; MSVC `.pdata` fragments were not mistaken for complete functions.
This is a bounded control-flow comparison, not whole-program equivalence or a portable
hook specification. The current evidence has also been checked independently against
the executable. The final **349** retained instruction-byte and mnemonic records match
the current on-disk image, with every excerpt decoding to complete instructions.
No engine test was run.

BG:EE 2.7.3.0 was also located at the adjacent Steam `Baldur's Gate Enhanced Edition`
directory: 7,145,352 bytes, SHA256
`187f89e1033999b2c8eae6591641325ba012071030364767f42221ecae92372a`.
It was fingerprinted, **not disassembled**. BG2 is the first prototype target.

The [older 2.6.6.0 trace](evidence/10-timestop-haste-2.6.6.0.txt) remains historical evidence.
SR/SCS spell-resource observations below still describe the read-only modded reference
installation, not a newly installed 2.7 mod stack.

## Expiry and frozen-actor path

Runtime offsets here are relative to `CGameEffect`, including its vtable pointer;
they are not SPL feature-block offsets. `+0x24` is timing, `+0x28` duration/deadline,
`+0x114` is `m_done`. `CInfGame+0x3FA0` supplies game time.
Names/layouts are cross-checked against the pinned InfinityLoader
[`CGameEffect` declarations](https://github.com/Bubb13/InfinityLoader/blob/f14a00527286f819b8034411bc92ca719cfe3c86/Core-Shared-Files/generate_bindings/in/Baldur-v2.7.3.0.h#L54580)
and [periodic-worker declarations](https://github.com/Bubb13/InfinityLoader/blob/f14a00527286f819b8034411bc92ca719cfe3c86/Core-Shared-Files/generate_bindings/in/Baldur-v2.7.3.0.h#L57874).

| Decision | Offline evidence |
|---|---|
| Normalize finite durations | `CGameEffect::ResolveEffect`, `0x1E84A1–0x1E84ED`: timing 0 becomes `0x1000`, seconds ×15 plus world time. Mode 10 has its own tick-duration path. |
| Detect that a list needs expiry handling | `CGameEffectList::CheckEffects`, `0x1CD2B2–0x1CD2EB`: `worldTime >= effect.deadline` returns true. It also normalizes some incoming durations. |
| Decide ordinary expiry | `ResolveEffect`, `0x1E8460–0x1E8491`: timing `0x1000`; unsigned comparison at **`0x1E847B`**; if no longer before the deadline, writes `m_done=1` at **`0x1E8487`**. Otherwise reaches native `ApplyEffect`. |
| Remove the expired object | `CGameEffectList::HandleList` calls virtual `ResolveEffect` at `0x1E5008`; tests `m_done` at `0x1E502A`, removes its list node, calls `OnRemove`, then deletes it at `0x1E5036–0x1E5050`. |
| Separate expiry/removal route | `FakeExpireCheck`, `0x1E44FB–0x1E4548`: timing 6/`0x1000`, compares `worldTime + suppliedOffset` to the deadline and directly removes it. `CMessageFakeExpireCheck::Run` calls it at `0x212B99/0x212BAE`. |

The latter route is now identified: script action **322,
[FakeEffectExpiryCheck](https://gibberlings3.github.io/iesdp/scripting/actions/bgeeactions.htm#322)**.
`ExecuteAction` maps action322 through byte table `0x398990` (index107), then dword
table `0x3987AC`, to `0x39857D`. At `0x3985B1–0x3985CF` it transfers the requested
tick offset into the message; `0x3985EC` enqueues it. Its vtable at `0x59ABB0` has
the above Run method. This is an explicit scripted removal request: reconcile actual
remaining lifetime before its comparison, but **do not suppress the action wholesale**.
Which installed scripts use it remains outside this bounded trace.

`CGameSprite::ProcessEffectList` explicitly recognizes a frozen noncaster at
`0x3ABA67–0x3ABA9D`: Time Stop active, actor ID different from caster, active-stat
Time Stop immunity zero. It sets sprite `+0x520C`, **then continues**, rather than
returning. It calls `CheckEffects` for timed/equipped lists at `0x3ABF9E/0x3ABFAE`
and `HandleList` at `0x3AC572/0x3AC58C`. When the stop counter becomes zero it clears
the marker and sets `m_newEffect` at `0x3ABAB5–0x3ABACE`, causing a rebuild.

The ordinary `ProcessAI` path calls `ProcessEffectList` at `0x3AB4DB`, **before**
its own Time Stop action suppression at `0x3AB5BA–0x3AB5D5`. There are additional
effect-list calls, including actor `AIUpdate`, load and time compression. Thus a
hook inside effect timing need not rely on a frozen actor performing an action.
This establishes static frozen-path reachability, **not** every off-area, dormant,
multiplayer, transition or reentrant runtime case. Do not count calls as elapsed time.

Time Stop itself has separate engine state: `CMessageSetTimeStop::Run` writes the
counter/caster at `0x2157C5/0x2157DC`; `CScreenWorld::AsynchronousUpdate` decrements
the counter at `0x2EBB28–0x2EBB36` and clears the caster when it reaches zero. Observe
actual transitions and ordering; do not extend this control timer or stop global time.

## Periodic decisions and Haste

The spelling **CPersistantEffect** is the upstream engine symbol spelling.

| Family | Parent ApplyEffect RVA | Native periodic AIUpdate RVA | Time Stop gate |
|---|---:|---:|---:|
| Poison, op25 | `0x1BB970` | `0x1A59F0` | `0x1A5A0E–0x1A5A3A` |
| Regeneration, op98 | `0x1BEC50` | `0x1A5CA0` | `0x1A5CBE–0x1A5CEA` |
| Disease, op78 | `0x1B17F0` | `0x1A4D90` | `0x1A4DAE` onward |
| Repeated EFF, op272 | `0x1BFD70` | `0x1A47B0` | `0x1A47DE` onward |

Each inspected worker checks Time Stop, caster identity and the appropriate active
stats' immunity before advancing its own periodic logic. The caster and immune actor
continue through. This corroborates the [IESDP Time Stop description](https://gibberlings3.github.io/iesdp/opcodes/bgee.htm#op231)
for these paths, not for arbitrary Lua repeaters or all damage/healing mechanisms.

Concrete regeneration trace: parent `ApplyEffect` constructs a native periodic worker,
seeds remaining duration from `parent.deadline - worldTime` at `0x1BED5F–0x1BED76`,
and seeds period phase from `floor((worldTime - parent[+0x6C])/15) % period` at
`0x1BED97–0x1BEDD2`. Parent `+0x6C` is `m_effectAmount5`; this path uses it as a time
origin. It is not a free field to repurpose. Poison/repeated EFF contain analogous
inline phase math; disease also calls `CPersistantEffect::SetPeriodCounter` at `0x1E87A0`.

The regeneration worker advances its subsecond counter at `0x1A5D02`, subtracts the
elapsed argument from remaining duration at `0x1A5D15`, and tests the 15-tick boundary
at `0x1A5D74–0x1A5D7A`. Mode-specific period comparison occurs at
`0x1A5E26–0x1A5E38`, before native healing is constructed/applied. Poison's counter
arithmetic differs (`+2` at `0x1A5A68`); do not generalize one family's arithmetic.

The shared regenerated list writes its own counter `+0x38` into worker `+0x1C` before
calling that worker (`0x22653D–0x22654F`), then increments the shared counter
(`0x22657E/0x226588`), even when the worker returned because of Time Stop. Consequently
the existing tick guard does **not** prove preservation of remaining pulse phase.
Effect-list rebuilding can also reconstruct workers from the parent time origin.

The Haste coupling is explicit:

1. `ProcessEffectList`, `0x3ACCAC–0x3ACDDC`, chooses actor `m_AISpeed` (`+0x58`):
   general-state bit16 (Slow) → mask3; otherwise bit15 (Haste) → mask0; else mask1.
   The corresponding on-disk constants at `0x59972D..0x59972F` are `01 03 00`.
2. `DoAIUpdate`, `0x353165–0x353189`, tests
   `(schedulerCount & mask) == (actorID & mask)`: Haste accepts every pass,
   normal every second pass, Slow every fourth. Area dispatch supplies the scheduler
   count at `0x17924D`, calls this gate at `0x179254`, then actor AIUpdate at `0x179275`.
3. Ordinary actor AIUpdate calls ProcessAI at `0x3451F3`; the effect-list path then
   calls the regenerated periodic list at `0x3ADFF7` with elapsed argument **1**.

That is a concrete static cause of Haste-dependent periodic cadence. Changing actor
`m_AISpeed`, clearing Haste globally, or slowing ProcessAI would also affect wanted
behavior. Adjust only the selected periodic clock inputs/dispatch. Shared-list counter
rewrites would affect unrelated maintenance workers and are also unsuitable.

## Existing EEex mechanisms versus a new capability

EEex 1.3's [assembly helpers](https://github.com/Bubb13/EEex/blob/9e8098ee696ca4b0bc055e7ff74b283704a8c02e/EEex/copy/EEex_scripts/EEex_Assembly_x86-64.lua#L819)
provide direct pre-call hooks (819–825), pre-conditional-branch hooks (827–889), hooks before
replayed instructions (893–932), and function shims retaining the original
(1349–1363). These helpers and `EEex_Opcode_Patch.lua` are unchanged in the inspected
1.3 tag. Existing effect copy/destruction hooks are at `EEex_Opcode_Patch.lua:6–41`;
they are lifecycle precedent, not arbitrary user metadata serialization support.

No ready pre-expiry/periodic-policy listener or matching timing-site label was found
in the **1.3** common loader database, version-specific pattern databases or Lua scripts.
The common database's `Data-CGameEffect::vftable` anchor (1017–1019) could help locate
the native resolver. `EEex_Opcode_Patch.lua:779–795` also supports a resolver override
when building **new custom opcode** vtables; it does not expose a listener across
existing native effects. Existing **ListsResolved listeners** remain after resolution.
There are earlier internal anchors: `FirstRandCall` at `0x3ABCF4`, `AfterRandCalls`
at `0x3ABDDF`, and `CDerivedStats::Reload()` at `0x3AC4F8`. The first precedes the
expiry checks; the reload call precedes `HandleList` on the rebuild path. These are
not a general timing callback, and EEex already patches the first/reload sites in
`EEex_Fix_Patch.lua:462–480` and `EEex_Stats_Patch.lua:84–87`. Any reuse must preserve
those existing patches and verify path coverage, rather than overwrite an owned site.
A **focused EEex capability** is therefore appropriate, potentially
implemented with the existing Lua/assembly machinery. A native extension becomes a
choice if reusable effect/worker association, lifecycle handling or hot-path cost
requires it; it is not a conclusion forced by the lateness of ordinary callbacks.

Candidate boundaries are now concrete: reconcile a selected parent's clock before
the list expiry checks/resolution; bind parent to worker at native construction; feed
that worker a stable, local elapsed time/phase before its native periodic decision.
The existing frozen-worker gate should remain effective. A resolver-only bypass that
lets every buff disappear immediately when Time Stop ends is not duration preservation.

There is a concrete small interception candidate for the periodic half. The dispatch
at `0x22654F` is a **three-byte indirect call** (`FF 50 08`), while `HookBeforeCall`
accepts only direct `E8` calls (`EEex_Assembly_x86-64.lua:974–980`). A generic
`HookBeforeRestoreWithLabels` could instead cover the preceding complete six bytes at
`0x226549–0x22654E` (`mov rax,[rbx]`; `mov rcx,rbx`) and resume at the native call.
That window has no RIP-relative operand. It is a research candidate, not a validated
patch: incoming branches, other patches and the live calling context still need checks.

The smallest useful clock contract is:

1. Account for actual frozen intervals independently of the subject's action cadence.
   Reconcile only opted-in parents before expiry checks and explicit expiry-based removal.
   An effect added mid-stop earns no compensation for earlier time.
2. Associate each selected native worker with its existing parent at construction.
   Supply a coherent local phase **after** the dispatcher has copied its shared counter,
   and admit native periodic work at the un-hasted rate. Keep the shared counter,
   actor scheduling and unrelated workers untouched.
3. Preserve the same phase across worker rebuilding and Haste transitions; do not
   compensate by applying extra healing/damage or recreating the parent effect.
   Observe start/end ordering, repeated calls at one time and larger time-compression
   arguments before choosing the final accounting mechanism.

Before writing a patch, validate whole original instructions and unique signatures on
the exact executable and detect conflicting hooks. The helpers replay stored bytes;
they are not proof that arbitrary RIP-relative operands/branches relocate safely.
Preserve live flags/registers, Win64 stack alignment/shadow space, native call order and
failure behavior. No Lua exception may leave partially changed clock state. A hook
watchdog passing would still not prove timing semantics. These safety checks are pending.

### Persistence evidence and limit

The versioned header separates saved `CGameEffectBase` data from runtime workers:
duration is base `+0x20`, phase-origin field is base `+0x64`; the live effect's vtable
shifts these to `+0x28/+0x6C`. Workers instead hold period/periodCounter at `+0x18/+0x1A`,
subsecond counter at `+0x1C`, and remaining duration at `+0x28`; the regenerated list
has its own `m_nCounter`. Exposing these fields to Lua does not persist them.

InfinityLoader's
[`CGameEffectList::Override_Unmarshal`](https://github.com/Bubb13/InfinityLoader/blob/f14a00527286f819b8034411bc92ca719cfe3c86/EEex-Core-Shared-Files/source/EEex.cpp#L4935)
loads extended effect-base records through native `DecodeEffectFromBase` and `AddTail`
(5000–5002), while recognizing EEex auxiliary records separately (4968 onward).
It contains no worker-counter restoration. This establishes a reconstruction input,
not exact round-trip values or the absence of another native persistence path.
Native marshal/decode transformations and subsecond phase restoration remain unverified.
EEex's explicit marshal exporters/importers are available if needed, but then stable
effect-instance matching, stacked identical effects and component removal need a design.

## Compatibility and unresolved design decisions

| Boundary | Concrete risk / decision still needed |
|---|---|
| Which durations? | Define the final selection of buffs, harmful periodic parents and their supporting markers/cleanup effects. Permanent/equipped effects, delayed activation, summons and item expiration are not interchangeable finite buffs. Begin with explicit test identities, not a heuristic over every effect. |
| SR versus non-SR | Installed SR4.19 `SPWI305/SPWI613` and SCS35.21 `DWSW305/DWSW613` contain op176 movement and op1 APR, **no op16/317** across their reachable effects. SR source `spell_rev/lib/kreso_haste_slow.tph:115–130,189–200` confirms the distinction. Base `DATA/SPELLS.BIF` instead has op16 p2=0/1. Names and shared SCS spell-state markers cannot select the engine correction. |
| SCS / Time Stop | Installed SPWI909 op328 state180 lasts18s while op231 carries36s. Neither the marker nor an assumed SPL length defines actual stop state. Keep SCS encounter timers/prebuff logic outside scope; source-specific corrections stay with their owner. |
| Maintenance graphs | `tempus_holy_power.tpa:1253–1279` couples op272 upkeep with same-deadline delayed op321 cleanup; `:2270–2279` uses31-tick op44/97 children for Slow coverage. A second op272 APR bridge is at `:3173–3179`, with one-second child at `:2944–2949`. Freezing only the positive parent can leave children expired or let cleanup remove them. Haste normalization must not blanket-select op272. |
| Caster / immune actors | Native workers continue for both. Decide whether buff duration and periodic effects should also continue for each category, including gaining/losing immunity during a stop. Initial prototype tests only a consistently nonimmune noncaster. |
| Slow / disease | Decide whether to preserve their native slower cadence or normalize them too; the first Haste test excludes both. Disease is both a periodic family and potentially a timing modifier. |
| Area spells | Projectiles, area hazards and their lifetimes have separate code. Decide whether creation, lifetime, pulses and hitting frozen targets should each pause. Actor-local success makes no claim about them. |
| Save/load / time compression | Absolute deadlines, parent phase origin, rebuilt workers and side metadata must agree. Do not save raw pointers. `CompressTime` separately calls `HandlePersistantEffects` at `0x350212`, forwarding a larger elapsed argument. Rest/travel/load cannot be treated as ordinary callbacks. Exact serialization coverage and current-save compatibility remain unproved. |
| Consecutive stops | Count each actual frozen tick once, even with back-to-back stops or caster replacement; effects applied midway receive only subsequent compensation. State read at a callback alone can miss a start/end between sparse passes. Observe transition ordering explicitly. |
| Removal / refresh | Dispel, cure, explicit source removal, charge depletion, death and refresh remain native operations. Clock suspension must not become removal immunity. Clear/rebind metadata on removal, copy and worker rebuilding; address reuse is not identity. Action322 must still remove effects according to their corrected remaining lifetime. |
| Component removal | Adjusted native deadlines and temporary metadata must have a defined removal/load policy. Prefer no new save format, but that is not proof a save remains safe without the component. No active-playthrough hotpatch promise. |

Binary anchors for the compatibility reading (all under the read-only game directory):

- `override/SPWI305.SPL`: SHA256 `52fa6b22207fab2427effb7aef29593f189289638cff53dc9cb1835f83fdcb7d`;
  first-ability records `0x2CA` op176 p1=6; `0x32A` op1 p1=6/p2=0 (half-APR encoding).
- `override/SPWI613.SPL`: SHA256 `aac408f7a60e6f7ebe032bdcd37e87605fe455aa87888c42132e45d256a3c013`;
  `0x9A` op176 p1=6; `0xFA` op1 p1=1/p2=0. Includes the local APR bridge.
- Packaged base SPWI305: KEY locator `0x014002FB`, BIF offset `0xDF2BC`, size6898,
  op16 at SPL `0x2F2`; SHA256 `58342f6f9ee8805cf9e458ad3d72b8995967136e5a7b20f78fdcff0ed7f41dc0`.
  Base SPWI613: locator `0x01400369`, BIF offset `0x12D26C`, size4362, op16 at `0x1DA`;
  SHA256 `a31fea52522839011c2d1745848c2a80eb4ebdf60897add390cd60d775e454a3`.
  Packaged base bytes are not a fully modded non-SR installation.
- `override/SPWI909.SPL`: SHA256 `7304d9b963858ad4b3f224327e5b554432c38d5492cda8f1f9ecefe3e79cc74e`;
  record `0xFA` op328 duration18, `0x12A` op231 duration36; last modifying owner unaudited.

## Smallest isolated prototype and acceptance plan — proposed only

Use a disposable BG2:EE **2.7.3.0 / EEex 1.3.1** copy and establish unmodified controls.
Match its executable to the current fingerprint above, then validate candidate patch
windows in the presence of EEex. No older-version support is required. Do not upgrade
or probe the active installation. Disable the prototype on an unexpected patch site.
Use two opt-in behaviors: Time Stop lifetime preservation and Haste-independent
periodic timing, initially scoped to the test actor and exact test effect identities.

One nonimmune subject receives one simple six-second timed AC buff and one twelve-second
native [op98 regeneration](https://gibberlings3.github.io/iesdp/opcodes/bgee.htm#op98)
effect (p1=2/p2=3: one HP per two seconds), with sufficient
missing HP. A separate controller starts Time Stop; it is not the measurement subject.
No area projectile, repeated EFF, damage substitute or buff recreation is needed.

1. **Observe first:** instrument pre-expiry, worker construction/rebuilding, pre-periodic
   decision and removal. Log raw game time, actual stop counter/caster/immunity, actor
   scheduler state, effect identity/source, timing/deadline, parent time origin, worker
   duration/counters and actual native HP events. Include both effect-list fast/rebuild
   paths and more than one callback at the same game time.
2. **Time Stop:** begin with roughly 20 game ticks left on the buff, away from a pulse
   boundary. The stop must outlast those 20 ticks. Require no expiry gap, no HP event
   during the observed frozen interval, the same remaining buff lifetime and time until
   next pulse afterward, normal later expiry, and no catch-up burst. Compare with the
   control; measure any native scheduling quantization, rather than hiding it in seconds.
3. **Haste:** with Time Stop absent, enter/leave genuine native Haste halfway through a
   pulse interval. Require unchanged native healing amount and pulse phase/rate against
   game time, while attacks and movement still show their native acceleration. Count
   resolved attacks against a dummy and measure movement, not icons or animation alone.
   Repeat with actual Improved Haste and the SR-shaped composition as separate cases.
4. **First robustness gate:** force a normal effect-list rebuild during each case; repeat
   with two consecutive stops, removal/refresh during a stop, and a mid-stop application.
   Removed effects must stay removed; newly applied effects get no retroactive credit.
   Rebuild must preserve phase without duplicate native HP effects.
5. **Before broader scope:** save/reload before/during/after if the disposable engine
   permits it; test clean process restart, component absence on a safe baseline, pause,
   rest/time compression and area transition. Then swap regeneration for native poison,
   add the parent/child/cleanup maintenance fixture, and test party/enemy symmetry.

Implementation should retain native effect identity and native HP application, with
clock accounting idempotent by actual elapsed time. Prefer updating selected native
deadlines before any expiry decision over end-of-stop compensation, which loses
already-deleted effects and splits saved deadlines from pending metadata. Periodic
phase needs a separate coherent solution across native worker reconstruction; whether
this can remain entirely save-native is an explicit prototype question.

**Go beyond the prototype only if** frozen-path interception, Haste-independent pulse
phase, ordinary expiry and explicit removal all pass. A result limited to post-expiry
repair, blanket buff recreation, shared actor-clock changes, or replacing native damage
fails this design. An offline address map is progress, not live acceptance.
