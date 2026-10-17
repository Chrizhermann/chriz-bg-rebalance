-- Original-effect potion admission prototype. No autoload, hooks or native calls.
-- A validated adapter supplies source/semantic identity and a real dose token.
-- This module never adds/removes effects or changes an incoming effect.
local M = {}
local MAX = 4294967295
local function requireValue(ok, message)
    if not ok then error("CBR potion admission: " .. message, 0) end
end
local function integer(value, name)
    requireValue(type(value) == "number" and value == math.floor(value)
        and value >= 0 and value <= MAX, "invalid " .. name)
    return value
end
local function copy(source)
    local result = {}
    for key, value in pairs(source) do result[key] = value end
    return result
end
local function sourceInfo(record, manifest)
    local name=record.source
    if record.ownerSource~=nil then
        -- Only the provenance-aware reader may supply this logical owner. The
        -- original effect remains a spell effect with its real SPL/caster data.
        requireValue(record.sourceType==1 and record.identity~=nil
            and type(record.ownerSource)=="string" and type(name)=="string",
            "invalid linked potion ownership")
        name=record.ownerSource
    elseif record.sourceType ~= 2 then return nil end
    requireValue(type(name) == "string", "invalid item source")
    local source = manifest.sources[name:upper()]
    if record.ownerSource~=nil then
        local expected=source and source.records and source.records[record.key]
        requireValue(expected and expected.nativeSourceType==1
            and (expected.nativeSource==record.source:upper()
                or (expected.nativeSources and expected.nativeSources[record.source:upper()]==true)),
            "linked owner disagrees with manifest")
    elseif source and source.records and source.records[record.key]
            and source.records[record.key].nativeSourceType==1 then
        return nil -- An item record cannot impersonate a declared SPL child.
    end
    if not source or not source.keys[record.key] then return nil end
    requireValue(manifest.families[source.family] ~= nil, "unknown manifest family")
    return source
end
local function live(record, now)
    requireValue(type(record.done) == "boolean", "invalid done flag")
    if record.done then return false end
    requireValue(record.timing == 4096, "active owned effect is not absolute timed")
    return integer(record.expiry, "active expiry") > now
end
local function deadline(incoming, now)
    local duration = integer(incoming.expiry, "incoming duration")
    requireValue(duration > 0, "incoming bonus has no finite lifetime")
    local ticks
    if incoming.timing == 0 then
        requireValue(duration <= 0x08888888, "duration needs native signed/clamped conversion")
        ticks = duration * 15
    elseif incoming.timing == 10 then ticks = duration
    else error("CBR potion admission: unsupported incoming timing", 0) end
    return integer(now + ticks, "replacement expiry")
end

function M.newDose(token, family, quotas)
    requireValue(token ~= nil, "missing dose token")
    requireValue(type(family) == "string" and type(quotas) == "table", "invalid dose manifest")
    local counts = {}
    for key, count in pairs(quotas) do
        requireValue(type(key) == "string" and integer(count, "effect quota") > 0,
            "invalid effect quota")
        counts[key] = count
    end
    return {token = token, family = family, quotas = counts, used = {}, admitted = {},
        refreshed = {}, snapshot = nil}
end

function M.plan(incoming, active, manifest, now, dose)
    integer(now, "clock")
    requireValue(type(manifest) == "table" and type(manifest.sources) == "table"
        and type(manifest.families) == "table", "invalid manifest")
    requireValue(manifest.policy == "unique" or manifest.policy == "except_genius", "invalid policy")
    requireValue(type(incoming) == "table" and type(active) == "table", "invalid effect input")
    local source = sourceInfo(incoming, manifest)
    if not source then return {allow = true, reason = "unowned", refresh = {}, state = dose} end
    local family = manifest.families[source.family]
    requireValue(type(family.hp) == "boolean" and type(family.genius) == "boolean", "invalid family policy")
    if manifest.policy == "except_genius" and family.genius then
        return {allow = true, reason = "genius", refresh = {}, state = dose}
    end
    requireValue(type(dose) == "table" and dose.token ~= nil and dose.family == source.family,
        "missing or mismatched dose")
    requireValue(incoming.object ~= nil, "missing original incoming effect")
    local quota = dose.quotas[incoming.key]
    requireValue(quota ~= nil, "effect absent from dose manifest")
    local expires = deadline(incoming, now)
    local state = copy(dose)
    state.used = copy(dose.used)
    state.admitted, state.refreshed = copy(dose.admitted), copy(dose.refreshed)
    local current, counts, hpPresent = {}, {}, false
    for _, record in ipairs(active) do
        local owner = sourceInfo(record, manifest)
        if owner and owner.family == source.family and live(record, now) then
            local identity = record.identity or record.object
            requireValue(record.object ~= nil and current[identity] == nil,
                "duplicate/missing active object")
            current[identity] = record
            -- A portrait is rejected with a repeated HP package, but an
            -- orphaned/longer-lived icon is not proof that a bonus remains.
            local nonBlocking = owner.nonBlockingKeys
            requireValue(nonBlocking == nil or type(nonBlocking) == "table",
                "invalid nonblocking companion keys")
            local companion = nonBlocking and nonBlocking[record.key]
            requireValue(companion == nil or companion == true,
                "invalid nonblocking companion marker")
            if not companion then hpPresent = true end
        end
    end
    if not state.snapshot then
        state.snapshot = {}
        for _, record in ipairs(active) do
            if current[record.identity or record.object] then
                local list = state.snapshot[record.key] or {}
                state.snapshot[record.key] = list
                list[#list + 1] = copy(record)
                counts[record.key] = #list
            end
        end
        state.hpBlocked = hpPresent
        if not family.hp then
            for key, count in pairs(counts) do
                requireValue(state.quotas[key] and count <= state.quotas[key],
                    "active package exceeds or differs from dose manifest")
            end
        end
    end
    local used = (state.used[incoming.key] or 0) + 1
    requireValue(used <= quota, "dose exceeded its declared effect multiset")
    state.used[incoming.key] = used
    if family.hp then
        return {allow = not state.hpBlocked,
            reason = state.hpBlocked and "hp-repeat" or "first-hp-dose", refresh = {}, state = state}
    end
    local record, selectedIdentity
    -- Prefer the old snapshot, but read its current lifetime/fields afresh.
    -- A different dose may have supplied a replacement after the snapshot's
    -- original was removed. Treat that live native object as the repeat target;
    -- never dereference the retired snapshot object or admit a second bonus.
    for _, old in ipairs(state.snapshot[incoming.key] or {}) do
        local identity = old.identity or old.object
        if current[identity] and not state.refreshed[identity] then
            record, selectedIdentity = current[identity], identity
            break
        end
    end
    local matchingCount = 0
    for identity, candidate in pairs(current) do
        if candidate.key == incoming.key then
            matchingCount = matchingCount + 1
            if not record and not state.admitted[identity] and not state.refreshed[identity] then
                record, selectedIdentity = candidate, identity
            end
        end
    end
    requireValue(matchingCount <= quota, "active multiset grew beyond the dose quota")
    if record then
        requireValue(record.key == incoming.key, "old effect identity changed during dose")
        state.refreshed[selectedIdentity] = true
        return {allow = false, reason = "refresh", state = state,
            refresh = {{record = record.object, identity = selectedIdentity,
                oldExpiry = record.expiry, expiry = expires}}}
    end
    state.admitted[incoming.identity or incoming.object] = true
    return {allow = true, reason = "new-bonus", refresh = {}, state = state}
end

function M.commit(plan)
    -- Validation is complete before any native field write. Do not call an
    -- engine method here: no iterator ownership, OnRemove or reentrant rebuild.
    requireValue(type(plan) == "table" and type(plan.refresh) == "table", "invalid plan")
    local seen = {}
    for _, update in ipairs(plan.refresh) do
        requireValue(update.record ~= nil and not seen[update.record], "duplicate refresh object")
        seen[update.record] = true
        integer(update.oldExpiry, "old expiry")
        integer(update.expiry, "planned expiry")
        requireValue(update.record.m_duration == update.oldExpiry, "effect changed before commit")
    end
    for _, update in ipairs(plan.refresh) do update.record.m_duration = update.expiry end
    return plan.allow, plan.state
end

return M
