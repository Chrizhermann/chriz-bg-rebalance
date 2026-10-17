# Existing potion self-immunity206 — bounded source check, 2026-10-09

Keep the native guard unchanged under the current prototype. An active206 can
already reject a repeated linked potion's SPL children before the successful
admission hook. Calling that an exception to refresh requires a policy decision;
it is not implemented refresh support. A selective future override is feasible
only with additional origin/lifetime metadata. Native immunity entries alone do
not identify which potion or unrelated protection produced them.

No hook, runtime, eligibility rule, resource, installed game or save was changed
for this investigation. All native addresses below are RVAs in the same pinned
BG2EE2.7.3.0 executable documented in `native-projectile-delivery-notes.md`:
SHA256 `b51093a49140b2b8a7c046b4652bb8e535be24ebbc12b1d735e0b94217a14d57`.

## Current source resources

These are **flat upstream source corpora**, not proof of an installed IR profile:

- IR: `C:\Games\Baldurs Gate 1 and 2 mods\ItemRevisions\item_rev\itm`
- IRR: `C:\Games\Baldurs Gate 1 and 2 mods\ItemRevisions-4b10\ItemRevisions-4b10\item_rev\itm`

| Corpus | Resource |206 byte offset| Parameter1 | Power |
| --- | --- | --- | --- | --- |
| IR | POTN36.SPL | `21A` |0|0|
| IR | POTN41.SPL | `39A` |0|0|
| IRR | POTN09.SPL | `1BA` |-1|3|
| IRR | POTN36.SPL | `24A` |-1|0|
| IRR | POTN41.SPL | `36A` |-1|0|

All five206 records have target1, parameter2=0, timing0, duration300seconds,
resist/dispel byte0, probability100/0, special0, and protected resref equal to the
listed SPL. IR POTN09 has no206. Compiler-worker extraction reports the original
ITM146 at `DA`: target1, p1=0, p2=1, duration0, resist/dispel0, special0,
probability100/0, resource equal to the linked SPL; timing9 in IR, timing1 in IRR.
The206 records were independently read and verified in this check.

Full paths, file hashes and exact48-byte206 records are saved in
`%USERPROFILE%\AppData\Local\Temp\cbr-potion-inventory-20261009\native-206-inputs.json`.
For the priority example, IR POTN36.SPL SHA256 is
`0048f45c8ca9266d099633a3895c85d07f54fdaab8db99f5f3436eac7f17ce04`;
IRR POTN36.SPL is
`048e781ed7d6aff4032906d159ee51a58f652c647bca4d63d3ecd4dc2068ec6c`.

## Native registration discards provenance

`CGameEffectImmunitySpell::ApplyEffect(1B6900)` receives RCX=effect and RDX=sprite.
It retains these in RDI/RSI, allocates **16bytes** at `1B6929`, initializes the
resref, and constructs only:

| Entry offset | Meaning and exact producer |
| --- | --- |
| `00..07` | protected resref from effect `+30`, copied at `1B6949..1B6955` |
| `08..0B` | effect parameter1 from `+1C`, with0 normalized to-1 at `1B695A..1B696A` |
| `0C..0F` |0 at `1B693E` (spell-only protection, excluding item-source lookup) |

It appends that entry to sprite `+1880` at `1B6974`. The native call's bytes are
`E8470C2500`; immediately before it, RDI still holds the originating effect,
RSI the sprite, RBX/RDX the new entry, and RCX the destination list. This is a
concrete registration point where a focused extension could capture metadata.
There is no originating effect pointer, parent source, source ID, duration,
caster level, or dose identifier anywhere in the16-byte entry.

The resref-copy helpers are simple native8-byte copies (`3FF870`, `3FF880`), not
an indirect object retaining an effect reference. IR p1=0 and IRR p1=-1 therefore
produce identical native entries for the same protected resource.

## Lookup and stat rebuilds

CheckAdd at `1CCCF6..1CCD1E` passes:

- incoming effect source resref `effect+94`;
- `r8d = (effect.sourceType[+90] != 1)`;
- immunity list at sprite `+1880` or `+2528`, selected by derived-stat state.

`CImmunitiesSpellList::FindRes(1F8C90)` traverses the list. At `1F8CA7..1F8CB1`
it skips entries whose `+0C` is0 when the incoming source is not type1. Otherwise
it compares the exact resref at `1F8CB3..1F8CB9`, and returns the **first** matching
entry at `1F8CC3`. Thus the original item146 (type2) can pass this206 while its
native SPL children (type1) are blocked. A match ultimately jumps to native
failed admission at `1CD076 -> 1CC9A5`, before the prototype's success hook.

Returning “no immunity” after recognizing the first entry is unsafe: a second,
unrelated matching protection may follow it. Any approved filter must continue
the native search past only proven eligible entries and retain the first other
match. This applies even when the first and second entries have identical bytes.

Entries are not stable handles for their source effects:

- ProcessEffectList calls `CDerivedStats::Reload` at `3AC4F8` for sprite `+1120`.
  Reload clears the resource immunity list at derived stats `+760` through
  `153D90..153D97 -> 1F8AE0`.
- ClearAll loops over and deletes16-byte entries at `1F8B00..1F8B0C`, then clears
  list nodes at `1F8B23`.
- `CDerivedStats::operator=` calls resource-list assignment at `14F6CA`.
  `CImmunitiesSpellList::operator=(1F85D0)` destroys destination entries,
  allocates new16-byte entries, and copies only resref/p1/include-items at
  `1F865E..1F867A`; it appends the new entries at `1F8680`.

During the copy, RSI is the old entry and RBX the new entry; RBP is the destination
list. That provides a concrete point to propagate metadata if a future extension
is approved. Registration alone would miss the copied list and leave stale
addresses after rebuild; both origin propagation and lifetime invalidation matter.

## Smallest missing capability, not an impossibility claim

A future narrow adapter would need all of these, without changing native effect
fields or weakening other admission checks:

1. Establish original linked-child lineage from the exact item146 dose and its
   actual message/child route. A shared SPL resref is insufficient.
2. Associate each newly registered206 entry with its originating native effect
   lifetime, actor, verified potion family and guard semantics. Mark other entries
   unknown/unowned rather than inferring ownership from their protected resref.
3. Propagate entry identity across native derived-stat copies and invalidate it
   on clear/rebuild/free/load. Existing effect-lifetime tokens do not by themselves
   track the separate16-byte immunity-entry allocations.
4. Restrict any filtered lookup to the proven linked-potion admission context.
   Skip only guards permitted by the chosen policy and continue searching for
   all other protections. Preserve the original failed-admission path on unknown
   metadata and preserve probability, other immunities, MR/save and source checks.

This is more than bypassing one conditional branch. The exact missing data is
the **origin of each currently searched immunity entry**, plus the incoming
linked child's proven dose lineage. The relevant native registration/copy/search
sites expose enough data for a focused extension, but no such extension has been
implemented or validated here. Save-restored linked effects also need a separate
lineage policy; a resource-name guess does not recover their original dose.

Leaving206 unchanged is the smallest safe policy exception: a repeat blocked by
that native ward remains blocked and does not refresh. It should be described as
preserving the existing potion's native guard, not as general refresh support or
a guarantee of uniqueness after arbitrary guard removal/expiry. Which exception
to accept remains the lead/user's policy decision.

## Offline check

The saved read-only diagnostic
`%USERPROFILE%\AppData\Local\Temp\cbr-potion-inventory-20261009\probe_206_provenance.py`
hash-pins and executes copied native206 Apply, the resref helpers, FindRes, list
assignment and ClearAll in Unicorn. Three synthetic source effects with different
parent/source IDs and caster levels, including p1=0 versus-1, produce identical
entry bytes: `504F544E33360000FFFFFFFF00000000`.

Assertions pass for first-match-only spell lookup, item-source skipping, new
addresses after list copying with no additional origin data, and deletion of every
copied entry on clear. Result:
`%USERPROFILE%\AppData\Local\Temp\cbr-potion-inventory-20261009\native-206-provenance.json`.

Allocation, list plumbing, deletion and the security-cookie service are explicit
test doubles. The source effects/list objects are synthetic. This does not execute
whole CheckAdd/stat rebuilding, live EEex hooks, a game process, or save/load.
