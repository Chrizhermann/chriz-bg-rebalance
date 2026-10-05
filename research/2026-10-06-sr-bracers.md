# Bracers of Blinding Strike with Spell Revisions

## Requested scope

Use the installed Spell Revisions Improved Haste package for BRAC16's existing
20-second, self-only, once-per-day activation. Preserve the item otherwise.
The user approved a private tail patch for the closed stream installation;
the lead owns deployment. This worker did not modify or launch the live game.

This is not the separate proposed Wish nerf. Native Improved Haste/Wish spells
receive only a reciprocal exclusion for the new bracer helper; their existing
mechanical effects remain byte-identical.

## Read-only evidence, 2026-10-06

Source: `C:\Users\chris\Games\Chriz Easy BG\game`.

- BRAC16.ITM: one self-targeted ability, one charge, daily recharge flag 2048.
  Its activation uses opcode 16, parameter2=1, duration=20: native double APR.
  The identified description (strref 39606) already says Improved Haste,
  duration 20 seconds, user only, once per day. No TLK edit is needed.
- SPELL.IDS resolves WIZARD_IMPROVED_HASTE to SPWI613 and WIZARD_HASTE to
  SPWI305. Production code resolves these symbols, rather than assuming slots.
- Effective SPWI613 has one 60-second ability with an area projectile (158).
  Its payload grants +1 APR (opcode1/p1=1/p2=0), SR movement (176/6/0),
  +2 THAC0/AC/Breath save, Slow protection/cleanup, graphics and exclusions.
  Calling SPWI613 directly from the bracers would incorrectly retain area
  delivery and 60 seconds.
- The donor also contains the installed Tempus bridge: state 246, plus
  conditional calls to CBRAPR1/6/7. Those helpers remain unchanged. The private
  clone retains the bridge and shortens its timed state to 20 seconds.
- Donor spell level 6 and secondary type 17 are retained. These are part of the
  installed SR/SCS protection classification, not disposable display fields.
- SPRA301/DWSW305 and additional installed Haste aliases have existing
  exclusions against canonical Improved Haste. These need reciprocal guards
  against the new helper, not just a guard in one direction.
- SPPR525A adds APR and blocks ordinary Haste, but does not block SR Improved
  Haste. It is intentionally not newly made exclusive with the bracers.

Source inspection found SR's general item-haste integration in
`spell_rev/lib/kreso_haste_slow.tph`, but no BRAC16-specific replacement of the
embedded native Improved Haste effect.

## Implementation

`chriz-bg-rebalance/lib/sr_bracers.tpa` supplies `cbr_apply_sr_bracers`.
`live-patch/CBR_SR_BRACERS/setup-cbr_sr_bracers.tp2` is a private tail adapter.
Stage the canonical library as `CBR_SR_BRACERS/lib/sr_bracers.tpa`.

1. Read-only, bounded probing finds actual Haste deliveries. Unrelated spells,
   including global-only and padded resources, are not held to donor shape.
2. Build CBRBIH.SPL from the effective SR donor. Change targeting to self,
   projectile to 1, timed effects to 20 seconds, and the sole required level to
   0. Instant effects and Tempus conditional calls retain their original data.
3. Replace BRAC16's native haste with an instant opcode146 mode1 call to CBRBIH.
   This retains inherited caster level; a level-zero helper header is eligible
   even for a noncaster. No fixed dispel level is invented. Remove only the
   recognized old haste presentation/cleanup effects, preserving other effects.
4. Add reciprocal opcode206 guards to qualifying installed Haste deliveries.
   All pre-existing effects remain unchanged; guard duration follows each
   source ability's own existing Haste exclusion. The helper's exclusions last
   20 seconds. Additive APR spells qualify only if they already exclude SR IH;
   native haste deliveries may instead carry an ordinary Haste exclusion.
5. Preflight the donor, item, and helper namespace. A pre-existing different
   CBRBIH fails rather than being overwritten. Repeating the tail operation is
   byte-identical.

Opcode reference: [IESDP opcode146](https://gibberlings3.github.io/iesdp/opcodes/bgee.htm#op146)
documents mode1 as immediate casting at the caster's level. Original opcode61
is a [color fade](https://gibberlings3.github.io/iesdp/opcodes/bgee.htm#op61),
not a gameplay stat; cleanup matches its actual parameters, not every opcode61.

## Automated validation

`python -B -m unittest tests.test_sr_bracers -v`: nine passing real-WeiDU tests.

Coverage: relocated SPELL.IDS symbols; self-only +1 APR and fixed 20 seconds;
noncaster-eligible header and inherited cast mode; unchanged recharge/other
item fields and unrelated effects; reciprocal alias guards; unchanged Tempus
helpers; namespace collision and unsupported donor rejection; late-failure
rollback; byte-exact reapplication; byte-exact uninstall in disposable games.
Uninstall tests never target a live installation.

A read-only capture includes all 6,747 effective SPLs (override plus BIFF-only),
BRAC16 and SPELL.IDS. Real WeiDU installs successfully in a synthetic game,
preserves original alias effects and TLK bytes, and a second tail invocation
produces byte-identical output. Latest-source full capture also verifies the
final, narrower cosmetic predicates produce identical expected live output.

Private evidence is ignored under `.worktrees/sr-bracers-full-dryrun-oct06-*`.
The `reviewed` folder contains the final expected override, before/after SHA256
manifest (`evidence.json`), original WeiDU backups, and install output. The
`final` folder additionally retains the repeat-install output.

### Exact modified-resource allowlist for this captured installation

BRAC16.ITM; CBRBIH.SPL; C0MF302.SPL; C0MF603.SPL; C0SBLUN3.SPL;
C0STK04.SPL; DW#WISH2.SPL; DWSW305.SPL; DWSW613.SPL; SPIN655.SPL;
SPRA301.SPL; SPWI305.SPL; SPWI613.SPL; SPWISH36.SPL; SPWISH37.SPL;
SPWISH40.SPL.

CBRBIH is new; the other 15 resources already exist. The 14 spell resources
other than CBRBIH receive only reciprocal guard additions. No saves, TLK,
Tempus child resources, or unrelated resources change.

## Remaining limits

This is source/binary and real-WeiDU evidence, not an in-engine playtest.
When convenient: activate the bracers on a noncaster, observe +1 APR for
20 seconds/self only, and check Haste/IH in both orders. A Tempus Holy Power
combination is the relevant optional integration check. No automated tool
here launches the game or edits a save.

Public component numbering, language strings, release packaging and CEBG
recipe selection remain with the owner/lead; this worker deliberately did not
edit public TP2, TRA or README files.

## Approved deployment completed by the lead

The lead applied this exact adapter to the closed stream game on October 6,
after checking every affected input against the captured original hashes.
WeiDU exited 0; the 16 output resources match the reviewed fixture byte-for-byte.
All 439 preceding component log rows remain exact. The only other new log row is
`CBR_SR_BRACERS:0`; TLK, the installed resistance cap, UI.MENU and other protected
files remain unchanged. No saves modified and no game launched.

Backup and verification:
`C:\Users\chris\Games\Chriz Easy BG\repair-backups\oct06-resistance-bracers\bracers`.
This confirms deployment, not in-game delivery/stacking acceptance. Existing
saved active effects are not retroactively rewritten; use a fresh activation.
