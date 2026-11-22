# Ducal Palace Coronation Fix

This standalone WeiDU patch (`CBR_DUCAL_PALACE`, matching BG Rebalance component 102) fixes the Ducal Palace Coronation hostility and Confusion bug in **Baldur's Gate: Enhanced Edition** (with or without Siege of Dragonspear) and **Enhanced Edition Trilogy (EET)**, including installs running Sword Coast Stratagems (SCS).

## What it fixes

- **Real Confusion, Fear, and Charm immunities for Belt and Liia Jannath:** Removes SCS's broken `148` opcode typo and gives both Grand Dukes permanent immunity (plus matching portrait-icon suppression and detectable spell states when present) against Confusion (`128`), Fear (`24`), and Charm (`5` / `241`) while keeping all existing class, kit, and proficiency effects intact.
- **No ally-on-ally or confused friendly-fire Game Over:** Replaces the single-attack `AttackedBy([GOODCUTOFF],DEFAULT)` betrayal triggers on Belt, Liia, and Sarevok during the Coronation with a player-only (`[PC]`) check that ignores confused attackers (`!StateCheck(LastAttackerOf(Myself),STATE_CONFUSED)`) and tolerates one accidental AoE/friendly-fire hit before a follow-up hit after a 6-second grace window triggers betrayal.

## Requirements and installation

Supports Windows **BG:EE**, **BG:EE + SoD**, and **EET** (both **2.6.6.0** and **2.7.3.0**). No EEex required, and safe to install on top of an existing modded/SCS installation without reinstalling other mods.

1. Close the game. Extract `CBR_DUCAL_PALACE-v0.8.12-windows.zip` into your game folder (next to `Baldur.exe` / `SiegeOfDragonspear.exe` and `chitin.key`).
2. Run `Setup-cbr_ducal_palace.exe` and choose **Install**. WeiDU records component 102 in `WeiDU.log`. (If you already use BG Rebalance component 102, do not install both.)
3. Load a save from before entering the Ducal Palace main hall (`AR0108` / `BG0108`) or play the Coronation normally. *(Note: creatures already baked into a save taken inside the hall keep their saved script/effect state; enter fresh or from outside.)*

## Tested

Verified offline with WeiDU 24900 across synthetic BG:EE, BG:EE + SoD, and EET + SCS installations (covering both CRE V1 and CRE V2 formats, variant scripts, double-install idempotence, and byte-exact uninstall). No live in-game playthrough test has been run yet.

## Uninstall

Close the game. Run `Setup-cbr_ducal_palace.exe` again and choose **Uninstall** for component 102. WeiDU uses `weidu_external/backup/cbr_ducal_palace` to restore your previous override files cleanly.
