"""Compiled resource -> real reader/Lineage/Messages/Core/Runtime composition.

Native construction, delivery outcome and list insertion are explicit doubles.
The persistence dependency is a boundary double here; these cases cannot prove
native hook execution, charge use, save/load, or an armed component.
"""
from dataclasses import replace
import unittest

from tests.potion_runtime_fixture import MODULES, ResourceRuntimeFixture
from tests.test_potion_admission_manifest import compiler, fx, potion
from tests.test_potion_linked_manifest import cast
from tests.test_potion_native_reader import FIELDS
from tests.test_potion_payload_audit import container


class LinkedRuntimeFixture(ResourceRuntimeFixture):
    def load_runtime(self):
        self.lua.globals().module_folder = MODULES.as_posix()
        self.lua.execute('''
            sprite_identity={}
            persistence_boundary={
                hasLive=function() return false end,
                requireSprite=function() return sprite_identity end,
                reset=function() end,
                invalidate=function(reason) persistence_failure=reason end,
                status=function() return persistence_failure==nil,persistence_failure end,
            }
            extra={lineage=dofile(module_folder.."/CBRPQLineage.lua"),persistence=persistence_boundary}
        ''')
        return self.lua.globals().load_parts(MODULES.as_posix(), self.table(self.manifest),
                                             self.lua.globals().extra)

    def child(self, spell, ordinal=0, ability=0, scaled=1):
        data = self.spells[spell + ".SPL"]
        node = compiler.audit.parse_resource(spell + ".SPL", data)
        part = next(s for s in node["slices"] if s["kind"] == f"ability:{ability}")
        fields = compiler._fields(part["effects"][ordinal], bytes(56), strict_resource=False)
        fields.update(school=data[0x25], secondary=data[0x27],
                      sourceFlags=compiler.audit.u32(data, 0x18))
        pointer = self.allocate()
        self.put(pointer, "Q", 0x140598888)  # Stable native class service double.
        for key, (offset, fmt) in FIELDS.items():
            self.put(pointer + offset, fmt, fields[key])
        self.resref(pointer + 0x30, fields["resource"])
        self.resref(pointer + 0x94, spell)
        self.put(pointer + 0x90, "I", 1)
        self.put(pointer + 0xC8, "I", 19)
        self.put(pointer + 0xCC, "I", 1)
        self.put(pointer + 0x110, "I", 42)
        self.put(pointer + 0x150, "I", 0xFFFFFFFF)
        self.put(pointer + 0x11C, "I", fields["duration"])
        self.put(pointer + 0x28, "I", fields["duration"] * scaled)
        self.objects[pointer] = self.lua.globals().native_object(pointer)
        self.meta[pointer] = (spell, ordinal, fields)
        return pointer

    def __init__(self, items, spells):
        self.spells = spells
        super().__init__(items, read_resource=spells.__getitem__)
        self.cast_sequence = 0x800000

    def queue_cast(self, dose, ordinal=0):
        message, pointer = dose[ordinal]
        self.runtime.messageEnter(message, pointer, 0)
        self.assert_enabled()
        self.assert_not_rejected(pointer)
        self.cast_sequence += 1
        cast_message = self.cast_sequence
        self.runtime.parentQueued(self.objects[pointer], cast_message, self.sprite)
        self.runtime.messageLeave(message)
        self.runtime.destroy(message)
        self.runtime.effectDestroy(pointer)
        self.assert_enabled()
        return cast_message

    def assert_not_rejected(self, pointer):
        if self.runtime.admit(self.objects[pointer], self.sprite):
            raise AssertionError("native carrier was rejected")

    def start_cast(self, message):
        entry = message + 0x1000000
        self.runtime.castEnter(message, entry)
        return entry - 0x70

    def deliver_child(self, frame, pointer, ordinal=0, ability=0, route="queue", rejected=False):
        obj = self.objects[pointer]
        self.runtime.childCreated(frame, obj, ordinal, ability, self.sprite, self.sprite)
        self.assert_enabled()
        self.next_message += 1
        message = self.next_message
        if route == "direct":
            self.runtime.childDirectEnter(frame, pointer, 0)
        else:
            if route == "projectile":
                self.runtime.childProjectile(frame, obj, ordinal, self.projectile_pointer)
            else:
                self.runtime.childQueued(frame, message, obj, ordinal)
            self.runtime.messageEnter(message, pointer, 0)
        self.assert_enabled()
        reject = rejected or bool(self.runtime.admit(obj, self.sprite))
        self.assert_enabled()
        if not reject:
            fields = self.meta[pointer][2]
            duration = self.read(pointer + 0x28, "I")
            if fields["timing"] in (0, 10) and duration > 0:
                self.put(pointer + 0x24, "I", 4096)
                self.put(pointer + 0x28, "I", self.now + duration * (15 if fields["timing"] == 0 else 1))
                if fields["opcode"] == 18:
                    self.put(pointer + 0x48, "I", fields["special"] | 1)
                self.sprite.m_timedEffectList[len(self.sprite.m_timedEffectList) + 1] = obj
        if route == "direct":
            self.runtime.childDirectLeave(frame)
        else:
            self.runtime.messageLeave(message)
            self.runtime.destroy(message)
        if reject:
            self.runtime.effectDestroy(pointer)
        self.assert_enabled()
        return not reject

    def finish_cast(self, message):
        self.runtime.castLeave(message)
        self.runtime.castDestroy(message)
        self.assert_enabled()


class LinkedRuntimeTests(unittest.TestCase):
    def fixture(self, effects=None, aliases=False):
        effects = effects or [fx(90, 40), fx(92, 30)]
        items = {"POTN36.ITM": potion([cast("FIRST")])}
        spells = {"FIRST.SPL": container("SPL", groups=[effects])}
        if aliases:
            items["DW#PTN36.ITM"] = potion([cast("SECOND")])
            spells["SECOND.SPL"] = spells["FIRST.SPL"]
        return LinkedRuntimeFixture(items, spells)

    def run_dose(self, f, source="POTN36", spell="FIRST", routes=("queue", "direct"), scaled=1,
                 rejected=()):
        message = f.queue_cast(f.queue(source))
        frame = f.start_cast(message)
        result = []
        for ordinal, route in enumerate(routes):
            pointer = f.child(spell, ordinal, scaled=scaled)
            result.append(f.deliver_child(frame, pointer, ordinal, route=route, rejected=ordinal in rejected))
        f.finish_cast(message)
        self.assertFalse(f.runtime.hasDelivery())
        return result

    def test_alias_repeat_refreshes_native_originals_without_source_or_caster_rewrite(self):
        f = self.fixture(aliases=True)
        self.assertEqual([True, True], self.run_dose(f, scaled=2))
        before = {p: f.bytes(p) for p in f.effects()}
        f.now += 75
        self.assertEqual([False, False], self.run_dose(f, "DW#PTN36", "SECOND",
                                                    routes=("projectile", "queue"), scaled=2))
        self.assertEqual(2, len(f.writes))
        for p, image in before.items():
            self.assertEqual(1000 + 75 + 600 * 2 * 15, f.read(p + 0x28, "I"))
            after = f.bytes(p)
            self.assertEqual(image[:0x28] + image[0x2C:], after[:0x28] + after[0x2C:])
            self.assertEqual(19, f.read(p + 0xC8, "I"))
            self.assertEqual(b"FIRST\0\0\0", after[0x94:0x9C])

    def test_ordinary_cast_of_same_spell_never_acquires_potion_ownership(self):
        f = self.fixture()
        pointer = f.child("FIRST")
        message = 900
        frame = f.start_cast(message)
        self.assertTrue(f.deliver_child(frame, pointer))
        f.finish_cast(message)
        self.assertIsNone(f.reader.identify(f.objects[pointer], None, False))
        self.assertEqual([True, True], self.run_dose(f))
        self.assertEqual([], f.writes)
        self.assertEqual(3, len(f.effects()))

    def test_hp_and_constitution_packages_ignore_repeat_without_any_write(self):
        for effects in ([fx(18, 10), fx(54, 90, parameter2=2)],
                        [fx(10, 3, parameter2=1), fx(44, 25, parameter2=1)]):
            with self.subTest(opcode=effects[0].opcode):
                f = self.fixture(effects, aliases=True)
                self.assertEqual([True, True], self.run_dose(f))
                before = {p: f.bytes(p) for p in f.effects()}
                f.now += 20
                self.assertEqual([False, False], self.run_dose(f, "DW#PTN36", "SECOND"))
                self.assertEqual(before, {p: f.bytes(p) for p in f.effects()})
                self.assertEqual([], f.writes)
                for pointer in list(f.effects()):
                    f.remove(pointer)
                self.assertEqual([True, True], self.run_dose(f))

    def test_native_rejection_leaves_only_the_admitted_sibling_refreshed(self):
        f = self.fixture()
        self.run_dose(f)
        first, second = f.effects()
        f.now += 50
        self.assertEqual([False, False], self.run_dose(f, rejected={0}))
        self.assertEqual(10000, f.read(first + 0x28, "I"))
        self.assertEqual(10050, f.read(second + 0x28, "I"))
        self.assertEqual(1, len(f.writes))

    def test_queued_child_cancellation_retires_tag_before_pointer_reuse(self):
        f = self.fixture()
        message = f.queue_cast(f.queue("POTN36"))
        frame = f.start_cast(message)
        pointer = f.child("FIRST")
        f.runtime.childCreated(frame, f.objects[pointer], 0, 0, f.sprite, f.sprite)
        f.runtime.childQueued(frame, 900, f.objects[pointer], 0)
        f.finish_cast(message)
        self.assertTrue(f.runtime.hasDelivery())
        f.runtime.destroy(900)
        f.runtime.effectDestroy(pointer)
        self.assertFalse(f.runtime.hasDelivery())
        self.assertIsNone(f.reader.identify(f.objects[pointer], None, False))
        self.assertEqual([True, True], self.run_dose(f))

    def test_unrun_cast_cancellation_does_not_leave_a_dose_or_adopt_other_cast(self):
        f = self.fixture()
        message = f.queue_cast(f.queue("POTN36"))
        self.assertTrue(f.runtime.hasDelivery())
        f.runtime.castDestroy(message)
        self.assertFalse(f.runtime.hasDelivery())
        frame = f.start_cast(message)
        pointer = f.child("FIRST")
        self.assertTrue(f.deliver_child(frame, pointer))
        f.finish_cast(message)
        self.assertIsNone(f.reader.identify(f.objects[pointer], None, False))

    def test_pending_cast_prevents_reset_from_silently_forgetting_delivery(self):
        f = self.fixture()
        f.queue_cast(f.queue("POTN36"))
        f.runtime.reset()
        self.assertFalse(f.runtime.status()[0])
        self.assertIn("surviving potion delivery", f.diagnostics[-1])
        self.assertIn("surviving potion delivery", f.lua.globals().persistence_failure)

    def test_queued_child_cannot_cross_sprite_reuse_or_content_reset_after_cast_return(self):
        for changed in ("allocation", "contents"):
            with self.subTest(changed=changed):
                f = self.fixture()
                message = f.queue_cast(f.queue("POTN36"))
                frame = f.start_cast(message)
                pointer = f.child("FIRST")
                f.runtime.childCreated(frame, f.objects[pointer], 0, 0, f.sprite, f.sprite)
                f.runtime.childQueued(frame, 999, f.objects[pointer], 0)
                f.finish_cast(message)
                if changed == "allocation":
                    f.lua.execute("sprite_identity={}")
                else:
                    f.runtime.onSpriteContentsInvalidated(f.sprite_pointer, f.lua.globals().sprite_identity)
                f.runtime.messageEnter(999, pointer, 0)
                f.runtime.admit(f.objects[pointer], f.sprite)
                self.assertFalse(f.runtime.status()[0])
                self.assertIn("target allocation/contents changed", f.diagnostics[-1])
                self.assertEqual([], f.writes)

    def test_new_dose_after_quiescent_contents_clear_uses_new_epoch(self):
        f = self.fixture()
        self.run_dose(f)
        f.runtime.onSpriteContentsInvalidated(f.sprite_pointer, f.lua.globals().sprite_identity)
        for pointer in list(f.effects()):
            f.remove(pointer)
        self.assertEqual([True, True], self.run_dose(f))
        self.assertEqual([], f.writes)

    def test_pending_cast_remembers_target_allocation_before_first_child_construction(self):
        f = self.fixture()
        message = f.queue_cast(f.queue("POTN36"))
        f.lua.execute("sprite_identity={}")
        frame = f.start_cast(message)
        pointer = f.child("FIRST")
        f.runtime.childCreated(frame, f.objects[pointer], 0, 0, f.sprite, f.sprite)
        self.assertFalse(f.runtime.status()[0])
        self.assertIn("target allocation changed", f.diagnostics[-1])
        self.assertIsNone(f.reader.identify(f.objects[pointer], None, False))

    def test_changed_projectile_or_native_child_fields_disables_before_mutating_bonuses(self):
        for mutation in ("projectile", "source", "amount"):
            with self.subTest(mutation=mutation):
                f = self.fixture()
                self.run_dose(f)
                message = f.queue_cast(f.queue("POTN36"))
                frame = f.start_cast(message)
                pointer = f.child("FIRST")
                if mutation == "source":
                    f.resref(pointer + 0x94, "OTHER")
                if mutation == "amount":
                    f.put(pointer + 0x1C, "i", 999)
                f.runtime.childCreated(frame, f.objects[pointer], 0, 0, f.sprite, f.sprite)
                if mutation == "projectile":
                    f.put(f.projectile_pointer, "Q", 0x140598888)
                    f.runtime.childProjectile(frame, f.objects[pointer], 0, f.projectile_pointer)
                self.assertFalse(f.runtime.status()[0])
                self.assertEqual([], f.writes)

    def test_original_direct_bonus_and_linked_sibling_share_one_hp_dose(self):
        f = LinkedRuntimeFixture({"POTN09.ITM": potion([fx(18, 10), cast("CHILD")])},
                                 {"CHILD.SPL": container("SPL", groups=[[fx(54, 90, parameter2=2)]])})
        for repeated in (False, True):
            queued = f.queue("POTN09")
            self.assertEqual([not repeated], f.deliver([queued[0]]))
            message = f.queue_cast(queued, 1)
            frame = f.start_cast(message)
            pointer = f.child("CHILD")
            self.assertEqual(not repeated, f.deliver_child(frame, pointer))
            f.finish_cast(message)
        self.assertEqual(2, len(f.effects()))
        self.assertEqual([], f.writes)

    def test_nested_direct_carrier_can_cast_without_becoming_an_owned_bonus(self):
        f = LinkedRuntimeFixture({"POTN36.ITM": potion([cast("OUTER")])},
                                 {"OUTER.SPL": container("SPL", groups=[[cast("INNER")]]),
                                  "INNER.SPL": container("SPL", groups=[[fx(90, 40)]])})
        for repeat in (False, True):
            outer = f.queue_cast(f.queue("POTN36"))
            outer_frame = f.start_cast(outer)
            pointer = f.child("OUTER")
            obj = f.objects[pointer]
            f.runtime.childCreated(outer_frame, obj, 0, 0, f.sprite, f.sprite)
            f.runtime.childDirectEnter(outer_frame, pointer, 0)
            f.assert_not_rejected(pointer)
            f.cast_sequence += 1
            inner = f.cast_sequence
            f.runtime.parentQueued(obj, inner, f.sprite)
            inner_frame = f.start_cast(inner)
            child = f.child("INNER")
            self.assertEqual(not repeat, f.deliver_child(inner_frame, child, route="direct"))
            f.finish_cast(inner)
            f.runtime.childDirectLeave(outer_frame)
            f.runtime.effectDestroy(pointer)
            f.finish_cast(outer)
            self.assertFalse(f.runtime.hasDelivery())
        self.assertEqual(1, len(f.effects()))
        self.assertEqual(1, len(f.writes))


if __name__ == "__main__":
    unittest.main()
