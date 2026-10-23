# Apex Dragons: current design decisions

Updated: 2026-09-16. **Included in v0.4.0; gameplay acceptance pending.** This document supersedes conflicting choices and implementation-status claims in the [July draft](2026-07-20-dragons-design.md). It does not authorize installation into the active game.

## First implementation after authorization to proceed

Components 110/111 now have a first implementation. Defaults: Firkraag 15%/-4;
Thaxll'ssillyia and the Watcher's Keep guardian 5%/-2; Nizidramanii'yt and Saladrex
10%/-2. Lethal attacks activate at SCS Dragon Hardcore/Insane (configuration values
5/6/7), with the game Hard/Insane fallback at configuration value 0. These allocations
and activation are implementation choices following the request to proceed; the original
explicit user values below remain their basis. No HP, aura or encounter-spell addition is
included.

The lethal component requires **EEex**, using an ordinary saved/chance-based on-hit
effect followed by a direct death application, without stripping protections. All runtime
files still go to `override`. Native chunking respects the game's gore/difficulty and
permanent-death protections, so the implementation warns that it **can** cause permanent
death. It preserves scripted minimum-HP protection. These engine details supersede any
unconditional chunking promise below. See the [README](../../README.md) for the implemented
contract and [research 19](../../research/19-dragon-vorpal-delivery.md) for the evidence.

## Agreed direction

This is an optional difficulty increase. Fights should become more dangerous and distinctive without becoming a grind. The community's "300% of current power" suggestion expresses that ambition; it is not a numerical specification.

| Dragon | Physical vorpal proc chance | Saving throw |
|---|---:|---|
| Firkraag | 15% | Save vs. death at -4 |
| Other selected dragons | 5% or 10%, assigned individually | Save vs. death at -2 |

These are actual intended probabilities, not raw effect probability bytes. The first implementation uses the allocation and activation defaults above. No additional Insane -6 variant is included.

The user chose the **permanent-death (chunking) alternative** on a failed save, with the native-engine qualification above. The physical claw/bite rider should pass through Stoneskin, physical resistance, Death Ward, and death immunity; it must not require actual HP damage from the weapon hit. A save remains the countermeasure. The implementation requires a qualifying melee hit, so weapon immunity can prevent delivery.

The implementation uses opcode 13 with death type 8. Its timing field does not establish whether death is permanent; the death type does. Combat acceptance must prove the intended delivery and protection interactions. The broader Death Ward correction belongs to the SR patch repository; see the [handover](../handovers/2026-09-06-sr-death-ward-vorpal.md). It is not a prerequisite for the dragon-specific EEex rider.

## Required player disclosure

The option/component must disclose permanent death at selection time and in its README and release notes. Do not hide the consequence behind the word "vorpal" or only mention it in a changelog.

Selection label: **EEex + SCS: Apex Dragons — lethal claws and bites (can cause permanent death)**.

Player disclosure (the installer and README include the individual encounter values):

> Selected dragons gain a chance to cause permanent death with a claw or bite after a failed save vs. death. A chunked companion cannot be raised or resurrected through normal gameplay. This effect bypasses Stoneskin, physical resistance, Death Ward, and death immunity. Native gore and permanent-death protection settings still apply and may convert the result to ordinary death. Weapon immunity can prevent a qualifying hit, and scripted minimum-HP protection remains intact.

Before release, publish the final affected-dragon list and activation settings alongside that warning. Clearly distinguish ordinary deaths from this permanent-death rider. Do not promise a new separate component number or a particular installation layout before those choices are made.

## Other encounter decisions and open questions

- **Wing buffet:** separate component 111 increases the cooldown from 6 to 18 seconds for the five selected dragon identities. Included in v0.4.0 as an independent option.
- **HP:** no additional increase is finalized. The earlier +25% proposal is not current approval. Account for SCS's existing HP adjustments before choosing and validating any increase.
- **Auras:** penalties should be modest. Exact resistance/save values and encounter-specific delivery remain open; the July universal -25/-40 resistance and -2/-4 save packages are superseded.
- **Escorts:** choose by the individual dragon's personality and encounter. Prideful or overconfident dragons need not have helpers. General spell-list expansion is low priority.
- **Thaxll'ssillyia:** shadow-creature summons are deferred; any future number should depend on difficulty.
- **Nizidramanii'yt:** discuss lowering acid resistance and more frequent high-caster-level Dispel Magic. On the inspected SR install, the Remove Magic/Dispel Magic symbols resolve to the same spell. Exact penalties and cadence are not finalized.
- **Saladrex:** discuss Time Stop and/or Improved Alacrity following his initial protection. Neither addition is approved yet. His inspected script has no existing Time Stop/Improved Alacrity cast, and its casting timers require consideration if adding a faster spell sequence.
- **Deferred:** Adalon and ToB dragon adjustments. Do not apply a generic shared-script patch that silently expands the agreed encounter scope.

## Evidence and remaining work

The [original dragon research](../../research/05-dragons.md) and July draft remain historical inputs. Current read-only research found that the installed SR Death Ward grants blanket opcode-13 immunity, which also blocks physical vorpals; its protection needs a deliberate compatibility solution. The [SR handover](../handovers/2026-09-06-sr-death-ward-vorpal.md) records those binaries, scope, and acceptance requirements. Author intent is not established by the installed behavior.

The implementation and binary evidence are present. On 2026-09-16 the user approved
including the implemented options now and doing the combat check after one combined
CEBG installation, rather than adding a separate pre-release playtest gate. Combat
and existing-save acceptance remain unverified. HP, aura and further encounter design
are separate future decisions. No existing-save retrofit or combat acceptance is claimed.
