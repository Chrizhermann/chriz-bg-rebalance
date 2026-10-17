-- Inert EEex capability bridge. Loading/new/validateServices do not allocate,
-- JIT, expose Lua functions, call a native service, register or arm hooks.
-- prepareServices is an explicit, one-attempt executable-allocation boundary.
-- Service execution requires the separately guarded lifecycle observers to be
-- active; validation/JIT preparation precede hook installation. Composition
-- routes original destruction here BEFORE reader.retire. Unknown sprites
-- are never adopted: the supplied SpriteLifetime owns allocation identities.
local M={}
local EXACT,U32=9007199254740991,4294967295
local function check(v,m) if not v then error("CBR regeneration native: "..m,0) end end
local function integer(v,lo,hi,m)
    check(type(v)=="number" and v==math.floor(v) and v>=lo and v<=hi,"invalid "..m);return v
end
local function pointer(v) return integer(v,1,EXACT-0x10000,"pointer") end
local function functions(t,names,what)
    check(type(t)=="table","missing "..what)
    for _,name in ipairs(names) do check(type(t[name])=="function","missing "..what.."."..name) end
end
local serviceNames={"allocate","insert","dispose"}
-- EEex_Assembly.lua's final label check mistakes a bare register CALL for a
-- local label. Annotating only this exact valid instruction preserves its
-- assembled bytes and leaves all actual label/branch checks in force.
local function eeexAssembly(text)
    return {(text:gsub("call rax\n","call rax ; indirect native service target\n"))}
end

function M.new(api,reader,spriteLifetime,parts,report)
    functions(api,{"EEex_GetImageBase","EEex_ReadPtr","EEex_ReadU32","EEex_Read32","EEex_ReadU16",
        "EEex_ReadU8","EEex_WritePtr","EEex_Write32","EEex_Write16","EEex_Write8",
        "EEex_PtrToUD","EEex_Malloc","EEex_Free"},"EEex")
    functions(reader,{"ptr","identify","active"},"reader")
    functions(spriteLifetime,{"identity"},"sprite lifetime")
    functions(parts,{"adapter","cache","recovery"},"factory")
    functions(parts.services,{"plan","luaWrapper"},"service generator")
    check(type(report)=="function","missing diagnostic callback")
    local base=integer(api.EEex_GetImageBase(),0x10000,EXACT-0x3500000,"image base")
    local associations,scopes,scratch={},{},{}
    local generation,fault,attempted,bound={},nil,false,nil
    local R={callbacks={}}
    local function healthy() check(not fault,"halted: "..tostring(fault)) end
    local function fail(message)
        if not fault then fault=tostring(message);pcall(report,fault) end
    end
    local function readPtr(p) return integer(api.EEex_ReadPtr(pointer(p)),0,EXACT-0x10000,"pointer value") end
    local function readU32(p) return integer(api.EEex_ReadU32(pointer(p)),0,U32,"unsigned dword") end
    local function readU16(p) return integer(api.EEex_ReadU16(pointer(p)),0,65535,"unsigned word") end
    local function spriteId(p)
        local id=spriteLifetime.identity(pointer(p))
        check(id==nil or type(id)=="table","sprite lifetime is not an opaque token")
        return id
    end
    local function describe(record)
        if not record then return nil end
        check(type(record.identity)=="table","reader lifetime is not an opaque token")
        local p=pointer(reader.ptr(record.object)) -- Fresh live object only.
        return {identity=record.identity,opcode=readU32(p+0x10),timing=record.timing,
            expiry=record.expiry,done=record.done}
    end
    local function current(sprite,p,id)
        local token=spriteId(sprite)
        if not token then return nil end
        local object=api.EEex_PtrToUD(sprite,"CGameSprite")
        check(object~=nil and reader.ptr(object)==sprite,"sprite conversion changed pointer")
        local found
        for _,r in ipairs(reader.active(object,{})) do
            if reader.ptr(r.object)==p and (id==nil or r.identity==id) then
                check(not found,"duplicate current original")
                found=r
            end
        end
        return found,token
    end
    local function original(p)
        healthy();pointer(p)
        local scope=scopes[#scopes]
        if scope and scope.pointer==p and scope.generation==generation and not scope.retired then
            check(spriteId(scope.sprite)==scope.spriteIdentity,"append sprite lifetime changed")
            -- Only the proven native appendOwned site provides this authority.
            -- First Apply can precede admission to the sprite timed list.
            local effect=api.EEex_PtrToUD(p,"CGameEffect")
            check(effect~=nil and reader.ptr(effect)==p,"original conversion changed pointer")
            local record=reader.identify(effect,nil,false)
            if record then
                associations[p]={sprite=scope.sprite,spriteIdentity=scope.spriteIdentity,identity=record.identity}
            end
            return describe(record)
        end
        local a=associations[p]
        if not a or spriteId(a.sprite)~=a.spriteIdentity then return nil end
        -- Never construct an effect userdata from a retained pointer here.
        -- Native.active enumerates the CURRENT timed list and returns fresh
        -- objects/tokens; absence or address reuse cannot authenticate old data.
        return describe(current(a.sprite,p,a.identity))
    end
    local function owns(p,n)
        pointer(p);integer(n,0,EXACT-p,"scratch range")
        for start,length in pairs(scratch) do
            if p>=start and p+n<=start+length then return true end
        end
        return false
    end
    local capabilities={imageBase=base,ptr=reader.ptr,original=original,spriteIdentity=spriteId,
        readPtr=readPtr,readU32=readU32,readU16=readU16,report=report,services={}}
    function capabilities.now()
        return integer(api.EngineGlobals.g_pBaldurChitin.m_pObjectGame.m_worldTime.m_gameTime,
            0,U32,"world tick")
    end
    function capabilities.isCurrentOriginal(s,p,id)
        healthy();pointer(s);pointer(p);check(type(id)=="table","missing original identity")
        return current(s,p,id)~=nil
    end
    function capabilities.readI32(p)
        return integer(api.EEex_Read32(pointer(p)),-2147483648,2147483647,"signed dword")
    end
    function capabilities.readBytes(p,n)
        pointer(p);integer(n,0,EXACT-p,"read length")
        local out={}
        for i=0,n-1 do out[i+1]=string.char(integer(api.EEex_ReadU8(p+i),0,255,"byte")) end
        return table.concat(out)
    end
    function capabilities.allocScratch(n)
        healthy();integer(n,1,0x10000,"scratch length")
        local p=pointer(api.EEex_Malloc(n))
        check(not scratch[p],"allocator reused owned scratch")
        scratch[p]=n;return p
    end
    function capabilities.freeScratch(p)
        check(scratch[p]~=nil,"free of unowned scratch")
        -- The pinned EEex MemoryManager uses this exact allocator/free pair.
        -- Retain the ownership record if Free throws; never retry implicitly.
        api.EEex_Free(p);scratch[p]=nil
    end
    function capabilities.writeBytes(p,bytes)
        check(type(bytes)=="string" and owns(p,#bytes),"write outside owned scratch")
        for i=1,#bytes do api.EEex_Write8(p+i-1,bytes:byte(i)) end
    end
    function capabilities.writePtr(p,v)
        check(owns(p,8),"pointer write outside owned scratch")
        api.EEex_WritePtr(p,integer(v,0,EXACT-0x10000,"pointer value"))
    end
    function capabilities.writeU16(p,v)
        check(owns(p,2),"word write outside owned scratch")
        api.EEex_Write16(p,integer(v,0,65535,"unsigned word"))
    end
    function capabilities.writeU32(p,v)
        -- Adapter also owns the narrowly validated live cache countdown write.
        -- Validation of that class/member/lineage is in Adapter.writeRemaining.
        api.EEex_Write32(pointer(p),integer(v,0,U32,"unsigned dword"))
    end
    for _,name in ipairs(serviceNames) do
        capabilities.services[name]=function(request)
            healthy();check(bound~=nil,"native services not explicitly prepared")
            check(scratch[request]==0x40,"service request is not owned 64-byte scratch")
            return integer(bound[name](request),0,U32,"native service status")
        end
    end
    local adapter=parts.adapter(capabilities,parts.cache,parts.recovery)
    for name,callback in pairs(adapter.callbacks) do
        R.callbacks[name]=function(...) if fault then return false end;return callback(...) end
    end
    R.callbacks.appendOwned=function(p,cache,sprite)
        if fault then return false end
        local scope
        local ok,result=pcall(function()
            pointer(p);pointer(sprite)
            local id=spriteId(sprite)
            if not id then return false end -- Do not inspect unknown allocations.
            scope={pointer=p,sprite=sprite,spriteIdentity=id,generation=generation}
            scopes[#scopes+1]=scope
            return adapter.callbacks.appendOwned(p,cache,sprite)
        end)
        if scope then
            if scopes[#scopes]~=scope then fail("unbalanced original append scope")
            else scopes[#scopes]=nil end
        end
        if not ok then fail(result);return false end
        return result
    end
    function R.prepare(plan,sprite)
        healthy();check(bound~=nil,"native services not explicitly prepared")
        local s=pointer(reader.ptr(sprite));local id=spriteId(s)
        check(id~=nil,"sprite lifetime unavailable")
        -- Seed pointer -> owner relations exclusively from current owned records.
        -- No descriptor or userdata is retained, only authoritative identities.
        for _,record in ipairs(reader.active(sprite,{})) do
            associations[pointer(reader.ptr(record.object))]={sprite=s,spriteIdentity=id,identity=record.identity}
        end
        return adapter.prepare(plan,sprite)
    end
    function R.onOriginalDestroy(p)
        pointer(p)
        local ok,err=pcall(adapter.onOriginalDestroy,p)
        associations[p]=nil
        for _,scope in ipairs(scopes) do if scope.pointer==p then scope.retired=true end end
        if not ok then fail(err);error(err,0) end
    end
    function R.onSpriteDestroy(p)
        pointer(p)
        local ok,err=pcall(adapter.onSpriteDestroy,p)
        for original,a in pairs(associations) do if a.sprite==p then associations[original]=nil end end
        for _,scope in ipairs(scopes) do if scope.sprite==p then scope.retired=true end end
        if not ok then fail(err);error(err,0) end
    end
    function R.reset()
        adapter.reset()
        check(next(scratch)==nil,"reset retains owned scratch")
        associations={};generation={};fault=nil
    end
    function R.cleanupDetached() return adapter.cleanupDetached() end
    function R.status()
        local s=adapter.status();s.halted=s.halted or fault~=nil;s.error=fault or s.error
        s.servicesPrepared=bound~=nil;s.servicePreparationAttempted=attempted;s.scratch={}
        for p,n in pairs(scratch) do s.scratch[#s.scratch+1]={pointer=p,length=n} end
        return s
    end
    function R.validateServices(prefix)
        healthy()
        functions(api,{"EEex_JITNear","EEex_ExposeToLua"},"EEex service preparation")
        -- ExposeToLua writes to the actual global Lua state. Do not silently
        -- bind to a caller's unrelated API table.
        check(api==_G,"service preparation requires the actual global Lua API")
        check(type(prefix)=="string" and prefix:match("^[%a_][%w_]*$"),"invalid temporary function prefix")
        local names={}
        for _,name in ipairs(serviceNames) do
            names[name]=prefix.."_"..name
            check(rawget(api,names[name])==nil,"temporary service namespace occupied")
        end
        local plan=parts.services.plan(api) -- Reads all signatures; no JIT/alloc.
        check(plan.imageBase==base,"image base changed")
        return {imageBase=base,names=names,requestSize=plan.requestSize}
    end
    function R.prepareServices(prefix)
        healthy();check(not attempted,"service preparation already attempted; restart required")
        local validation=R.validateServices(prefix)
        local plan=parts.services.plan(api) -- Revalidate immediately before JIT.
        local staged,temporary={},{}
        attempted=true
        local ok,err=pcall(function()
            for _,name in ipairs(serviceNames) do
                local address=pointer(api.EEex_JITNear(eeexAssembly(plan[name])))
                local wrapper=pointer(api.EEex_JITNear(eeexAssembly(parts.services.luaWrapper(address))))
                local global=validation.names[name]
                check(rawget(api,global)==nil,"temporary service namespace changed")
                -- Track only the function actually returned by our successful
                -- exposure. If exposure throws after publishing an unknown
                -- value, leave it untouched and diagnose/restart; no rollback.
                api.EEex_ExposeToLua(wrapper,global)
                local fn=rawget(api,global)
                check(type(fn)=="function","EEex did not expose a Lua C function")
                temporary[global]=fn;staged[name]=fn
            end
        end)
        for global,fn in pairs(temporary) do
            if rawget(api,global)==fn then rawset(api,global,nil)
            else ok=false;err="temporary service binding was replaced" end
        end
        if not ok then fail(err);error(err,0) end
        bound=staged;return true
    end
    return R
end
return M
