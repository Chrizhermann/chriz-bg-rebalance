# Time Stop / Haste observation lab

This is disposable research infrastructure, not a balance component. It records
native decisions without correcting clocks, rebuilding buffs, replacing healing,
or changing attack/movement scheduling. No hooks activate merely by loading the
diagnostic Lua module. Engine execution and acceptance are still pending.

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
- EEex 1.3.0, commit `9e8098ee696ca4b0bc055e7ff74b283704a8c02e`;
  official components 0, 1 and 8 (core, main, LuaJIT).
- WeiDU 25100, SHA256
  `0d17e26e3f3ef5b36796eb0ee8ae73cb851d8b62c9702c2e224da2945caafb75`.
- Remote Console 0.2.0, commit
  `661927e56e28435541a3128568cd4ee6d5d80164`; only its Lua/menu files are
  staged in this lab. Diagnostic resources are also staged directly and recorded
  separately from the official EEex installation.

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

```powershell
pwsh -NoProfile -File research/timestop-lab/Prepare-Lab.ps1 -Phase Copy `
  -EEexArchiveRoot '%USERPROFILE%\AppData\Local\Temp\cbr-timestop-lab-20260926\EEex-v1.3.0' `
  -WeiduPath "C:\Games\Baldur's Gate II Enhanced Edition modded\Setup-Branwen.exe"
pwsh -NoProfile -File research/timestop-lab/Prepare-Lab.ps1 -Phase Install
pwsh -NoProfile -File research/timestop-lab/Prepare-Lab.ps1 -Phase Validate
pwsh -NoProfile -File research/timestop-lab/Stage-Diagnostics.ps1
pwsh -NoProfile -File research/timestop-lab/Invoke-Lab.ps1
```

These commands do not launch the game. Copy resumes only matching owned files;
an uncertain installation stops for inspection. There is no uninstall or reset
operation. Staging refuses differing assets unless `-Refresh` is supplied and the
existing hashes still match its previous ownership manifest.

The manifests, source inventory and installation logs remain in the disposable
lab. The repository contains no game executable, save or copied proprietary data.

## Runtime coordination — for the later engine session

`Invoke-Lab.ps1 -Launch` is the explicit launch operation. It holds
`Local\ChrizInfinityEngineLab` until the owned game/loader exit and refuses to
start while **any** `Baldur.exe` or `InfinityLoader.exe` is present. Keep its
PowerShell process alive for the session. It never terminates a process.

The mutex coordinates only runners that use that same name. Other agents' runners
may not participate, so agree on an exclusive game slot before launch. The global
process check reduces collisions but cannot guarantee that an unrelated runner
will not start concurrently. A failed or uncertain startup is an inspection point,
not permission to retry repeatedly. A surviving process still blocks the next run.

Use only this lab's `override` for Remote Console commands, one command at a time.
First verify the running executable path and perform the client's `ping` and
watchdog checks; a leftover ready file is insufficient. An action-queue response
does not prove the action executed. Check resulting actor/effect state after
engine ticks. Do not import a playthrough save for convenience.

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

The next engine session has three bounded steps:

1. Startup/IPC and hook-integration smoke test, then a fresh baseline with the
   one subject, buff and regeneration effect. Verify native HP amount, buff expiry,
   worker construction and rebuilding, and complete trace decoding.
2. Repeat with a separate controller's Time Stop when about twenty game ticks
   remain on the buff, away from a pulse boundary. Measure the native expiry and
   periodic phase through the stop; do not correct either yet.
3. Repeat without Time Stop, entering/leaving native Haste midway through a pulse
   interval. Compare native healing cadence in world ticks. Movement and attack
   controls become acceptance requirements when a correction is proposed.

Only after these traces resolve the disputed engine paths should a separate,
actor/effect-scoped clock correction be designed. Caster/immune behavior, Slow,
area effects, SR/SCS maintenance graphs, consecutive stops, removal/refresh and
save/load remain explicit later gates. This lab has no current-save safety claim.

## Host validation

```powershell
pwsh -NoProfile -File research/timestop-lab/Test-LabGuards.ps1
$env:CBRTS_TEST_DEPS = '%USERPROFILE%\AppData\Local\Temp\cbr-timestop-research-20260926\pylibs'
python -B -m unittest discover -s research/timestop-lab -p 'test_*.py' -v
```

Python 3.11, `lupa.luajit21`, Capstone 5.0.9, pefile 2024.8.26,
Keystone 0.9.2 and Unicorn 2.1.4 were used. The extra native-analysis libraries
are in the temporary dependency directory, not installed into the game.
Fixture and decoder tests use synthetic data; assembly tests use synthetic memory
and the pinned executable on disk. They do not execute the game or prove the
EEex trampoline integration works at runtime.
