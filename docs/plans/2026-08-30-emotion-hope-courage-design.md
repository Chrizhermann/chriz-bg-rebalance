# Emotion, Hope and Courage Exclusivity — Design

**Date:** 2026-08-30
**Component:** 301 (`cbr_emotion_hope_courage_exclusion`)
**Status:** implemented and automated-verified; delivery/mutual exclusion live-verified;
manual status-list retest pending

## Goal

Make *Emotion, Courage* and *Emotion, Hope* mutually exclusive on each affected creature,
regardless of whether the installed spell resources came from IWDification, SCS, or neither
mod. Recasting either spell refreshes that spell; casting the other removes the earlier
beneficial Emotion before applying the new one. The most recently applied beneficial
Emotion therefore wins.

The component is a tail-installed cross-cutting spell component. It owns the effective
mechanics and English descriptions at the dynamically resolved `SPELL.IDS` resources and
documents that later spell mods can overwrite it again.

## Evidence that shapes the design

- The read-only reference install maps `WIZARD_EMOTION_COURAGE` to `SPWI428` and
  `WIZARD_EMOTION_HOPE` to `SPWI429`. These allocations are install-specific; source defaults
  use other slots, so the installer must never hardcode either final resref.
- Both installed beneficial spells use the IWD projectile and icon/animation resources.
  SCS component 5900 subsequently added opcode-328 detectable-state markers.
- Installed Courage has a relocation defect: its self-removal was rewritten into a second
  removal of the relocated Fear spell. It can therefore stack with itself. The new component
  must generate explicit removers only after both final resrefs are known.
- Installed Fear removes Courage; installed Emotion: Hopelessness and Symbol: Hopelessness
  remove Hope. The component will retain and normalize those pairwise adverse interactions.
- The IWDification and SCS spell packages depend on more than two SPL files: custom BAM,
  WAV, PRO, VVC, STATDESC, scroll, and post-processing resources are involved. No third-party
  mod binary is committed. The standalone branch packages only independently extracted IWDEE
  game presentation assets, with provenance and hashes recorded beside them.
- Both upstream pipelines generate a new scroll and mirror every store entry containing a
  designated donor scroll. Courage shadows Enchanted Weapon; Hope shadows Emotion,
  Hopelessness. IWDification additionally scatters scrolls into fixed campaign containers,
  but SCS does not invoke that optional custom placement layer.

Full hashes, decoded effect tables, provenance, and source-path evidence belong in
`research/11-emotion-hope-courage.md`.

## Architecture

### 1. Allocate or retain symbolic spell slots

Use WeiDU `ADD_SPELL` for both level-four wizard symbols. When a symbol already exists at
wizard level four, use `IF_EXISTING` to transform that current resource in place. When it is
absent, rebuild a temporary canonical spell buffer and let `ADD_SPELL` allocate the first free
level-four slot and append the symbol to `SPELL.IDS`.

After allocation, derive both final resrefs from the returned numeric IDs. All reciprocal,
adverse, scroll, and AI-marker references use those final values. No chained resref text
substitution is permitted.

### 2. Deterministically rebuild the two beneficial spells

Both output spells are original CBR installer constructions. They reproduce the intended
IWD/PnP-style mechanical identities while enforcing a canonical effect order. Existing
spell icon, ability icon, projectile, casting animation, and audio/visual records are
retained when they are valid. The standalone path uses the packaged, verified IWDEE
presentation assets; it never reads a hardcoded path to a separate IWDEE installation.

Common spell shape:

- wizard level 4, Enchantment/Charm;
- visual-range point target and approximately seven-foot recipient area;
- casting time 4;
- duration 300 seconds (one in-game hour / 50 rounds);
- no saving throw for the beneficial effects;
- friendly effects bypass magic resistance but remain dispellable where appropriate.

When valid IWD-derived presentation resources are already present, retain their references.
The standalone branch combines the BG2EE/EET Enchantment casting package (opcode 141
parameter 2 = 10, `EFF_M05`, BG glow, and `CAS_M05`) with the original blue IWDEE A/B/C icons,
allies-only Emotion projectile/VVC/animation, projectile sound, and delayed Emotion sound.
The shared graph is remapped to private `CBR301*` resrefs and the icons are published under
the dynamically allocated spell name. Native BG2EE/EET `STATDESC.2DA` rows 186 and 187 have no
portrait BAM. For each standalone spell, the installer therefore publishes an independently
extracted 13x13 IWDEE heart as `<resolved spell>D`, allocates a distinct extensible STATDESC row
at 200 or above with the localized `Courage` or `Hope` label, and applies one timed opcode 142
for 300 seconds. Valid opcode-142 presentation supplied by an installed provider is retained
byte-for-byte.

Every recipient header starts with opcode-321 removers. Only the new self and reciprocal
Hope/Courage transition removers use target 2, power 4, timing 1, parameter 2 = 2 (timed
effects only), no save, and magic-resistance bypass. Beneficial cleansing removers for
Fear, Horror, Innate Horror, Emotion: Hopelessness, and Symbol: Hopelessness instead use
parameter 2 = 0, no save, and magic-resistance bypass so they clear the matching source
effects completely. All transitions and cleanses occur per creature rather than globally per
cast.

Canonical Courage mechanics:

1. remove timed effects from Courage itself;
2. remove timed effects from Hope;
3. clear the dynamically resolved `WIZARD_EMOTION_FEAR`, `WIZARD_HORROR`, and
   `INNATE_HORROR` sources with the full-source cleansing shape when those symbols exist;
4. retain the installed fear-cleansing tail: opcode 23 morale normalization
   (`p1=20`, `p2=1`, timing 0, `resist_dispel=3`, duration 300, special 0), opcode 240
   removal of portrait icon 36, and opcode 161 Cure Horror. This ends fear and morale
   failure; it is not described as a maintained +20 morale bonus;
5. grant +1 THAC0, +3 damage, and +5 maximum/temporary hit points for 300 seconds;
6. retain an installed portrait icon when available and apply the SCS detectable-state marker.

Canonical Hope mechanics:

1. remove timed effects from Hope itself;
2. remove timed effects from Courage;
3. clear dynamically resolved `WIZARD_EMOTION_HOPELESSNESS` and
   `CLERIC_SYMBOL_HOPELESSNESS` sources with the full-source cleansing shape when those
   symbols exist;
4. grant +2 morale, +2 THAC0, +2 damage, and +2 to all saving throws for 300 seconds;
5. retain an installed portrait icon when available and apply the SCS detectable-state marker.

### 3. Normalize the adverse pair

If `WIZARD_EMOTION_FEAR` exists, each of its recipient headers must contain exactly one
Courage remover in the same resistance/save domain as the hostile Fear delivery. If
`WIZARD_EMOTION_HOPELESSNESS` exists, each recipient header must contain exactly one Hope
remover. If `CLERIC_SYMBOL_HOPELESSNESS` exists, its recipient delivery must likewise remove
Hope. Missing adverse spells are not created by this component.

The adverse spell still has to land according to its own rules. A resisted Fear must not
strip Courage merely because its cleanup record ran unconditionally.

### 4. Preserve SCS AI observability

If `SPLSTATE.IDS` defines `EMOTION_COURAGE` or `EMOTION_HOPE`, add exactly one opcode-328
record using the resolved value, parameter 1 = 1, special = 1, and the same 300-second
duration as the buff. Do not hardcode the currently observed state values 195 and 194.

This keeps SCS's `CheckSpellState`-based AI from treating an active buff as absent and
needlessly recasting it.

### 5. Scroll handling

Scan installed ITM resources for learn-spell records that reference either final spell.
Repoint matching scroll display/description fields to CBR's translated strings while
preserving the scroll's icon, price, usability, and placement.

If no learn-scroll exists for a newly allocated spell, create one with private eight-character
CBR resrefs. Construct a fresh 322-byte wizard scroll using IWDification's semantic contract:
point target, range 50, opcode 148 at caster level 10, followed by a self-targeted opcode-147
learning ability. All three item/ability icon fields use `<final spell>A`. The dynamically
discovered Enchanted Weapon and Emotion, Hopelessness scrolls are distribution anchors only;
no donor item bytes are inherited. One unambiguous teaching scroll for each required donor is
a guarded version-one requirement, and a missing or ambiguous donor fails transactionally.

For standalone distribution, scan every effective STO resource and clone each live entry for
the corresponding donor scroll, changing only the cloned scroll resref. This mirrors the
common IWDification/SCS donor-shadow algorithm while preserving each store's quantity,
charges, flags, and ordering. The current install uses Enchanted Weapon's `SCRL6M` entries for
Courage and Emotion, Hopelessness's `SCRL5H` entries for Hope, but neither donor resref nor the
observed store names are implementation constants.

Existing IWDification/SCS scrolls and placements are reused, not duplicated. Do not recreate
IWDification's optional fixed Iron Throne/SoD container scatter or NPC known-spell grants;
SCS's spell component does not use those additions. The component must not patch saves or
assume that a previously visited store/area will refresh in an active playthrough.

### 6. Text

The component adds original English names and descriptions through TRA references. Both
descriptions explicitly say:

> A creature can be affected by only one of Emotion, Courage and Emotion, Hope at a time.
> Applying either spell removes the other.

The descriptions also list the complete CBR mechanics, duration, area, and adverse Emotion
interaction. Courage uses simple player-facing language such as "ends fear and morale
failure"; it does not expose opcode fields or promise a maintained +20 morale bonus. Existing
third-party description text is not copied.

## Compatibility contract

- Supported games: BG2EE and EET.
- Install after SCS, IWDification, SR, and other spell-overhaul components.
- Existing symbolic slots are retained; absent slots are allocated.
- Existing valid visual/audio references are retained. Standalone output deliberately uses
  byte-identical original IWDEE icons and privately namespaced IWDEE presentation resources.
- SCS detectable-state markers are recreated from symbols when present.
- The README must state that component 301 overwrites the effective Hope/Courage mechanics
  and descriptions, and that a later-installed spell mod can overwrite them again.
- No writes or tests occur in the active game directory during development.

## Safety and acceptance criteria

Automated fixtures must cover:

1. IWDification-shaped existing spells in noncanonical slots;
2. SCS-shaped spells with opcode-328 markers;
3. the observed Courage duplicate-Fear/self-removal regression;
4. neither symbol present;
5. exactly one symbol present;
6. reciprocal application in both directions and self-refresh;
7. adverse Fear/Hopelessness cleanup semantics;
8. existing-scroll discovery, standalone scroll creation, and dynamic donor-store mirroring
   without fixed campaign scatter;
9. original descriptions on SPL and scroll resources;
10. byte-stable second application;
11. transactional install/uninstall restoration in a synthetic BG2EE game;
12. a strict publication allowlist containing only the documented IWDEE asset graph and
    dynamically named icons in addition to the owned spell/scroll/store/IDS resources.

Live behavioral testing is a separate, explicitly approved step. It is not authorized by
this design.

## Out of scope for component 301

- Redistributing IWDification or SCS binaries; the documented original IWDEE game presentation
  assets are the only binary exception.
- Creating missing hostile Emotion spells.
- Making every positive and negative Emotion mutually exclusive as one universal family.
- Editing active saves to refresh cached areas, stores, spellbooks, or memorized spells.
- Compatibility with a spell overhaul installed after this component.
