# Ducal Palace Coronation Fix

Standalone WeiDU patch (`CBR_DUCAL_PALACE`) for the Ducal Palace Coronation (`AR0108` / `BG0108`) Confusion and hostility Game Over bug in **Baldur's Gate: Enhanced Edition** (with or without Siege of Dragonspear) and **Enhanced Edition Trilogy (EET)**, especially on installs running **Sword Coast Stratagems (SCS)**.

## What it fixes

- **Real Confusion, Fear, and Charm immunities for Belt and Liia Jannath:** Removes SCS's broken opcode `148` typo and grants both Grand Dukes permanent immunity (plus matching portrait-icon suppression and detectable spell states when present) against Confusion (`128`), Fear (`24`), and Charm (`5` / `241`), while preserving all existing class, kit, and proficiency effects.
- **No ally-on-ally or confused friendly-fire Game Over:** Replaces the single-hit `AttackedBy([GOODCUTOFF],DEFAULT)` betrayal triggers on Belt, Liia, and Sarevok during the Coronation with a player-only (`[PC]`) check that ignores confused attackers (`!StateCheck(LastAttackerOf(Myself),STATE_CONFUSED)`) and grants a 6-second grace window for one stray accidental AoE/friendly-fire hit (a follow-up hit after the grace window still triggers betrayal normally).

## Requirements and installation

Supports Windows **BG:EE**, **BG:EE + SoD**, and **EET** (**2.6.6.0** and **2.7.3.0**). No EEex required, and safe to install on top of an existing modded/SCS installation without reinstalling any other mods.

1. Close the game and extract the archive into your game folder (right next to `Baldur.exe` / `SiegeOfDragonspear.exe` and `chitin.key`).
2. Run `Setup-cbr_ducal_palace.exe` and install component `102` (WeiDU records it in `WeiDU.log`; if you already use BG Rebalance component `102`, do not install both).
3. Load any save from **before** entering the Ducal Palace main hall (`AR0108` / `BG0108`), or start a new run. *(Creatures already baked into a save taken inside the hall keep their saved scripts and effects; enter the hall fresh or from outside.)*

## Tested

- **Live in-game verification (`EET 2.7.3.0` + `SCS 35.21`):** Confirmed Belt and Liia resist real *Chaos* (`SPWI508`) while nearby Flaming Fist guards become confused; confused Flaming Fist guards damaging Belt, Liia, or Sarevok and confused `Player1` damaging Belt do not trigger hostility or Game Over; a first non-confused *Fireball* triggers the 6-second grace window without flipping hostility; and a second deliberate *Fireball* after the grace window triggers betrayal and `EA = ENEMY` as intended.
- **Offline WeiDU 24900 test suite:** Verified across synthetic `BG:EE`, `BG:EE + SoD`, and `EET + SCS` installations (covering CRE V1 and CRE V2 formats, variant scripts, double-install idempotence, and byte-exact uninstall).

## Uninstall

Close the game, run `Setup-cbr_ducal_palace.exe` again, and choose **Uninstall** for component `102`. WeiDU restores your previous override files from `weidu_external/backup/cbr_ducal_palace`.
