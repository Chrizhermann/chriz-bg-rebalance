# SR anti-magic existing-install patch

Current source follows [We overwrite](../../AGENTS.md#we-overwrite): Spell Revisions
is not a feature requirement, and changed payloads or descriptions do not veto an
owned write. The release instructions below describe the older v0.8.10 archive;
its separate setup template still has SR footprint gates pending integration.
Do not infer that the source policy update has been released or live accepted.

Source version **v0.8.10** (210 and 211 are unchanged since v0.8.1 except for their texts in v0.8.9;
212 and 213 are new in v0.8.9). Component 210 was applied
with authorization to Christopher's private stream installation on October 6;
211 was not. See the collection handover for backups and verification. Native
gameplay acceptance remains separate from the automated release checks.

- **210:** Pierce Magic halves current MR, subtracting at least 10 and at most
  40 percentage points, rounded up; never below zero. Duration: five rounds.
  Recasts refresh the existing reduction, preserving its original amount.
  Combines with Lower Resistance. Requires **EEex**. The older archive additionally requires SR.
- **211:** Spellstrike gives **15% arcane/divine spell failure for two rounds**;
  its own failures refresh instead of stacking. The older archive requires SR.

Both preserve spell-protection removal, Spell Shield interception and installed
invisible targeting. Pierce Shield, Lower Resistance and Entropy Shield are not
changed. These components are independent; choose either or both.

## After authorization to modify the intended game

1. Close the game and InfinityLoader. Verify the intended game root and its
   `WeiDU.log`. Keep a backup of the game, string tables and saves, plus a copy of
   the pre-patch log. Do not reuse an archive from a different development commit.
2. Extract `CBR_SR_ANTIMAGIC-v0.8.10-windows.zip` into that root.
   It contains `Setup-cbr_sr_antimagic.exe` and the `CBR_SR_ANTIMAGIC` directory.
3. Run the separate setup and choose 210 and/or 211. They append new entries at
   the end of the stack and use their own backup namespace. **Do not reinstall SR,
   reinstall existing BG Rebalance components, or manually edit WeiDU.log.**
4. Do not install the same component from both the main and tail installer.
   Symmetric guards enforce this. Different components can use different
   installers, although keeping this pair together is simpler.
5. Restart through **InfinityLoader** for component 210, so `M_CBRPM.lua` loads.
   Let any old Pierce Magic / Spellstrike effects expire
   before testing new casts: stored effects are not rewritten by an installer.

The installer resolves parent spells through `spell.ids` and follows their actual
payload links. The current libraries write owned payloads and private resources
even when previous content differs. They write each description in Spell Revisions' layout (keeping the
invisible-target note only for a spell that can target invisible creatures) and updates the
items and spells that show the old mechanic. The runtime's private resource identity is `CBRPM`; no existing
MR modifier or save is globally rewritten.

## Texts only: 212 and 213

For an installation that already has the changed mechanic, whichever installer or private
tail made it, **212** (Pierce Magic) and **213** (Spellstrike) change descriptions and nothing
else. Selecting them declares that the mechanic was installed separately; current
libraries do not inspect old payloads to approve or reject that choice.

- Complete owned English descriptions are written from the mod's templates,
  including linked scrolls, spells and the Wand of Spell Striking.
- Other languages keep their existing text with a log line until a translation exists.

Select 212 and/or 213 only (`--force-install-list 212 213`): choosing 210 or 211 there installs
the mechanic. They also work after the main installer's 210 / 211. Uninstalling restores the
changed files; added strings stay in `dialog.tlk`.

## Acceptance still required

Check first cast, repeated casts and expiry against MR 0, 10, 21, 60, 80 and 100;
Lower Resistance before/after Pierce Magic; save/reload during the reduction;
Spell Shield absorption; and successful Spellstrike recasts. Expected examples:
MR 100 -> 60, 60 -> 30, 21 -> 10. An active reduction's amount stays fixed when
refreshed, even if another MR modifier changed meanwhile. Spellstrike's 15% can
combine with failure caused by *other* spells; only its own stacking is prevented.

Automated binary and Lua-model checks are not live gameplay acceptance. The
expiry-boundary queue specifically waits for native effect removal and completed
effect-list processing; it does not use an arbitrary delayed spell.
