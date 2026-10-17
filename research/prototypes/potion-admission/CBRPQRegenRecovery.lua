-- Optional, bounded natural-cache-death recovery. No autoload/native adapter.
-- api.recovery MUST implement the separately reviewed allocation/insertion
-- capability before this factory is used. prepare is read-only. commit and the
-- after-counter-increment exit callback can allocate and insert native objects.
return function(api, host)
    local function check(ok, message)
        if not ok then error("CBR potion regeneration recovery: " .. message, 0) end
    end
    local function integer(value, low, high, name)
        check(type(value)=="number" and value==math.floor(value) and value>=low and value<=high,
            "invalid " .. name)
        return value
    end
    local U32, I32, EXACT = 4294967295, 2147483647, 9007199254740991
    local function pointer(p) return integer(p, 1, EXACT-0x6000, "pointer") end
    local function token(t) check(type(t)=="table", "missing opaque lifetime token"); return t end
    local A = api.recovery
    check(type(A)=="table", "native allocation/insertion adapter unavailable")
    for _, name in ipairs({"list", "capture", "allocate", "insert", "dispose"}) do
        check(type(A[name])=="function", "native capability unavailable: " .. name)
    end
    local snapshots, markers, frames, active, pending, sessions = {}, {}, {}, {}, {}, {}
    local generation, serial, busy = {}, 0, false
    local M = {}
    local function readList(sprite)
        local l = A.list(sprite)
        check(type(l)=="table", "missing current list")
        pointer(l.pointer); token(l.identity)
        integer(l.counter, 0, I32-1, "bounded list counter")
        check(type(l.entries)=="table", "missing ordered list entries")
        local result, seenPointers, seenTokens, seenNodes, count = {}, {}, {}, {}, 0
        for key in pairs(l.entries) do
            integer(key, 1, #l.entries, "list entry index"); count=count+1
        end
        check(count==#l.entries and count<=4096, "sparse/oversized cache list")
        for i=1,count do
            local e=l.entries[i]
            check(type(e)=="table", "invalid list entry")
            pointer(e.pointer); pointer(e.node); token(e.identity)
            check(not seenPointers[e.pointer] and not seenTokens[e.identity] and not seenNodes[e.node],
                "duplicate current cache/node lifetime")
            seenPointers[e.pointer],seenTokens[e.identity],seenNodes[e.node]=true,true,true
            result[i]={pointer=e.pointer, identity=e.identity, node=e.node}
        end
        return {pointer=l.pointer,identity=l.identity,counter=l.counter,entries=result}
    end
    local function cancel(owner)
        local s=snapshots[owner]
        if s then
            local group=pending[s.listIdentity]
            if group then group[s]=nil; if next(group)==nil then pending[s.listIdentity]=nil end end
            snapshots[owner]=nil
            s.session.owners[owner]=nil
            if next(s.session.owners)==nil then sessions[s.listIdentity]=nil end
        end
    end
    local function notBusy() check(not busy, "native adapter reentered recovery lifecycle") end
    local function currentPosition(s, now, duringPass)
        check(snapshots[s.owner]==s and s.retired, "missing retired natural-death snapshot")
        check(now==s.deathTime and s.oldExpiry==now+1, "outside proved expiry-minus-one window")
        check(not host.hasCurrent(s.owner), "original already has a current cache")
        local l=readList(s.owner.sprite)
        check(l.pointer==s.listPointer and l.identity==s.listIdentity, "list lifetime changed")
        local elapsed=l.counter+(duringPass and 1 or 0)-s.processedCounter
        check(elapsed>=0 and elapsed<15, "outside bounded elapsed-list-update window")
        local cursor, nextNode=1,0
        for _, e in ipairs(l.entries) do
            while cursor<=#s.order and s.order[cursor].identity~=e.identity do cursor=cursor+1 end
            check(cursor<=#s.order and s.order[cursor].pointer==e.pointer,
                "new/reordered/reused cache lifetime")
            local c=api.cache(e.pointer)
            check(type(c)=="table" and (duringPass or (c.done==false and c.canceled==false)),
                "current predecessor/successor is done or canceled")
            if cursor>s.index and nextNode==0 then nextNode=e.node end
            cursor=cursor+1
        end
        return l,nextNode,elapsed
    end
    local function fields(s, expiry, elapsed, counter)
        local remaining=s.remaining+(expiry-s.oldExpiry)-elapsed
        integer(remaining,1,I32,"reconstructed countdown")
        local phase=s.phase
        if s.mode==3 then
            phase=(phase+math.floor(counter/15)-math.floor(s.processedCounter/15))%s.interval
        end
        return {remaining=remaining,phase=phase,done=false}
    end
    local function target(s, expiry, now)
        host.liveOwner(s.owner,expiry,now)
        local l,node,elapsed=currentPosition(s,now)
        return l,node,fields(s,expiry,elapsed,l.counter)
    end

    function M.onUpdateEnter(sprite, listPointer)
        notBusy(); pointer(sprite); pointer(listPointer)
        local now=integer(api.now(),0,U32,"world time")
        for owner,s in pairs(snapshots) do if s.deathTime~=now then cancel(owner) end end
        local l=readList(sprite)
        check(l.pointer==listPointer, "wrong list entry pointer")
        check(l.counter<I32-1,"list update is outside bounded nonwrapping counter range")
        check(active[l.identity]==nil, "nested update of same list is not proved")
        local f={sprite=sprite,pointer=l.pointer,identity=l.identity,counter=l.counter,generation=generation}
        frames[#frames+1],active[l.identity]=f,f
        return f
    end
    function M.onNaturalDeath(cachePointer)
        notBusy(); pointer(cachePointer)
        local b=host.binding(cachePointer)
        if not b then return false end
        local l=readList(b.owner.sprite)
        local f=active[l.identity]
        check(f and f.pointer==l.pointer and f.counter==l.counter, "natural death outside exact native pass")
        markers[b]=f
        return true
    end
    function M.onBeforeRemove(cachePointer)
        notBusy(); pointer(cachePointer)
        local b=host.binding(cachePointer)
        if not b then return false end
        local f=markers[b]
        markers[b]=nil
        if not f then return false end -- Cancellation is never natural expiry.
        local c=api.cache(cachePointer)
        if not c or c.canceled~=false then cancel(b.owner); return false end
        check(c.vtable==api.regenerationVtable and c.done==true and c.remaining==0,
            "unproved natural-death cache state")
        local now=integer(api.now(),0,U32,"world time")
        local o=api.original(b.owner.pointer)
        if not o or o.identity~=b.owner.identity or o.done or o.expiry~=now+1 then
            cancel(b.owner); return false -- Ordinary death outside our recovery window.
        end
        local l=readList(b.owner.sprite)
        check(f.generation==generation and active[l.identity]==f and l.counter==f.counter,
            "native update frame changed")
        integer(c.mode,2,3,"regeneration mode")
        integer(c.interval,1,32767,"regeneration interval")
        integer(c.phase,0,c.interval-1,"regeneration phase")
        integer(c.amount,0,65535,"regeneration heal amount")
        local session=sessions[l.identity]
        if not session then
            session={order={},owners={}}
            for i,e in ipairs(l.entries) do session.order[i]={pointer=e.pointer,identity=e.identity} end
        end
        local order,index,cursor=session.order,nil,1
        for _,e in ipairs(l.entries) do
            while cursor<=#order and order[cursor].identity~=e.identity do cursor=cursor+1 end
            check(cursor<=#order and order[cursor].pointer==e.pointer,
                "new/reordered cache during removal history")
            if e.pointer==cachePointer then index=cursor end
            cursor=cursor+1
        end
        check(index~=nil, "removed cache is not current list member")
        local state=A.capture(cachePointer)
        check(type(state)=="string" and #state==0x30, "snapshot must be immutable native cache bytes")
        cancel(b.owner)
        sessions[l.identity]=session
        session.owners[b.owner]=true
        snapshots[b.owner]={owner=b.owner,binding=b,listPointer=l.pointer,listIdentity=l.identity,
            session=session,order=order,index=index,state=state,oldExpiry=o.expiry,deathTime=now,
            processedCounter=l.counter+1,remaining=0,mode=c.mode,interval=c.interval,phase=c.phase,
            amount=c.amount,retired=false,serial=serial}
        return true
    end
    function M.onCacheDestroy(binding)
        if not binding then return end
        notBusy()
        markers[binding]=nil
        local s=snapshots[binding.owner]
        if s and s.binding==binding then s.retired=true end
    end
    function M.onNativeAppend(sprite, cachePointer)
        notBusy(); pointer(sprite); pointer(cachePointer)
        local l=readList(sprite)
        local session=sessions[l.identity]
        if not session then return false end
        local appended=l.entries[#l.entries]
        check(appended and appended.pointer==cachePointer,"observed append is not current native tail")
        local cursor=1
        for i,entry in ipairs(l.entries) do
            if i<#l.entries then
                while cursor<=#session.order and session.order[cursor].identity~=entry.identity do cursor=cursor+1 end
                check(cursor<=#session.order and session.order[cursor].pointer==entry.pointer,
                    "append observation contains another unknown/reordered cache")
                cursor=cursor+1
            end
        end
        for _,entry in ipairs(session.order) do
            check(entry.identity~=appended.identity,"duplicate native append lifetime")
        end
        -- A proved AddTail event belongs after all prior logical positions,
        -- including naturally retired positions retained for recovery. Pointer
        -- reuse is valid only with the new lifetime supplied by this event.
        session.order[#session.order+1]={pointer=appended.pointer,identity=appended.identity}
        return true
    end
    function M.onAppend(owner) notBusy(); cancel(owner) end
    function M.onOriginalDestroy(owner)
        notBusy(); cancel(owner)
        for binding in pairs(markers) do if binding.owner==owner then markers[binding]=nil end end
    end
    function M.onCancelList(sprite)
        notBusy(); pointer(sprite)
        for owner in pairs(snapshots) do if owner.sprite==sprite then cancel(owner) end end
        for b in pairs(markers) do if b.owner.sprite==sprite then markers[b]=nil end end
    end
    M.onListDestroy=M.onCancelList
    function M.reset()
        notBusy()
        snapshots,markers,frames,active,pending,sessions={},{},{},{},{},{}
        generation={}; serial=serial+1
    end

    function M.prepare(owner, before, after, now)
        notBusy()
        local s=snapshots[owner]
        check(s and s.retired, "missing current cache has no recoverable natural-death snapshot")
        local expected=s.pendingExpiry or s.oldExpiry
        check(before==expected, "pending original deadline changed outside recovery")
        check(after>=before and after>s.oldExpiry, "missing-cache recovery requires nonshortening extension")
        host.liveOwner(owner,before,now)
        -- During the current pass, the counter has not yet incremented. Native
        -- reconstruction waits; preflight uses the common exit's future value.
        local l=readList(owner.sprite)
        local f=active[s.listIdentity]
        if f then
            check(l.pointer==s.listPointer and l.identity==s.listIdentity and l.counter==f.counter,
                "deferred pass counter changed")
            check(now==s.deathTime and now+1==s.oldExpiry and not host.hasCurrent(owner),
                "deferred original/window changed")
            local _,_,elapsed=currentPosition(s,now,true)
            fields(s,after,elapsed,l.counter+1)
        else
            local _,_,elapsed=currentPosition(s,now)
            fields(s,after,elapsed,l.counter)
        end
        return {snapshot=s,listIdentity=s.listIdentity,expiry=after,before=before,
            frame=f,generation=generation,serial=s.serial}
    end
    function M.validate(t,now)
        notBusy()
        check(t.generation==generation and snapshots[t.snapshot.owner]==t.snapshot and
            t.serial==t.snapshot.serial, "recovery ticket became stale")
        host.liveOwner(t.snapshot.owner,t.expiry,now)
        check(active[t.listIdentity]==t.frame, "native update frame changed after prepare")
        if t.frame then
            local l=readList(t.snapshot.owner.sprite)
            check(l.identity==t.listIdentity and l.pointer==t.snapshot.listPointer and
                l.counter==t.frame.counter and now==t.snapshot.deathTime,
                "deferred recovery window changed")
            check(not host.hasCurrent(t.snapshot.owner), "current cache appeared after prepare")
            currentPosition(t.snapshot,now,true)
        else target(t.snapshot,t.expiry,now) end
    end

    local function reconstructBatch(items)
        local now=integer(api.now(),0,U32,"world time")
        for _,item in ipairs(items) do
            local s=item.snapshot
            check(active[s.listIdentity]==nil, "cannot insert during native list iteration")
            item.list,item.node,item.changes=target(s,item.expiry,now)
        end
        -- All caches are staged before any list insertion. A failure here can
        -- dispose detached allocations; original Core expiry writes remain.
        busy=true
        local staged,allocationPointers,allocationTokens={},{},{}
        local checked,err=pcall(function()
            for _,item in ipairs(items) do
                local allocation=A.allocate(item.snapshot.state,item.changes,item.list)
                check(type(allocation)=="table", "native allocation failed")
                pointer(allocation.pointer); token(allocation.identity)
                check(not allocationPointers[allocation.pointer] and not allocationTokens[allocation.identity],
                    "allocator reused staged pointer/lifetime")
                for _,other in ipairs(items) do
                    for _,entry in ipairs(other.list.entries) do
                        check(entry.pointer~=allocation.pointer and entry.identity~=allocation.identity,
                            "allocator returned an existing live cache")
                    end
                end
                allocationPointers[allocation.pointer],allocationTokens[allocation.identity]=true,true
                item.allocation=allocation; staged[#staged+1]=item
                local c=api.cache(allocation.pointer)
                local s,changes=item.snapshot,item.changes
                check(c and c.vtable==api.regenerationVtable and c.done==false and c.canceled==false and
                    c.remaining==changes.remaining and c.phase==changes.phase and
                    c.mode==s.mode and c.interval==s.interval and c.amount==s.amount,
                    "allocator did not restore exact cache fields")
            end
            for _,item in ipairs(items) do
                local l,node,changes=target(item.snapshot,item.expiry,integer(api.now(),0,U32,"world time"))
                check(l.pointer==item.list.pointer and l.identity==item.list.identity and node==item.node and
                    changes.remaining==item.changes.remaining and changes.phase==item.changes.phase,
                    "allocation changed native state")
            end
        end)
        if not checked then
            local cleanupErrors={}
            for _,item in ipairs(staged) do
                local ok,e=pcall(A.dispose,item.allocation)
                if not ok then cleanupErrors[#cleanupErrors+1]=tostring(e) end
            end
            busy=false
            if #cleanupErrors>0 then error(tostring(err).."; detached cleanup failed: "..table.concat(cleanupErrors,"; "),0) end
            error(err,0)
        end
        table.sort(items,function(a,b) return a.snapshot.index>b.snapshot.index end)
        -- Insertion can fail after changing a native list. Never guess whether
        -- it is detached or free it blindly; no rollback guarantee is made.
        local inserted,insertError=pcall(function()
            for _,item in ipairs(items) do
                local s,allocation=item.snapshot,item.allocation
                local l,node=target(s,item.expiry,integer(api.now(),0,U32,"world time"))
                A.insert(l.pointer,l.identity,allocation,node)
                local expected,placed={},false
                for _,entry in ipairs(l.entries) do
                    if entry.node==node then
                        expected[#expected+1]=allocation; placed=true
                    end
                    expected[#expected+1]=entry
                end
                if node==0 then expected[#expected+1]=allocation; placed=true end
                check(placed,"successor disappeared before native insertion")
                local actual=readList(s.owner.sprite)
                check(actual.pointer==l.pointer and actual.identity==l.identity and actual.counter==l.counter and
                    #actual.entries==#expected,"native insertion changed unrelated list state")
                for i,entry in ipairs(expected) do
                    check(actual.entries[i].pointer==entry.pointer and actual.entries[i].identity==entry.identity,
                        "native insertion did not preserve exact cache order/lifetimes")
                end
                host.bindRecovered(s.owner,allocation.pointer)
                -- This is a known replacement at exactly the retired position.
                -- Later fresh traversal may recognize our own new lifetime.
                s.order[s.index]={pointer=allocation.pointer,identity=allocation.identity}
                cancel(s.owner)
            end
        end)
        busy=false
        if not inserted then error(insertError,0) end
    end
    function M.commitBatch(tickets)
        local groups={}
        for _,t in ipairs(tickets) do M.validate(t,integer(api.now(),0,U32,"world time")) end
        for _,t in ipairs(tickets) do
            local s=t.snapshot
            s.serial=s.serial+1
            if t.frame then
                s.pendingExpiry=t.expiry
                pending[s.listIdentity]=pending[s.listIdentity] or {}
                pending[s.listIdentity][s]=true
            else
                groups[s.listIdentity]=groups[s.listIdentity] or {}
                local group=groups[s.listIdentity]
                group[#group+1]={snapshot=s,expiry=t.expiry}
            end
        end
        for _,items in pairs(groups) do reconstructBatch(items) end
    end
    function M.commit(t)
        M.commitBatch({t})
        return t.frame and "deferred" or "reconstructed"
    end
    function M.onUpdateExit(frame)
        notBusy()
        check(type(frame)=="table", "invalid native update frame")
        if frame.generation~=generation then return false end
        check(frames[#frames]==frame and active[frame.identity]==frame, "unbalanced native list exit")
        local l=readList(frame.sprite)
        check(l.pointer==frame.pointer and l.identity==frame.identity and l.counter==frame.counter+1,
            "exit is not the exact after-counter-increment boundary")
        frames[#frames],active[frame.identity]=nil,nil
        local group=pending[frame.identity]
        if group then
            pending[frame.identity]=nil
            local items={}
            for s in pairs(group) do items[#items+1]={snapshot=s,expiry=s.pendingExpiry} end
            reconstructBatch(items)
        end
        return true
    end
    return M
end
