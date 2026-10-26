# 10 — Time Stop / Haste: engine clock decisions

2026-09-26. **Research only; no prototype implemented or run.** Continues the
[September 25 feasibility report](%USERPROFILE%/.codex/worktrees/installer-v0-real-alpha/chriz-bg-collection/docs/plans/2026-09-25-timestop-haste-feasibility.md).
Game files were read offline. No game/process interaction, save access/editing,
installation, publication, or upstream contact occurred. Unrelated work was preserved.
Upstream work credited here: EEex/InfinityLoader by Bubb; Sword Coast Stratagems by
DavidW; Spell Revisions by Demivrgvs and the G3 contributors.

**Status 2026-10-26:** this research led to the [Time Stop lab](timestop-lab/README.md) (steps
1 to 7) and to Rebalance component 360, Time Stop and Haste effect clocks, which ships the
lab's correction for every creature as `chriz-bg-rebalance/lua/CBRTC.lua`, switched on at
every game start by `M_CBRTC.lua` (see the
[README](../README.md#component-360--time-stop-and-haste-effect-clocks)). The sections below
keep the September analysis as written.

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

Update 2026-10-20, baseline: the first native capture, `baseline_01`, decoded complete
(no Time Stop, no Haste, a subject at normal speed, `CBRTBUF` plus `CBRTREG`). It confirms
the regeneration path described below in the running engine:

- One worker dispatch per world tick, and remaining duration falling by 1 per dispatch.
- Each construction seeds remaining duration from `parent.deadline - worldTime` and phase
  from `floor((worldTime - origin)/15) % period`.
- The 15-tick boundary is tested on the list counter, and there were six native +1 HP pulses
  over the twelve seconds.

The trace adds two facts. First, every heal changes HP, and one tick later the effect-list
pass destroys the worker and rebuilds it from the parent, re-seeding both values. Here that
put the first two pulses 20 and 15 ticks apart before they settled at 30. Second, timed
parents were removed only during such passes, 6 and 12 ticks after their deadlines, not at
the deadline tick. Time Stop and Haste remain unmeasured. Details are in the
[lab README](timestop-lab/README.md#baseline-capture-baseline_01-2026-10-20).

Update 2026-10-23, Time Stop: two native captures, `timestop_01` and `timestop_02`, decoded
complete. A second actor applied `CBRTSTP` to itself, with 16 and 53 ticks left on the
subject's buff. They confirm the frozen-actor reading below in the running engine:

- `ProcessEffectList` still runs its expiry checks for a frozen noncaster, so the buff was
  removed inside the stop both times.
- The regeneration worker was dispatched every tick but returned at its Time Stop gate: no
  healing, no countdown. The shared list counter kept rising.
- The stop's end set `m_newEffect`, and the first free tick rebuilt the list.

Every rebuild in the stop, and the one at its end, reseeded the worker from
`parent.deadline - worldTime` and the origin. So the frozen time was lost: the regeneration
ended at its absolute deadline with 3 and 2 HP instead of 6, and no catch-up burst. After
the stop, pulses followed the absolute grid.

The captures add two facts:

- **The 6- and 12-tick lateness has a cause.** The full pass, including `CheckEffects`,
  runs only when sprite `+0x3A0` mod 15 equals the actor ID mod 15, or when `m_newEffect` or
  `+0x4E44` is set (`0x3ABB7C–0x3ABBC5`). Expiry is therefore checked once per second at
  an actor-specific tick. The predicted ticks matched all four removals.
- **A pause can shift that tick and the pulse boundaries by one tick against world time.**
  Pause toggles step world time back by one tick, but actor counters do not go back.

`CBRTSTP`, encoded as 12 s, set a counter that fell by 2 per world tick. It froze the
subject for 89 ticks. A Time Stop correction must therefore act before the frozen actor's
next full effect check, and keep the preserved lifetime in the parent, because every
rebuild reseeds from it. Haste remains unmeasured. Details are in the
[lab README](timestop-lab/README.md#time-stop-captures-timestop_01-and-timestop_02-2026-10-23).

Update 2026-10-23, Haste: four native captures, `haste_01` to `haste_04`, decoded complete.
Native Haste or Improved Haste began or ended during the regeneration fixture, without
Time Stop. They confirm the `m_AISpeed` coupling below in the running engine:

- The hasted subject got two AI updates per world tick. The regenerated list's counter rose
  by 2 per tick, the worker's remaining duration fell by 2 per tick, and pulses came every
  7.5 ticks. Haste and Improved Haste behaved the same.
- The full pass also ran twice per second, so hasted expiry came at most about 7 ticks late.

The captures add three facts:

- **Hasted regeneration heals more than twice as often.** Every heal was followed by a
  rebuild, and the rebuild reseeds the phase from world time in 15-tick steps. Hasted, two
  pulses fall into each step, so most rebuilds started at phase 1. Per 30 hasted ticks the
  captures gave 2.4 to 2.75 heals, against 1 at normal speed.
- **Durations stay in world time, but the worker can run dry first.** Each rebuild reseeds
  remaining duration from `parent.deadline - worldTime`, and the hasted worker then counts
  it down twice as fast. After the last rebuild it ran out 15 ticks before the deadline in
  `haste_02`.
- **Entering and leaving Haste each force a rebuild with a world-time phase.** The pass that
  adds or removes Haste rebuilds the list. Haste's own expiry waits for the next full pass,
  like any other parent's.

So a Haste correction must slow the selected worker's countdown and pulses to world time
and keep its phase across rebuilds. Actor scheduling, `m_AISpeed` and the shared counter
stay untouched, as the recommendation says. SR-shaped Haste, movement and attacks remain
unmeasured. Details are in the
[lab README](timestop-lab/README.md#haste-captures-haste_01-to-haste_04-2026-10-23).

Update 2026-10-23, correction prototype: the lab's `CBRTFix.lua` corrects both clocks for one
selected subject and the two fixtures. It is opt-in and stays inert until a subject is
selected. Four hooks do the work:

- in each frozen world tick, before the expiry check, the selected deadlines and the
  regeneration origin move one tick later;
- the regeneration worker runs once per world tick on the subject's active time, and a
  second hasted dispatch is a no-op;
- every rebuild gets the kept phase back;
- after a heal, the kept phase is the one a native un-hasted rebuild would seed, so the
  native heal pattern at normal speed stays (Christopher's choice).

Four corrected captures decoded complete:

- **Control.** The corrected control matched the native rules tick for tick.
- **Time Stop.** In an 89-tick stop the buff kept its 20 remaining ticks, and the
  regeneration gave all 6 HP: none inside the stop, the next heal 23 active ticks later as
  before, no catch-up burst. Natively the buff ended inside the stop, and the regeneration
  gave 3 and 2 HP.
- **Haste.** Both Haste cases, entering midway and ending midway, healed 6 times with native
  spacing, against 13 and 10 natively.

Two one-tick residuals remain under Haste. A regeneration applied while paused to a subject
that is already hasted can start its grid one tick early. A rebuild in the second hasted
update of a tick leaves the worker one tick longer. Neither changed a heal count here; the
lab README describes fixes for both.

Expiry still waits for the subject's next full pass, so its timing stays native. The go-beyond
gate below is not passed yet: explicit removal is untested. Attacks and movement, corrected
Improved Haste and SR-shaped Haste, consecutive stops, removal during a stop, save/load and
caster/immune subjects are open too. Christopher closed the prototype step on 2026-10-24; the
fixes for both residuals and these open items go into the next lab run. Details are in the
[lab README](timestop-lab/README.md#corrected-captures-fixctl_01-fixstop_01-fixhaste_01-and-fixhaste_02-2026-10-23).

Update 2026-10-25, lab step 5: the revised correction (five hooks) fixed both residuals, and on
Christopher's choice it now also runs periodic effects in world time under Slow, while
movement and attacks stay slowed. One run gave 29 traces; 27 decoded complete, and the two
armed after a load were incomplete as expected.

- **Haste.** Normal, Improved and Weak Haste, entering and ending, healed on the un-hasted
  ticks, and the worker ended at deadline − 1. SR-shaped Haste has no op16: the subject keeps
  one update per tick, so nothing needs correcting.
- **Slow.** Natively the slowed subject updates every second tick and healed 3 times instead of
  6. Corrected, it healed 6 times, at most one tick late, because a heal can only land on one of
  its updates.
- **Pauses.** Nine pauses, with and without Haste, left the corrected heals on their ticks.
- **Stops.** Two stops in a row shifted the deadlines by each frozen tick once (178). A
  regeneration removed during a stop stayed removed. One applied or refreshed during a stop got
  no credit for the frozen time: its first tick was the first free one, and its whole duration
  ran after the stop. Removal and reapplication without a stop behaved the same.
- **Caster and immune subjects.** The engine freezes neither, the correction counted no frozen
  tick, and their effects ran in world time through the stop, as natively.
- **Attacks and movement.** Native and corrected Haste both walked 192 pixels in 11 ticks
  instead of 22 and hit 5 times instead of 4 in the same time, while only the corrected subject's
  regeneration kept world time (6 heals instead of 14).
- **Save/load.** Shifted deadlines and the regeneration's origin are native effect fields: a
  quick save kept them, and the reload restored them. The correction's own phase state is not
  saved; after the load the regeneration ran natively, on a grid restarted with the subject's
  list counter, 2 ticks off here but with the same heal count.

Expiry still waits for the subject's next full pass. The four go-beyond conditions below held
for the fixture: frozen-path interception, Haste-independent pulse phase, ordinary expiry and
explicit removal. That covers one subject and two lab effects; whether to go beyond the
prototype is Christopher's decision. Saving during a stop, time compression, area transition, area effects,
maintenance graphs, other periodic opcodes and party/enemy symmetry are open. Details are in
the [lab README](timestop-lab/README.md#lab-run-of-2026-10-25-step-5).

Update 2026-10-25, Christopher's decisions: poison, disease and repeated EFF get exactly the
regeneration handling (frozen time kept, world time under Haste and Slow), as the September 25
feasibility plan already intended. Area effects stop with the stop as well: no pulse and no
lifetime lost. [IESDP op231](https://gibberlings3.github.io/iesdp/opcodes/bgee.htm#op231) says
the engine already suppresses them during a stop but lets their duration run; the code says
otherwise (next update), and lab step 7 confirmed the code. Installing or removing the component
in a running playthrough is not supported, so component absence needs no lab test.

Update 2026-10-25, the other periodic families and area effects (offline, 2.7.3.0, names from
EEex's `function_names.db`):

- **One clock for all four families.** Poison, disease, repeated EFF and regeneration workers
  live in the sprite's periodic list (`+0x1A08`). Its dispatcher (`0x226500`) copies the list
  counter (`+0x38`) into each worker (`+0x1C`), calls the worker with the caller's elapsed, and
  raises the counter once per call. A worker pulses when its counter plus a family step is a
  multiple of 15: regeneration, disease and repeated EFF add 1, poison adds 2. All four seed
  the remaining duration from `parent.deadline - world` and the phase from
  `floor((world - parent+0x6C) / 15) % period` (disease through
  `CPersistantEffect::SetPeriodCounter`, `0x1E87A0`, called only by the disease constructor).
  `+0x6C` is therefore the time origin of all four, not only of op98, and the correction's
  Haste/Slow logic applies to each with its family step.
- **Sites.** After the phase seed, before `CObList::AddTail`: poison `0x1BBB05` (the bytes and
  registers of regeneration's `0x1BEDD2`: actor rbp, parent rdi, worker rbx), repeated EFF
  `0x1BFEC8` (actor rsi, parent rdi, worker rbx), disease `0x1B1894` and `0x1B1AC1` (actor
  rdi, parent rsi, worker rbx). Epilogs reached by every return: regeneration `0x1A5F19` and
  poison `0x1A5C8A` (`48 83 C4 58 5E 5B`), disease `0x1A5156` (`48 83 C4 68 5E 5B`), repeated
  EFF `0x1A4A91` (`48 83 C4 68 41 5E 5B`, after its stack-cookie check). A sixth worker,
  `CPersistantEffectMove` (AIUpdate `0x1A5700`, built at `0x1BD7B1`), has no duration or pulse
  and is Time-Stop-gated like the others.
- **Area effects.** `CProjectileArea::AIUpdate` (`0x2284B0`), the 13 other projectile classes'
  AIUpdate, `CVisualEffect`, `CGameTemporal`, `CGameStatic`, `CGameFireball3d` and
  `CGameChunk` return at once while `m_nTimeStop` runs, unless the object is the caster.
  `CProjectileArea` counts its lifetime in triggers (`+0x3C6`) and its trigger delay
  (`+0x3CE`) inside its own update, after that gate. A cloud therefore keeps its whole
  remaining lifetime through a stop, which is what Christopher asked for and contradicts
  IESDP; lab step 7 confirmed it (update below).
- **Saving.** `CProjectile::CanSaveGame` (`0x22BA00`) refuses while a projectile is in flight
  and `CGameTemporal::CanSaveGame` (`0x34BCA0`) while a temporal object is unfinished. The quick
  save that wrote nothing shortly after a stop fits a leftover object of the stop's spell; a
  native control is still open. In step 6, a quick save right after the caster's op231 ran out
  wrote at the first click.

Design for the full scope (proposed 2026-10-25), replacing the one-subject prototype:

- Every sprite, party or not. Frozen ticks are counted per actor; at each one, every timed
  effect with an absolute deadline (and delayed ones with an absolute start) moves one tick
  later, and `+0x6C` moves for op25, op78, op98 and op272. Groups such as Tempus' Holy Power
  (op272 upkeep, children, delayed op321 cleanup) stay consistent because all their parts move
  together.
- Haste, Slow and pauses: per actor, one delivery per active tick, decided once per dispatcher
  pass so that every worker of the actor sees the same decision; the counter follows a fixed
  per-actor offset plus active time; the boundary scan uses the family step; each worker keeps
  its own first uncounted tick (the 4-byte padding after `+0x28` in the four worker classes,
  to be verified per class). A worker built after the tick's delivery seeds its phase for the
  next tick, as an un-hasted rebuild would. Native reseeds at rebuilds stay, so normal speed is
  exactly native and the per-parent phase table of the prototype is not needed.
- Bookkeeping moves to Lua behind thin assembly gates (per-actor tables, cleanup on destroyed
  objects and on load), so the logic is testable on the host; an error disables the correction
  and leaves the game native.
- Clouds need nothing beyond the lab confirmation, which step 7 gave. Save/load behaves as in
  step 5.

Update 2026-10-26, lab step 6: [`timestop-lab/CBRTCor.lua`](timestop-lab/README.md#correction-for-every-creature-cbrtcorlua)
implements this design for every creature. Eight thin gates call Lua: the frozen marker, the
periodic dispatcher's entry and its per-worker counter copy, and the five constructions
(regeneration, poison, disease twice, repeated EFF). Per-worker state stays in Lua, so the worker
padding was not needed. Four lab runs on fresh parties, the third with 18 cases and the fourth
with stops aimed at a slowed creature:

- **Every creature, all four families.** Party members, three neutral dummies and a hostile
  smoke mephit alike. In an 89- or 90-tick stop each frozen creature's deadlines and origins moved
  by its own frozen ticks, and every family gave its 6 units with the phase kept across the stop
  (natively 3 or 4). The caster and an op310-immune creature kept world time, as natively.
- **Haste and Slow.** Hasted creatures gave 6 units instead of 11 to 15, slowed ones 6 instead of
  2 or 3, the slowed ones at most a tick late. With several families, a slowed creature's last
  unit can be lost when it falls on the effect's last tick and the creature skips that tick.
- **Normal speed.** Corrected creatures without Haste, Slow, pauses or stops matched the native
  ones; with the correction enabled right before the applications, every dispatch was native.
- **Groups.** The Holy-Power-like group (op272 upkeep, op44 child, delayed op321 cleanup) moved
  as one: all three parts by the same frozen ticks.
- **Time compression and loads.** `DayNight` to the next full hour (about 4,800 ticks) passed
  natively: one dispatch with the whole span per creature, no catch-up. A quick save after a
  corrected stop kept the moved deadlines and origins; the reload cleared the correction's state
  through EEex's destroyed-session listener, and the effects ran on to their moved deadlines on
  the native grid the load restarts (5 units instead of 6 across the load).

The runs found four defects, each fixed with host tests first: an effect applied while paused
right after Enable stretched its creature's first dispatch; a hasted creature updated once
before the stop began counted that tick as frozen; a slowed creature lost the 15-tick boundary of
the active tick it skipped right before its first frozen update, and with it a unit, since the
correction delivered that tick in the frozen update and the native workers ignore frozen
updates; and a slowed creature updated before the caster missed the frozen tick it skipped next.
The fourth run timed three stops onto the slowed case and confirmed both slowed fixes. The engine
also showed that a stop's first tick freezes only the creatures updated after the caster (90
frozen ticks against 89). Still open: a lab capture of a cloud through a stop (step 7 below), and a
stop ending between a hasted creature's two updates (host-tested only). Christopher, 2026-10-26: saving
during a stop, dispel, cure and death come later; area transition needs no test; the slowed
creature's lost last unit is not urgent and goes on the agenda. Details are in the
[lab README](timestop-lab/README.md#lab-run-of-2026-10-26-step-6).

Update 2026-10-26, lab step 7: a real Incendiary Cloud (`SPWI810`) ran through a stop, followed
by [`timestop-lab/CBRTCld.lua`](timestop-lab/README.md#cloud-observer-cbrtcldlua) at every update
of five sampled creatures. In four cases (P0's cloud corrected and as a native control, Imoen's
own cloud through her own stop, and a cloud without a stop) the cloud made 685 updates from its
arrival to its tenth explosion, 76 between explosions, stop or not. Inside each 90-tick stop its
countdown and explosions left stood still and no sampled creature's hit points changed, the
caster's inside the cloud included; the cloud skipped the stop's ticks (89 when its update in
the stop's first tick came before the caster's, the rule creatures follow) and lost no lifetime.
A hit already on its way when the stop began arrived after it. The code reading above holds and
IESDP's running area duration does not: Christopher's rule for area effects holds natively, and
the correction needs nothing for clouds. Details are in the
[lab README](timestop-lab/README.md#lab-run-of-2026-10-26-step-7).

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
| Which durations? | Define the final selection of buffs, harmful periodic parents and their supporting markers/cleanup effects. Permanent/equipped effects, delayed activation, summons and item expiration are not interchangeable finite buffs. Begin with explicit test identities, not a heuristic over every effect. Decided 2026-10-25 (Christopher): every periodic family (poison, disease, repeated EFF) gets the regeneration handling. Lab 2026-10-26 (step 6): `CBRTCor.lua` moves every effect with an absolute deadline or a delayed start, and the periodic origin of all four families, timed or equipped, on every creature; summon and item lifetimes were not tested. |
| SR versus non-SR | Installed SR4.19 `SPWI305/SPWI613` and SCS35.21 `DWSW305/DWSW613` contain op176 movement and op1 APR, **no op16/317** across their reachable effects. SR source `spell_rev/lib/kreso_haste_slow.tph:115–130,189–200` confirms the distinction. Base `DATA/SPELLS.BIF` instead has op16 p2=0/1. Names and shared SCS spell-state markers cannot select the engine correction. |
| SCS / Time Stop | Installed SPWI909 op328 state180 lasts18s while op231 carries36s. Neither the marker nor an assumed SPL length defines actual stop state. Keep SCS encounter timers/prebuff logic outside scope; source-specific corrections stay with their owner. |
| Maintenance graphs | `tempus_holy_power.tpa:1253–1279` couples op272 upkeep with same-deadline delayed op321 cleanup; `:2270–2279` uses31-tick op44/97 children for Slow coverage. A second op272 APR bridge is at `:3173–3179`, with one-second child at `:2944–2949`. Freezing only the positive parent can leave children expired or let cleanup remove them. Haste normalization must not blanket-select op272. Lab 2026-10-26 (step 6): a group of that shape (op272 upkeep every second, op44 child, op321 cleanup delayed 12 s) moved as one through a stop, every part by the creature's own frozen ticks. |
| Caster / immune actors | Native workers continue for both. Decide whether buff duration and periodic effects should also continue for each category, including gaining/losing immunity during a stop. Lab 2026-10-25: the engine freezes neither a caster nor an op310-immune subject; with the correction selected, both kept world time, buff expiry included. Lab 2026-10-26 (step 6): the same with every creature corrected. Gaining or losing immunity during a stop is untested. |
| Slow / disease | Slow decided 2026-10-25 (Christopher): periodic effects run in world time under Slow too; movement and attacks stay slowed. Lab 2026-10-25: corrected, 6 heals instead of 3, at most one tick late, since a slowed actor updates every second tick. Lab 2026-10-26 (step 6): all four families on slowed creatures, 6 units instead of 2 or 3; a pulse on the tick a slowed creature skips right before a stop comes up to two active ticks late. With several families an effect's last pulse on its last, skipped tick can be lost; Christopher, 2026-10-26: not urgent, on the agenda. Disease as a periodic family is corrected like regeneration; as a timing modifier it is untested. |
| Area spells | Projectiles, area hazards and their lifetimes have separate code. Decide whether creation, lifetime, pulses and hitting frozen targets should each pause. Actor-local success makes no claim about them. IESDP op231: area-effect projectiles are suppressed until the stop ends while their duration runs; projectiles in flight wait. Decided 2026-10-25 (Christopher): area effects stop with the stop, with no pulse and no lifetime lost. The 2.7.3.0 code already freezes every projectile class, `CProjectileArea`'s trigger count and delay included, so IESDP's running duration does not match it. Lab step 7 (2026-10-26) confirmed it: a real Incendiary Cloud kept its 10 explosions and 685 updates through a 90-tick stop, changed nothing and hit no one inside it, whoever cast it, and a hit already on its way waited out the stop. Nothing to correct. |
| Save/load / time compression | Absolute deadlines, parent phase origin, rebuilt workers and side metadata must agree. Do not save raw pointers. `CompressTime` separately calls `HandlePersistantEffects` at `0x350212`, forwarding a larger elapsed argument. Rest/travel/load cannot be treated as ordinary callbacks. Exact serialization coverage and current-save compatibility remain unproved. Lab 2026-10-25: a quick save after a corrected stop kept the shifted deadlines and the regeneration's origin through the reload; the correction's phase state is not saved, and after the load the grid restarted with the subject's list counter. A quick save shortly after a stop wrote nothing once (cause not isolated); saving during a stop is untested (later, Christopher 2026-10-26). Lab 2026-10-26 (step 6): `DayNight` to the next full hour (4,824 ticks) passed natively, one dispatch with the whole span per creature; a quick save right after a corrected stop kept every creature's moved deadlines and origins, and the reload cleared the correction's state through EEex's destroyed-session listener (5 units instead of 6 across the load, as the list counters restart). |
| Consecutive stops | Count each actual frozen tick once, even with back-to-back stops or caster replacement; effects applied midway receive only subsequent compensation. State read at a callback alone can miss a start/end between sparse passes. Observe transition ordering explicitly. Lab 2026-10-25: two stops 16 ticks apart counted each frozen tick once (178); an effect applied mid-stop was compensated only for the frozen ticks after it. Caster replacement is untested. |
| Removal / refresh | Dispel, cure, explicit source removal, charge depletion, death and refresh remain native operations. Clock suspension must not become removal immunity. Clear/rebind metadata on removal, copy and worker rebuilding; address reuse is not identity. Action322 must still remove effects according to their corrected remaining lifetime. Lab 2026-10-25: op321 removal stayed removal, during a stop and without one, and a refresh during a stop started a full new duration after the stop. Lab 2026-10-26 (step 6): the same with every creature corrected, and a regeneration applied to a frozen creature got no credit for the frozen ticks before it. Dispel, cure, charge depletion, death and Action322 are untested (dispel, cure and death later, Christopher 2026-10-26). |
| Component removal | Adjusted native deadlines and temporary metadata must have a defined removal/load policy. Prefer no new save format, but that is not proof a save remains safe without the component. No active-playthrough hotpatch promise. Decided 2026-10-25 (Christopher): installing or removing the component in a running playthrough is not supported; no lab test. |

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

Status 2026-10-23: the prototype exists as
[`timestop-lab/CBRTFix.lua`](timestop-lab/README.md#correction-prototype-cbrtfixlua). For the
fixture it met the Time Stop requirements of step 2 and the healing requirements of step 3,
with a one-tick phase offset in one Haste case. In every case the rebuilds kept the phase
without a duplicate HP event, the first item of step 4. Attacks and movement, the other Haste
cases and the rest of steps 4 and 5 are open (see the update above).

Status 2026-10-25: lab step 5 covered steps 3 and 4 for the fixture: Improved and SR-shaped
Haste, attacks and movement, two consecutive stops, removal, refresh and application during a
stop. Of step 5 it covered save/reload after a stop and pauses. Saving during a stop, rest/time
compression, area transition, process restart, poison, the maintenance fixture and party/enemy
symmetry remain; component absence was dropped (see Christopher's decisions above).

Status 2026-10-26: lab step 6 covered the rest of step 5 except saving during a stop, area
transition and process restart: time compression, poison and the other families, the maintenance
fixture, and party and enemy creatures alike, with every creature corrected (see the update
above). Christopher, 2026-10-26: saving during a stop comes later, and area transition needs no
test. Lab step 7 then confirmed that a cloud freezes completely in a stop and keeps its lifetime.

Status 2026-10-26, component 360: the correction of step 6 became Rebalance's core
`CBRTC.lua`, installed by WeiDU with only its autoload. In the lab game it switched itself on
at the main menu without a console and corrected a stop, Haste, a save and reload and the stop
and Haste after it. In the full CEBG stack (EET, Recommended preset) it did the same for Spell
Revisions' Time Stop and Oil of Speed after loading a save right after the game started, which
covers a clean process restart before a load. Saving during a stop, dispel, cure and death in
a stop, and equipping or unequipping during one remain open.

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
   permits it; test clean process restart, pause, rest/time compression and area transition
   (component absence dropped on 2026-10-25). Then swap regeneration for native poison,
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
