# Research 15: actor-scoped SCS wing-buffet cooldown

2026-09-07. Read-only evidence precedes component 111 implementation. The current
design accepts a separate 6-to-18-second cooldown option, with the first-pass
roster limited to five dragons. No active-game install or gameplay acceptance.

## Captured evidence

Reference: `C:\Games\Baldur's Gate II Enhanced Edition modded`, SCS 35.21. Exact
pre-images and SHA-256 hashes are in `originals/dragon_wing_buffet/manifest.json`.
Five complete compiled BCS files and five CRE files were copied without modifying
their sources. The smaller test BCS fixtures consist only of the two original
buffet blocks, byte-identical across all five scripts, in an `SC` wrapper.

| Creature | Exact death variable (CRE +0x280) | SCS script and slot |
|---|---|---|
| FIRKRA02 | firkra02 | DRAGRED, class (+0x250) |
| SHADRA01 | ShaDra01 | SHADRA01, override (+0x248) |
| DRAGBLAC | Dragblac | DRAGBLAC, class (+0x250) |
| GORSAL | GorSal | GORSAL, default (+0x268) |
| FSDRAGON | FSdragon | DRAGGREE, class (+0x250) |

`stratagems/dragon/ssl/wingbuffet.ssl` supplies two blocks. The cloud-clearing
block sets `castspell` to 3 seconds and `Buffet` to 6, breaks invisibility, and
casts wing buffet on self. The mob-clearing block has two equally weighted
responses: cast on the nearest enemy after the same timer assignments, or set
`Buffet` to 6 and Continue. Thus there are **three** cooldown assignments, not
two. The no-cast response must also change to 18 to preserve the cadence model.
All guards, response weights, castspell timers and cast targets stay intact.

The exact blocks have SHA-256:

- Cloud: `ef3c155da3c2` (prefix; full fixture hashes in the manifest).
- Mob: `c839f9ebf430` (prefix).

The compiled actions use `115` (SetGlobalTimer), `160` (ApplySpellRES), and `181`
(ReallyForceSpell). Final SPELL.IDS resolves wing buffet to 3695, and cloud
triggers to 2502/2213/2614/2810. These spell numbers are observations only:
production compiles symbolic names against the install's IDS maps.

A read-only audit of effective CRE headers found the other shared-script users:
`DRAGRED` and `DW#YSDRA` have death variable `DragRed`, and `DW#ABRED` has
`dw#abred`; all fail the selected actors' Name gates. `DRAGSHAD` is an alias/donor
of the named shadow dragon: both it and `SHADRA01` use death variable `ShaDra01`,
script `SHADRA01`, and name strref 33905 (Thaxll'ssillyia). SCS's dragon.tpa line
214 specifically upgrades `SHADRA01`. A targeted scan of effective ARE/BCS/DLG
files found no DRAGSHAD spawn reference (only NPC dialog death-variable checks).
The gate identifies that named actor, including its same-name donor, rather than
distinguishing two indistinguishable instances of the same death variable.

## Scope-preserving transformation

Changing a shared DRAGRED script unconditionally would reach deferred creatures.
Instead, insert a copy of the exact two recognized blocks immediately before
the originals. Both copies require `Name("<verified death variable>",Myself)`
(TRIGGER.IDS 0x40A5) and use cooldown 18. The original blocks remain byte-identical
for other actors. For the selected actor, the copied no-cast response's Continue
cannot fall through into another buffet: it has already set the shared timer.

The installer must verify each CRE identity and expected script slot, recognize
the exact SCS block pair or its exact already-patched pair, and preflight every
target before publishing any BCS. Unknown, partial, or foreign timer shapes must
fail without partial publication. It must not patch CREs, shared SPLs, other
scripts, difficulty variables, or add a marker to a saved creature.

The five named actors receive the cooldown at every difficulty where their
existing SCS conditions allow wing buffet. Adalon, generic/Hell dragons and ToB
dragons retain their original paths. New scripts loaded after installation can
use the new blocks for an existing actor; an already-running timer is not reset
and an in-process script reload is not promised.

## Validation contract

Dedicated tests exercise real WeiDU against captured fixtures and a synthetic
game. They must prove exact untouched-original preservation, all three timer
changes only in the actor-gated copies, idempotence, dynamic spell identifiers,
strict preflight/rollback, and BIFF-only materialization without CRE publication.
Static branch simulation checks selected/non-selected identities and both mob
responses. This is not engine gameplay acceptance.

## Implementation verification (2026-09-07)

The first dedicated test run was RED because the production library did not yet
exist. After implementation, `python -m pytest tests/test_dragon_wing_buffet.py -q`
passes **11 tests**, including six foreign/partial script-shape variants and two
foreign CRE identity/assignment variants. The synthetic game puts all five CREs
and BCS donors in a BIFF; the production game path publishes only the five changed
BCS files. Its isolated uninstall restores the prior override tree, and KEY, BIF,
root TLK and language TLK remain byte-identical. No WeiDU operation targeted the
reference game.

WeiDU 24900 `--nogame --parse-check TPA` also accepts the production library.

Production entry point: `cbr_apply_dragon_wing_buffet`, default `game_mode=1`.
The public TP2 must predicate on BG2EE/EET and SCS Smarter Dragons (6540). The
function itself verifies all five identities/script slots and all target blocks
before any BCS publication. Each shared script retains its complete original
byte sequence; only the two actor-gated blocks are inserted. No CRE or SPL is
published. Existing actor timers are left alone. Runtime gameplay acceptance
remains outstanding.
