-- Inert composition of regeneration bookkeeping and explicit native services.
-- No global callback registration, JIT, installation, engine call at load, or
-- sprite lifetime inference. See regeneration-adapter-contract.md.
return function(api,cacheFactory,recoveryFactory)
    local function check(v,m) if not v then error("CBR regeneration adapter: "..m,0) end end
    local function int(v,lo,hi,m)
        check(type(v)=="number" and v==math.floor(v) and v>=lo and v<=hi,"invalid "..m); return v
    end
    local function ptr(v) return int(v,1,9007199254740991-0x10000,"pointer") end
    check(type(api)=="table" and type(cacheFactory)=="function" and type(recoveryFactory)=="function","missing factories")
    for _,name in ipairs({"ptr","now","original","isCurrentOriginal","spriteIdentity","readPtr","readU32",
        "readI32","readU16","readBytes","writePtr","writeU32","writeU16","writeBytes",
        "allocScratch","freeScratch","report"}) do
        check(type(api[name])=="function","missing capability "..name)
    end
    check(type(api.services)=="table","missing native services")
    for _,name in ipairs({"allocate","insert","dispose"}) do
        check(type(api.services[name])=="function","missing native service "..name)
    end
    local base=int(api.imageBase,0x10000,9007199254740991-0x3500000,"image base")
    local regenVtable,listVtable=base+0x598B18,base+0x58F528
    local M={callbacks={}}
    local cacheIds,lists,frames,handles={}, {}, {}, {}
    local generation,fault,service={},nil,nil
    local cache
    local function healthy() check(not fault,"halted: "..tostring(fault)) end
    local function token(p)
        ptr(p)
        if not cacheIds[p] then cacheIds[p]={} end
        return cacheIds[p]
    end
    local function knownList(pointer) return lists[pointer] end
    local function associate(sprite,required)
        ptr(sprite)
        local id=api.spriteIdentity(sprite)
        if id==nil then check(not required,"sprite lifetime unavailable"); return nil end
        check(type(id)=="table","sprite identity must be an opaque lifetime token")
        local p=sprite+0x1A08
        local l=lists[p]
        if l then check(l.spriteIdentity==id,"sprite address reused without retirement")
        else l={pointer=p,identity={},sprite=sprite,spriteIdentity=id}; lists[p]=l end
        check(api.readPtr(p)==listVtable,"wrong regenerated-list class")
        return l
    end
    local function readList(sprite)
        local l=associate(sprite,true)
        int(api.readU32(l.pointer+0x30),1,2147483647,"native pool block count")
        local count=int(api.readU32(l.pointer+0x18),0,4096,"list count")
        local counter=int(api.readU32(l.pointer+0x38),0,2147483646,"list counter")
        local head,tail=api.readPtr(l.pointer+8),api.readPtr(l.pointer+0x10)
        local entries,nodes,pointers={}, {}, {}
        local node,previous=head,0
        while node~=0 do
            ptr(node); check(not nodes[node] and #entries<count,"cyclic/oversized native list")
            nodes[node]=true
            check(api.readPtr(node+8)==previous,"native previous-node link mismatch")
            local p=ptr(api.readPtr(node+0x10))
            check(not pointers[p],"duplicate current cache pointer"); pointers[p]=true
            entries[#entries+1]={pointer=p,identity=token(p),node=node}
            previous,node=node,api.readPtr(node)
        end
        check(#entries==count and previous==tail and ((count==0)==(head==0 and tail==0)),"native list count/tail mismatch")
        return {pointer=l.pointer,identity=l.identity,counter=counter,entries=entries}
    end
    local function readCache(p)
        ptr(p)
        local c={vtable=api.readPtr(p),done=api.readU32(p+8)~=0,canceled=api.readU32(p+0xC)~=0}
        -- Unrelated successor classes can be only0x20 bytes. Never read the
        -- regeneration-specific tail until the exact class is established.
        if c.vtable==regenVtable then
            c.mode=api.readU16(p+0x20); c.interval=api.readU16(p+0x18)
            c.phase=api.readU16(p+0x1A); c.amount=api.readU16(p+0x24)
            c.remaining=api.readI32(p+0x28)
        end
        return c
    end
    local function currentMember(l,p,node)
        for _,e in ipairs(l.entries) do
            if e.pointer==p and (node==nil or e.node==node) then return e end
        end
    end
    local function freshList(p,id)
        local known=knownList(p)
        check(known and known.identity==id,"retired list lifetime")
        local l=readList(known.sprite)
        check(l.identity==id,"changed list lifetime"); return l
    end
    local function beginService(kind,h)
        check(not service,"native service reentry")
        service={kind=kind,handle=h}
    end
    local function callService(kind,h)
        beginService(kind,h)
        local ok,status=pcall(api.services[kind],h.request)
        service=nil
        if not ok then error(status,0) end
        int(status,0,4,"native service status")
        return status
    end
    local function freeScratch(h)
        if h.snapshot then api.freeScratch(h.snapshot); h.snapshot=nil end
        if h.request then api.freeScratch(h.request); h.request=nil end
        handles[h]=nil
    end
    local function outputs(h)
        return api.readPtr(h.request+0x18),api.readPtr(h.request+0x20),api.readPtr(h.request+0x38)
    end
    local function allocation(state,changes,l)
        healthy()
        check(type(state)=="string" and #state==48,"wrong snapshot length")
        local current=freshList(l.pointer,l.identity)
        check(current.counter==l.counter,"counter changed before allocation")
        local block=int(api.readU32(l.pointer+0x30),1,2147483647,"native pool block count")
        local h={list=l.pointer,listIdentity=l.identity,counter=l.counter,adopted=false,uncertain=false}
        handles[h]=true
        -- Keep each scratch handle as soon as obtained, including later failures.
        h.request=ptr(api.allocScratch(64)); api.writeBytes(h.request,string.rep("\0",64))
        h.snapshot=ptr(api.allocScratch(48)); api.writeBytes(h.snapshot,state)
        api.writePtr(h.request,h.snapshot)
        api.writeU32(h.request+8,int(changes.remaining,1,2147483647,"remaining"))
        api.writeU16(h.request+0xC,int(changes.phase,0,32766,"phase"))
        api.writeU32(h.request+0x10,block)
        h.engineAttempted=true
        local ok,status=pcall(callService,"allocate",h)
        if not ok then h.uncertain=true; error(status,0) end
        local p,pool,node=outputs(h)
        h.pointer=p~=0 and ptr(p) or nil
        if node~=0 then h.uncertain=true end
        check(node==0,"allocation unexpectedly adopted a node")
        if status~=0 then
            -- Null outputs prove no engine allocation remains; status4 may
            -- retain a detached cache. Keep its request visible for cleanup.
            if p==0 and pool==0 then freeScratch(h) end
            error("CBR regeneration adapter: native allocation status "..status,0)
        end
        if p==0 or pool==0 or cacheIds[p] then h.uncertain=true end
        check(p~=0 and pool~=0 and not cacheIds[p],"allocation pointer/lifetime collision")
        h.identity=token(p)
        healthy() -- A callback failure during the service cannot be ignored.
        return h
    end
    local function insertion(p,id,h,node)
        healthy()
        check(handles[h] and not h.adopted and not h.uncertain,"invalid detached allocation")
        local l=freshList(p,id)
        check(p==h.list and id==h.listIdentity and l.counter==h.counter,"allocation target changed")
        if node~=0 then
            local found=false
            for _,e in ipairs(l.entries) do if e.node==node then found=true end end
            check(found,"successor node is no longer current")
        end
        check(not currentMember(l,h.pointer),"detached cache already belongs to list")
        check(cacheIds[h.pointer]==h.identity,"detached cache lifetime changed")
        api.writePtr(h.request+0x28,p); api.writePtr(h.request+0x30,node)
        local ok,status=pcall(callService,"insert",h)
        if not ok then h.uncertain=true; error(status,0) end
        local cp,pool,adopted=outputs(h)
        if status~=0 then
            -- Known service1/2 returns precede adoption. Anything inconsistent
            -- is uncertain: never free it as detached after a native failure.
            if adopted~=0 or cp~=h.pointer then h.uncertain=true end
            error("CBR regeneration adapter: native insert status "..status,0)
        end
        h.adopted=true
        check(cp==0 and pool==0 and adopted~=0,"service adoption outputs inconsistent")
        local after=freshList(p,id)
        check(after.counter==h.counter and currentMember(after,h.pointer,adopted),"adopted cache/node missing")
        healthy()
        freeScratch(h)
    end
    local function disposal(h)
        check(handles[h] and not h.adopted and not h.uncertain,"refusing to dispose adopted/uncertain allocation")
        local p=api.readPtr(h.request+0x18)
        h.pointer=p~=0 and p or h.pointer
        local status=callService("dispose",h)
        local cp,pool,node=outputs(h)
        check(status==0 and cp==0 and pool==0 and node==0,"native detached disposal incomplete")
        if h.pointer then cacheIds[h.pointer]=nil end
        freeScratch(h)
    end
    local cacheApi={regenerationVtable=regenVtable,ptr=api.ptr,original=api.original,
        isCurrentOriginal=api.isCurrentOriginal,now=api.now,cache=readCache,
        currentCaches=function(s) local out={}; for i,e in ipairs(readList(s).entries) do out[i]=e.pointer end; return out end,
        writeRemaining=function(p,n)
            healthy(); check(not service,"countdown write during service")
            api.writeU32(p+0x28,int(n,1,2147483647,"cache countdown"))
        end,
        recovery={list=readList,capture=function(p)
            check(readCache(p).vtable==regenVtable,"capture of unrelated cache class")
            check(api.readU32(p+8)==1 and api.readU32(p+0xC)==0 and api.readU16(p+0x12)==5
                and api.readI32(p+0x28)==0,"snapshot not exact native natural-death state")
            local bytes=api.readBytes(p,48); check(type(bytes)=="string" and #bytes==48,"invalid native snapshot")
            return bytes
        end,allocate=allocation,insert=insertion,dispose=disposal},
    }
    cache=cacheFactory(cacheApi,recoveryFactory)
    local function normal() healthy(); check(not service,"unexpected lifecycle callback during native service") end
    local function bindCallback(name,fn)
        M.callbacks[name]=function(...)
            if fault and not service then return false end
            local ok,result=pcall(fn,...)
            if not ok then
                fault=tostring(result)
                -- Reporting must not let a native callback throw through Lua.
                pcall(api.report,fault)
                return false
            end
            return result
        end
    end
    bindCallback("updateEnter",function(list,sprite,delta,key)
        normal(); ptr(list); ptr(key)
        for _,f in ipairs(frames) do check(f.key~=key,"live native frame key reused") end
        local l=associate(sprite,false)
        local f={list=list,key=key,generation=generation}
        if l then
            check(l.pointer==list,"sprite/list mismatch")
            check(delta==1,"unproved native list delta")
            f.frame=cache.onUpdateEnter(sprite,list)
        end
        frames[#frames+1]=f
        return true
    end)
    bindCallback("updateExit",function(list,key)
        normal()
        local f=frames[#frames]
        check(f and f.key==key and f.list==list,"unbalanced native update exit")
        frames[#frames]=nil
        if f.generation~=generation or not f.frame then return false end
        return cache.onUpdateExit(f.frame)
    end)
    bindCallback("naturalDeath",function(p) normal(); return cache.onNaturalDeath(ptr(p)) end)
    bindCallback("beforeRemove",function(list,p,node)
        normal()
        local l=knownList(list)
        if not l then return false end
        local current=readList(l.sprite)
        check(currentMember(current,p,node),"removal pointer/node is not current")
        return cache.onBeforeRemove(p)
    end)
    local function cancel(list)
        normal()
        local l=knownList(list)
        if not l then return false end
        cache.onCancelList(l.sprite); return true
    end
    bindCallback("clear",cancel)
    bindCallback("replace",function(destination) return cancel(destination) end)
    bindCallback("removeType",function(list,kind)
        normal(); if kind~=5 then return false end; return cancel(list)
    end)
    bindCallback("listDestroy",function(list)
        local result=cancel(list); lists[list]=nil; return result
    end)
    bindCallback("cacheDestroy",function(p)
        ptr(p)
        if service then
            local h=service.handle
            check(service.kind=="dispose" and h.pointer==p and not h.adopted and not h.uncertain,
                "unexpected cache destruction during native service")
            cacheIds[p]=nil
            return true -- Detached cleanup: no recursive recovery/module event.
        end
        healthy(); cache.onCacheDestroy(p); cacheIds[p]=nil; return true
    end)
    bindCallback("copy",function(old,new)
        normal(); ptr(old); ptr(new)
        check(not cacheIds[new],"copy reused a live cache pointer")
        token(new)
        return cache.onCopy(old,new)
    end)
    bindCallback("appendOwned",function(original,p,sprite)
        normal(); local l=associate(sprite,false)
        if not l then return false end
        local current=readList(sprite)
        check(current.entries[#current.entries] and current.entries[#current.entries].pointer==p,"owned append is not tail")
        return cache.onAppend(original,p,sprite)
    end)
    bindCallback("append",function(list,p,node,returnAddress)
        ptr(list); ptr(p); ptr(node)
        if service then
            local h=service.handle
            check(service.kind=="insert" and h.pointer==p and h.list==list and not h.adopted,
                "unexpected append during native service")
            local l=freshList(list,h.listIdentity)
            check(currentMember(l,p,node) and l.entries[#l.entries].pointer==p and l.counter==h.counter,
                "staged native append did not adopt the expected tail")
            return true -- Recovery records its known replacement, not an append.
        end
        normal()
        local known=knownList(list)
        if not known then return false end
        local l=readList(known.sprite)
        check(currentMember(l,p,node) and l.entries[#l.entries].pointer==p,"append is not current tail")
        if returnAddress==base+0x1BEDE5 then return false end -- appendOwned handles order once.
        return cache.onNativeAppend(known.sprite,p)
    end)
    function M.prepare(plan,sprite)
        healthy(); check(not service,"prepare during native service")
        check(type(plan)=="table" and type(plan.refresh)=="table","invalid core plan")
        local s=ptr(api.ptr(sprite)); associate(s,true)
        for _,u in ipairs(plan.refresh) do
            local p=ptr(api.ptr(u.record)); local o=api.original(p)
            check(o and o.identity==u.identity and api.isCurrentOriginal(s,p,u.identity),"refresh is not current sprite effect")
        end
        local transaction=cache.prepare(plan.refresh)
        local used=false
        return {commit=function()
            healthy(); check(not used,"adapter transaction already used"); used=true
            local ok,result=pcall(transaction.commit)
            if not ok then fault=tostring(result); pcall(api.report,fault); error(fault,0) end
            return result
        end}
    end
    function M.onOriginalDestroy(p) normal(); cache.onOriginalDestroy(ptr(p)) end
    function M.onSpriteDestroy(sprite)
        normal(); ptr(sprite)
        local l=lists[sprite+0x1A08]
        if l then cache.onListDestroy(sprite); lists[l.pointer]=nil end
    end
    function M.reset()
        check(not service,"reset during service")
        cache.reset(); cacheIds,lists={},{}; generation={}
        -- Keep old stack sentinels to pair late exits without touching old data.
        for _,f in ipairs(frames) do f.frame=nil end
        check(next(handles)==nil,"reset retains unresolved native allocation ownership")
        fault=nil
    end
    function M.status()
        local out={halted=fault~=nil,error=fault,pending={}}
        for h in pairs(handles) do out.pending[#out.pending+1]={pointer=h.pointer,request=h.request,
            adopted=h.adopted,uncertain=h.uncertain} end
        return out
    end
    function M.cleanupDetached()
        check(not service,"cleanup during service")
        local done=0
        for h in pairs(handles) do
            if not h.adopted and not h.uncertain then
                if not h.engineAttempted then freeScratch(h)
                else disposal(h) end
                done=done+1
            end
        end
        return done
    end
    return M
end
