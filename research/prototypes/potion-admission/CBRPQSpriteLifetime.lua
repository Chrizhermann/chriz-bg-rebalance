-- Native allocation-lifetime authority, inert until explicit composition.
-- No existing sprite is adopted from address, objectID, UUID or loaded-listener.
local M={}
M.expectedExecutableSha256="b51093a49140b2b8a7c046b4652bb8e535be24ebbc12b1d735e0b94217a14d57"
M.guards={
 {"beginDefault",0x1A3480,"48895C241048896C2418",5,8},
 {"beginData",0x341860,"48895C24185556574154415541564157",5,8},
 {"readyDefault",0x1A3C50,"4C8D5C2470498B5B28498B6B30498B7338",5,0},
 {"readyData",0x34310E,"899EF8510000E8C7720300",6,0},
 {"destroy",0x343CC0,"48895C240848896C24104889742418",5,8},
 {"clear",0x34FD30,"48895C240848896C2410488974241848897C2420",5,8},
}
function M.new(api)
 local function check(v,m) if not v then error("CBR sprite lifetime: "..m,0) end end
 local function ptr(p) check(type(p)=="number" and p==math.floor(p) and p>0 and p<9007199250000000,"invalid pointer");return p end
 for _,name in ipairs({"readPtr","onRetire","onContentsReset","onReset","report"}) do
  check(type(api[name])=="function","missing capability "..name)
 end
 local base=ptr(api.imageBase)
 local records,failed={},nil
 local R={callbacks={}}
 local function ensure() check(not failed,"halted: "..tostring(failed)) end
 local function callback(name,fn)
  R.callbacks[name]=function(...)
   if failed then return false end
   local ok,value=pcall(fn,...)
   if not ok then failed=tostring(value);pcall(api.report,failed);return false end
   return value
  end
 end
 local function begin(p)
  ptr(p);check(records[p]==nil,"constructor reused a live allocation without destruction")
  records[p]={identity={},ready=false};return true -- Never inspect uninitialized memory.
 end
 callback("beginDefault",begin);callback("beginData",begin)
 local function ready(p)
  ptr(p);local r=records[p]
  check(r and not r.ready,"readiness without an unmatched constructor")
  check(api.readPtr(p)==base+0x598B68 and api.readPtr(p+0x1A08)==base+0x58F528,
   "initialized sprite/regenerated-list class mismatch")
  r.ready=true;return true
 end
 callback("readyDefault",ready);callback("readyData",ready)
 callback("destroy",function(p)
  ptr(p);local r=records[p]
  if not r then return false end -- Unknown objects are never retrospectively adopted.
  -- Keep identity available during the cleanup notification, then retire even
  -- when cleanup reports failure. Native destruction will proceed regardless.
  local ok,err=pcall(api.onRetire,p,r.identity)
  records[p]=nil
  if not ok then error(err,0) end
  return true
 end)
 callback("clear",function(p)
  ptr(p);local r=records[p]
  if not r then return false end
  check(r.ready,"ClearMarshal observed before structural readiness")
  api.onContentsReset(p,r.identity)
  return true -- Same physical sprite allocation; never create a replacement token.
 end)
 function R.identity(p)
  ensure();ptr(p);local r=records[p]
  return r and r.ready and r.identity or nil
 end
 function R.reset()
  ensure()
  -- Root's already-proved native reset observer must invoke this. Cleanup of
  -- transient effect/cache state runs before token epochs change. Keep known
  -- allocation records until their destructors: reset is not a free operation.
  local ok,err=pcall(api.onReset)
  if not ok then failed=tostring(err);pcall(api.report,failed);error(failed,0) end
  for _,r in pairs(records) do r.identity={} end
 end
 function R.status() return {halted=failed~=nil,error=failed} end
 return R
end
function M.validate(api,config,watchdog)
 assert(type(api.EEex_HookIntegrityWatchdog_Load)=="boolean","sprite lifetime: watchdog state unavailable")
 if api.EEex_HookIntegrityWatchdog_Load then
  assert(watchdog and type(watchdog.validate)=="function" and type(watchdog.withPreservation)=="function",
   "sprite lifetime: watchdog preservation helper required");watchdog.validate(api)
 end
 for _,name in ipairs({"EEex_GetImageBase","EEex_ReadU8","EEex_GenLuaCall","EEex_FlattenTable"}) do
  assert(type(api[name])=="function","sprite lifetime: missing API "..name)
 end
 assert(type(config)=="table" and type(config.callbacks)=="table","sprite lifetime: callbacks required")
 local base=api.EEex_GetImageBase(); assert(type(base)=="number" and base>0 and base==math.floor(base),"invalid image base")
 local names={}
 for _,g in ipairs(M.guards) do
  local name=config.callbacks[g[1]]
  assert(type(name)=="string" and name:match("^[%a_][%w_]*$") and type(api[name])=="function","sprite lifetime: callback unavailable "..g[1])
  names[g[1]]=name
  for i=1,#g[3],2 do
   assert(api.EEex_ReadU8(base+g[2]+(i-1)/2)==tonumber(g[3]:sub(i,i+1),16),"sprite lifetime: unsupported/patched site "..g[1])
  end
 end
 local value=base+0x1A4630
 for i=0,7 do
  assert(api.EEex_ReadU8(base+0x598B68+i)==value%256,"sprite lifetime: unsupported sprite destructor vtable")
  value=math.floor(value/256)
 end
 return {base=base,callbacks=names,watchdog=api.EEex_HookIntegrityWatchdog_Load}
end
local save = [[
    pushfq
    push rax
    push rcx
    push rdx
    push r8
    push r9
    push r10
    push r11
    sub rsp, 60h
    movdqu xmmword ptr ss:[rsp+00h], xmm0
    movdqu xmmword ptr ss:[rsp+10h], xmm1
    movdqu xmmword ptr ss:[rsp+20h], xmm2
    movdqu xmmword ptr ss:[rsp+30h], xmm3
    movdqu xmmword ptr ss:[rsp+40h], xmm4
    movdqu xmmword ptr ss:[rsp+50h], xmm5
    #STACK_MOD(160)
]]
local restore = [[
    #DESTROY_SHADOW_SPACE
    movdqu xmm0, xmmword ptr ss:[rsp+00h]
    movdqu xmm1, xmmword ptr ss:[rsp+10h]
    movdqu xmm2, xmmword ptr ss:[rsp+20h]
    movdqu xmm3, xmmword ptr ss:[rsp+30h]
    movdqu xmm4, xmmword ptr ss:[rsp+40h]
    movdqu xmm5, xmmword ptr ss:[rsp+50h]
    add rsp, 60h
    pop r11
    pop r10
    pop r9
    pop r8
    pop rdx
    pop rcx
    pop rax
    popfq
    #STACK_MOD(-160)
]]

-- Argument builders may clobber only RAX, which is already saved. GenLuaCall
-- emits arguments in reverse order; none of these builders consume scratch RAX.
local function reg(register, userType)
    return function(offset)
        return {"mov qword ptr ss:[rsp+#$(1)], " .. register .. " #ENDL", {offset}}, userType
    end
end
local function calculated(instruction)
    return function(offset)
        return {instruction .. " #ENDL mov qword ptr ss:[rsp+#$(1)], rax #ENDL", {offset}}
    end
end

local function callback(api,name,key,args)
    local suffix="_cbrpq_sprite_lifetime_"..key
    return api.EEex_FlattenTable({{save},api.EEex_GenLuaCall(name,{args=args,labelSuffix=suffix}),
        {"call_error"..suffix..": #ENDL",restore}})
end

function M.prepare(api,config,watchdog)
 local v=M.validate(api,config,watchdog)
 local out={base=v.base,watchdog=v.watchdog,descriptors={}}
 for _,g in ipairs(M.guards) do
  local register=(g[1]=="readyDefault" or g[1]=="readyData") and "rsi" or "rcx"
  out.descriptors[#out.descriptors+1]={key=g[1],address=v.base+g[2],restoreSize=g[4],stackMod=g[5],
   labels=g[5]==8 and {{"stack_mod",8}} or {},assembly=callback(api,v.callbacks[g[1]],g[1],{reg(register)})}
 end
 return out
end
return M
