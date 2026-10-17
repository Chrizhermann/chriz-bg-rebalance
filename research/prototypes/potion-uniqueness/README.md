# Rejected potion implementation prototype

Research only. This private-SPL architecture has known native compatibility and
guard failures. It is excluded from normal packaging and has no public TP2
components. Do not install it into a game or use it as a collection dependency.

The retained WeiDU libraries allow the failures to be reproduced in disposable
synthetic fixtures. `tests/test_potion_uniqueness_installer.py` constructs its own
research TP2; identifiers330/331 in that fixture are not public components.
The corrected model and dispel regression deliberately retain failing assertions
until the implementation is replaced. Do not mark them skipped or weaken the
expected behavior to make this draft pass.

Run the fixture suite explicitly:

```powershell
python -B -m unittest tests.test_potion_uniqueness_installer -v
```

The optional captured-profile checks copy only potion graphs into temporary
fixtures. Their previous passes do not validate engine-created fields, current
saves, external consumers or the native guard ordering. No private game resources
are stored here.

See [diagnosis](../../2026-10-09-potion-uniqueness.md) and
[handover](../../../docs/handovers/2026-10-09-potion-uniqueness.md).
