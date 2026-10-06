# EET elemental arrows — public component 130

Component 130 promotes the approved, tested October 3 private repair without
changing its scope. SCS 35.21's elemental-arrows component 3017 has an EET
exclusion; EET v14 keeps the BG1 arrow damage. The captured BG2 ITEMS.BIF
independently established the intended acid 1d3, cold 1d2 and fire 1d2 values.

The public adaptation requires EET and SCS general spell tweaks (2000).
AROW04 becomes 1d3 acid; AROW09 becomes 1d2 cold; AROW08/AROWKC become 1d2
fire and lose their +2 attack/physical-damage bonuses. Fire dice are written
explicitly because upstream SCS's code does not perform that advertised change.
Original save fields, SCS troll helpers and all other bytes except local
name/description pointers remain. Other special arrows, including ARROPHE2,
are outside the allowlist. English descriptions retain surrounding text.

Private source/evidence: collection
`target/work/oct03-current-game-fixes/arrows`, retained locally and not shipped.
That adapter passed real-WeiDU capture installation, idempotence, all old TLK
entry preservation, exact item uninstall and late-failure rollback before its
approved application. Public synthetic tests independently cover the four
transformations, exact byte delta, saves/helpers, exclusions, missing SCS and
malformed-last-item rollback. No new game or save was modified for publication.

This is an EET implementation of the user's chosen SCS balance rule, not a new
global item overhaul or a claim that upstream SCS 3017 now supports EET.
