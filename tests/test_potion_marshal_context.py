"""Pure native-frame observer tests; no hooks, game, or save is executed."""
from pathlib import Path
import unittest

from lupa.luajit21 import LuaRuntime

MODULE=Path(__file__).resolve().parents[1]/"research/prototypes/potion-admission/CBRPQMarshal.lua"


class MarshalContextTests(unittest.TestCase):
    def setUp(self):
        self.lua=LuaRuntime(unpack_returned_tuples=True)
        factory=self.lua.execute(MODULE.read_text())
        self.observer=factory(self.lua.eval("function(sprite) return sprite.list end"))
        self.sprite=self.lua.table_from({"list":0x20000})

    def enter(self,frame=0x10000,list_pointer=0x20000,version=1,only=0,exclude=1):
        self.observer.enter(frame,list_pointer,version,only,exclude)

    def test_exact_count_and_native_nonzero_filter_arguments_are_preserved(self):
        self.enter(version=255,only=0xFFFFFFFF,exclude=2)
        with self.assertRaisesRegex(Exception,"count is unavailable"):
            self.observer.context(self.sprite)
        self.observer.counted(0x10000,0x20000,3*0x108)
        context=self.observer.context(self.sprite)
        self.assertEqual((context.version,context.onlyTiming9,context.excludeTiming2,context.normalBytes),
                         (1,True,True,3*0x108))
        context.normalBytes=999
        self.assertEqual(self.observer.context(self.sprite).normalBytes,3*0x108)
        self.assertTrue(self.observer.leave(0x10000))
        self.assertFalse(self.observer.hasLive())

    def test_unrelated_nested_list_is_a_sentinel_and_cannot_borrow_outer_context(self):
        self.enter()
        self.observer.counted(0x10000,0x20000,0x108)
        outer=self.observer.context(self.sprite).identity
        self.enter(frame=0xF000,list_pointer=0x30000)
        self.observer.counted(0xF000,0x30000,2*0x108)
        with self.assertRaisesRegex(Exception,"not this sprite's timed list"):
            self.observer.context(self.sprite)
        with self.assertRaisesRegex(Exception,"unbalanced"):
            self.observer.leave(0x10000)
        self.observer.leave(0xF000)
        self.assertTrue(self.lua.eval("function(a,b) return rawequal(a,b) end")(
            outer,self.observer.context(self.sprite).identity))

    def test_count_rejects_other_frame_list_duplicate_and_invalid_native_size(self):
        for frame,list_pointer,bytes_count,reason in (
            (0x9999,0x20000,264,"current native frame"),
            (0x10000,0x30000,264,"different native list"),
            (0x10000,0x20000,1,"V2 aligned"),
            (0x10000,0x20000,-1,"byte count"),
            (0x10000,0x20000,2**31,"byte count")):
            with self.subTest(reason=reason):
                self.setUp(); self.enter()
                with self.assertRaisesRegex(Exception,reason):
                    self.observer.counted(frame,list_pointer,bytes_count)
        self.setUp(); self.enter()
        self.observer.counted(0x10000,0x20000,0)
        self.assertEqual(self.observer.context(self.sprite).normalBytes,0)
        with self.assertRaisesRegex(Exception,"counted twice"):
            self.observer.counted(0x10000,0x20000,0)

    def test_v1_sentinel_reset_and_old_return_cannot_publish_v2_context(self):
        self.enter(version=0)
        with self.assertRaisesRegex(Exception,"V1 marshal"):
            self.observer.counted(0x10000,0x20000,0)
        with self.assertRaisesRegex(Exception,"count is unavailable"):
            self.observer.context(self.sprite)
        self.observer.reset()
        self.assertFalse(self.observer.leave(0x10000))
        with self.assertRaisesRegex(Exception,"outside native Marshal"):
            self.observer.context(self.sprite)

    def test_reused_frame_has_a_new_identity_after_balanced_return(self):
        self.enter(); self.observer.counted(0x10000,0x20000,0)
        old=self.observer.context(self.sprite).identity
        with self.assertRaisesRegex(Exception,"already live"):
            self.enter()
        self.observer.leave(0x10000)
        self.enter(); self.observer.counted(0x10000,0x20000,0)
        self.assertFalse(self.lua.eval("function(a,b) return rawequal(a,b) end")(
            old,self.observer.context(self.sprite).identity))


if __name__=="__main__": unittest.main()
