# SR anti-magic existing-install patch

Prepared development source **v0.8.1-dev**. No game installation or publication
has been performed. Live acceptance remains pending.

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
2. Extract the prepared `CBR_SR_ANTIMAGIC-v0.8.1-dev-windows.zip` into that root.
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
resource collisions. It updates descriptions privately, retaining SCS's invisible
targeting note. The runtime's private resource identity is `CBRPM`; no existing
MR modifier or save is globally rewritten.

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
