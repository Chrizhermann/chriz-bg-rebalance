# Time Stop / Haste observation lab

This is disposable research infrastructure, not a balance component. It records
native decisions without correcting clocks, rebuilding buffs, replacing healing,
or changing attack/movement scheduling. No hooks activate merely by loading the
diagnostic Lua module. The startup and hook-integration smoke test passed on EEex 1.3.1
([below](#engine-smoke-test-eeex-131-2026-10-20)). So did the first native baseline
capture, `baseline_01` ([below](#baseline-capture-baseline_01-2026-10-20)), the two
native Time Stop captures, `timestop_01` and `timestop_02`
([below](#time-stop-captures-timestop_01-and-timestop_02-2026-10-23)), and the four
native Haste captures, `haste_01` to `haste_04`
([below](#haste-captures-haste_01-to-haste_04-2026-10-23)). No clock correction exists
yet, and no acceptance has run.

The diagnosis, instruction evidence and open design questions are in
[`../10-timestop-haste-engine-clocks.md`](../10-timestop-haste-engine-clocks.md).

## Isolation and provenance

- Game: `%USERPROFILE%\Games\CBR-TimeStop-2.7.3.0`.
- Engine/profile name: `CBR TimeStop Lab 2730`. The profile is resolved through
  Windows Known Documents; on this machine that is
  `%USERPROFILE%\OneDrive\Documents\CBR TimeStop Lab 2730`.
- Source: pristine Steam BG2:EE 2.7.3.0, copied as physical files. No existing
  saves or settings are imported. The source tree is hashed before and after setup.
- Executable SHA256:
  `b51093a49140b2b8a7c046b4652bb8e535be24ebbc12b1d735e0b94217a14d57`.
- EEex 1.3.1, tag commit `a6d21abe44e20509f5d0259ccc6c7e7f9d12b285`, the version
  Christopher chose for everything on 2026-10-18; official components 0, 1 and 8
  (core, main, LuaJIT). The staged `EEex` tree (134 files, 33,554,881 bytes) has the
  lab digest `cd776455c2c9202dcffa526d7ccd81c496bbf8c99d9cd4e260e9ed4bc3b826bd`.
  This replaces the earlier EEex 1.3.0 pin (`9e8098ee696ca4b0bc055e7ff74b283704a8c02e`).
- WeiDU 25100, SHA256
  `0d17e26e3f3ef5b36796eb0ee8ae73cb851d8b62c9702c2e224da2945caafb75`.
- Remote Console 0.2.0, commit
  `661927e56e28435541a3128568cd4ee6d5d80164`; only its Lua/menu files are
  staged in this lab. Diagnostic resources are also staged directly and recorded
  separately from the official EEex installation.

EEex component 9 (Attack Info) is not installed, and a WeiDU.log line for it is
refused. The component only sets `Enable=1` for the Attack Info module in `EEex.ini`
(default `0`), an in-game to-hit display this observation does not need. Its TP2
declaration is unchanged since 1.3.0, which excluded it in the same way.

Compared with 1.3.0, the 1.3.1 tag changes the TP2 version line, UI, keybinding and
utility Lua modules, translations, the pattern database and the loader/EEex DLLs.
Every Lua file that defines an EEex function `CBRTObs.lua` calls, the
`Data-CGameEffect::vftable` pattern and the 2.7.3.0 `function_names.db` are
byte-identical, so the instruction evidence in the research note still applies.
The native primitives (`EEex_Read32`, `EEex_Malloc` and others) come from the changed
DLLs. This is a static comparison; only `CBRTS.Inspect()` and `CBRTS.Install()` in the
engine show that the observer works with 1.3.1.

The game and profile carry matching ownership markers. Paths outside the exact
lab are rejected. Junctions, symlinks and hard links are rejected; verified
Microsoft Cloud metadata is permitted only along Known Documents and this
profile, because OneDrive uses non-redirecting reparse points there.

The setup derives safeguards from `bgee-itemrandomiser-fix/tests/runtime/` and
its handover. Its older, hardcoded EET runner is not used against this lab.
The active modded game remains a read-only reference.

## Offline preparation

Use PowerShell 7 from the repository root. Inputs must match the fingerprints
above. The archive argument is the parent of the extracted `EEex` directory.

The EEex input is a `git archive` export of the pinned tag commit, extracted with
`Expand-Archive`. With `core.autocrlf=true`, Git writes its text files with CRLF line
endings on every platform, as the digest requires. The same command reproduces the
1.3.0 digest from that tag. The release asset `eeex-v1.3.1.zip` (SHA256
`9c8104bd63fe7e7dfff889d89ab2d98e158b6e552846370a924ed7eacea4ecf3`) contains the same
134 files, but 113 text files have LF line endings, so its tree digest
`67e86dbabefa412ce0d510270e95d99e45b9a0356308802b687918fa37609e1a` is refused.

```powershell
$eeex = Join-Path $env:TEMP 'cbr-timestop-lab-20261018'
git clone https://github.com/Bubb13/EEex.git "$eeex\repo"
git -c core.autocrlf=true -C "$eeex\repo" archive --format=zip "--output=$eeex\EEex-v1.3.1.zip" a6d21abe44e20509f5d0259ccc6c7e7f9d12b285
Expand-Archive -LiteralPath "$eeex\EEex-v1.3.1.zip" -DestinationPath "$eeex\EEex-v1.3.1"
pwsh -NoProfile -File research/timestop-lab/Prepare-Lab.ps1 -Phase Copy `
  -EEexArchiveRoot "$eeex\EEex-v1.3.1" `
  -WeiduPath "C:\Games\Baldur's Gate II Enhanced Edition modded\Setup-Branwen.exe"
pwsh -NoProfile -File research/timestop-lab/Prepare-Lab.ps1 -Phase Install
pwsh -NoProfile -File research/timestop-lab/Prepare-Lab.ps1 -Phase Validate
git -C C:\src\private\eeex-remote-console worktree add --detach "$eeex\rc-661927e" 661927e56e28435541a3128568cd4ee6d5d80164
pwsh -NoProfile -File research/timestop-lab/Stage-Diagnostics.ps1 -RemoteConsoleRoot "$eeex\rc-661927e"
pwsh -NoProfile -File research/timestop-lab/Invoke-Lab.ps1
```

Staging copies the Remote Console files only from a clean checkout whose HEAD is the
reviewed pin. `-RemoteConsoleRoot` names that checkout or worktree. The default, the main
checkout, is refused as soon as its HEAD moves on, even by a documentation-only commit.
Staging also builds the lab's QA copy of `UI.MENU` from the lab's own stock file
([fresh test party](#fresh-test-party-in-the-hidden-game)).

These commands do not launch the game. Copy resumes only matching owned files;
an uncertain installation stops for inspection. There is no uninstall or reset
operation. The ownership markers bind the EEex commit, so a lab created under the
1.3.0 pin is refused (`INVALID_OWNERSHIP_MARKER`). A leftover profile folder without
its lab blocks Copy (`PROFILE_ALREADY_EXISTS_UNRELATED`). Neither is removed
automatically. Staging refuses differing assets unless `-Refresh` is supplied and the
existing hashes still match its previous ownership manifest.

The manifests, source inventory and installation logs remain in the disposable
lab. The repository contains no game executable, save or copied proprietary data.

## Runtime coordination

`Invoke-Lab.ps1` without `-Launch` is the read-only preflight. It checks the ownership
markers, the installed EEex files, the executable and the staged diagnostic assets.

On Christopher's PC the game starts only through the verified quiet runner
`lab_quiet_run.py` from the local lab tools. It uses a hidden desktop, a muted windowed
profile, a job object, and guards that stop the game on audio, a pointer clip, a gamma
change or a foreground window. `Invoke-Lab.ps1 -Launch` is not that runner: it starts the
loader with a plain `Start-Process` on the user's desktop, so do not use it there.

Before the first quiet run:

1. Rename the lab copy's `steam_api64.dll` to `steam_api64.dll.bgse-disabled`, so that
   Steam Cloud cannot sync this profile. The runner refuses an active Steam DLL.
2. Run `python -I lab_quiet_run.py prepare <lab> <profile>`. It makes the profile
   windowed and sets every volume to 0, keeping `Baldur.lua.before-quiet-lab` as a backup.

Install, staging and the preflight refuse while any `Baldur.exe` or `InfinityLoader.exe`
runs, so this lab runs alone. Take the exclusive `bg-game-install.lock` of the shared lab
coordination folder, wait until no BG game runs, then run
`python -I lab_quiet_run.py run <lab> <profile> <out.json> 600`. Parallel lab slots
(`bg_lab_slots.py`) start nothing while that lock is held. The run ends at its time limit,
on a message box, or when the game exits; `<out.json>` records the guards' result. Release
the lock by renaming it only after no process runs from the lab.

A failed or uncertain startup is an inspection point, not permission to retry
repeatedly. A surviving process still blocks the next run.

Use only this lab's `override` for Remote Console commands, one command at a time.
First verify the running executable path and perform the client's `ping` and
watchdog checks; a leftover ready file is insufficient. An action-queue response
does not prove the action executed. Check resulting actor/effect state after
engine ticks. Do not import a playthrough save for convenience.

## Fresh test party in the hidden game

The hidden game gets no mouse or keyboard input, and the Remote Console polls only while
START or WORLD_ACTIONBAR renders. A new game therefore goes through the game's own buttons,
clicked with `Infinity_ClickItem`, Christopher's choice on 2026-10-20.

- **QA menu.** `qa_menu.py` reads the stock `UI.MENU` from `chitin.key`/BIF and writes a
  lab-only copy. It names 15 stock items (`CBRTSQA_*`): the SoA logo, Single Player, New
  Game, the character-creation buttons, Import's Character File, the Done buttons, the
  difficulty and the dialogue confirm button. Each name is added only where exactly one item
  with the stock action exists. It also adds an inert START label (2.7.3 reopens START after
  the campaign choice only on the next mouse event) and a 1×1 polling widget to the 12 menus
  that cover START during character creation and dialogue. The builder is idempotent and
  refuses unknown actions, ambiguous or missing items and name collisions.
  `qa_menu.py describe <lab>` prints the expected hash. `Stage-Diagnostics.ps1` builds the
  copy into the lab (`cbr-generated-qa-menu-<sha16>`), stages it as `override/UI.MENU` and
  records the builder, stock and output hashes. The preflight checks it like every other
  staged asset.
- **Client.** `lab_rc.py` (`procs`, `ready`, `lua`, `collect`) talks only to this lab's
  `override`, requires exactly one `Baldur.exe` from the lab, and refuses while a request is
  pending. A request that times out is never resent: `collect` waits for the same request,
  because the console stays deaf during a cutscene. `--arg` values reach Lua as decimal
  byte escapes in `ARGS`, never as code. `--delay` waits before sending, for a timed case.
  A game that exits can never answer: `--expect-exit` (for `rc/quit.lua`) and `collect`
  end with status `exited` once the lab's game is gone, and move a request file the game
  never claimed out of `override`, so that no later start runs it. Every exchange is logged
  under `<lab>\cbr-timestop-output\rc-log\`.
- **Requests.** `rc/*.lua` holds the requests. Read-only: `ping`, `state`, `menus`,
  `status`, `subject`, `nearby`. Changing: `watchdog`, `install`, `arm`, `stop`, `export`,
  `start-soa`, `click`, `pick-character`, `set-name`, `dialog`, `pause`, `queue`, `quit`.
  Each changing request checks its precondition first (menu on the stack, no transition,
  paused game, armed or disarmed capture, the subject's name).
- **Time Stop trigger and clocks.** `queue what=timestop` makes the controller in portrait 1
  wait `SmallWait(N)` AI updates and then apply `CBRTSTP` to itself, so it is the caster
  and the subject is frozen. It refuses without an armed capture, without exactly one of
  each fixture on the subject, while a stop runs, with a busy controller, or with the subject
  as controller. `queue what=fixtures` refuses while a fixture from an earlier case is still
  on the subject. `subject` also reports each actor's current action and the raw counters
  behind native effect timing on 2.7.3.0:
  - `+0x3A0`: the full effect check runs only when this value mod 15 equals the actor ID
    mod 15 (`0x3ABB7C–0x3ABBC5`).
  - `+0x1A08+0x38`: the regenerated periodic list's counter, which the dispatcher copies into
    each worker (`0x22653D`).
  - `+0x520C`: the frozen-actor marker (`0x3ABA9D`).
  - `+0x4BA4`: `m_newEffect`, which is set when a stop ends (`0x3ABACE`).
- **Haste trigger.** `queue what=haste` makes the subject wait `SmallWait(N)` AI updates and
  then apply `CBRTHST` (Haste) or `CBRTIHS` (Improved Haste) to itself. It refuses without
  an armed capture, with a busy subject, with a Haste fixture already on it, with a partial
  or doubled fixture set, or while a stop runs. `subject` lists the Haste fixtures with their
  deadlines. Its `ai_speed` is `m_AISpeed` (`+0x58`): 1 at normal speed, 0 while hasted.

The 2026-10-20 sequence: `ping`, `watchdog`, `ping`, `state`, `install`, `status`, then
`start-soa`, `click` Single Player and New Game, `click` Import and Character File,
`pick-character "Abdel - Fighter - Neutral Good"` (the pregenerated character shipped with
the game), `click` Appearance, colors Done and sounds Done, `click` Name,
`set-name "CBRTS Subject"`, `click` Accept and the difficulty. During the SoA opening the
console was deaf for about two minutes, so `collect` picked up the menu probe. Then
`dialog confirm-on`, 11 `dialog step` requests through Imoen's dialogue (first reply each
time), `pause paused`, `dialog confirm-off`. Imoen joins and is the second actor. In
AR0602 the nearest hostile, a Smoke Mephit, stood about 1,200 pixels away. The caged
NPCs and the Jailkeep Golem are neutral.

## Diagnostic controls

`M_CBRTS.lua` loads `CBRTObs.lua` and exposes `CBRTS`. It does not install hooks.
The first engine session must verify the command surface and hook integration
before measuring any gameplay behavior.

1. `CBRTS.Inspect()` checks the owned lab, image identity, vtables and all eight
   instruction windows. Unexpected bytes stop installation before the first patch.
2. `CBRTS.Install()` compiles recording bodies and explicitly installs the hooks.
   They remain disarmed. An interrupted installation requires a clean process
   restart; do not try to undo or reapply partially installed hooks in place.
3. In a fresh test game, pause and choose one nonimmune, noncaster subject with
   missing HP. A second actor is the Time Stop controller.
4. `CBRTS.Arm(0)` selects portrait zero, records its pointer plus object ID, and
   opens one capture epoch. Arm **before** applying the fixtures so construction
   and worker lineage are visible. Existing workers cannot be retroactively linked.
5. Apply the exact native fixtures below, unpause, and observe one short case.
6. Pause, call `CBRTS.Stop()`, then call `CBRTS.Export("baseline_01")` in a
   **separate** command. Export refuses an existing filename. Read `CBRTS.Status()`
   for overflow, session destruction or other incomplete-capture indicators.
7. Decode the resulting file offline. Export before rearming. Never carry an armed
   capture across load, area travel, actor replacement or a return to the main menu.

Native recording uses a bounded 8,192-record buffer, preserves flags/registers,
and makes no Lua callbacks or file writes in the intercepted timing paths.
Overflow disarms instead of overwriting earlier evidence. Each record is committed
last; the decoder flags incomplete reservations. These choices reduce disturbance;
they do not establish engine-thread quiescence, negligible timing overhead or live
safety. First compare an uninstrumented control with installed-but-disarmed hooks.

| Fixture | Native effect | Purpose |
|---|---|---|
| `CBRTBUF` | op0, -2 AC, six seconds | One simple finite buff |
| `CBRTREG` | op98, p1=2/p2=3, twelve seconds | One native HP every two seconds |
| `CBRTHST` | op16, p2=0, twenty seconds | Native Haste control |
| `CBRTIHS` | op16, p2=1, twenty seconds | Native Improved Haste control |
| `CBRTSTP` | op231, encoded twelve seconds | Native six-second Time Stop request |

The engine must confirm actual durations. These resources have one single-target
ability and one effect, no TLK or secondary-resource dependency, and no area effect.
Baseline fixtures ignore MR and are nondispellable; use explicit source removal
for the first removal test, not a dispel check that cannot affect this fixture.

## Evidence and smallest next test

Eight sites cover parent pre-expiry/removal, regeneration worker creation/copy,
pre/post dispatch, native healing submission and worker destruction. The binary
schema is `CBRTS001`: 128-byte header and 128-byte records. Addresses are diagnostic
identities scoped to a capture; the decoder tracks generations and rejects ambiguous
reuse. A healing submission is not counted as successful healing by itself; the
decoder pairs pre/post-worker HP readings. This first buffer observes regeneration,
not every periodic opcode or arbitrary removal route.

```powershell
python -B research/timestop-lab/decode_trace.py `
  '%USERPROFILE%\Games\CBR-TimeStop-2.7.3.0\cbr-timestop-output\baseline_01.bin' `
  --json '%USERPROFILE%\Games\CBR-TimeStop-2.7.3.0\cbr-timestop-output\baseline_01.json'
```

Decoder exit 0 means structurally complete evidence, **not** gameplay acceptance.
Exit 1 means incomplete/ambiguous capture; exit 2 means invalid input or I/O failure.
Time Stop records are sampled observations, not invented exact start/end edges.

The engine sessions have three bounded steps:

1. A fresh baseline with the one subject, buff and regeneration effect. Verify
   native HP amount, buff expiry, worker construction and rebuilding, and complete
   trace decoding. **Done on 2026-10-20** as `baseline_01`
   ([results](#baseline-capture-baseline_01-2026-10-20)), after the startup/IPC and
   hook-integration smoke test.
2. Repeat with a separate controller's Time Stop when about twenty game ticks
   remain on the buff, away from a pulse boundary. Measure the native expiry and
   periodic phase through the stop; do not correct either yet. **Done on 2026-10-23**
   as `timestop_01` and `timestop_02`
   ([results](#time-stop-captures-timestop_01-and-timestop_02-2026-10-23)).
3. Repeat without Time Stop, entering/leaving native Haste midway through a pulse
   interval. Compare native healing cadence in world ticks. Movement and attack
   controls become acceptance requirements when a correction is proposed. **Done on
   2026-10-23** as `haste_01` to `haste_04`
   ([results](#haste-captures-haste_01-to-haste_04-2026-10-23)).

Only after these traces resolve the disputed engine paths should a separate,
actor/effect-scoped clock correction be designed. Caster/immune behavior, Slow,
area effects, SR/SCS maintenance graphs, consecutive stops, removal/refresh and
save/load remain explicit later gates. This lab has no current-save safety claim.

## Engine smoke test (EEex 1.3.1, 2026-10-20)

This covered only README step 1: startup, Remote Console and hook integration at the fresh
main menu. Nothing was armed or measured, and no save was created or loaded.

- **Build.** The `git archive` export of the tag commit reproduced the pinned tree digest.
  Copy, Install, Validate and staging passed. `WeiDU.log` lists exactly components 0, 1 and
  8 at v1.3.1. The Remote Console files came from a clean worktree at their pin.
- **Runs.** There were two quiet runs through `lab_quiet_run.py run`, 600 s each, while
  holding the exclusive lock. Neither tripped a guard: audio peak 0.0, pointer clip
  unchanged, no message box, nothing left in the job. Both ended at their time limit.
- **Remote Console.** Each run rewrote the ready file. `ping` answered. A runaway loop
  stopped at a 2,000,000-instruction watchdog, and the game answered again afterwards.
- **Run 1.** `CBRTS.Inspect()` passed: image base `0x140000000`, 8 sites, 2.7.3.0.
  `CBRTS.Install()` stopped in its fresh-main-menu check, at `CBRTObs.lua:66`: "attempt to
  call method 'GetActiveEngine' (a nil value)". The EEex binding object
  `EngineGlobals.g_pBaldurChitin` has no such method. The engine global `e` is the same
  object and has it, and the bound field `pActiveEngine` equals `m_pEngineStart` at the main
  menu. Nothing was patched: `installed` and `failed` stayed false, no buffer was allocated,
  and all eight sites kept their original bytes.
  - Fix: the check reads `chitin.pActiveEngine`.
  - `test_observer.py` now runs `Install()`'s precondition with bindings shaped like 1.3.1.
    With the old accessor, its new tests fail with the lab's error.
- **Loader cache.** Run 1 also showed that InfinityLoader adds its own cache to
  `InfinityLoader.ini`: one `CachedExeTime=` and four `CachedAddress=` lines under
  `[Auto-Generated]`. The preflight compared raw hashes, so it refused every launch after
  the first.
  - It now ignores exactly those loader lines; every other byte must still match the
    validated installation.
  - `Test-LabGuards.ps1` covers both cases. Mutants that keep the raw hash, strip such
    lines anywhere in the file, or accept any value all fail.
- **Run 2.** This was a fresh process with the fix re-staged (`-Refresh`). The preflight
  passed after the earlier launch, and `Inspect()` passed again. `Install()` returned
  `installed=true`, 8 sites and `armed=false` in 10 ms. `Status()` showed `failed=false`,
  `reserved=0`, `overflow=0` and no active recorder. All eight sites now start with `E9`, a
  jump to their hook. Ping and status still answered a minute later.

## Baseline capture `baseline_01` (2026-10-20)

This was step 1 of the engine sessions: measurement only, no clock correction.

- **Run.** One quiet run through `lab_quiet_run.py run … 1800`, holding the exclusive lock,
  ended after 864 s by `rc/quit.lua` (the stock `Infinity_ShutdownGame`, no save). No guard
  tripped: audio peak 0.0, pointer clip unchanged, nothing left in the job. The QA menu was
  `61dd3832…8b78`, built from the stock `7987e9d3…31fe` in `data/Patch2.bif`.
- **Party.** A new SoA game on Venture through the [fresh-party
  sequence](#fresh-test-party-in-the-hidden-game). Portrait 0: "CBRTS Subject", the
  pregenerated fighter Abdel, 98 HP, in AR0602. Portrait 1: Imoen. AI speed byte 1
  (normal) and no Time Stop throughout. While the capture was disarmed,
  `ApplyDamage(Myself,20,0)` lowered the subject from 98 to 83 HP. That 20 requested
  crushing damage removed only 15 HP was not investigated; the fixtures do not depend on it.
- **Case.** At world 33172, paused: `Arm(0)` (epoch 1), then the queued `ApplySpellRES` of
  `CBRTBUF` and `CBRTREG`. Both ran within that paused request: a probe at the same tick
  already showed deadlines 33262 and 33352, timing `0x1000`. The game ran from 33172 to
  33434 (262 ticks, about 17.5 s). Then `Stop()`, and `Export("baseline_01")` as a separate
  request: 451 records, no overflow, no failure, no active recorder. The file is the 8-byte
  magic, the 128-byte header and 451 records. It stays in the lab, with its decoded JSON/CSV
  and the request log.
- **Decoding.** `decode_trace.py` exited 0: status complete, 451 of 451 records committed, no
  issues, 179 paired dispatches, 436 fixture events and 15 unattributed lifecycle events.

| Check | Native result |
|---|---|
| HP amount | 6 healing submissions, each +1 HP within its paired dispatch: 83 → 89. The live probe afterwards agreed (89/98). |
| Pulse times | Worlds 33192, 33207, 33237, 33267, 33297, 33327: 20 ticks after the application, then 15, then every 30. |
| Worker dispatch | 179 dispatches, one per world tick from 33173 to 33351. Remaining duration fell by 1 per dispatch. The list counter stayed world − 31498. |
| Construction and rebuild | Two passes at the application (33172) each constructed a worker; the second one ran. Then one tick after every heal (33193, 33208, 33238, 33268, 33298, 33328) the live worker was destroyed and a new one constructed from the parent. Seeded remaining duration = parent deadline − world (180, 159, 144, 114, 84, 54, 24). Seeded phase = floor((world − origin)/15) mod 2 (0, 1, 0, 0, 0, 0, 0). The engine also copies the worker at each heal and each pass; a copy lives until the next pass or heal and is never dispatched. |
| Worker end | The last worker reached 0 at 33351, set done and was destroyed. There was no seventh heal. |
| Buff expiry | A parent is removed only during an effect-list pass. `CBRTBUF` (deadline 33262) went at 33268, 6 ticks late, in the rebuild after the heal at 33267. `CBRTREG` (deadline 33352) went at 33364, 12 ticks late, in a pass without a heal. Pre-expiry checks ran only at 33172, at the six post-heal rebuilds and at 33364. |
| Other actors | 15 unattributed copy/destroy events at 33221–2, 33311–2 and 33401–2 (every 90 ticks), remaining duration about 2^30: another creature's permanent worker of the same class. They are not fixture evidence. |
| Time Stop | Counter 0 and caster −1 in all 451 records. |

What this shows:

- **Pulse rule.** At each dispatch the list writes its counter into the worker, which adds 1.
  The worker's period counter advances when the result is a multiple of 15 (here world ≡ 12
  mod 15), and it heals at 2. The first heal came at the second such boundary after the application (33177,
  33192). The rebuild at 33193 seeded phase 1, one whole second after the origin, so the next
  heal came one boundary later. From the 33208 rebuild on, the elapsed whole seconds were
  even at every rebuild: phase 0, 30-tick spacing. Two clocks thus set the pulses: the list
  counter's 15-tick boundary, and the parent origin, read again at every rebuild.
- **Static path confirmed.** This matches the research note's seeding (`0x1BED5F–0x1BED76`,
  `0x1BED97–0x1BEDD2`), the 15-tick boundary (`0x1A5D74–0x1A5D7A`) and one dispatch per world
  tick for an actor at normal speed.
- **Expiry is not detected at the deadline tick.** A heal-driven rebuild removed the buff 6
  ticks late. Without a heal, the regeneration parent stayed 12 ticks. This trace does not
  show what started the pass at 33364.

For steps 2 and 3:

- Fixtures queued while paused apply at once. A case's origin and deadlines are known
  before the game runs.
- Pulse boundaries follow the list counter, which started with the game, not the
  application tick. Read them from the case's own origin and counter.
- The buff's removal can ride on a regeneration rebuild. Step 2 must note whether its
  removal pass coincides with one.
- Each pause toggle read the world time one tick lower afterwards than just before
  (33104 → 33103, 33173 → 33172, 33434 → 33433); unpausing did not. Use the trace's own
  world values, not the pause probe.

## Time Stop captures `timestop_01` and `timestop_02` (2026-10-23)

This was step 2: native Time Stop through the fixtures, measurement only, no clock correction.

- **Run.** One quiet run through `lab_quiet_run.py run … 1800`, holding the exclusive lock.
  Another session's lab game had to end first. The run ended after 590 s through
  `rc/quit.lua`, without a save. No guard tripped: audio peak 0.0, pointer clip unchanged,
  nothing left in the job.
- **Party.** The [fresh-party sequence](#fresh-test-party-in-the-hidden-game) again, sent by a
  scratch driver that checks the menu after every click. The same actor IDs came back:
  subject 132974572, Imoen 131401684. `ApplyDamage(Myself,20,0)` again left the subject at
  83 of 98 HP.
- **Trigger.** Each case started paused:
  1. `Arm(0)`, then the fixtures, then a `subject` probe.
  2. `queue what=timestop`: Imoen runs `SmallWait(N)`, then applies `CBRTSTP` to herself. N
     came from the probe's list counter, so that the stop would begin at least six ticks
     from a pulse boundary.

  Both stops began on the planned tick, N + 1 ticks after the application. The game then
  ran for 20 s without a pause, about 300 ticks. After that came the pause, then `Stop()`,
  then `Export()` as a separate request.
- **Decoding.** `decode_trace.py` exited 0 for both traces. Both are complete, with all
  records committed (443 and 426), no issues, and 179 paired dispatches each, one per
  world tick. The files stay in the lab with their decoded JSON/CSV and the request log.

| Check | `timestop_01` (buff nearly out) | `timestop_02` (early stop) |
|---|---|---|
| Application | 33004. Deadlines 33094 (buff) and 33184 (regeneration). | 33311. Deadlines 33401 and 33491. |
| Stop | Frozen dispatches 33078 (application + 74) to 33166, caster Imoen. The buff had 16 ticks left. | 33348 (application + 37) to 33436. The buff had 53 ticks left. |
| Stop counter | 178 at the first frozen dispatch, then −2 per world tick down to 2. The encoded 12 s thus froze the subject for 89 dispatches, about 6 s, as IESDP describes. | Same. |
| Frozen worker | Dispatched every tick and returned at its Time Stop gate. Remaining duration held (106, then 90), the period counter held, no healing submission. The list counter still rose by 1 per tick. | Held 143, then 83. Otherwise the same. |
| Buff | Removed **during the stop** at 33094, its deadline. | Removed **during the stop** at 33408, 7 ticks after its deadline. |
| Rebuild in the stop | The removal pass rebuilt the regeneration worker with remaining 90 = deadline − world. The held 106 was dropped. | Remaining 83 = deadline − world. The held 143 was dropped. |
| Stop end | At the first free tick, 33167, the list was rebuilt (`m_newEffect`): remaining 17 = deadline − world, phase 0. | 33437: remaining 54, phase 0. |
| Pulses | Heals at 33027, 33042 and 33072, all before the stop: 83 → 86. None during or after it. | 33341 before the stop and 33461 after it: 86 → 88. |
| Regeneration end | Worker done at 33183, parent removed at 33184 (the deadline). | Worker done at 33490, parent removed at 33498 (deadline + 7). |

What this shows:

- **The frozen subject keeps losing buff time.** The full effect check still runs for a
  frozen actor. It finds the expired buff and removes it. In both cases the buff ended inside
  the stop, at its absolute deadline or at the actor's next check tick after it. Neither
  removal rode on a regeneration rebuild, because nothing heals during a stop.
- **The regeneration worker is gated, but every rebuild reseeds it.** While frozen, it
  neither heals nor counts down. A rebuild reseeds remaining duration from deadline − world
  and the phase from the origin. Two rebuilds did that here: the pass that removed the buff,
  and the forced one at the end of the stop. So the frozen time is lost, and the regeneration
  ends at its absolute deadline. It delivered 3 and 2 HP, against 6 in the baseline. There
  was no catch-up burst.
- **After the stop, pulses follow the absolute grid.** The list counter kept counting
  through the stop, and the phase was reseeded from the origin. In `timestop_02`, the next
  heal was 23 ticks away when the stop began; it came 24 ticks after the stop ended. A
  90-tick stop is three heal periods long, so the grid put the pulse almost back in its old
  phase. A stop of another length would move it.
- **The full effect check runs once per second, at a phase set by the actor ID.**
  `ProcessEffectList` runs `CheckEffects` and the rest of its full pass only in three cases
  (`0x3ABB7C–0x3ABBC5`):
  - the counter at `+0x3A0`, mod 15, equals the actor ID mod 15;
  - `m_newEffect` is set;
  - `+0x4E44` is set.

  From each case's probe, the check ticks were predicted as world ≡ 4 (mod 15) for
  `timestop_01` and world ≡ 3 for `timestop_02`. All four parent removals fell on those
  ticks. This also explains why `baseline_01` removed its regeneration parent 12 ticks late
  (33364 ≡ 4).
- **A pause can move both phases by one tick.** During `timestop_01`, world − list counter was
  31498; during `timestop_02` it was 31497. Between them, a pause read 33312 and then 33311,
  but the subject's counters did not go back. Pulse boundaries and check ticks follow the
  actor's own counters, not world time.

For step 3 and a later correction:

- Preserving a buff through Time Stop must reconcile the selected parent's deadline before
  the frozen actor's next full effect check. A repair after the stop comes too late.
- Each rebuild reseeds the worker from the parent's deadline and origin. A preserved
  remaining duration must therefore survive in the parent. The pulse phase also depends on
  the shared list counter, which keeps running through the stop.
- For the Haste case, `queue` and the `subject` clocks can align the Haste start to the list
  counter in the same way.

## Haste captures `haste_01` to `haste_04` (2026-10-23)

This was step 3: native Haste and Improved Haste through the regeneration fixture, without
Time Stop. Measurement only, no correction.

- **Run.** One quiet run through `lab_quiet_run.py run … 1800`, holding the exclusive lock.
  It ended after 953 s through `rc/quit.lua`, without a save. No guard tripped: audio peak
  0.0, pointer clip unchanged, nothing left in the job.
- **Party.** The same [fresh-party sequence](#fresh-test-party-in-the-hidden-game) and the
  same actor IDs. `ApplyDamage(Myself,20,0)` again left the subject at 83 of 98 HP. Between
  cases, a disarmed run let every lab fixture run out, Haste included, and `ApplyDamage`
  topped the missing HP back up to at least 13.
- **Trigger.** Each case started paused with `Arm(0)`.
  - *Entering* (`haste_01` Haste, `haste_02` Improved Haste): the fixtures, a `subject`
    probe, then `queue what=haste`. The subject runs `SmallWait(N)` and then applies the
    Haste fixture to itself. N came from the probe's list counter and the baseline heal
    rule, so that Haste would begin 7 ticks after the third native heal, midway through a
    15-tick pulse interval. Both began on the planned tick.
  - *Leaving* (`haste_03`, `haste_04`, both Haste): Haste first, applied while paused, then
    about 14 s of hasted running, a pause and the fixtures. Haste's deadline fell 76 and 87
    ticks after the fixtures. `haste_03` was not aligned further. For `haste_04` the driver
    predicted from the probe's counters which full pass would first reach the Haste
    deadline (rules below). It was ready to shift the subject's pulse grid by one tick per
    short pause cycle until a scheduled pass between two pulses would end Haste; the first
    probe already qualified.

  Then 20 s of running without a pause, the pause, `Stop()` and `Export()`.
- **Decoding.** `decode_trace.py` exited 0 for all four traces. All are complete, with all
  records committed (732, 656, 668 and 710) and no issues. A hasted tick has two paired
  dispatches, a normal tick one. The files stay in the lab with their decoded JSON/CSV and
  the request log.

Times are world ticks; +n counts from the fixtures' application.

| Check | `haste_01` (Haste in) | `haste_02` (Improved Haste in) | `haste_03` (Haste out) | `haste_04` (Haste out, mid-interval) |
|---|---|---|---|---|
| Fixtures | 32993. Deadlines 33083 (buff) and 33173 (regeneration). | 33432. Deadlines 33522 and 33612. | 34107. Deadlines 34197 and 34287. | 34667. Deadlines 34757 and 34847. |
| Haste | Began at +71, 7 ticks after a heal. Still on at the end. | Began at +79, 7 ticks after a heal. Still on at the end. | Deadline +76. Removed at +79 by the pass that the heal at +78 forced. | Deadline +87. Removed at +89 by a scheduled pass, 4 ticks after the pulse at +85. |
| Heals | +19, +34, +64; hasted +82, +90, +105, +112, +120, +135, +142, +150, +165, +172. | +27, +42, +72; hasted +83, +90, +105, +113, +120, +135, +143, +150. | Hasted +11, +26, +33, +48, +56, +63, +78; then +93, +123, +153. | Hasted +10, +25, +33, +48, +55, +63, +78, +85; then +97, +127, +157. |
| HP | 83 → 96 | 81 → 92 | 80 → 90 | 80 → 91 |
| Buff removed | At its deadline, in a heal rebuild. | Deadline + 1, heal rebuild. | Deadline + 4, heal rebuild. | Deadline + 8, heal rebuild. |
| Regeneration removed | Deadline + 3, scheduled pass. The worker was done 4 ticks before the deadline. | Deadline + 4, scheduled pass. The worker ran dry 15 ticks before the deadline. | Deadline + 10, scheduled pass. | Deadline + 14, scheduled pass. |

For comparison, `baseline_01` healed at +20, +35, +65, +95, +125 and +155: 6 HP.

What this shows:

- **Haste and Improved Haste double the subject's effect clocks.** Both behaved the same. The
  subject got two AI updates per world tick (`ai_speed` 0), as the static `m_AISpeed` gate
  predicts. Each update dispatched the regenerated list once and advanced its counter. So
  the counter rose by 2 per tick, the worker's remaining duration fell by 2 per tick, and
  pulses came every 7.5 ticks instead of 15. The check counter `+0x3A0` kept pace, so the
  full pass also ran twice per second: hasted removals came 3 and 4 ticks late, against up
  to 14 at normal speed.
- **Hasted regeneration healed up to 2.75 times as often, not twice.** Hasted heals came
  mostly 15, 7–8 and 8–7 ticks apart. Per 30 hasted ticks the four captures gave 2.75, 2.38
  (with the dry stretch below), 2.66 and 2.70 heals, against 1 at normal speed and 2 for
  plain doubling. Every heal here was followed by a rebuild, which reseeds the phase from
  world time in 15-tick steps: floor((world − origin)/15) mod 2. At normal speed that agrees
  with the pulse grid. Hasted, two pulses fall into each step, so 20 of the 32 hasted
  rebuilds started at phase 1, and the next pulse healed at once. Between Haste's start and
  the regeneration's end, `haste_01` healed 10 times in 109 ticks. Normal speed would give
  about 3.6, plain doubling about 7.3. An actor at full HP, whose heals change nothing, was
  not tested.
- **The duration stays in world time, but the worker can run dry first.** No parent deadline
  moved. Each rebuild reseeded remaining = deadline − world, but in between the worker
  counted down twice as fast. In `haste_02` the last rebuild set a remaining duration of 29.
  It ran out 14 ticks later, 15 ticks before the deadline, and that stretch had no pulse.
- **Entering Haste forces a rebuild with a world-time phase.** Applying Haste rebuilt the
  list on the same tick. Both cases began 7 ticks after a heal. `haste_01`, 71 ticks after
  the fixtures, got phase 0 and healed 11 ticks later. `haste_02`, at 79 ticks, got phase 1
  and healed 4 ticks later.
- **Leaving Haste waits for the next full pass, which rebuilds too.** Haste's own deadline is
  checked like any other parent's. In `haste_03` the pass that a heal forced removed it.
  In `haste_04` a scheduled pass removed it, 2 ticks after the deadline and midway between
  two pulses. Both passes reseeded the worker by world time, to phase 1 both times. So the
  first normal-speed pulse, 14 and 8 ticks later, healed, and the 30-tick cadence was back.
- **Three rules replay all five captures without Time Stop.** They were checked against
  `baseline_01` and the four Haste traces, 51 heals and 10 parent removals:
  - every construction seeds remaining = deadline − world and phase =
    floor((world − origin)/15) mod 2;
  - a pulse falls on the update whose list counter + 1 is a multiple of 15, and the phase
    heals when it reaches 2;
  - a full pass runs at the update whose list counter + 1 matches the actor ID mod 15 (the
    step-2 rule; the counter equalled `+0x3A0` in every probe), and at the update after a
    heal or another change to the list.

  One detail is still loose: which tick takes the first hasted update after a pause. It was
  the paused tick in `haste_03` and the next one in `haste_04`. So the `haste_04`
  prediction (34755) came one tick early, still inside the window it aimed for.

For a later correction:

- Under Haste the per-actor counters run twice as fast, and so does every clock that hangs
  on them, the expiry check included, while durations stay in world time.
- The rebuild's world-time phase reseed causes the extra hasted heals. It also causes the
  short second interval at normal speed (+20, then +35 in `baseline_01`). A correction that
  owns a worker's phase must keep it across rebuilds.
- Movement and attack were not measured. They become acceptance requirements once a
  correction is proposed.

## Host validation

```powershell
pwsh -NoProfile -File research/timestop-lab/Test-LabGuards.ps1
$env:CBRTS_TEST_DEPS = '%USERPROFILE%\AppData\Local\Temp\cbr-timestop-research-20260926\pylibs'
python -B -m unittest discover -s research/timestop-lab -p 'test_*.py' -v
```

Python 3.11, `lupa.luajit21`, Capstone 5.0.9, pefile 2024.8.26,
Keystone 0.9.2 and Unicorn 2.1.4 were used. The extra native-analysis libraries
are in the temporary dependency directory, not installed into the game.
For the 1.3.1 pin on 2026-10-20, the same versions were installed with
`pip install --no-deps --require-hashes --target <dir>` beside lupa 2.8 (LuaJIT 2.1):
all 14 guard groups and all 32 Python tests passed. With the smoke-test fixes above there
are 16 guard groups and 34 Python tests, all passing. The fresh-party tooling adds 23
Python tests (QA menu 12, console client 11); on 2026-10-20 all 16 guard groups and all 57
Python tests passed. The Time Stop trigger adds 3 queue-request tests that run the request
against stub bindings; on 2026-10-23 all 16 guard groups and all 60 Python tests passed.
The Haste trigger adds 2 more; after step 3 on 2026-10-23, all 16 guard groups and all 62
Python tests passed.
Fixture and decoder tests use synthetic data; assembly tests use synthetic memory
and the pinned executable on disk. They do not execute the game or prove the
EEex trampoline integration works at runtime.
