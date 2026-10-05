# Hardiness existing-install patch — v0.8.1-dev (unpublished)

This new, standalone WeiDU mod appends its own entry after the current install.
It does not reinstall Spell Revisions or any previously installed component.
Requires BG2:EE/EET and SR component 65, Revised Warrior HLAs. It changes both
normal Hardiness (`SPCL907`) and Wish-granted Hardiness (`SPWISH12`).

| Selection | Result |
| --- | --- |
| 200 | 40% physical resistance only — recommended vanilla resistance profile |
| 201 | 30% physical resistance only — alternative to 200 |
| 200 + 202 | 40% physical plus SR's extra 20% damage resistances |
| 201 + 202 | 30% physical plus SR's extra 20% damage resistances |

200 and 201 are mutually exclusive. 202 is optional and requires a base choice.
The extra resistances cover acid, cold, electricity, fire, magic damage, magical
fire and magical cold. They do not add Magic Resistance or poison resistance.

Duration, targeting, casting, dispel flags, stacking protections and secondary
types remain unchanged. In particular, this does not harmonize normal and Wish
Hardiness's existing Breach behavior. Only the resistance profile is vanilla.

## Prepare and install later

1. Build the archive from the mod source with
   `python tools/package_sr_hardiness.py`. The builder copies the canonical
   library and English strings; the source template folder alone is not a
   complete distribution.
2. Before applying it, close the game and back up the game directory and saves.
   This package has not been applied to or playtested in a live game.
3. Extract `CBR_SR_HARDINESS-v0.8.1-dev-windows.zip` into the game directory.
4. Run `Setup-cbr_sr_hardiness.exe`. Choose 200 (recommended) or 201. Leave 202
   uninstalled unless the extra damage resistances are wanted.

For an unattended first install, after the game is closed, the equivalent is:

```powershell
.\Setup-cbr_sr_hardiness.exe --language 0 --use-lang en_us --force-install-list 200 --no-exit-pause
```

Substitute `201`, `200 202`, or `201 202` for the other combinations. These commands
are instructions for later application; building the package does not run them.

Use either full BG Rebalance's Hardiness components or this standalone family.
Both installers refuse to overlap those families. Earlier, unrelated BG Rebalance
components can remain installed; this separate TP2 avoids replacing their installer
or backup files. Do not switch an existing mid-stack installation by uninstalling
or reinstalling old entries. A future full reinstall should use the full mod.

The change applies to future casts after loading the updated resources. An active
Hardiness effect already stored in a save is not rewritten: let it expire and recast.
No save files are changed. Unsupported spell structures abort transactionally.

## Scope and evidence

The patch recognizes SR's extra effects by matching every donor byte except opcode
and resistance amount. Foreign effects with different delivery metadata survive.
Each level header must have one additive modifier per physical damage type and
either the complete seven-effect SR clone set or none. This supports SR's original
20%, the old 40% hotfix, and repeated applications of these choices. It rejects
partial or duplicate clone sets instead of deleting ambiguous effects.

Automated verification uses real WeiDU with synthetic games and archived spell
copies. It does not establish live-engine acceptance or collection integration.
The collection must separately select and pin the full mod's new components.
