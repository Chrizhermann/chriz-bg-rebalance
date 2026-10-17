"""Composition/preflight/error lifecycle; native patching is deliberately mocked."""
from pathlib import Path
import unittest

from lupa.luajit21 import LuaRuntime


ROOT = Path(__file__).resolve().parents[1]
LAB = ROOT / "research/prototypes/potion-admission/CBRPQLab.lua"
HARNESS = r'''
    labModule = dofile(labPath)
    events,diagnostics,listeners={},{},{}
    local function event(value) events[#events+1]=value end
    local function check(which)
        event("validate:"..which)
        if failValidation==which then error("signature changed:"..which) end
    end
    local function install(which)
        event("install:"..which)
        if failInstall==which then error("patch failed:"..which) end
    end
    EEex_GameState_AddDestroyedListener=function(fn) listeners[#listeners+1]=fn end
    parts={
        core={},messages={},
        native=function() return {} end,
        runtime=function()
            local r={}
            for _,key in ipairs({"useBegin","useQueue","useEnd","fireBegin","fireQueue",
                    "fireEnd","useProjectile","fireProjectile","messageEnter","messageLeave","destroy","effectDestroy","admit"}) do
                r[key]=function() end
            end
            r.disable=function(reason) diagnostics[#diagnostics+1]=reason end
            r.reset=function() event("reset") end
            return r
        end,
        hook={validate=function() check("admission") end,install=function() install("admission") end},
        transport={validate=function() check("transport") end,install=function() install("transport") end},
    }
    function prepare() return labModule.prepare(_G,parts,{},function() end) end
'''


class PotionLabCompositionTests(unittest.TestCase):
    def setUp(self):
        self.lua = LuaRuntime(unpack_returned_tuples=True)
        self.lua.globals().labPath = LAB.as_posix()
        self.lua.execute(HARNESS)

    def test_load_has_no_side_effects_and_prepare_only_validates(self):
        self.lua.execute('''
            assert(#events==0 and CBRPQ_Lab_admit==nil)
            local lab=prepare()
            assert(#events==2 and events[1]=="validate:transport" and events[2]=="validate:admission")
            assert(not lab.armed and not lab.attempted and #listeners==1)
            assert(type(CBRPQ_Lab_admit)=="function" and type(CBRPQ_Lab_reset)=="function")
            listeners[1](); assert(events[3]=="reset")
        ''')

    def test_explicit_arm_revalidates_both_sites_before_first_patch(self):
        self.lua.execute('''
            local lab=prepare(); lab.arm()
            assert(lab.armed and lab.attempted)
            assert(table.concat(events,",")=="validate:transport,validate:admission,validate:transport,validate:admission,install:transport,install:admission")
            assert(not pcall(lab.arm))
        ''')

    def test_validation_failure_removes_uninstalled_callbacks(self):
        self.lua.execute('''
            failValidation="admission"
            assert(not pcall(prepare))
            assert(CBRPQ_Lab_admit==nil and CBRPQ_Lab_reset==nil and #listeners==0)
            assert(#events==2 and #diagnostics==1)
        ''')

    def test_later_conflict_prevents_patch_attempt(self):
        self.lua.execute('''
            local lab=prepare(); failValidation="transport"
            assert(not pcall(lab.arm) and not lab.attempted)
            assert(#events==3 and #diagnostics==0)
        ''')

    def test_partial_patch_failure_disables_runtime_and_forbids_retry(self):
        self.lua.execute('''
            local lab=prepare(); failInstall="admission"
            assert(not pcall(lab.arm) and lab.attempted and not lab.armed)
            assert(#diagnostics==1 and type(CBRPQ_Lab_admit)=="function")
            local count=#events
            assert(not pcall(lab.arm) and #events==count)
        ''')

    def test_namespace_collision_and_non_global_api_are_rejected(self):
        self.lua.execute('''
            CBRPQ_Lab_reset=function() end
            assert(not pcall(prepare) and #events==0)
            CBRPQ_Lab_reset=nil
            assert(not pcall(labModule.prepare,{},parts,{},function() end))
        ''')


if __name__ == "__main__":
    unittest.main()
