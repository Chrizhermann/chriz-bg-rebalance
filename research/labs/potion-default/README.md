# Local disposable potion pilot — not a released component

This bundle is a reviewable native-trial candidate. **No live trial has been
accepted. Do not install it in the played/reference game.** The broader linked
and regeneration prototype remains separate; this pilot does not fulfill the
all-potion feature.

Scope: Heroism `POTN09`, Genius `POTN29`, Master Thievery `POTN36`, Mind Focusing
`POTN37`, Perception `POTN39`, Power `POTN41`, and whichever corresponding
`DW#PTNxx` SCS copies are present. Other potion sources are outside this pilot.
Safe owned bonuses refresh the existing native effect's expiry. HP-sensitive
families ignore a repeat's owned bonuses while the active package remains;
the dose is consumed normally. Original item/resource bytes are not patched.

The two mutually exclusive local policies are component **0: unique** and
**1: except_genius**. These are local trial identifiers, not public 330/331.
Genius exemption follows the compiler's current effective canonical semantics,
not every intelligence bonus or a historical item value. Use separate disposable
copies to compare policies; do not uninstall existing WeiDU entries to switch.

## Preparation and prerequisites

Build from the source checkout, choosing a nonexistent directory outside any
game and outside the checkout:

```powershell
python tools/build_potion_trial.py --output %USERPROFILE%\AppData\Local\Temp\cbr-potion-trial-candidate
```

The generator only writes that new staging directory. It copies no potion,
save, engine, loader or EEex binary and executes nothing. `trial-manifest.json`
records bundle hashes and the pinned binary fingerprints. WeiDU and its license
are included for a later separately authorized disposable installation.

Required target: pinned BG2EE **2.7.3.0**, one of the two exact recorded EEex
binary sets (**1.3.0 pinned** or **1.2.0 default direct trial**), LuaJIT, and
effective direct resource forms accepted by the compiler. Fingerprints are checked by
the installer (MD5) and again at startup (SHA-256), with exact native hook-byte
checks additionally retained. There is no production digest-bypass switch.

The read-only default resource tree `%USERPROFILE%\Games\Chriz Easy BG\game`
supplies the separately recorded **EEex 1.2.0** set. Relevant direct-path Lua
providers and generated-trampoline tests were reviewed separately by the lead;
this permits an experimental disposable copy without upgrading that profile.
It is not a general 1.2/1.3 compatibility claim or native-trial acceptance.
Mixed sets are rejected. Never install into the reference tree itself.

## Commands only after exact disposable-trial authorization

Copy the generated bundle's contents into the specifically approved disposable
game copy. During that separately approved setup, first verify its isolated
`Engine.lua`/profile path, then create a plain `.cbr-potion-trial` marker in that
disposable copy only. The installer refuses even matching binaries without the
marker. This package does not create it or verify isolation on its own. Then
run ONE command there:

```powershell
.\setup-cbr_potion_trial.exe --force-install-list 0 --no-exit-pause
# Or, in a separate disposable copy:
.\setup-cbr_potion_trial.exe --force-install-list 1 --no-exit-pause
```

Installation adds only `override/M_CBRPQ.lua` and twelve owned modules in
`EEex_scripts/override/`. It refuses existing files in that namespace. It does
not edit `EEex_Modules.lua`, install the early lifetime tracker, patch potion
resources, edit a save or launch anything. Keep other agents' game tests
coordinated; this bundle does not start a competing executable. A future trial
must use the existing `Local\ChrizInfinityEngineLab` runtime mutex and refuse
to launch while any game executable is running. No launcher or Time Stop
manifest is copied by this package.

At the next separately authorized launch through InfinityLoader, M_CBRPQ runs
in the pinned includes stage before `CInfGame` exists. It loads each wrapped
module into a checked registry because EEex_DoFile returns no module value and
can swallow errors. It compiles current engine-resolved resources at startup,
then rejects linked owned records or regeneration98 with a pilot-scope error
before any native patch. It never embeds captured potion bytes or demands their
reference counts, order or values. Unsupported delivery/layout semantics retain
the compiler's concrete diagnostic instead of a false success.

`CBRPQTrialStatus()` returns a read-only snapshot containing `armed`, `enabled`,
`failure`, `phase`, `policy`, `sources` and `binaryProfile`. `armed` is true only
after successful native installation; a runtime failure changes the phase to
`failed`. It creates no actor/item, saves nothing and emits no periodic log.
Partial native installation requires restarting
the process; no native patch rollback is claimed.

## Minimal manual acceptance, still pending

On one disposable actor, compare an initial dose with a repeat before expiry:
Master Thievery/Perception retain one potency and refresh; distinct potion
types may overlap; an unrelated spell/equipment bonus remains. Test reordered
or changed effective data through the automated compiler fixtures, not edits
to the played save. For Heroism/Power, damage the actor before a repeat and
verify no extra healing, HP clamp or bonus-deadline extension. Check the two
Genius policies in separate runs. Include present SCS copies in both use orders,
ordinary dispel/removal/reuse, and save/reload in a fresh trial save.

Keep the first native check to roughly10-15 minutes. Compare the native expiry
timestamps for long-duration effects; naturally expire one short-duration
representative such as Power. Record long-duration natural expiry as not yet
observed rather than waiting hours or rewriting effect deadlines/global time.
These checks are planned, not completed or proof of current-save safety.

Existing independent tests cover more engine behavior than this package, but
synthetic installer checks and copied-instruction probes are not live acceptance.
Credit: EEex / InfinityLoader by Bubb; SCS by DavidW; native BG2EE resources and
engine by their respective authors. No upstream contact or publication occurs.
