# Changelog

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
