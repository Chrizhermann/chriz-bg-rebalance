# Round Clock

After a character has finished casting, several hours of travel should usually be enough to cast again. This standalone edition of BG Rebalance component 361 counts time that the game clock actually advances during travel, rest, scripted time jumps, forced multiplayer time updates and the world-screen hour advance.

Elapsed time counts toward spent spell and item aura, recovery after a completed attack, the wait before another Hide in Shadows attempt, and the delay before the engine can check a contingency again. A partial jump grants partial recovery at the character's current speed. An interrupted rest that advances the clock by zero grants zero recovery.

## Requirements and installation

Use a Windows x64 **2.7.3.0** executable for BG:EE, Siege of Dragonspear, BG2:EE, EET or IWD:EE. Install EEex first. The component targets EEex v1.2.0 and v1.3.1 with either embedded Lua or the optional LuaJIT runtime.

1. Close the game. Extract the Windows ZIP into the game folder containing `InfinityLoader.exe`.
2. Run `Setup-cbr_round_clock.exe` and choose **Install**. WeiDU records component 361 in `WeiDU.log`. If you use the full BG Rebalance installer, select component 361 there instead. Component 360 is a separate choice.
3. Start the game through InfinityLoader. Look for `[CBR Round Clock] on` in the loader log. A line beginning `[CBR Round Clock] off, the game stays native:` gives the reason if the build, hook site or required EEex capability differs.

## What to expect

The correction applies to locally owned party members and creatures in loaded areas. During Time Stop, the caster and creatures immune to Time Stop can recover. A spell, item use or attack already in progress keeps its native execution. The engine handles charges, memorization, attack rolls, Hide attempts, periodic effects and the next contingency check.

Loading a save or changing areas without advancing world time grants zero recovery. The component uses the native action-bar refresh for the Hide button. First-frame behavior on a paused arrival and multiplayer delivery are scheduled for in-game testing.

## Uninstall

Close the game. Run `Setup-cbr_round_clock.exe` again and choose **Uninstall** for component 361. WeiDU uses `weidu_external/backup/cbr_round_clock` to restore the previous override files. If you installed through BG Rebalance, use its installer for this step.
