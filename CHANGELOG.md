# Changelog

## v0.6.0 — 2026-09-26

- Add component 301: Emotion, Courage and Emotion, Hope are mutually exclusive on each
  creature. The last beneficial Emotion applied wins; recasting the same spell refreshes
  it. This also repairs the installed Courage defect that let it stack with itself.
- IWDification- or SCS-supplied spells are rebuilt in place, keeping their slots,
  presentation, scroll placement and SCS detectable-spell markers. Fear and Symbol,
  Hopelessness remove their matching benefit in their own save/MR domain; Emotion,
  Hopelessness keeps its unconditional Hope removal.
- Without either spell pack, 301 adds both spells in dynamic level-four slots with the
  original IWDEE icons and animation, character-sheet status entries, and point-target
  learn-scrolls stocked wherever Enchanted Weapon / Emotion, Hopelessness scrolls are sold.
- Install 301 after IWDification, SCS, Spell Revisions and other spell, scroll or store
  overhauls. It overwrites the effective Courage/Hope mechanics and English descriptions;
  a later spell mod can overwrite it again.

Validation: 369 automated tests pass; 26 capture-gated dragon tests skip on a fresh
clone. The 44 component-301 tests cover standalone, mixed-provider, provider-only,
reinstall and uninstall paths. A disposable standalone install confirmed real spell
delivery, stat changes and Hope/Courage replacement. The standalone status-list retest
and a live check on IWDification-supplied spells are not separately recorded; the user
approved this release based on earlier in-game testing, with any issue fixed in a follow-up.
All v0.5.0 components are unchanged.

See [release notes](docs/release-notes/v0.6.0.md).

## v0.5.0 — 2026-09-20

- Add component 420: shared EEex provider for native per-kit bard spell progression,
  with a registry and installer API for independent kit adapters.
- Add component 421: Bard/Jester use IWD progression through spell level 7;
  Blade/Skald use the original BG progression through spell level 6.
- Support Bardic Wonders component 3010 for its custom kit policy and descriptions,
  including optional Darkbloom. Preserve existing slot modifiers, caster levels,
  innate/HLA access and the shared CDTweaks table.
- Check actual EEex capabilities and a unique native hook signature. Accept the
  verified BG2EE/EET and IWDEE 2.7.3 layouts without a fixed file-offset/version gate.
- Record the user's successful BG2EE/EET check and focused offline installer/runtime
  checks. IWDEE in-game verification remains pending. Existing saved spellbooks use
  normal level-up calculations; no automatic migration is included.

See [release notes](docs/release-notes/v0.5.0.md) for installation and compatibility.

## v0.4.0 — 2026-09-16

- Add optional component 110: EEex + SCS Apex Dragons lethal melee attacks for five
  explicitly identified encounters. At SCS Dragon Hardcore/Insane, Firkraag uses
  15% / death save -4, Nizidramanii'yt and Saladrex 10% / -2, and Thaxll'ssillyia
  and the Watcher's Keep guardian 5% / -2. Game-slider fallback is Hard/Insane.
  A failed save can cause permanent death; normal resurrection cannot restore a
  chunked companion. Native gore/anti-chunking settings and plot minimum HP remain
  respected. This physical rider bypasses Death Ward and physical resistance.
- Add independent optional component 111: 18-second wing-buffet cooldown for the
  same five identities, at all SCS difficulty settings. No EEex required for 111.
- Preserve unrelated users of shared encounter scripts, dynamically resolve spell
  IDs, reject unsupported input shapes, and make repeated application byte-stable.
- Retain every v0.3.2 Tempus, SCS and ambient/urgent-readiness fix.
- Include the Windows setup executable and its WeiDU license in the release ZIP.

Native combat and existing-save acceptance remain pending. On 2026-09-16 the user
approved shipping these implemented optional candidates before the combined CEBG
installation test; the former standalone combat-before-release gate is superseded.
No automatic existing-game or save migration is included.

## v0.3.2 — 2026-09-07

- Fix component 401 on installations without Spell Revisions when Improved Haste
  delegates its doubling effect through opcode 146. Validate every child header,
  preserve both spells, and reject unsafe or ambiguous delivery.
- Recognize the existing non-SR Divine Power cleanup prefix and upgrade it to the
  Tempus cleanup while preserving its self-refresh and unrelated effects.
- Retain direct SR/additive and non-SR/doubling support, including opcode 317.
  SCS and Spell Revisions are optional for the Holy Power component family.
- Add captured base-game and SCS/no-SR regression fixtures, graph validation,
  override/KEY lookup, byte-exact rollback, and repeat-application coverage.

Validation: 281 automated tests pass with WeiDU 24900. Full installation tests use
captured resources in disposable synthetic games; live playthrough acceptance and
collection installation recovery remain separate.

## v0.3.1 — 2026-09-04

- Accept Artisan's legitimate `AP_C0PR#CL` grants in ordinary Tempus CLAB cells,
  preserving those grants while capping the late Holy Power uses.
