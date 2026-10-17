"""Failure ordering through the actual EEex reader and inert save composition.

All memory and native list operations are bounded service doubles. No game,
DLL, installed resource or save is executed or modified. Errors diagnose an
unsupported import; these tests do not claim native load rollback.
"""
import unittest

from tests import test_potion_saved_eeex as serializer_fixture

BASE, EEEX = serializer_fixture.BASE, serializer_fixture.EEEX


@unittest.skipUnless(EEEX, "set EEEX_LUA_DIR for the actual EEex Lua serializer")
class SaveImportFailureTests(unittest.TestCase):
    def fixture(self, corrupt=None):
        fixture = serializer_fixture.PotionSavedEEexTests()
        original_read = fixture.read
        self.corrupted = False
        prepared = False

        def read(address, fmt):
            nonlocal prepared
            # Mutate only the newly serialized, synthetic footer immediately
            # before its first bounded pre-parser read. Setup effect reads must
            # retain the ordinary fixture behavior.
            if (not prepared and fixture.lua.globals()[b"imported"] is not None
                    and address == fixture.lua.globals()[b"footer"]):
                prepared = True
                # Replace the helper's unexpected-failure assertion only for
                # this explicit failure test. Preserve the current native input
                # context while disabling ownership and retiring its bindings.
                fixture.lua.execute(b'''
                    invalidated={}; ownershipDisabled=false
                    inputContext.invalidate=function(reason)
                        invalidated[#invalidated+1]=reason
                        invalidatedBeforeForeign=foreignCalls
                        ownershipDisabled=true
                        native.resetTokens()
                    end
                ''')
                if corrupt is not None:
                    self.corrupted = True
                    corrupt(fixture, int(address) - BASE)
            return original_read(address, fmt)

        fixture.read = read
        fixture.setUp()
        return fixture

    def assert_no_foreign_import_or_owner(self, fixture):
        fixture.lua.execute(b'''
            assert(foreignCalls==0 and #ignoredErrors==0)
            assert(native.identify(potion,nil,false)==nil)
            assert(native.identify(foreign,nil,false)==nil)
        ''')

    def test_bad_footer_signature_fails_before_foreign_importers(self):
        fixture = self.fixture(lambda h, offset: h.memory.__setitem__(offset, 0))
        with self.assertRaisesRegex(Exception, "signature"):
            fixture.composed_native_import(b"")
        self.assertTrue(self.corrupted)
        self.assert_no_foreign_import_or_owner(fixture)

    def test_footer_must_occupy_the_final_native_interval_before_any_importer(self):
        def truncate(h, offset):
            self.assertGreater(h.lua.globals()[b"input_size"] - 2 * 0x108, 0x108)
            # Keep the real signature, but close its table immediately. The
            # parsed one-record footer no longer fills the native input range.
            h.memory[offset + 8] = 0

        fixture = self.fixture(truncate)
        with self.assertRaisesRegex(Exception, "final native input block"):
            fixture.composed_native_import(b"")
        self.assertTrue(self.corrupted)
        self.assert_no_foreign_import_or_owner(fixture)

    def test_invalid_schema_disables_ownership_before_foreign_importers_continue(self):
        def invalid_schema(h, offset):
            key = h.memory.index(b"version\0", offset)
            value_type = key + len(b"version\0")
            self.assertIn(h.memory[value_type], (3, 4))  # actual EEex int8 encoding
            h.memory[value_type + 1] = 99

        fixture = self.fixture(invalid_schema)
        consumed = fixture.composed_native_import(b'''
            assert(ownershipDisabled and invalidatedBeforeForeign==0)
            assert(native.identify(potion,nil,false)==nil)
        ''')
        self.assertGreater(consumed, 0)
        self.assertTrue(self.corrupted)
        fixture.lua.execute(b'''
            assert(foreignCalls==1 and #ignoredErrors==0 and #invalidated==1)
            assert(invalidated[1]:find('unsupported schema',1,true))
            assert(native.identify(potion,nil,false)==nil)
            assert(native.identify(foreign,nil,false)==nil)
        ''')

    def test_foreign_importer_removing_owner_handler_is_not_silent_success(self):
        fixture = self.fixture()
        with self.assertRaisesRegex(Exception, "handler failed, disappeared, or changed"):
            fixture.composed_native_import(b"EEex_Sprite_Private_MarshalHandlers.CBRPQ=nil")
        fixture.lua.execute(b"assert(foreignCalls==1 and #ignoredErrors==0)")

    def test_stock_tryignore_cannot_hide_changed_owner_handler_data(self):
        fixture = self.fixture()
        with self.assertRaisesRegex(Exception, "handler failed, disappeared, or changed"):
            fixture.composed_native_import(b'''
                EEex_Sprite_Private_MarshalHandlers.CBRPQ.importer=function(sprite,data)
                    data.version=99
                    imported.importer(sprite,data)
                end
            ''')
        fixture.lua.execute(b'''
            assert(foreignCalls==1 and #ignoredErrors==1)
            assert(ignoredErrors[1]:find('data/order changed',1,true))
        ''')


if __name__ == "__main__":
    unittest.main()
