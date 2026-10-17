"""Real adapter/cache/recovery Lua; explicit byte memory/native service doubles."""
from pathlib import Path
import unittest
from lupa.luajit21 import LuaRuntime
ROOT=Path(__file__).resolve().parents[1]/"research/prototypes/potion-admission"
HARNESS=r"""
BASE=0x140000000; SPRITE=0x90000; LIST=SPRITE+0x1A08
mem,originals,spriteIds,errors,scratch,allocations={},{},{},{},{},{}
spriteIds[SPRITE]={}; now=1449; nextScratch=0x100000; nextNative=0x200000; nextNode=0x300000
allocateStatus,insertStatus,throwAfterInsert,injectCallback=0,0,false,nil
serviceCalls={allocate=0,insert=0,dispose=0}; freed={}
function bytes(p,n) local b={}; for i=0,n-1 do assert(mem[p+i]~=nil,'invalid memory '..p+i); b[#b+1]=string.char(mem[p+i]) end; return table.concat(b) end
function putBytes(p,s) for i=1,#s do mem[p+i-1]=s:byte(i) end end
function put(p,n,v) for i=0,n-1 do mem[p+i]=v%256; v=math.floor(v/256) end end
function get(p,n) local v=0; for i=n-1,0,-1 do assert(mem[p+i]~=nil,'invalid memory '..p+i); v=v*256+mem[p+i] end; return v end
function zero(p,n) putBytes(p,string.rep('\0',n)) end
function ptr(p) return type(p)=='number' and p or p.pointer end
function allocScratch(n) local p=nextScratch; nextScratch=p+n+16; zero(p,n); scratch[p]=n; return p end
function freeScratch(p) assert(scratch[p],'unknown scratch'); scratch[p]=nil; freed[#freed+1]=p end
function listInit(p) zero(p,64); put(p,8,BASE+0x58F528); put(p+0x30,4,3) end
listInit(LIST)
function listPointers(p) local out={}; local n=get(p+8,8); while n~=0 do out[#out+1]=get(n+16,8); n=get(n,8) end; return out end
function insertRaw(list,p,node)
 local n=nextNode; nextNode=n+32; zero(n,24)
 local previous=node==0 and get(list+16,8) or get(node+8,8)
 put(n,8,node); put(n+8,8,previous); put(n+16,8,p)
 if previous==0 then put(list+8,8,n) else put(previous,8,n) end
 if node==0 then put(list+16,8,n) else put(node+8,8,n) end
 put(list+24,4,get(list+24,4)+1)
 return n
end
function removeRaw(list,p)
 local n=get(list+8,8)
 while n~=0 and get(n+16,8)~=p do n=get(n,8) end
 assert(n~=0); local nx,pr=get(n,8),get(n+8,8)
 if pr==0 then put(list+8,8,nx) else put(pr,8,nx) end
 if nx==0 then put(list+16,8,pr) else put(nx+8,8,pr) end
 put(list+24,4,get(list+24,4)-1)
end
function effect(p,expiry)
 originals[p]={identity={},opcode=98,timing=4096,expiry=expiry,done=false,sprite=SPRITE,current=true}
 return setmetatable({pointer=p},{__index=function(_,k) if k=='m_duration' then return originals[p].expiry end end,
 __newindex=function(_,k,v) assert(k=='m_duration'); originals[p].expiry=v end})
end
function makeCache(p,remaining)
 zero(p,48); put(p,8,BASE+0x598B18); put(p+0x12,2,5); put(p+0x18,2,3); put(p+0x1A,2,2)
 put(p+0x20,2,3); put(p+0x24,2,5); put(p+0x28,4,remaining)
end
function add(original,p,expiry)
 local record=effect(original,expiry or 1450); makeCache(p,1)
 local n=insertRaw(LIST,p,0)
 adapter.callbacks.append(LIST,p,n,BASE+0x1BEDE5)
 assert(adapter.callbacks.appendOwned(original,p,SPRITE))
 return record
end
api={imageBase=BASE,ptr=ptr,now=function() return now end,
 original=function(p) return originals[p] end,
 isCurrentOriginal=function(s,p,id) local o=originals[p]; return o and o.sprite==s and o.identity==id and o.current end,
 spriteIdentity=function(p) return spriteIds[p] end,
 readPtr=function(p) return get(p,8) end,readU32=function(p) return get(p,4) end,
 readI32=function(p) local n=get(p,4); return n>=0x80000000 and n-0x100000000 or n end,
 readU16=function(p) return get(p,2) end,readBytes=bytes,
 writePtr=function(p,v) put(p,8,v) end,writeU32=function(p,v) put(p,4,v) end,
 writeU16=function(p,v) put(p,2,v) end,writeBytes=putBytes,
 allocScratch=allocScratch,freeScratch=freeScratch,report=function(e) errors[#errors+1]=e end,services={}}
api.services.allocate=function(r)
 serviceCalls.allocate=serviceCalls.allocate+1
 if injectCallback then injectCallback('allocate') end
 if allocateStatus==2 then return 2 end
 local p=nextNative; nextNative=p+256; zero(p,48)
 if allocateStatus==4 then put(r+24,8,p); allocations[p]=true; return 4 end
 local pool=nextNative; nextNative=pool+256; allocations[p]=true; allocations[pool]=true
 putBytes(p,bytes(get(r,8),48)); put(p+8,4,0); put(p+0x28,4,get(r+8,4)); put(p+0x1A,2,get(r+12,2))
 put(r+24,8,p); put(r+32,8,pool); return 0
end
api.services.insert=function(r)
 serviceCalls.insert=serviceCalls.insert+1
 if insertStatus~=0 then return insertStatus end
 local p,pool,list,node=get(r+24,8),get(r+32,8),get(r+40,8),get(r+48,8)
 local n=insertRaw(list,p,node)
 if node==0 then adapter.callbacks.append(list,p,n,BASE+0x3600100) end
 if injectCallback then injectCallback('insert') end
 if throwAfterInsert then error('injected after native adoption') end
 put(r+24,8,0); put(r+32,8,0); put(r+56,8,n); return 0
end
api.services.dispose=function(r)
 serviceCalls.dispose=serviceCalls.dispose+1
 local p,pool=get(r+24,8),get(r+32,8)
 if p~=0 then adapter.callbacks.cacheDestroy(p); allocations[p]=nil; put(r+24,8,0) end
 if pool~=0 then allocations[pool]=nil; put(r+32,8,0) end
 return 0
end
function plan(record,expiry)
 return {allow=false,state={},refresh={{record=record,identity=originals[record.pointer].identity,
 oldExpiry=originals[record.pointer].expiry,expiry=expiry}}}
end
function commit(record,expiry)
 local p=plan(record,expiry); local t=adapter.prepare(p,SPRITE); core.commit(p); return t.commit()
end
function enter(key) assert(adapter.callbacks.updateEnter(LIST,SPRITE,1,key or 0x400000)) end
function death(p)
 put(p+0x28,4,0); assert(adapter.callbacks.naturalDeath(p)); put(p+8,4,1)
 local n=get(LIST+8,8); while get(n+16,8)~=p do n=get(n,8) end
 assert(adapter.callbacks.beforeRemove(LIST,p,n)); removeRaw(LIST,p); adapter.callbacks.cacheDestroy(p)
end
function finish(key)
 put(LIST+0x38,4,get(LIST+0x38,4)+1)
 return adapter.callbacks.updateExit(LIST,key or 0x400000)
end
function count(t) local n=0; for _ in pairs(t) do n=n+1 end; return n end
"""

class RegenerationAdapterTests(unittest.TestCase):
 def setUp(self):
  self.lua=LuaRuntime(unpack_returned_tuples=True)
  self.lua.execute(HARNESS)
  self.g=self.lua.globals()
  factory=self.lua.execute((ROOT/'CBRPQRegenAdapter.lua').read_text())
  cache=self.lua.execute((ROOT/'CBRPQRegenCache.lua').read_text())
  recovery=self.lua.execute((ROOT/'CBRPQRegenRecovery.lua').read_text())
  self.adapter=factory(self.g.api,cache,recovery); self.g.adapter=self.adapter
  self.g.core=self.lua.execute((ROOT/'CBRPQCore.lua').read_text())
  self.record=self.g.add(0x20000,0x30000,1450)
 def missing(self,finish=True):
  self.g.enter(); self.g.death(0x30000)
  if finish: self.assertTrue(self.g.finish())
 def values(self): return list(self.g.listPointers(self.g.LIST).values())
 def test_live_refresh_writes_only_countdown_and_no_service_or_phase_change(self):
  self.assertEqual(1,self.g.commit(self.record,1900))
  self.assertEqual(451,self.g.get(0x30028,4))
  self.assertEqual(2,self.g.get(0x3001A,2))
  self.assertEqual(0,self.g.serviceCalls.allocate)
  self.assertFalse(self.adapter.status().halted)
 def test_missing_tail_recovers_through_staged_append_without_recursive_recovery(self):
  self.missing(); self.assertEqual(1,self.g.commit(self.record,1900))
  self.assertEqual([0x200000],self.values())
  self.assertEqual(450,self.g.get(0x200028,4)); self.assertEqual(2,self.g.get(0x20001A,2))
  self.assertEqual(0,self.g.count(self.g.scratch)); self.assertFalse(self.adapter.status().halted)
 def test_missing_middle_and_two_originals_preserve_order_with_batch(self):
  second=self.g.add(0x21000,0x31000,1450); self.g.add(0x22000,0x32000,2000)
  self.g.enter(); self.g.death(0x30000); self.g.death(0x31000); self.g.finish()
  p=self.g.plan(self.record,1900); p.refresh[2]=self.g.plan(second,1950).refresh[1]
  t=self.adapter.prepare(p,self.g.SPRITE); self.g.core.commit(p); self.assertEqual(2,t.commit())
  self.assertEqual([0x200000,0x200200,0x32000],self.values())
  self.assertEqual(2,self.g.serviceCalls.allocate)
 def test_deferred_repeated_deadline_updates_allocate_only_at_matching_exit(self):
  self.missing(False); self.g.commit(self.record,1900); self.g.commit(self.record,2000)
  self.assertEqual(0,self.g.serviceCalls.allocate)
  self.assertTrue(self.g.finish()); self.assertEqual(1,self.g.serviceCalls.allocate)
  self.assertEqual(550,self.g.get(self.values()[0]+0x28,4))
 def test_unknown_native_append_extends_history_and_original_append_is_not_duplicated(self):
  self.missing(); self.g.makeCache(0x31000,500)
  n=self.g.insertRaw(self.g.LIST,0x31000,0)
  self.assertTrue(self.adapter.callbacks.append(self.g.LIST,0x31000,n,0x12345))
  self.g.commit(self.record,1900)
  self.assertEqual([0x200000,0x31000],self.values())
 def test_cancel_clear_replace_and_type5_prevent_reconstruction(self):
  for which in ('clear','replace','removeType'):
   with self.subTest(which=which):
    self.setUp(); self.missing(False); self.g.commit(self.record,1900)
    self.adapter.callbacks[which](self.g.LIST,5 if which=='removeType' else 0x12345)
    self.assertTrue(self.g.finish()); self.assertEqual([],self.values())
    self.assertEqual(0,self.g.serviceCalls.allocate)
 def test_other_type_cancellation_does_not_cancel_regeneration(self):
  self.missing(False); self.g.commit(self.record,1900)
  self.assertFalse(self.adapter.callbacks.removeType(self.g.LIST,3))
  self.assertTrue(self.g.finish()); self.assertEqual(1,len(self.values()))
 def test_unknown_and_nested_frames_pair_without_reading_arbitrary_sprite_memory(self):
  self.assertTrue(self.adapter.callbacks.updateEnter(0xDEAD,0xBEEF,17,0x111))
  self.g.enter(0x222); self.assertTrue(self.g.finish(0x222))
  self.assertFalse(self.adapter.callbacks.updateExit(0xDEAD,0x111)); self.assertFalse(self.adapter.status().halted)
 def test_frame_mismatch_halts_and_reports_without_throwing_native_callback(self):
  self.g.enter(); self.assertFalse(self.adapter.callbacks.updateExit(self.g.LIST,0x999))
  self.assertTrue(self.adapter.status().halted); self.assertEqual(1,len(self.g.errors))
  with self.assertRaisesRegex(Exception,'halted'): self.adapter.prepare(self.g.plan(self.record,1900),self.g.SPRITE)
 def test_reset_preserves_old_exit_sentinel_without_native_recovery(self):
  self.missing(False); self.g.commit(self.record,1900); self.adapter.reset()
  self.assertFalse(self.g.finish()); self.assertEqual(0,self.g.serviceCalls.allocate)
 def test_sprite_address_reuse_without_retirement_rejected_before_core_write(self):
  self.lua.execute('spriteIds[SPRITE]={}')
  with self.assertRaisesRegex(Exception,'reused without retirement'): self.g.commit(self.record,1900)
  self.assertEqual(1450,self.record.m_duration)
 def test_malformed_list_and_stale_successor_fail_before_core(self):
  self.g.put(self.g.LIST+0x18,4,2)
  with self.assertRaisesRegex(Exception,'list count'): self.g.commit(self.record,1900)
  self.assertEqual(1450,self.record.m_duration)
 def test_unrelated_small_cache_reads_only_common_header(self):
  self.g.zero(0x31000,32); self.g.put(0x31000,8,self.g.BASE+0x598A40)
  n=self.g.insertRaw(self.g.LIST,0x31000,0)
  self.adapter.callbacks.append(self.g.LIST,0x31000,n,0x12345)
  self.missing(); self.g.commit(self.record,1900)
  self.assertEqual(0x31000,self.values()[-1])
 def test_allocation_null_frees_scratch_and_never_touches_current_list(self):
  self.missing(); self.g.allocateStatus=2
  with self.assertRaisesRegex(Exception,'allocation status 2'): self.g.commit(self.record,1900)
  self.assertEqual([],self.values()); self.assertEqual(0,self.g.count(self.g.scratch))
  self.assertEqual(1900,self.record.m_duration) # Core write was already committed; no rollback claim.
 def test_cleanup_failure_status_retains_explicit_detached_ownership(self):
  self.missing(); self.g.allocateStatus=4
  with self.assertRaisesRegex(Exception,'allocation status 4'): self.g.commit(self.record,1900)
  self.assertEqual(1,len(self.adapter.status().pending))
  self.assertEqual(1,self.adapter.cleanupDetached())
  self.assertEqual(0,self.g.count(self.g.scratch)); self.assertEqual(0,self.g.count(self.g.allocations))
  self.assertTrue(self.adapter.status().halted)
 def test_insert_throw_after_adoption_never_frees_uncertain_cache_or_pool(self):
  self.missing(); self.g.throwAfterInsert=True
  with self.assertRaisesRegex(Exception,'after native adoption'): self.g.commit(self.record,1900)
  self.assertEqual([0x200000],self.values()); self.assertEqual(0,self.adapter.cleanupDetached())
  self.assertTrue(self.adapter.status().pending[1].uncertain)
  self.assertEqual(0,self.g.serviceCalls.dispose)
 def test_unexpected_service_callback_halts_and_prevents_silent_success(self):
  self.missing(); self.lua.execute("injectCallback=function(kind) if kind=='insert' then adapter.callbacks.copy(0x30000,0x55555) end end")
  with self.assertRaisesRegex(Exception,'halted'): self.g.commit(self.record,1900)
  self.assertTrue(self.adapter.status().halted); self.assertTrue(self.adapter.status().pending[1].adopted)
  self.assertEqual(0,self.adapter.cleanupDetached())
 def test_copy_lineage_is_registered_then_destruction_retires_pointer(self):
  self.g.makeCache(0x31000,1)
  self.assertTrue(self.adapter.callbacks.copy(0x30000,0x31000))
  self.assertTrue(self.adapter.callbacks.cacheDestroy(0x31000))
  self.assertTrue(self.adapter.callbacks.copy(0x30000,0x31000))
 def test_missing_sprite_lifetime_capability_rejects_factory(self):
  self.g.api.spriteIdentity=None
  f=self.lua.execute((ROOT/'CBRPQRegenAdapter.lua').read_text())
  with self.assertRaisesRegex(Exception,'spriteIdentity'): f(self.g.api,self.lua.eval('function() end'),self.lua.eval('function() end'))

 def test_invalid_pool_count_is_rejected_before_core_commit(self):
  self.missing(); self.g.put(self.g.LIST+0x30,4,0)
  with self.assertRaisesRegex(Exception,'pool block count'): self.g.commit(self.record,1900)
  self.assertEqual(1450,self.record.m_duration); self.assertEqual(0,self.g.serviceCalls.allocate)
 def test_wrong_cache_type_rejects_snapshot_before_recovery(self):
  self.g.enter(); self.g.put(0x30028,4,0); self.adapter.callbacks.naturalDeath(0x30000)
  self.g.put(0x30008,4,1); self.g.put(0x30012,2,6)
  n=self.g.get(self.g.LIST+8,8)
  self.assertFalse(self.adapter.callbacks.beforeRemove(self.g.LIST,0x30000,n))
  self.assertIn('exact native natural-death',self.adapter.status().error)
  self.assertEqual(1450,self.record.m_duration)
 def test_known_insert_failure_can_clean_detached_allocations_without_freeing_any_list_member(self):
  self.missing(); self.g.insertStatus=2
  with self.assertRaisesRegex(Exception,'insert status 2'): self.g.commit(self.record,1900)
  self.assertEqual([],self.values()); self.assertEqual(1,self.adapter.cleanupDetached())
  self.assertEqual(0,self.g.count(self.g.allocations)); self.assertEqual(0,self.g.count(self.g.scratch))
 def test_scratch_failure_before_engine_call_retains_and_cleans_known_scratch_only(self):
  self.missing(); self.lua.execute("api.allocScratch=function(n) if n==48 then return 0 end return allocScratch(n) end")
  with self.assertRaisesRegex(Exception,'invalid pointer'): self.g.commit(self.record,1900)
  self.assertEqual(0,self.g.serviceCalls.allocate)
  self.assertEqual(1,self.adapter.cleanupDetached()); self.assertEqual(0,self.g.count(self.g.scratch))
 def test_reset_does_not_forget_uncertain_adopted_allocations(self):
  self.missing(); self.g.throwAfterInsert=True
  with self.assertRaises(Exception): self.g.commit(self.record,1900)
  with self.assertRaisesRegex(Exception,'unresolved native allocation'): self.adapter.reset()
  self.assertEqual(1,len(self.adapter.status().pending)); self.assertEqual([0x200000],self.values())

if __name__=='__main__': unittest.main()
