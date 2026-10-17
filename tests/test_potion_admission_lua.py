"""Offline policy/commit tests for the isolated original-effect Lua prototype.

These execute the real Lua core in LuaJIT, with write-audited mock native
objects. They do not model CheckAdd/CheckSave, hook placement, assembly/register
safety, dose-token acquisition, native duration normalization or save/load.
The native admission gate needs independent version-pinned evidence. The older
private-SPL research regressions remain unchanged and intentionally failing.
"""
from pathlib import Path
import unittest

from lupa.luajit21 import LuaRuntime


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "research/prototypes/potion-admission/CBRPQCore.lua"

HARNESS = r'''
    core = dofile(module_path)
    writes, nativeCalls, writeEnabled = {}, 0, false
    local backing = {}
    function native(duration, tag)
        local data = {
            m_duration=duration, m_sourceType=2, m_sourceRes=tag or "POTN36",
            m_casterLevel=10, m_effectAmount=40, m_effectAmount2=0,
            m_flags=1, m_firstCall=1, m_done=false, opaque="untouched",
        }
        local object = setmetatable({}, {
            __index=data,
            __newindex=function(object, key, value)
                assert(writeEnabled, "planning attempted a native write")
                assert(key == "m_duration", "changed native metadata: " .. tostring(key))
                writes[#writes+1] = {object=object, key=key, value=value}
                data[key] = value
            end,
        })
        backing[object] = data
        return object
    end
    function forceExpiry(object, expiry)
        backing[object].m_duration = expiry -- test-only concurrent-change simulation
    end
    function record(source, key, expiry, timing, object)
        return {object=object or native(expiry, source), sourceType=2,
                source=source, key=key, expiry=expiry, timing=timing or 4096, done=false}
    end
    function commit(plan)
        writeEnabled = true
        local ok, allow, state = pcall(core.commit, plan)
        writeEnabled = false
        assert(ok, allow)
        return allow, state
    end
    function commitFails(plan)
        local count = #writes
        writeEnabled = true
        local ok, error = pcall(core.commit, plan)
        writeEnabled = false
        assert(not ok, "invalid/stale plan was committed")
        assert(#writes == count, "failed commit partially mutated native objects")
        return error
    end
    function snapshot(value, seen)
        if type(value) ~= "table" then return type(value) .. ":" .. tostring(value) end
        seen = seen or {}
        if seen[value] then return "ref:" .. seen[value] end
        seen[value] = tostring(value)
        if backing[value] then return "native:" .. tostring(value) .. snapshot(backing[value], seen) end
        local keys, parts = {}, {}
        for key in pairs(value) do keys[#keys+1] = key end
        table.sort(keys, function(a,b) return tostring(a) < tostring(b) end)
        for _,key in ipairs(keys) do
            parts[#parts+1] = snapshot(key, seen) .. "=" .. snapshot(value[key], seen)
        end
        return "{" .. table.concat(parts, ";") .. "}"
    end
    function plan(incoming, active, manifest, now, state)
        local input = {incoming, active, manifest, state}
        local before, count = snapshot(input), #writes
        local result = core.plan(incoming, active, manifest, now, state)
        assert(snapshot(input) == before, "plan mutated an input")
        assert(#writes == count, "plan mutated native state")
        assert(type(result.allow) == "boolean" and type(result.reason) == "string")
        return result
    end
    function planFails(incoming, active, manifest, now, state)
        local input = {incoming, active, manifest, state}
        local before, count = snapshot(input), #writes
        local ok, error = pcall(core.plan, incoming, active, manifest, now, state)
        assert(not ok, "malformed or ambiguous input was accepted")
        assert(snapshot(input) == before, "failed plan mutated an input")
        assert(#writes == count, "failed plan wrote native state")
        return error
    end
    function forbidden()
        nativeCalls = nativeCalls + 1
        error("core called an engine mutation API")
    end
    EEex_ApplyEffect, EEex_Sprite_ApplyEffect, EEex_Sprite_RemoveEffects = forbidden, forbidden, forbidden
    manifest = {
        policy="unique",
        sources={
            POTN36={family="thievery",keys={PICK=true,LOCK=true}},
            ["DW#PTN36"]={family="thievery",keys={PICK=true,LOCK=true}},
            POTN09={family="heroism",keys={HP=true,THAC0=true}},
            ["DW#PTN09"]={family="heroism",keys={HP=true,THAC0=true}},
            POTN41={family="power",keys={HP=true,THAC0=true}},
            POTN29={family="genius",keys={INT=true}},
            POTN37={family="focus",keys={INT=true,DEX=true}},
        },
        families={
            thievery={hp=false,genius=false}, heroism={hp=true,genius=false},
            power={hp=true,genius=false}, genius={hp=false,genius=true},
            focus={hp=false,genius=false},
        },
    }
'''


class PotionAdmissionLuaTests(unittest.TestCase):
    def setUp(self):
        self.lua = LuaRuntime(unpack_returned_tuples=True)
        self.lua.globals().module_path = SOURCE.as_posix()
        self.lua.execute(HARNESS)

    def tearDown(self):
        self.assertEqual(0, self.lua.globals().nativeCalls)

    def run_lua(self, source):
        self.lua.execute(source)

    def test_linked_owner_refreshes_only_proven_potion_record_without_changing_spell_identity(self):
        self.run_lua(r'''
            manifest.sources.POTN36.records={PICK={nativeSourceType=1,nativeSource="SHARED"}}
            local old=record("SHARED","PICK",150)
            old.sourceType,old.ownerSource,old.identity=1,"POTN36",{}
            local foreign=record("SHARED","PICK",150); foreign.sourceType=1
            local incoming=record("SHARED","PICK",9,0)
            incoming.sourceType,incoming.ownerSource,incoming.identity=1,"POTN36",{}
            local before=snapshot(incoming)
            local result=plan(incoming,{foreign,old},manifest,100,core.newDose({},"thievery",{PICK=1}))
            assert(not commit(result) and old.object.m_duration==235 and foreign.object.m_duration==150)
            assert(snapshot(incoming)==before and #writes==1)
        ''')

    def test_linked_hp_repeat_and_foreign_spell_preserve_same_family_policy(self):
        self.run_lua(r'''
            manifest.sources.POTN09.records={HP={nativeSourceType=1,nativeSource="SHARED"}}
            local old=record("SHARED","HP",150)
            old.sourceType,old.ownerSource,old.identity=1,"POTN09",{}
            local incoming=record("SHARED","HP",6,0)
            incoming.sourceType,incoming.ownerSource,incoming.identity=1,"POTN09",{}
            local result=plan(incoming,{old},manifest,100,core.newDose({},"heroism",{HP=1}))
            assert(not commit(result) and old.object.m_duration==150 and #writes==0)
            old.ownerSource=nil
            result=plan(incoming,{old},manifest,100,core.newDose({},"heroism",{HP=1}))
            assert(commit(result) and #writes==0)
        ''')

    def test_linked_owner_mismatch_is_diagnosed_before_writes(self):
        self.run_lua(r'''
            manifest.sources.POTN36.records={PICK={nativeSourceType=1,nativeSource="SHARED"}}
            local incoming=record("WRONG","PICK",6,0)
            incoming.sourceType,incoming.ownerSource,incoming.identity=1,"POTN36",{}
            assert(planFails(incoming,{},manifest,100,core.newDose({},"thievery",{PICK=1}))
                :find("linked owner",1,true))
            incoming.source="SHARED"; incoming.sourceType=2
            assert(planFails(incoming,{},manifest,100,core.newDose({},"thievery",{PICK=1}))
                :find("linked potion ownership",1,true))
        ''')

    def test_recycled_address_is_matched_as_a_fresh_live_replacement_not_the_old_snapshot(self):
        self.run_lua(r'''
            local old = record("POTN36", "PICK", 150)
            old.identity = {}
            local lock = record("POTN36", "LOCK", 150)
            lock.identity = {}
            local state = core.newDose("dose", "thievery", {PICK=1,LOCK=1})
            local first = plan(record("POTN36","LOCK",6,0), {old,lock}, manifest,100,state)
            local _,nextState = commit(first)
            -- Same userdata/native address and semantics, new lifetime token.
            -- A destructor hook invalidates the old token before reuse.
            forceExpiry(old.object,170)
            local replacement = record("POTN36","PICK",170,4096,old.object)
            replacement.identity = {}
            local second = plan(record("POTN36","PICK",6,0), {replacement,lock},
                manifest,100,nextState)
            assert(not second.allow and #second.refresh==1)
            assert(second.refresh[1].oldExpiry==170)
            assert(second.state.refreshed[replacement.identity] and not second.state.refreshed[old.identity])
            commit(second)
            assert(old.object.m_duration==190)
        ''')

    def test_first_effect_keeps_the_original_object_and_every_native_field(self):
        self.run_lua(r'''
            local incoming = record("POTN36", "PICK", 6, 0)
            local before = snapshot(incoming)
            local result = plan(incoming, {}, manifest, 100, core.newDose("dose1", "thievery", {PICK=1}))
            assert(result.allow and #result.refresh == 0)
            assert(commit(result) == true)
            assert(snapshot(incoming) == before and #writes == 0)
        ''')

    def test_hp_portrait_is_rejected_with_package_but_cannot_prolong_repeat_lock(self):
        self.run_lua(r'''
            manifest.sources.POTN09.keys.ICON = true
            manifest.sources.POTN09.nonBlockingKeys = {ICON=true}
            manifest.sources["DW#PTN09"].keys.OTHER_ICON = true
            manifest.sources["DW#PTN09"].nonBlockingKeys = {OTHER_ICON=true}
            for _,firstKey in ipairs({"HP", "OTHER_ICON"}) do
                local secondKey = firstKey == "HP" and "OTHER_ICON" or "HP"
                for _,liveBonus in ipairs({false,true}) do
                    local icon = record("POTN09","ICON",900)
                    local active = {icon}
                    if liveBonus then active[#active+1] = record("POTN09","THAC0",500) end
                    local state = core.newDose({},"heroism",{HP=1,OTHER_ICON=1})
                    for _,key in ipairs({firstKey,secondKey}) do
                        local incoming = record("DW#PTN09",key,60,0)
                        local result = plan(incoming,active,manifest,100,state)
                        assert(result.allow == not liveBonus and #result.refresh == 0)
                        local allow; allow,state = commit(result)
                        if allow then
                            incoming.timing, incoming.expiry = 4096, 1000
                            active[#active+1] = incoming
                        end
                    end
                    assert(icon.object.m_duration == 900)
                end
            end
            assert(#writes==0)
        ''')

    def test_hp_expired_mechanical_record_with_longer_icon_allows_new_dose(self):
        self.run_lua(r'''
            manifest.sources.POTN09.keys.ICON = true
            manifest.sources.POTN09.nonBlockingKeys = {ICON=true}
            local active = {record("POTN09","HP",100),record("POTN09","ICON",500)}
            local result = plan(record("POTN09","HP",60,0),active,manifest,100,
                core.newDose({},"heroism",{HP=1,ICON=1}))
            assert(result.allow and #result.refresh==0 and #writes==0)
        ''')

    def test_native_clamped_seconds_are_not_silently_replaced_by_unclamped_math(self):
        self.run_lua(r'''
            local incoming=record("POTN36","PICK",200000000,0)
            planFails(incoming,{record("POTN36","PICK",150)},manifest,100,
                core.newDose("long", "thievery", {PICK=1}))
            assert(#writes==0)
        ''')

    def test_safe_repeat_refreshes_only_original_expiry_and_rejects_new_object(self):
        self.run_lua(r'''
            for _,timing in ipairs({0,10}) do
                local old = record("POTN36", "PICK", 150)
                local duration = timing == 0 and 6 or 90
                local incoming = record("POTN36", "PICK", duration, timing)
                local inputBefore = snapshot(incoming)
                local result = plan(incoming, {old}, manifest, 100,
                    core.newDose("repeat", "thievery", {PICK=1}))
                assert(not result.allow and #result.refresh == 1)
                local update = result.refresh[1]
                assert(rawequal(update.record, old.object))
                assert(update.oldExpiry == 150 and update.expiry == 190)
                assert(commit(result) == false and old.object.m_duration == 190)
                assert(snapshot(incoming) == inputBefore)
                assert(old.object.m_sourceType == 2 and old.object.m_sourceRes == "POTN36")
                assert(old.object.m_casterLevel == 10 and old.object.m_firstCall == 1)
                assert(old.object.m_effectAmount == 40 and old.object.m_effectAmount2 == 0)
                assert(old.object.m_flags == 1 and not old.object.m_done and old.object.opaque == "untouched")
            end
            assert(#writes == 2)
        ''')

    def test_refresh_uses_incoming_deadline_even_if_old_bonus_would_last_longer(self):
        self.run_lua(r'''
            local old = record("POTN36", "PICK", 900)
            local result = plan(record("POTN36","PICK",10,10), {old}, manifest, 100,
                core.newDose("repeat", "thievery", {PICK=1}))
            assert(result.refresh[1].expiry == 110)
            commit(result)
            assert(old.object.m_duration == 110)
        ''')

    def test_aliases_share_one_family_in_either_order(self):
        self.run_lua(r'''
            for _,sources in ipairs({{"POTN36","DW#PTN36"},{"DW#PTN36","POTN36"}}) do
                local old = record(sources[1],"PICK",200)
                local result = plan(record(sources[2],"PICK",30,10), {old}, manifest, 100,
                    core.newDose("alias", "thievery", {PICK=1}))
                assert(not result.allow and rawequal(result.refresh[1].record, old.object))
            end
        ''')

    def test_hp_repeat_and_partial_family_do_not_mutate_or_extend_anything(self):
        self.run_lua(r'''
            for _,remaining in ipairs({"HP","THAC0"}) do
                local old = record("POTN09",remaining,500)
                local before = snapshot(old)
                local dose = core.newDose("repeat", "heroism", {HP=1,THAC0=1})
                for _,key in ipairs({"HP","THAC0"}) do
                    local result = plan(record("DW#PTN09",key,900,10), {old}, manifest, 100, dose)
                    assert(not result.allow and #result.refresh == 0)
                    local allow; allow,dose = commit(result)
                    assert(not allow)
                end
                assert(snapshot(old) == before and #writes == 0)
            end
        ''')

    def test_heroism_and_power_remain_distinct_despite_shared_fingerprint_names(self):
        self.run_lua(r'''
            local hero = record("POTN09","HP",500)
            local result = plan(record("POTN41","HP",60,10), {hero}, manifest, 100,
                core.newDose("power", "power", {HP=1,THAC0=1}))
            assert(result.allow and #result.refresh == 0 and #writes == 0)
        ''')

    def test_absent_expired_and_done_effects_allow_a_new_hp_dose(self):
        self.run_lua(r'''
            local expired = record("POTN09","HP",100)
            local done = record("POTN09","HP",500); done.done = true
            for _,active in ipairs({{}, {expired}, {done}}) do
                local result = plan(record("POTN09","HP",60,10), active, manifest, 100,
                    core.newDose("new", "heroism", {HP=1}))
                assert(result.allow and #result.refresh == 0)
            end
        ''')

    def test_hp_block_decision_persists_for_whole_dose_if_old_effect_disappears(self):
        self.run_lua(r'''
            local state = core.newDose("repeat", "heroism", {HP=1,THAC0=1})
            local first = plan(record("POTN09","HP",60,10), {record("POTN09","HP",500)}, manifest, 100, state)
            assert(not first.allow)
            local second = plan(record("POTN09","THAC0",60,10), {}, manifest, 100, first.state)
            assert(not second.allow and #second.refresh == 0)
            local nextDose = plan(record("POTN09","HP",60,10), {}, manifest, 100,
                core.newDose("different-token", "heroism", {HP=1,THAC0=1}))
            assert(nextDose.allow)
        ''')

    def test_first_hp_package_allows_later_records_from_the_same_dose(self):
        self.run_lua(r'''
            local state = core.newDose("first", "heroism", {HP=1,THAC0=1})
            local first = plan(record("POTN09","HP",60,10), {}, manifest, 100, state)
            assert(first.allow)
            local second = plan(record("POTN09","THAC0",60,10), {record("POTN09","HP",160)}, manifest, 100, first.state)
            assert(second.allow and #second.refresh == 0)
        ''')

    def test_identical_records_are_allowed_up_to_same_dose_quota(self):
        self.run_lua(r'''
            local original = record("POTN36","PICK",60,10)
            local first = plan(original, {}, manifest, 100,
                core.newDose("first", "thievery", {PICK=2}))
            -- Native AddEffect retains the admitted original; it does not
            -- allocate an unrelated object when appending it to the timed list.
            forceExpiry(original.object,160)
            local newlyAdmitted = record("POTN36","PICK",160,4096,original.object)
            local second = plan(record("POTN36","PICK",60,10), {newlyAdmitted}, manifest, 100, first.state)
            assert(first.allow and second.allow and #second.refresh == 0)
            planFails(record("POTN36","PICK",60,10), {newlyAdmitted}, manifest, 100, second.state)
        ''')

    def test_safe_snapshot_assigns_each_old_identical_record_once(self):
        self.run_lua(r'''
            local a,b = record("POTN36","PICK",200),record("DW#PTN36","PICK",300)
            local first = plan(record("POTN36","PICK",60,10), {a,b}, manifest, 100,
                core.newDose("repeat", "thievery", {PICK=2}))
            local second = plan(record("POTN36","PICK",60,10), {b,a}, manifest, 100, first.state)
            assert(not first.allow and not second.allow)
            assert(rawequal(first.refresh[1].record,a.object))
            assert(rawequal(second.refresh[1].record,b.object))
            commit(first); commit(second)
            assert(a.object.m_duration == 160 and b.object.m_duration == 160)
        ''')

    def test_safe_record_removed_since_snapshot_allows_replacement(self):
        self.run_lua(r'''
            local a,b = record("POTN36","PICK",200),record("POTN36","LOCK",300)
            local first = plan(record("POTN36","PICK",60,10), {a,b}, manifest, 100,
                core.newDose("repeat", "thievery", {PICK=1,LOCK=1}))
            local second = plan(record("POTN36","LOCK",60,10), {a}, manifest, 100, first.state)
            assert(not first.allow and second.allow and #second.refresh == 0)
        ''')

    def test_two_dose_tokens_in_the_same_tick_are_separate_uses(self):
        self.run_lua(r'''
            local first = plan(record("POTN09","HP",60,10), {}, manifest, 100,
                core.newDose("one", "heroism", {HP=1}))
            local second = plan(record("POTN09","HP",60,10), {record("POTN09","HP",160)}, manifest, 100,
                core.newDose("two", "heroism", {HP=1}))
            assert(first.allow and not second.allow)
        ''')

    def test_genius_exception_uses_family_policy_not_int_opcode_or_filename(self):
        self.run_lua(r'''
            manifest.policy = "except_genius"
            local genius = plan(record("POTN29","INT",60,10), {record("POTN29","INT",200)}, manifest, 100,
                core.newDose("genius", "genius", {INT=1}))
            local focus = plan(record("POTN37","INT",60,10), {record("POTN37","INT",200)}, manifest, 100,
                core.newDose("focus", "focus", {INT=1,DEX=1}))
            assert(genius.allow and #genius.refresh == 0 and not focus.allow)
            manifest.families.vocalize = {hp=false,genius=false}
            manifest.sources.POTN29 = {family="vocalize",keys={VOCAL=true}}
            local repurposed = plan(record("POTN29","VOCAL",60,10), {record("POTN29","VOCAL",200)}, manifest, 100,
                core.newDose("vocalize", "vocalize", {VOCAL=1}))
            assert(not repurposed.allow)
        ''')

    def test_unique_policy_still_refreshes_genius(self):
        self.run_lua(r'''
            local result = plan(record("POTN29","INT",60,10), {record("POTN29","INT",200)}, manifest, 100,
                core.newDose("genius", "genius", {INT=1}))
            assert(not result.allow and #result.refresh == 1)
        ''')

    def test_unowned_source_spell_source_and_unowned_key_stay_untouched(self):
        self.run_lua(r'''
            local unowned = record("OTHER","PICK",60,10)
            local spell = record("POTN36","PICK",60,10); spell.sourceType = 1
            local foreign = record("POTN36","UNRELATED",60,10)
            for _,incoming in ipairs({unowned,spell,foreign}) do
                local result = plan(incoming, {}, manifest, 100, nil)
                assert(result.allow and #result.refresh == 0)
            end
        ''')

    def test_extra_preexisting_stack_and_duplicate_pointer_fail_without_mutation(self):
        self.run_lua(r'''
            local a,b = record("POTN36","PICK",200),record("POTN36","PICK",300)
            for _,active in ipairs({{a,b},{a,a}}) do
                planFails(record("POTN36","PICK",60,10), active, manifest, 100,
                    core.newDose("repeat", "thievery", {PICK=1}))
            end
        ''')

    def test_malformed_manifest_family_dose_and_native_lifetime_fail_without_mutation(self):
        self.run_lua(r'''
            local incoming = record("POTN36","PICK",60,10)
            local dose = core.newDose("x", "thievery", {PICK=1})
            planFails(incoming, {}, {policy="unique"}, 100, dose)
            manifest.policy="unknown"; planFails(incoming, {}, manifest, 100, dose); manifest.policy="unique"
            manifest.families.thievery.hp="yes"; planFails(incoming, {}, manifest, 100, dose); manifest.families.thievery.hp=false
            planFails(incoming, {}, manifest, 100, core.newDose("x", "power", {PICK=1}))
            planFails(incoming, {}, manifest, 100, core.newDose("x", "thievery", {LOCK=1}))
            local bad = record("POTN36","PICK",200); bad.timing=0
            planFails(incoming, {bad}, manifest, 100, dose)
            bad.timing=4096; bad.done=nil
            planFails(incoming, {bad}, manifest, 100, dose)
            for _,value in ipairs({-1, 0/0, math.huge, 1.5, 4294967296}) do
                planFails(incoming, {}, manifest, value, dose)
            end
            for _,value in ipairs({0, -1, 0/0, math.huge, 1.5, 4294967296}) do
                incoming.expiry=value
                planFails(incoming, {}, manifest, 100, dose)
            end
            incoming.expiry=60; incoming.timing=1
            planFails(incoming, {}, manifest, 100, dose)
            incoming.timing=10
            planFails(incoming, {}, manifest, 4294967290, dose)
        ''')

    def test_commit_validates_all_targets_before_any_native_write(self):
        self.run_lua(r'''
            local a,b = native(200),native(300)
            local result = {allow=false,state={},refresh={
                {record=a,oldExpiry=200,expiry=400},{record=b,oldExpiry=300,expiry=400}}}
            forceExpiry(b,301)
            commitFails(result)
            assert(a.m_duration == 200 and b.m_duration == 301)
            result.refresh[2] = {record=a,oldExpiry=200,expiry=500}
            commitFails(result)
            assert(a.m_duration == 200)
            result.refresh[2] = {record=b,oldExpiry=301,expiry=0/0}
            commitFails(result)
            assert(a.m_duration == 200 and b.m_duration == 301)
        ''')

    def test_commit_is_not_silently_replayed_after_expiry_changed(self):
        self.run_lua(r'''
            local old = record("POTN36","PICK",200)
            local result = plan(record("POTN36","PICK",60,10), {old}, manifest, 100,
                core.newDose("repeat", "thievery", {PICK=1}))
            commit(result)
            commitFails(result)
            assert(old.object.m_duration == 160 and #writes == 1)
        ''')

    def test_nested_planning_keeps_independent_doses_and_lists_unchanged(self):
        self.run_lua(r'''
            local nested, entered
            local source = manifest.sources.POTN36
            manifest.sources.POTN36 = nil
            setmetatable(manifest.sources, {__index=function(_,key)
                if key == "POTN36" then
                    if not entered then
                        entered=true
                        nested=plan(record("POTN09","HP",60,10), {}, manifest, 100,
                            core.newDose("nested", "heroism", {HP=1}))
                    end
                    return source
                end
            end})
            local old=record("POTN36","PICK",200)
            local active={old}
            local outer=plan(record("POTN36","PICK",60,10), active, manifest, 100,
                core.newDose("outer", "thievery", {PICK=1}))
            assert(nested.allow and not outer.allow and #writes == 0)
            assert(#active == 1 and rawequal(active[1], old))
            assert(outer.state.token == "outer" and nested.state.token == "nested")
        ''')


if __name__ == "__main__":
    unittest.main()
