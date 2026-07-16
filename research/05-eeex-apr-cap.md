# Research 05 — deferred EEex APR-cap experiment

**Date:** 2026-07-16 · **Status:** research only; prototype deferred · **Live game:**
read-only

## Supported conclusion

The active playthrough has **EEex v0.11.0-alpha**, not EEex 1.0. This is confirmed twice:

- `WeiDU.log` records the main component and optional components 1–7 as
  `v0.11.0-alpha`;
- the installed `EEex/EEex.tp2` declares `VERSION ~v0.11.0-alpha~`.

A text audit of the installed v0.11 source found no supported public API for replacing the
combat-round attack schedule or lifting the five-APR cap. In particular,
`EEex/copy/EEex_Opcode_Patch.lua` has no opcode-342 `parameter2=5`, `combat_round_*`, or
`RNDBASE*` implementation. Its nearby `Swing()` hooks serve specific opcode/immunity paths;
they are not a public attack-scheduler listener. EEex exposes low-level patch machinery, so
this conclusion is deliberately **“no supported public hook found,” not “a custom engine
patch is impossible.”**

`CDerivedStatsTemplate.m_nNumberOfAttacks` is the derived APR field. The official EEex
structure documentation identifies it as a 16-bit field at offset `0x12`. A Lua write may
alter the current derived value and any UI that reads it, but that observation would not
prove that `CGameSprite` scheduled or resolved the corresponding number of attacks. Derived
stats may also be rebuilt. A displayed value above five, extra animation swings, or a raw
memory value is therefore **not an acceptance test**.

EEex **v1.0.0** adds a materially different experiment surface. Its official release notes
define this opcode-342 extension:

- `parameter2 = 5` selects a combat-round bitmap override;
- `parameter1` selects the animation INI `combat_round_<parameter1>` slot; and
- the effect resource is an `RNDBASE*`-like BMP.

The tagged source routes the override into the attack-frame lookup used by both
`CGameSprite::OneSwing()` and `CGameSprite::Swing()`. That makes custom six-to-ten-attack
round bitmaps **plausible**, because it reaches an engine path involved in real combat-round
swing selection rather than merely changing a displayed stat.

The extension is also materially better suited to a temporary Holy Power buff than the old
animation-cloning technique: opcode 342 is applied to one `CGameSprite`, its `parameter1`
selects one of that sprite's five `combat_round_*` slots, and normal effect timing can bound
the override to the buff duration. Expiry must still be tested to prove that the original
animation-INI mapping resumes cleanly; the tagged Lua patch establishes the per-sprite lookup,
not every lifecycle transition.

### Installed Artisan precedent

The active installation contains a stronger local precedent than the upstream hook alone.
Artisan's Kitpack Monk Revision implements Flurry of Blows by cloning Monk animations and
changing their combat-round BMP mappings:

| Installed animation INI | `combat_round_0` | `combat_round_1` | `combat_round_2` | `combat_round_3` | `combat_round_4` |
|---|---|---|---|---|---|
| `override/6006.ini` | `C0MSHO02` | `C0MSHO02` | `C0MSHO03` | `C0MSHO04` | `C0MSHO05` |
| `override/6007.ini` | `C0MSHO06` | `C0MSHO06` | `C0MSHO07` | `C0MSHO08` | `C0MSHO09` |

`override/ANIMATE.IDS` names these slots `MONK_MALE_HUMAN_1` and
`MONK_MALE_HUMAN_2`. `ArtisansKitpack/lib/MonkRevision.tpa` dynamically allocates and
installs the paired animations, while its class text says that Flurry's extra attack is not
subject to the APR limit and Greater Flurry adds a second extra attack.

The installed BMPs confirm how that claim is encoded. They are 102-by-11, 4-bit combat-round
maps with one row for every weapon-speed value from 0 through 10. In **every row**:

- `C0MSHO05.BMP` contains six attack-color-to-red-roll-marker pairs; and
- `C0MSHO09.BMP` contains seven attack-color-to-red-roll-marker pairs.

For example, the first row of `C0MSHO05` contains a duplicated first
attack-color/red sequence and then four ordinary sequences; `C0MSHO09` additionally
duplicates the second sequence. The teal cosmetic sequence was excluded from these counts.
The file hashes are respectively
`b2569826f8efaee7500332139448f6c5bc7d9a2410879182cdd8d91b5eb2e34c` and
`cc1c06e72065a147675d930a4f2cb4811b6d6e964a33f2c67baeb1084f004d31`.

This is compelling evidence that an established installed mod deliberately uses these maps
to encode sixth and seventh **statistical attack-roll markers**, not just extra animation.
It is not direct proof that a timed v1 opcode-342 override produces the same measured result
for a Tempus Cleric: no combat-log or hit-count experiment was run during this read-only
audit.

The timed v1 Tempus application is still only a hypothesis. Neither the release note nor the
tagged hook proves that the rest of the engine accepts, schedules, networks, and resolves
more than five attacks in one round for this use case. No isolated prototype or in-engine
hit-count test has been run here. **Actual scheduled attacks above five remain unverified.**

Consequently:

- components 401–403 do not alter the APR cap, install an EEex hook, or ship custom
  `RNDBASE*` resources;
- upgrading EEex in the active playthrough is explicitly out of scope; and
- no EEex file, game resource, configuration, save, or executable was changed for this
  research task.

## Compatibility findings

The local precedent is strongest for melee attacks. The v1 hook is in
`CGameSprite::Swing()`, and EEex's own adjacent hook labels show that `Swing()` contains both
melee and ranged branches, so crossbow/projectile attacks are plausible. They remain
unverified: a ranged pass must count attack rolls, projectiles, ammunition consumption, and
on-hit resolution rather than inferring success from animation.

Dual wielding is a separate correctness problem. Combat-round colors identify attack
sequences, and duplicating a color can duplicate that sequence's hand rather than
proportionally distributing new attacks between main and off hand. A passing total count is
therefore insufficient; test weapons need distinguishable main-hand and off-hand hit markers.

The final installed haste resources have two different semantics:

- Spell Revisions Improved Haste, `SPWI613`, uses timed opcode 1 with `p1=1`, `p2=0`:
  additive `+1 APR`. A full Holy Power prototype should override all five
  `combat_round_0..4` slots so the engine can select the correct custom map after the stat
  changes, regardless of casting order.
- Spell Revisions Whirlwind and Greater Whirlwind, `SPCL900` and `SPCL901`, each use timed
  opcode 317 with `p2=1`. Opcode 317 has true Improved-Haste semantics, including the faster
  attack-round timer. It can therefore double the rate of the bitmap's extra roll markers
  and exceed an intended effective ceiling of ten.

A future EEex component needs an explicit policy for true-doubling haste: make it mutually
exclusive with Holy Power, dynamically select a reduced schedule while it is present, or
document that the nominal ceiling can be exceeded. The pure Tempus Cleric normally lacks
Whirlwind, but flexible mod compatibility should not silently assume that no kit, item, or
save grants it.

## Evidence and primary sources

The live-install files below were read and hashed before and after the audit. Each pair was
byte-identical.

| Read-only live file | Size | SHA-256 before and after |
|---|---:|---|
| `WeiDU.log` | 41,444 | `bcea63fa0ca8883ba015fd674819c561ae28dcb41a054d9a2ab2992fdca3939f` |
| `EEex/EEex.tp2` | 3,669 | `494d9064944a5bb264659eb972ae72a326cedc73f84bc2b1b5ac326825511112` |
| `EEex/copy/EEex_Opcode_Patch.lua` | 57,009 | `b4bdadfdfb0cfb17ad96e92ac09328aee365642f720d750dfe6e2116c7e047b3` |
| `EEex/copy/EEex_Sprite_Patch.lua` | 38,357 | `2e0b5983c414d14dbd38c3bfcd5917ce43d19fd2734c9636b0a33eea23300a45` |

Upstream evidence is pinned rather than inferred from the moving default branch:

- installed-version source tag: [`v0.11.0-alpha`](https://github.com/Bubb13/EEex/tree/v0.11.0-alpha),
  commit `89e524640766aa61d6963070299eaaac86f883d8`;
- [EEex v1.0.0 release notes](https://github.com/Bubb13/EEex/releases/tag/v1.0.0),
  tag commit `1487384cf4d5974482e596ca654bec35c340149a`;
- [v1.0.0 opcode-342 implementation and the `OneSwing`/`Swing` hook sites](https://github.com/Bubb13/EEex/blob/v1.0.0/EEex/copy/EEex_scripts/EEex_Opcode_Patch.lua#L578-L620);
- [official x64 `CDerivedStatsTemplate` layout](https://eeex-docs.readthedocs.io/en/latest/EE%20Game%20Structures%20%28x64%29/CD/#cderivedstatstemplate),
  including `m_nNumberOfAttacks` at `0x12`.

The v0.11 tagged and installed opcode patch contains none of `Opcode #342`, `RNDBASE`,
`combat_round_`, or the new attack-frame override hook labels. The v1.0.0 tagged file places
those definitions together at lines 578–620. This version difference—not a general claim
that opcode 342 itself is new—is the relevant boundary.

## Future isolated prototype

This experiment must run only in a disposable game clone with a version-pinned executable,
EEex v1.0.0 or later, and a complete rollback/rebuild path. It must not begin by upgrading
the active playthrough.

### Smallest go/no-go experiment

Before building the full matrix, run one narrowly-scoped proof:

1. Clone a version-pinned BG2:EE 2.6.6 installation and install EEex v1.0.0 with LuaJIT.
   Record the executable, EEex tag, SPL, BMP, and save hashes. Do not upgrade the active
   playthrough.
2. Give a disposable test actor exactly 5 APR and attack an inert, high-HP target. Establish
   the unmodified `RNDBASE5` control over repeated complete rounds.
3. Apply a three-round test spell containing one timed opcode-342 effect with `p1=4`,
   `p2=5`, and resource `C0MSHO09`. At this APR slot the installed Artisan bitmap encodes
   seven attack-color/red-roll pairs.
4. Require the combat log to show five resolved attack attempts per control round and seven
   while the override is active. Cross-check successful resolutions with an on-hit sentinel;
   neither seven animations nor a displayed APR value is sufficient.
5. Confirm return to five after expiry, then repeat save/load during the effect. Any stale
   map, lost cleanup, or different post-load count fails the prototype.
6. Only after that proof, repeat with a crossbow (including projectile and ammunition counts),
   dual wielding (distinct per-hand markers), additive `SPWI613`, and true-doubling
   `SPCL900`/`SPCL901`, applying each effect in both orders.

### Instrumentation

1. Disable cosmetic attacks for every run. Animations are not measurements.
2. Log every **resolved attack attempt** with round/tick, attacker, target, weapon hand,
   melee/ranged path, and hit/miss result. Add an independent on-hit sentinel counter so
   actual hit resolution can be cross-checked against the attempt log.
3. Record the engine-derived APR and UI-displayed APR alongside the event log, but never use
   either as the primary result.
4. Use inert, high-HP targets and fixed equipment. Run enough complete six-second combat
   rounds to expose fractional scheduling, missed slots, duplicate slots, and timing drift.
5. Keep an unmodified `RNDBASE1`–`RNDBASE5` control set, then derive candidate 6–10 and
   half-APR bitmaps without changing unrelated animation data.

Success requires the measured combat events—not the bitmap, animations, or displayed
number—to match the requested schedule in every applicable row below.

### Test matrix

| Dimension | Required cases | Required observation |
|---|---|---|
| Control | Vanilla integer and half-APR schedules through five | Instrumentation reproduces known engine scheduling before custom assets are tested. |
| Candidate schedules | 6, 7, 8, 9, 10 APR plus 5.5/6.5/7.5/8.5/9.5 | Exact attempts per round over repeated rounds; no wrap, clip, bunching, or cosmetic-only swings. |
| Melee | One-handed and two-handed main-hand attacks | Correct real swing count, attack rolls, damage/on-hit resolution, and round timing. |
| Ranged | Bow/crossbow or equivalent launcher/ammunition paths | Correct attack rolls, projectiles, ammunition consumption, and on-hit resolution with no melee-only false success. |
| Dual wield | Main hand plus off hand, including an off-hand-producing half-APR case | Correct total and per-hand allocation; no duplicated or starved off-hand attacks. |
| Haste semantics | No haste; SR additive opcode 1; opcode 16 type 1; opcode 317 type 1 | Measured behavior is defined rather than inferred for additive and true-doubling implementations. |
| Casting order | Schedule override before/after opcode 16 or 317; expiry/removal in both orders | No stale schedule, double application, lost attack, or one-round transition glitch. |
| UI | Inventory and character-record APR before, during, and after each effect | UI is truthful and returns to baseline; UI agreement alone does not pass the test. |
| Save/reload | Save during each representative integer/half schedule and after expiry | Schedule, resource references, counters, and cleanup survive or restore deterministically. |
| Multiplayer | Host and client as attacker, reconnect/load, melee/ranged/dual wield | Identical authoritative attack counts and hand allocation; no host-only hook behavior or desync. |
| Performance | Party-scale combat with several actors at the highest schedule | No material frame-time spike, scripting backlog, log-independent stutter, or runaway hook cost. |

The matrix must also retain raw logs, exact BMP hashes, spell/effect parameters, EEex tag,
game executable hash, and save hashes so another tester can reproduce each result.

## Fallback if bitmap schedules fail

If a custom `RNDBASE*` bitmap clips at five, creates only cosmetic swings, mishandles a
weapon path, or desynchronizes, do not compensate by writing
`m_nNumberOfAttacks`. The fallback is a dedicated EEex scheduler patch at both
`CGameSprite::OneSwing()` and `CGameSprite::Swing()` paths.

That hook should expose a narrow schedule decision, emit genuine engine attack resolution
at deterministic round slots, preserve main/off-hand and melee/ranged behavior, and leave
derived stats as an input/reporting value rather than the scheduling mechanism. It must
then pass the same instrumentation and matrix above. Until either the bitmap prototype or
that dedicated scheduler hook passes, the APR-cap idea remains deferred research and must
not enter components 401–403.
