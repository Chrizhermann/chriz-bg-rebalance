# SR anti-magic existing-install patch

Source version **v0.8.8** (its components are unchanged since v0.8.1). Component 210 was applied
with authorization to Christopher's private stream installation on October 6;
211 was not. See the collection handover for backups and verification. Native
gameplay acceptance remains separate from the automated release checks.

- **210:** Pierce Magic halves current MR, subtracting at least 10 and at most
  40 percentage points, rounded up; never below zero. Duration: five rounds.
  Recasts refresh the existing reduction, preserving its original amount.
  Combines with Lower Resistance. Requires **SR main component 0 and EEex**.
- **211:** Spellstrike gives **15% arcane/divine spell failure for two rounds**;
  its own failures refresh instead of stacking. Requires **SR main component 0**.

Both preserve spell-protection removal, Spell Shield interception and installed
invisible targeting. Pierce Shield, Lower Resistance and Entropy Shield are not
changed. These components are independent; choose either or both.

## After authorization to modify the intended game

1. Close the game and InfinityLoader. Verify the intended game root and its
   `WeiDU.log`. Keep a backup of the game, string tables and saves, plus a copy of
   the pre-patch log. Do not reuse an archive from a different development commit.
2. Extract `CBR_SR_ANTIMAGIC-v0.8.8-windows.zip` into that root.
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
payload links. It rejects unsupported or ambiguous payloads and foreign private
resource collisions. It writes each description in Spell Revisions' layout (keeping the
invisible-target note only for a spell that can target invisible creatures) and updates the
items and spells that show the old mechanic. The runtime's private resource identity is `CBRPM`; no existing
MR modifier or save is globally rewritten.

## Texts only: 212 and 213

For an installation that already has the changed mechanic, whichever installer or private
tail made it, **212** (Pierce Magic) and **213** (Spellstrike) change descriptions and nothing
else. They refuse a payload that does not carry the mechanic (the `CBRPM` callback for 212,
a 15% failure for 213), so they cannot describe a mechanic that is not there.

- The spell's description is rewritten in Spell Revisions' layout. 213 keeps a Spellstrike
  text that already has that layout and states the 15%, and points the rest at it.
- Scrolls and other items that learn or cast the spell and still show an old description
  (the strref of the spell as it was, of its payload spells, or any string with the same long
  text) show the new one; an item with its own text keeps it and the installer prints its name.
- Items that reach the payload through another spell, such as the Wand of Spell Striking, get a
  private copy of their text with only this spell's `Special:` line replaced, if it is
  recognizable; otherwise they keep their text and the installer prints their name.
- Other spells that cast the same payload and show an old description are repointed.

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
