# True Time Stop – fair Haste & Slow (standalone)

BG Rebalance's component 360 on its own, for BG2:EE and EET games with EEex and without BG
Rebalance. It makes the same checks and installs the same two files into `override`, the
correction `CBRTC.lua` and its autoload `M_CBRTC.lua`. Nothing else in the game is changed.

Christopher's rule: in a Time Stop everything but the caster and Time-Stop-immune creatures
stops; Haste and Slow change only actions and movement.

The engine freezes creatures in a Time Stop but lets their effects run on: a frozen creature's
spells and potions can run out, and its poison or regeneration counts down, while it cannot act.
Engine Haste also speeds up a creature's regeneration, poison, disease and repeated effects,
and Slow slows them down, because they advance with the creature's own updates. With this
package:

- **Time Stop.** The frozen creatures' effects wait: spell and item durations, delayed effects,
  poison, disease, regeneration and repeated effects continue after the stop with the time they
  had left. The caster and Time-Stop-immune creatures keep their normal clocks.
- **Haste and Slow.** Regeneration, poison, disease and repeated effects pulse at the normal rate
  on hasted and slowed creatures. Actions, attacks and movement stay hasted or slowed.
- **Normal speed** stays as it is. Clouds and other area effects already wait out a stop natively
  and are left alone.

## Requirements

- BG2:EE or EET on game version **2.7.3.0, 64-bit**. Steam's `Baldur.exe` and GOG's
  `BaldurII.exe` of 2.7.3.0 are the same file. The installer reads the executable's header and
  refuses any other build, such as 2.6.6.0. Beamdog's 2.7.3.0 build could not be compared: it
  installs only if it is that same file.
- **EEex**, installed before this package (tested with EEex 1.3.1 and its LuaJIT option). Start
  the game through InfinityLoader.
- Not together with BG Rebalance's component 360, which is the same correction (below).

## Install

1. Close the game and InfinityLoader. Back up your saves.
2. Extract `CBR_TRUE_TIMESTOP-v<version>-windows.zip` into the game folder, the one with
   `Baldur.exe` or `BaldurII.exe` and `InfinityLoader.exe`. It contains
   `Setup-cbr_true_timestop.exe` and the `CBR_TRUE_TIMESTOP` folder.
3. Run `Setup-cbr_true_timestop.exe` and answer **I** (Install). It appends one entry at the end
   of `WeiDU.log` and keeps its backup apart from other mods.
4. Start the game through InfinityLoader.

## Check that it runs

At every game start, before changing anything, the correction checks EEex, the executable (its
build, the four effect worker classes and all eight code locations it changes) and how EEex sees
the effect lists. If anything differs, the game runs natively. Either way one line in
InfinityLoader's console says what happened:

```text
[CBR Time Stop/Haste] on (BG2:EE/EET 2.7.3.0): effects of creatures frozen by Time Stop wait; Haste and Slow leave periodic effects at the normal rate
[CBR Time Stop/Haste] off, the game stays native: <reason>
```

To keep the console output in a file, set `LogFile=InfinityLoader.log` in `InfinityLoader.ini`
(it is blank by default). The line then appears in `InfinityLoader.log` in the game folder,
after the prefix `INFO: LPRINT:`.

There is never a message in the game. Should the correction hit an error while playing, it
switches itself off until the game restarts, the game continues natively, and the log says why.

## Uninstall

Close the game, run `Setup-cbr_true_timestop.exe` again and answer **U** (Uninstall). WeiDU
removes both files.

## Adding or removing it during a playthrough

Not supported. Install it before you start a playthrough, and do not remove it during one.

## With BG Rebalance

Use one installer for this correction: BG Rebalance's component 360 or this package. This
package refuses to install while BG Rebalance's 360 is installed, and BG Rebalance's 360 refuses
while this package is installed, from the BG Rebalance release that also ships this package.
BG Rebalance v0.8.6, the first release with 360, does not check for the package yet. Both
install the same two files under the same names, so even then the game loads the correction
once, and uninstalling either one leaves the other's files in place.

## Known limits

- Saving during a Time Stop, and dispel, cure or death during one, are not covered yet.
- Equipping or unequipping items during a stop was not tested in the lab.
- A slowed creature's pulses can come a tick or two late around a stop, and after a load an
  effect that was already running can move its remaining pulses by one.

## Tested

In a disposable lab: Steam BG2:EE 2.7.3.0 with EEex 1.3.1 (LuaJIT) and no other mod, played by
the lab's test tools. The package was installed from its archive as above. With it, Time Stop,
Haste, Slow, a cloud through a stop, walking and attacking, and a save with its reload behaved
as described at the top. Uninstalling put `override` back to the files it had before the
install. On EET the same two files ran as BG Rebalance's 360 in a fully modded game; this
installer ran on BG2:EE only.

Design and lab evidence: research note 10 and the Time Stop lab notes in
[BG Rebalance](https://github.com/Chrizhermann/chriz-bg-rebalance).
