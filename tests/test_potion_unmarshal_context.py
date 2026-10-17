"""Pure native Unmarshal-context tests with bounded lifetime-reader doubles.

No native hooks, game, DLL, installed resource or save is executed or modified.
The list reader is responsible for validating the native sprite/list relation;
this context module must forward exact pointers and preserve its returned order.
"""
from pathlib import Path
import unittest

from lupa.luajit21 import LuaRuntime

MODULE = Path(__file__).resolve().parents[1] / "research/prototypes/potion-admission/CBRPQUnmarshal.lua"
FRAME, LIST, SPRITE, DATA = 0x10000, 0x20000, 0x30000, 0x40000


class UnmarshalContextTests(unittest.TestCase):
    def setUp(self):
        self.lua = LuaRuntime(unpack_returned_tuples=True)
        self.lua.execute('''
            originalA={}; originalB={}; prefix={originalA,originalB}
            baselineCalls=0; pointerCalls=0
            baseline=function(list,sprite)
                baselineCalls=baselineCalls+1
                assert(list==0x20000 and sprite==0x30000,"reader rejects foreign sprite/list pair")
                if failBaseline then error("native list read failed") end
                return prefix
            end
            spritePointer=function(sprite)
                pointerCalls=pointerCalls+1
                return sprite.pointer
            end
        ''')
        self.observer = self.lua.execute(MODULE.read_text())(
            self.lua.globals().baseline, self.lua.globals().spritePointer)
        self.sprite = self.lua.table_from({"pointer": SPRITE})
        self.same = self.lua.eval("function(a,b) return rawequal(a,b) end")

    def enter(self, *, frame=FRAME, list_pointer=LIST, data=DATA,
              size=3 * 0x108, sprite=SPRITE, version=1):
        self.observer.enter(frame, list_pointer, data, size, sprite, version)

    def context(self, memory=DATA + 0x108, sprite=None):
        return self.observer.context(self.sprite if sprite is None else sprite, memory)

    def test_nonempty_baseline_is_an_ordered_lifetime_snapshot_not_a_live_array(self):
        self.enter(version=255)
        context = self.context()
        self.assertEqual((1, DATA, 3 * 0x108), (context.version, context.data, context.size))
        self.assertEqual(2, len(context.baseline))
        self.assertTrue(self.same(context.baseline[1], self.lua.globals().originalA))
        self.assertTrue(self.same(context.baseline[2], self.lua.globals().originalB))
        # Mutating either the reader's array or a returned context cannot reorder
        # the stored native baseline; the opaque lifetime tokens remain shared.
        self.lua.execute("prefix[1]=originalB; prefix[2]=originalA; prefix[3]={}")
        context.baseline[1] = self.lua.table()
        context.data, context.size, context.version = 9, 1, 0
        fresh = self.context()
        self.assertTrue(self.same(fresh.baseline[1], self.lua.globals().originalA))
        self.assertTrue(self.same(fresh.baseline[2], self.lua.globals().originalB))
        self.assertEqual(2, len(fresh.baseline))
        self.assertEqual((1, DATA, 3 * 0x108), (fresh.version, fresh.data, fresh.size))
        self.assertTrue(self.same(context.identity, fresh.identity))
        self.assertEqual(1, self.lua.globals().baselineCalls)

    def test_empty_baseline_is_valid_and_noncanonical_version_is_normalized(self):
        self.lua.execute("prefix={}")
        self.enter(version=7)
        self.assertEqual(0, len(self.context().baseline))
        self.assertEqual(1, self.context().version)
        self.assertTrue(self.observer.leave(FRAME))
        self.assertFalse(self.observer.hasLive())
        self.assertIsNone(self.context())

    def test_nested_projectile_and_v1_sentinels_do_not_borrow_outer_identity(self):
        self.enter()
        outer = self.context().identity
        self.enter(frame=FRAME - 0x100, list_pointer=0x50000, sprite=0, version=1)
        # Sentinel paths must not even ask the sprite-pointer/baseline readers.
        self.assertIsNone(self.observer.context(None, DATA))
        self.enter(frame=FRAME - 0x200, list_pointer=0x60000, sprite=0x70000, version=0)
        self.assertIsNone(self.observer.context(None, DATA))
        self.assertEqual(1, self.lua.globals().baselineCalls)
        self.assertEqual(1, self.lua.globals().pointerCalls)
        with self.assertRaisesRegex(Exception, "unbalanced"):
            self.observer.leave(FRAME)
        self.assertTrue(self.observer.leave(FRAME - 0x200))
        self.assertIsNone(self.observer.context(None, DATA))
        self.assertTrue(self.observer.leave(FRAME - 0x100))
        self.assertTrue(self.same(outer, self.context().identity))
        self.assertTrue(self.observer.leave(FRAME))

    def test_wrong_frame_list_and_sprite_fail_without_corrupting_live_context(self):
        self.enter()
        identity = self.context().identity
        with self.assertRaisesRegex(Exception, "already live"):
            self.enter()
        self.assertEqual(1, self.lua.globals().baselineCalls)
        for values in ({"frame": FRAME - 0x100, "list_pointer": LIST + 1},
                       {"frame": FRAME - 0x100, "sprite": SPRITE + 1}):
            with self.subTest(values=values):
                with self.assertRaisesRegex(Exception, "reader rejects foreign sprite/list pair"):
                    self.enter(**values)
                self.assertTrue(self.same(identity, self.context().identity))
        with self.assertRaisesRegex(Exception, "different sprite"):
            self.context(sprite=self.lua.table_from({"pointer": SPRITE + 1}))
        self.assertFalse(self.observer.leave(FRAME + 0x100))
        self.assertTrue(self.same(identity, self.context().identity))

    def test_metadata_interval_is_half_open_and_zero_size_cannot_contain_footer(self):
        self.enter()
        self.assertIsNotNone(self.context(DATA))
        self.assertIsNotNone(self.context(DATA + 3 * 0x108 - 1))
        for memory in (DATA - 1, DATA + 3 * 0x108, DATA + 0.5, float("nan"), float("inf")):
            with self.subTest(memory=memory):
                with self.assertRaisesRegex(Exception, "metadata pointer"):
                    self.context(memory)
        self.observer.reset()
        self.enter(data=0, size=0)
        with self.assertRaisesRegex(Exception, "metadata pointer"):
            self.context(0)
        # Record alignment/footer-last are intentionally validated downstream
        # against this interval, not guessed from a pointer inside it.

    def test_invalid_native_arguments_do_not_publish_context(self):
        cases = ({"frame": 0}, {"frame": 1.5}, {"list_pointer": 0}, {"data": -1},
                 {"size": -1}, {"size": 2**32}, {"sprite": -1}, {"version": 256},
                 {"version": 1.5}, {"data": 2**53 - 1, "size": 1})
        for values in cases:
            with self.subTest(values=values):
                with self.assertRaisesRegex(Exception, "invalid|overflows exact pointer range"):
                    self.enter(**values)
                self.assertFalse(self.observer.hasLive())
                self.assertIsNone(self.context())
        self.assertEqual(0, self.lua.globals().baselineCalls)

    def test_malformed_sparse_duplicate_or_failed_prefix_leaves_outer_context_intact(self):
        self.enter()
        identity = self.context().identity
        for expression, reason in (("nil", "missing original list prefix"),
                                   ("7", "missing original list prefix"),
                                   ("{originalA,originalA}", "duplicate prefix lifetime"),
                                   ("{[1]=originalA,[3]=originalB}", "sparse native prefix"),
                                   ("{[2]=originalA}", "sparse native prefix"),
                                   ("{originalA, extra=originalB}", "sparse native prefix"),
                                   ("{[0]=originalA}", "sparse native prefix"),
                                   ("{[1.5]=originalA}", "sparse native prefix")):
            with self.subTest(expression=expression):
                self.lua.execute("prefix=" + expression)
                with self.assertRaisesRegex(Exception, reason):
                    self.enter(frame=FRAME - 0x100)
                self.assertTrue(self.same(identity, self.context().identity))
                self.assertFalse(self.observer.leave(FRAME - 0x100))
        self.lua.execute("prefix={}; failBaseline=true")
        with self.assertRaisesRegex(Exception, "native list read failed"):
            self.enter(frame=FRAME - 0x100)
        self.assertTrue(self.same(identity, self.context().identity))

    def test_balanced_reused_frames_get_fresh_context_identities(self):
        self.enter()
        old = self.context().identity
        self.assertTrue(self.observer.leave(FRAME))
        self.assertFalse(self.observer.leave(FRAME))
        self.enter()
        self.assertFalse(self.same(old, self.context().identity))
        self.observer.reset()
        self.enter()
        self.assertFalse(self.same(old, self.context().identity))

    def test_reset_discards_nested_contexts_and_stale_returns_cannot_pop_new_frame(self):
        self.enter()
        self.enter(frame=FRAME - 0x100, sprite=0)
        self.observer.reset()
        self.assertFalse(self.observer.hasLive())
        self.assertIsNone(self.context())
        self.assertFalse(self.observer.leave(FRAME - 0x100))
        self.assertFalse(self.observer.leave(FRAME))
        self.enter(frame=FRAME - 0x200)
        fresh = self.context().identity
        self.assertFalse(self.observer.leave(FRAME))
        self.assertTrue(self.same(fresh, self.context().identity))
        self.assertTrue(self.observer.leave(FRAME - 0x200))


if __name__ == "__main__":
    unittest.main()
