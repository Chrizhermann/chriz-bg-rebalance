# Damageable combat cloud forms — read-only audit, 2026-10-06

Status: Christopher selected **75% damage resistance** on October 6. Component
320 and the independent `CBR_CLOUD_FORMS:0` tail adapter are implemented and the
adapter is applied to the authorized closed stream game. Twenty-seven real-WeiDU
cloud tests, 23 related regression tests, independent review and an exact captured
resource comparison passed. No runtime acceptance is claimed.
The implementation deliberately uses the existing native flat-set effects:
75% is the cloud form's resistance, not `max(natural resistance, 75)`. The lead
clarified this scope before implementation. Normal-form CREs/items stay intact;
natural immunity can be temporarily overridden in a channel set by the cloud.
Existing poison immunity, regeneration, timings and quest/death escapes remain.

## Evidence and scope

Effective resources were read from
`C:\Users\chris\Games\Chriz Easy BG\game`, preferring `override` and otherwise
resolving KEY/BIF entries. This installation has Spell Revisions
`v4.21-chriz.5` component 0 and SCS `35.21` component 6520 (Smarter genies).
The installed mod sources and effective compiled scripts were also inspected.

The audit scanned effective SPL/ITM resources for mist animation changes and
gas/mist polymorph/replacement effects, and effective BCS/CRE/SPL/ITM/EFF
resources for references to the resulting candidates. This is a bounded resource
graph audit, not proof of every dynamically constructed script reference or
every possible installation profile. No broad animation-based patch is safe.

### Recommended known combat targets

| Resource owned by patch | Mechanism and concrete callers | Existing protection and behavior |
| --- | --- | --- |
| `DVGASFRM.ITM` | `DVGASFRM.SPL` dispels the caster, then creates this magical weapon for 20 seconds. Six effective BCS callers: `EFREET01`, `EFREET04`, `DJINNI01`, `DJINNI04`, `DVEFREET`, `DVDJINNI`. | Equipped opcodes 27/28/29/30/31/86/87/88/89 set acid/cold/electricity/fire/magic damage/four physical resistances to 100; opcode 166 sets magic resistance to 100; opcode 101 blocks poison opcode 25; opcode 173 adds poison resistance 100. Regeneration is 3 HP/sec. All item effects use timing 2. |
| `OHBEGASF.SPL` | EE combat spell called by `OHBNAJI2.BCS` and `OHBDORM2.BCS`. `OHBDORMA.CRE` (Dormamus) uses the latter. | Timed 18-second animation and regeneration (13 HP/sec); 100 resistance to four physical types, acid, cold, magic cold and magic damage; poison immunity/resistance. It does not itself grant fire/electricity resistance or magic resistance. |
| `BDGASFOR.SPL` | SoD combat spell called by `BDDJINNO.BCS`, assigned to `BDNAZRAM.CRE` (Nazramu). | Same resistance channels and 18-second/13 HP/sec behavior as `OHBEGASF`, plus its self-refresh/state bookkeeping. The actor has separate quest protection; see below. |
| Private clone of `GASFORM4.CRE`, referenced only by patched `DW#VMGAS.SPL` | SCS combat mist: opcode 135, mode 0, 18 seconds. The stock donor is shared with vampire death escape and must remain unchanged. | Donor has all eleven CRE resistance bytes at 100 (including magic resistance); no equipped items, opcode 120 or minimum-HP effect. Its four installed CRE effects are unrelated Artisan class/proficiency dispatchers. Preserve non-resistance donor data. |
| `FINBODGF.ITM` (optional supported Ascension combat variant) | `BODGASF.SPL` creates this weapon for 18 seconds. `FINBODH.BCS` calls the spell. | Acid/cold/electricity/magic cold/physical resistance 100; fire/magic fire 50; magic damage 75; magic resistance 0; regeneration 20 HP/sec. Polymorph uses `GASFORM4` **appearance only**, so donor resistance changes would not affect it. |

The default stack has SCS 8085, which replaces Ascension Bodhi's AI. No effective
CRE in the scan was directly assigned `FINBODH`; therefore the existence of this
authored combat graph is confirmed, but active use on this exact stack was not.
It is a legitimate optional compatibility case, not a reason to alter plot mists.

Concrete DVGASFRM script consumers include ordinary/noble Djinni and Efreeti,
their summoned versions, `BDEFREET`, `BPAL_ATA`, `DVDJINNI` and `DVEFREET`.
SCS `stratagems/genie/ssl/genie_top.ssl:97-128` triggers cloud at HP below 30%,
at most three times, while not GOODCUTOFF, and idles/wanders while the item exists.
SCS `genie/genie.tpa:58` installs the shared DVGASFRM pair; SR independently ships
the same resource names in `spell_rev/components/main_component.tpa:312-313`.
Preserve these AI decisions, regeneration, durations, dispel/visual effects and
action restrictions.

SCS combat mist callers are `SARVAM02`, `VAMPVIC`, `VAMPJAH`, `VAMPIR01`,
`VAMPANO`, `VAMPAER`, `VAMEMI01`, `PPVAMPIR`, `PPVAMP`, `PPJOYE`, `LASSAL`,
and `C6VAMPIR`. Its source graph is
`stratagems/vampire/vampire.tpa:135-152` and
`vampire/ssl/vampire_mist.ssl` / `vampire_mist_top.ssl`: tactical mist followed
by movement/teleport and natural-form restoration, with a five-second fallback.
Keep those scripts unchanged. Opcode 135 mode 0 copies donor resistances and
specific physical statistics; it is not a creature replacement.

Ascension describes BODGASF explicitly as a defensive cooldown in
`ascension/ascensionmain/ascension_bodhi_irenicus.tpa:50-94`, then constructs
the item-backed form. The effective bytes, rather than prose alone, establish the
actual elemental values listed above.

### Inactive variants and exclusions

* `OHGASFRM.SPL` has a similar 20-second/10 HP/sec combat-looking package, but
  no incoming reference was observed in scanned effective resource types; only
  its own reference was found. Do not advertise active coverage without another
  caller. It can be an explicitly supported optional variant after validation.
* `SPIN970/971/972` (EFREETI/DOA/DJINNI_GAS_FORM_CHANGE) use opcode 151 to
  **replace** the creature with `GASFORM3/2/1.CRE`. These templates have 8 HP and
  100 in all eleven resistance bytes. `GASFORM1/3` wait 20 seconds and replace
  themselves with physical Djinni/Efreeti. No numeric 3970/3971/3972 action call
  was found in effective BCS. `CDNEF1 -> CDNEFGAS` is another such graph without
  an observed incoming reference. These are not safe targets for blindly lowering
  CRE resistance: the resulting 8-HP replacement kill also raises original
  actor/reward/loot questions. Leave dormant legacy replacement routes unchanged
  until an active consumer and the intended replacement lifecycle are established.
* Keep `GASFORM4.CRE` and `SPIN964` (VAMPIRE_GAS_FORM_CHANGE) intact. SCS
  `vampire/ssl/vampire_flight.ssl:5-11` explicitly calls the latter on `Die()`;
  GASFORM4 has `ESCAPE` AI. Isolate the combat DW#VMGAS donor by cloning.
* Keep named death/quest mists and their spells intact: `DACEMIST`, `C6BMIST`,
  `TANOMIST`, `DELMIST`, `VALEMIST`, `LASMIST`, `BODMIST1/2`, and their
  SPIN803/809/814/815/816/904/903/902 spell families. Hexxat's `OHHEXAM4`
  and other plot/escape actors are not combat defensive cooldowns.
* Do not touch permanent mist monsters, Nishruu/Hakeashar, spell effects, portals,
  cosmetic animation changes or actors merely sharing animation `0x7F39`/`0x7F35`.

## Protection boundary and balance parameters

The chosen value is **75% resisted / 25% taken**, before other effects and engine
rounding. Only identified cloud-granted 100% damage-resistance setters become
75%. Do not add resistance to channels the original form leaves open, or change
FINBODGF's pre-existing 50/75 values. No global cap or resistance floor is added.

Magic resistance is a separate chance to reject spells; opcode 31 is resistance
to magic **damage**. Keeping DVGASFRM's opcode-166 value 100 would still reject
ordinary damaging spells after changing opcode 31. Prefer removing its added
MR100 effect, thereby retaining the actor's natural MR, rather than setting both
MR and magic damage resistance to R (which produces two independent protections).
For SCS's mode-0 polymorph, the private donor has 75 in CRE V1.0 resistance bytes
0x59 through 0x63, except **0x5d (Magic Resistance) = 0**. This temporarily replaces
natural MR during combat mist, rather than adding a second chance to reject spells.
0x63 is missile resistance, NOT poison; CRE V1.0 has no poison-resistance header
byte. All donor fields outside these eleven bytes, and mode-0 behavior, remain.

Poison immunity is retained: DVGASFRM and both EE spell families have opcode 101
immunity to opcode 25 as well as opcode 173 poison resistance. Neither changes.
Underlying racial/quest protections outside the cloud resources also stay intact.

No opcode 120, minimum-HP opcode 208, or opcode-101 immunity to opcode 12 exists
in the identified combat-form protection packages. However, **underlying actor
protection is separate**: BDNAZRAM carries `BDMISC1B.ITM`, which independently
grants opcode-101 immunity to damage opcode 12 and MR100. This appears in its
ordinary inventory and must not be removed as part of a cloud patch. Therefore
changing BDGASFOR alone does not promise that this protected actor can be killed.
Natural elemental immunities also exist: GENEFR01 has fire125, OHBDORMA fire127,
and GENDJI01 electricity100. Preserve their underlying CRE/item data. Where a
cloud already uses a flat-set resistance effect, its new value can temporarily
override that natural resistance; where no cloud effect covers that channel
(for example OHBEGASF and fire), the natural immunity still applies.

## Implementation and checks

1. Add an optional tail component with a reusable effect-table transformer and
   explicit resource allowlist. Handle missing optional provider resources
   gracefully; preflight the recognized animation/delivery/protection graph.
   Reject an unknown present shape rather than falling back to animation-wide edits.
2. Use the approved fixed 75% and the documented poison/MR policies. Patch identified
   effect fields in place, preserving all unrelated bytes and effect slices.
   Clone GASFORM4 to a private collision-checked resref and redirect only the
   DW#VMGAS polymorph reference. Never repoint SPIN964 or change its donor.
3. Update SR's actual Summon Efreeti/Djinni descriptions: dynamically resolve
   WIZARD_SUMMON_EFREET / WIZARD_SUMMON_DJINNI (here SPWI717/718). Their current
   description says the form becomes immune to almost all damage; replace just
   the relevant claim and preserve unrelated spell/summon information.
   `spell_rev/languages/english/arcane.tra:2358,2387` contains the source wording.
4. Use private captures of effective resources and vanilla/provider variants in
   synthetic games. Check 75%, exact channel policy, removal of cloud MR
   immunity, unchanged durations/regen/AI/non-damage effects, description integrity,
   absent providers, unknown layouts, private resref collision, idempotence,
   transactional failure, and byte-exact uninstall. Assert excluded death/quest
   resources remain identical and no existing unrelated TLK entry changes.
5. Treat runtime combat as separate acceptance: physical and magic damage while
   clouded, regeneration still active, natural return, kill/reward behavior,
   vampire tactical movement and unchanged death escape. Static transformations
   cannot prove final damage after other active buffs or integer rounding.

Existing saves: future casts/equips can use patched resources. Already-active
SPL effects are serialized on the actor, and a saved DW#VMGAS polymorph still
references the original donor until another cast. Do not promise that installing
the component retrofits a currently active cloud. These forms are finite;
expiry and the next transformation are the normal transition. Direct save surgery
or runtime effect migration is outside this implementation proposal.

Primary opcode semantics were checked against IESDP:
[opcode 135](https://gibberlings3.github.io/iesdp/opcodes/bgee.htm#op135),
[opcode 151](https://gibberlings3.github.io/iesdp/opcodes/bgee.htm#op151), and
[opcode 98](https://gibberlings3.github.io/iesdp/opcodes/bgee.htm#op98).

## Applied private repair — October 6

Target: `C:\Users\chris\Games\Chriz Easy BG\game`, game/loader closed.
WeiDU exit 0; all 441 previous log rows preserved exactly, with only the new
`CBR_CLOUD_FORMS:0` tail appended. Nine outputs match the tested capture byte for
byte: five direct form resources, DW#VMGAS, its private CBRGAS75 donor, and the two
SR summon descriptions. All 330,156 previous TLK entries and sound metadata are
unchanged; two descriptions were appended. Saves and game processes untouched.

Backup and result:
`C:\Users\chris\Games\Chriz Easy BG\repair-backups\oct06-cloud-forms\verified.json`.
Private test inputs/results and deployment checks remain in ignored collection
`target/work/oct06-cloud-forms/`, final fixture `capture-review-verified`.
Do not redistribute these captured game resources. The owner component has not
been released and the CEBG recipe has not yet been updated. No in-engine combat
test was run; encounter behavior remains user/community acceptance.
