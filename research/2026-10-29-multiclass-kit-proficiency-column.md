# Multiclass characters with a kit: which WEAPPROF column the engine reads

Status: engine finding of 2026-10-29, built into component 411 (Alaghor of
Clangeddin weapons) the same day at Christopher's request: Yeslick's kit
should let him both train axes and wield them ("Wir können es doch selber
implementieren").

## Finding

The 2026-10-27 labs showed that multiclass Yeslick (FIGHTER_CLERIC with the
cleric kit LK_ALAGHOR) trains from the FIGHTER_CLERIC column of WEAPPROF.2DA,
not from his kit's column. The reason is in
`CRuleTables::GetProficiencyClassIndex(class, kit)` (BG2:EE / EET 2.7.3.0
`0x1402456C0`; the same instructions in 2.6.6.0). It returns the kit's KITLIST
`PROFICIENCY` column only when all of these hold:

- the kit value has the 0x4000 bit and a kit index other than 0;
- the index is a KITLIST row;
- that row's `CLASS` equals the character's class byte.

Otherwise it falls through to the class column. Yeslick's class is 8
(FIGHTER_CLERIC) and his kit's KITLIST `CLASS` is 3 (CLERIC), so the third
check fails and he gets the multiclass column. The callers are
`GetClassProficiency`, used by character creation and level-up (proficiency
panel, `CanSpendProficiencySlots`, the plus/minus buttons, `ResetLevelUpPanel`)
and by dual-classing on both screens.

## Rejected alternatives

- **KITLIST `CLASS` 3 → 8 for the kit.** Other engine code reads that cell:
  `GetClassAbilityTable` (the kit's CLAB abilities), `GetClassFromKitId` and
  `GetClassString` (the class name on the record screen). Changing it would
  change Yeslick's kit abilities and name, not only his weapons.
- **Raising FIGHTER_CLERIC.** Every fighter/cleric would get axes.
- **Only the C0PR#CL kit grant.** Yeslick could wield axes but never train
  them, which Christopher rejected.

## The hook

`M_CBRKP.lua` hooks the conditional jump taken on a class mismatch
(`EEex_HookConditionalJumpOnSuccess`, 2.7.3.0 `0x140245741`, restoring the
seven-byte `MOVSX` after it). The added code only compares and branches: for a
class/kit pair registered in `CBRKPKIT.2DA` (EBX holds the kit index, EBP the
class), it jumps to `jmp_fail`, that is on along the native kit-column path;
every other pair keeps the native jump. That path reads row EBX's `PROFICIENCY`
cell and returns it; it does not read the compared class again, and its next
instruction (`cmp edx, 5`) sets the flags anew. No other reader of KITLIST
`CLASS` changes.

The EEex pattern `CBR-KitProficiencyColumn` (`kitprof/CBRKP.db`) covers the
function from its entry to the kit-column read: 138 bytes, the format string's
RIP displacement (bytes 112–115) and the `sscanf` call displacement (117–120)
as wildcards, label at byte 129. It occurs exactly once in BG2:EE 2.7.3.0
`Baldur.exe` (sha256 `b51093a49140b2b8…`, the lab and Christopher's game) and
in the 2.6.6.0 reference executable (`fc821a4806a0305b…`). An unresolved
pattern would stop EEex's Lua from starting, so the installer refuses an
executable without exactly one match inside an executable section. At run time
the hook checks the 17 bytes around the jump and leaves the function alone if
they differ, for example because another mod hooked the same jump.

The registry is shared: a later component can register another class/kit
pair. 411 registers `FIGHTER_CLERIC` with `LK_ALAGHOR`, the kit only Yeslick
uses.

## The kit column

With the hook, Yeslick's limits come from his kit column. 411 sets its weapon
rows to the cleric weapons and axes at the fighter/cleric limits (Christopher:
"Kleriker-Waffen plus Axt", "Bis 2 Punkte"); thief weapons drop to 0, and pips
he already has stay. Every other row (fighting styles, the BG1 groups and the
unused rows) copies FIGHTER_CLERIC, the limits he trains under without the
hook, so his fighting styles do not change.
