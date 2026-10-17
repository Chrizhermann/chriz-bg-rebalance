-- Original98 -> native regenerated-cache lifetime bookkeeping. No autoload,
-- hooks or EEex calls. The caller supplies a read/write adapter and installs
-- separately verified append, Copy, cache/original destructor and reset hooks.
-- Never infer cache ownership from equal healing amount, interval or source.
return function(api, recoveryFactory)
    local function check(ok, message)
        if not ok then error("CBR potion regeneration: " .. message, 0) end
    end
    local function integer(value, low, high, name)
        check(type(value) == "number" and value == math.floor(value)
            and value >= low and value <= high, "invalid " .. name)
        return value
    end
    local U32, I32, EXACT = 4294967295, 2147483647, 9007199254740991
    local function pointer(value)
        return integer(value, 1, EXACT - 0x6000, "native pointer")
    end
    local function array(value, name)
        check(type(value) == "table", "invalid " .. name)
        local n, count = #value, 0
        for key in pairs(value) do
            integer(key, 1, n, name .. " index")
            count = count + 1
        end
        check(count == n, "sparse " .. name)
        for i = 1, n do check(value[i] ~= nil, "sparse " .. name) end
        return n
    end
    check(type(api) == "table", "missing adapter")
    for _, name in ipairs({"ptr", "original", "isCurrentOriginal", "currentCaches", "cache", "now", "writeRemaining"}) do
        check(type(api[name]) == "function", "missing adapter " .. name)
    end
    local vtable = pointer(api.regenerationVtable)
    local originals, caches, revision = {}, {}, 0
    local M, recovery = {}, nil

    local function original(pointerValue)
        local record = api.original(pointerValue)
        if record == nil then return nil end
        check(type(record) == "table" and record.identity ~= nil, "missing original lifetime")
        integer(record.opcode, 0, U32, "original opcode")
        integer(record.timing, 0, U32, "original timing")
        integer(record.expiry, 0, U32, "original expiry")
        check(type(record.done) == "boolean", "invalid original done flag")
        return record
    end
    local function detach(binding)
        caches[binding.pointer] = nil
        binding.owner.caches[binding] = nil
    end
    local function bind(owner, cachePointer)
        local binding = {pointer = cachePointer, owner = owner, lifetime = {}}
        caches[cachePointer], owner.caches[binding] = binding, true
    end

    function M.onAppend(originalPointer, cachePointer, spritePointer)
        pointer(originalPointer); pointer(cachePointer); pointer(spritePointer)
        check(caches[cachePointer] == nil, "live cache pointer reused at append")
        if recovery then recovery.onNativeAppend(spritePointer,cachePointer) end
        -- The native append callback proves these pointers exist now. On first
        -- Apply the original may not yet be inserted into the timed list.
        local record = original(originalPointer)
        if not record or record.opcode ~= 98 then return false end
        local owner = originals[originalPointer]
        if owner then
            check(owner.identity == record.identity and owner.sprite == spritePointer,
                "original lifetime changed without destruction")
        else
            owner = {pointer = originalPointer, identity = record.identity,
                sprite = spritePointer, caches = {}}
        end
        originals[originalPointer] = owner
        bind(owner, cachePointer)
        if recovery then recovery.onAppend(owner) end
        revision = revision + 1
        return true
    end

    function M.onCopy(oldCache, newCache)
        pointer(oldCache); pointer(newCache)
        check(caches[newCache] == nil, "live cache pointer reused at copy")
        local binding = caches[oldCache]
        if not binding then return false end
        -- A copied snapshot is tracked, but is never selected unless it later
        -- appears in this original's actual sprite regenerated-effect list.
        bind(binding.owner, newCache)
        revision = revision + 1
        return true
    end

    function M.onCacheDestroy(cachePointer)
        pointer(cachePointer)
        local binding = caches[cachePointer]
        if recovery then recovery.onCacheDestroy(binding) end
        if binding then detach(binding); revision = revision + 1 end
    end

    function M.onOriginalDestroy(originalPointer)
        pointer(originalPointer)
        local owner = originals[originalPointer]
        if owner then
            if recovery then recovery.onOriginalDestroy(owner) end
            -- No native reads: the caller may be at the start of destruction.
            for binding in pairs(owner.caches) do caches[binding.pointer] = nil end
            originals[originalPointer] = nil
            revision = revision + 1
        end
    end

    function M.reset()
        if recovery then recovery.reset() end
        originals, caches = {}, {}
        revision = revision + 1
    end

    local function liveOwner(owner, expiry, now)
        check(originals[owner.pointer] == owner, "retired original lifetime")
        check(api.isCurrentOriginal(owner.sprite, owner.pointer, owner.identity) == true,
            "original is not a current timed effect")
        local current = original(owner.pointer)
        check(current and current.identity == owner.identity and current.opcode == 98,
            "original identity changed")
        check(current.timing == 4096 and not current.done and current.expiry == expiry and expiry > now,
            "original timing/expiry changed or expired")
    end

    local function currentBinding(owner, allowMissing)
        local list, selected, seen = api.currentCaches(owner.sprite), nil, {}
        for index = 1, array(list, "current cache list") do
            local p = pointer(list[index])
            check(not seen[p], "duplicate current cache pointer")
            seen[p] = true
            local binding = caches[p]
            if binding and binding.owner == owner then
                check(selected == nil, "multiple current caches for original")
                selected = binding
            end
        end
        check(selected ~= nil or allowMissing, "missing current cache lineage")
        return selected
    end

    local function countdown(binding)
        check(caches[binding.pointer] == binding, "retired cache lifetime")
        local current = api.cache(binding.pointer)
        check(type(current) == "table" and current.vtable == vtable, "wrong regeneration cache class")
        check(type(current.done) == "boolean" and type(current.canceled) == "boolean",
            "invalid cache flags")
        check(not current.done and not current.canceled, "done or canceled regeneration cache")
        integer(current.remaining, -2147483648, I32, "signed cache countdown")
        check(current.remaining ~= -1, "unsupported cache countdown sentinel -1")
        check(current.remaining > 0, "nonpositive cache countdown")
        return current.remaining
    end

    function M.prepare(refreshUpdates)
        local count = array(refreshUpdates, "refresh updates")
        local now = integer(api.now(), 0, U32, "world time")
        local prepared, seen = {}, {}
        for index = 1, count do
            local update = refreshUpdates[index]
            check(type(update) == "table" and update.record ~= nil, "invalid refresh update")
            local p = pointer(api.ptr(update.record))
            check(not seen[p], "duplicate original refresh")
            seen[p] = true
            local before = integer(update.oldExpiry, 0, U32, "old expiry")
            local after = integer(update.expiry, 0, U32, "new expiry")
            local record = original(p)
            check(record ~= nil, "refresh object is no longer identified")
            if record.opcode == 98 then
                local owner = originals[p]
                check(owner and owner.identity == record.identity, "missing original cache lineage")
                check(update.identity ~= nil and update.identity == owner.identity,
                    "planned original lifetime changed")
                liveOwner(owner, before, now)
                check(after > now, "new expiry is not live")
                local binding = currentBinding(owner, recovery ~= nil)
                if not binding then
                    local ticket = recovery.prepare(owner, before, after, now)
                    prepared[#prepared + 1] = {owner=owner, ticket=ticket, expiry=after}
                else
                local previous = countdown(binding)
                -- Deliberately signed arithmetic, without dword wrap. A shorter
                -- deadline is supported only if its exact delta leaves a live
                -- cache countdown. Unknown/sentinel/overflow states diagnose.
                local replacement = previous + (after - before)
                integer(replacement, 1, I32, "replacement cache countdown")
                prepared[#prepared + 1] = {owner = owner, binding = binding,
                    previous = previous, replacement = replacement, expiry = after}
                end
            end
        end
        local preparedRevision, attempted = revision, false
        return {commit = function()
            check(not attempted, "cache transaction already used")
            attempted = true
            check(revision == preparedRevision, "cache lifetimes changed after prepare")
            local commitNow = integer(api.now(), 0, U32, "world time")
            -- Core.commit must already have written ALL original expiries.
            -- Revalidate every target before the first cache write. No engine
            -- method, yield or callback is allowed between the two commits.
            for _, item in ipairs(prepared) do
                liveOwner(item.owner, item.expiry, commitNow)
                if item.ticket then
                    recovery.validate(item.ticket, commitNow)
                else
                    check(currentBinding(item.owner) == item.binding, "current cache changed after prepare")
                    check(countdown(item.binding) == item.previous, "cache countdown changed after prepare")
                end
            end
            revision = revision + 1
            local recoveryTickets={}
            for _, item in ipairs(prepared) do
                if item.ticket then recoveryTickets[#recoveryTickets+1]=item.ticket
                else api.writeRemaining(item.binding.pointer, item.replacement) end
            end
            if #recoveryTickets>0 then recovery.commitBatch(recoveryTickets) end
            return #prepared
        end}
    end
    if recoveryFactory ~= nil then
        check(type(recoveryFactory) == "function", "invalid recovery factory")
        recovery = recoveryFactory(api, {
            binding=function(p) return caches[p] end,
            liveOwner=liveOwner,
            hasCurrent=function(owner) return currentBinding(owner, true) ~= nil end,
            bindRecovered=function(owner, p)
                pointer(p)
                check(caches[p] == nil, "recovered cache pointer is already live")
                bind(owner, p)
                revision = revision + 1
            end,
        })
        for _, name in ipairs({"onUpdateEnter", "onUpdateExit", "onNaturalDeath",
                "onBeforeRemove", "onCancelList", "onListDestroy", "onNativeAppend"}) do
            M[name] = recovery[name]
        end
    end
    M.recoveryEnabled = recovery ~= nil
    -- Atomicity is conditional on scalar adapter writes not throwing. If an
    -- adapter/native write throws after Core.commit or partway through this
    -- loop, original expiries and/or earlier caches may already be changed.
    -- Do not retry or claim rollback; the outer runtime must halt/diagnose.
    return M
end
