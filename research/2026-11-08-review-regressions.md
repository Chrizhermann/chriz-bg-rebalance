# Four integration regressions reviewed at 0b69d6d

The independent review identified four defects, confirmed against current source.
This correction changes no balance choices or native hook policy.

1. SR's SPWI608C and SPWI903C use opcode 230/19 to consume Spell Shield.
   sr_antimagic.tpa recognized 221/19 and treated every 230 as Pierce Magic's
   offensive payload. Tests used the same wrong opcode. Captured helpers under
   tests/fixtures/sr_antimagic preserve the actual one-ability shape and casting
   hooks, with provenance hashes. Only offensive delivery receives our package.
2. Component 100 called ADD_SPELL_EFFECT on non-normalized nonempty resources.
   WeiDU 249 does not update 0x6e when ability insertion precedes casting effects.
   Normalize independent slices before insertion; retain casting and foreign
   effects, including shared or reversed storage and repeated application.
3. Item links were treated as ownership of the item's complete text. Restrict
   complete descriptions to the named scrolls and Wand of Spell Striking. Other
   callers keep their own identity, abilities and both descriptions. Only the
   invoked spell changes; there is no invented Breach charge in their item text.
4. Readiness unconditionally excluded WIZARD_IMPROVED_MANTLE as SR's MoP.
   The symbol can still be a genuine weapon protection. Determine that capability
   from the resolved resource and preserve the runtime's existing selection rule.

All execution uses disposable fixtures. No reference installation or save is
modified, and automated tests do not establish native Spell Shield behavior.


Validation on the final source: `python -B -m unittest discover -s tests -q`
ran 957 tests in 723.157s: 931 passed, 26 private-capture skips, no failures or
errors. Both changed libraries and the public setup parsed with WeiDU 249.
The real shield helper bytes stay unchanged; casting slices and foreign ability
effects survive insertion and repeat application; custom item descriptions and
abilities stay unchanged under public/tail installs; the generated readiness
runtime selects genuine Improved Mantle with or without SCS. SR's MoP remains
outside the weapon-protection ladder. See `work/review-0b69d6d/` for logs.
