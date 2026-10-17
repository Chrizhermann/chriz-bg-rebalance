# Wish / SR Improved Haste — bounded owner check

October 9, 2026. Source/design only: no component, default, resource patch or
game test. Inspected BG Rebalance `v0.8.1` (`09db97dc5cbd14f1b8bf7fe3af64f69bee313585`)
and SR owner `v4.21-chriz.5` (`c8494181c224d22002b5f4ee6fc4411235dd4a9f`).
Neither inspected release implements the requested Wish replacement.

## Actual party result

Read-only effective resources from `%USERPROFILE%\Games\Chriz Easy BG\game`:

`WIZARD_WISH` → `SPWI919` → op177 `WISH2.EFF` → op67 `WISH02.CRE`
→ `WISH25.DLG` → party result `SPWISH37`.

The inspected DLG's transition33 (offset`0x524`) uses action16 (text offset`0x15DD`):
`ActionOverride(LastTalkedToBy,ForceSpellRES("spwish37",Myself))`.
The result has native op16, p2=1, target3 (party), timing0, duration138 at`0xFA`.
SHA256: `f9335502ec27e261fb58d68ea31f7fd662dbe2e4bcefafe7d0c3b1c7f85fee49`.
These are observations, not exact-count/duration requirements for a future patch.

`SPWISH36` (everyone) and `SPWISH40` (enemies) are different outcomes and must
not be silently included. DLG structure follows the
[IESDP format](https://gibberlings3.github.io/iesdp/file_formats/ie_formats/dlg_v1.htm).

## Provider and order

- SR `spell_rev/components/main_component.tpa:2670` installs Improved Haste;
  lines3268–3272 install Wish and the separate Mass Breach result.
- `spell_rev/lib/kreso_haste_slow.tph:47–109,189–201` adds Haste/Slow integration
  but does not replace Wish's native doubling with the SR package.
- SCS35.21 `stratagems/mage/mage.tpa:958–985` clones `SPWISH37` into `DW#WISH2`
  and changes party targeting to enemy-side delivery. Its summoning wrapper is
  built separately. A patch after SCS that changes only `SPWISH37` will leave
  that previously generated clone unchanged.
- Rebalance220 (`setup-chriz-bg-rebalance.tp2:1496–1501`) changes bracers only.
  Its `sr_bracers.tpa:298–306` resolves the donor symbolically. The helper builder
  at142–235 supplies relevant exclusion/Tempus-bridge knowledge, but its self-only
  targeting,20-second duration and narrow donor-layout assumptions do not belong
  in a Wish implementation. Its only observed Wish addition is a reciprocal
  immunity to the private bracers helper; existing Wish mechanics remain intact.

Read final resources after SR, SCS and any Tempus donor changes. Preserve the
Wish result's own duration, recipients, original resource identity and unrelated
effects; adapt the effective SR Improved Haste mechanics to that delivery.
Simply casting canonical SR Improved Haste would introduce its own projectile
and duration instead. Non-SR behavior must remain byte-identical.

## Decisions before implementation

1. Whether the SCS enemy clone should change too; the present request names the
   party result and does not settle other Wish outcomes.
2. How to preserve reciprocal Haste/IH/bracers exclusions and protection types
   when adapting the effective donor, including the optional Tempus bridge.
3. How multiple headers and linked donor payloads retain recipient attribution,
   duration and original resource protections.

Later tests should cover SR with/without SCS, Tempus and bracers; relocated IDs;
reordered/extra effects; multiple headers and bounded linked payloads; second
application/rollback; unchanged other Wish outcomes; and unchanged non-SR input.
No component number, selection default or release commitment is chosen here.
