# Cross-repository BG compatibility follow-up

2026-10-08. User requested a hard compatibility policy after component 302
rejected a community player's modified Flail of the Ages. The shared policy is
`~/.agents/skills/bg-modding/references/compatibility-policy.md`; it applies across
repositories. Fixture counts, old values and English wording are not identity.
Bounds, actual capability requirements and genuine semantic ambiguity still matter.

## Implementation now

- FoA: repair in `codex/foa-compatibility-20261008`, based on Rebalance `83e51d2`.
  See [research and test evidence](../../research/15-flail-of-ages.md).
  Prepared on the review branch; no release, collection pin, live game or save
  changed. Audit findings below are separate from the implemented FoA fix.
- The reporter's resource/debug files are not available here. Automated tests
  reproduce the rejected classes of valid layouts; they do not prove the exact
  contents of that player's installation or universal mod compatibility.

## Open follow-ups by owner

These are source audits, **not completed fixes**. Each report records exact
checkout/ref, affected paths, plausible counterexamples, and tests to add.

1. [Modpack and SoD Remix](2026-10-08-modpack-sod-compatibility.md): prioritize
   the jailbreak's silent wrong-spell fallback, then fixed dialogue IDs/counts,
   encounter-coordinate fingerprints, creature/effect-layout restrictions.
2. [Rebalance, SR and BuffBot](2026-10-08-sr-rebalance-compatibility.md): Bracers,
   Emotion, elemental arrows, RR spell migration, Tempus, cloud forms and SR
   Lightning Bolt are implemented on review branches (2026-10-17, unreleased);
   see its implementation status. Open: Christopher's cloud-form balance
   decision (75% as target or maximum).
3. [Artisan, Bardic, Aura and Randomiser](2026-10-08-forks-compatibility.md):
   Bardic's Abettor payload and Artisan's standalone Fighter Modals retrofit.
   No comparable defect established in inspected Aura/BuffBot paths. Randomiser's
   same-operation stale-plan checks protect item accounting and must remain.

Implement in each owning repository, not by moving their code into this repo.
Use isolated branches; preserve other agents' WIP. For each fix, demonstrate the
valid alternate input and preservation first, then adjust matching and tests
together. Do not mass-delete checks or turn omitted behavior into quiet success.
