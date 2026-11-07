# Spell Shield helper fixtures

Read-only copies of SR 4.19 helpers with installed SCS casting hooks, inspected
2026-11-08. These are resource-format evidence from the historical reference,
not a native-engine acceptance test. Tests bind them to arbitrary child names.

Both files have one ability (minimum level 1, target 1, projectile 1) containing
only opcode 230: parameter1=9, parameter2=19, target=2, timing=1, resist_dispel=0.
Their two casting effects are opcode 146 DW#BLHDA and opcode 321 DW#HDANI.
Pierce Magic has level 6/casting speed 6; Spellstrike has level 9/speed 5.

| Source resource | SHA-256 |
| --- | --- |
| SPWI608C.SPL | 637fb7fb828b8cbd9701c9eb9e67ae11f82edab029ce3fc30ca5ac73e0a322db |
| SPWI903C.SPL | a6d6917d68d66fb3be4d948dd262364d2ed3e4b8b11a5ba378ab69faae88aafc |

Original mechanics are by Spell Revisions (Demivrgvs/G3); casting hooks are by
Sword Coast Stratagems (DavidW). No reference game is needed to run these tests.
