-- Copy effective engine resource bytes into Lua-owned strings for preflight.
-- No enumeration, game-file writes, hooks, retained native buffers or patching.
-- EEex_Resource_Fetch preserves the engine's KEY/BIFF/override resolution.
-- CRes::Demand returns the whole buffer (EFF included); unlike the convenience
-- EEex_Resource_Demand wrapper it does not skip the EFF file's outer signature.
return function(api)
    for _, name in ipairs({"EEex_Resource_Fetch", "EEex_UDToPtr", "EEex_ReadU8", "EEex_ReadU32"}) do
        assert(type(api[name]) == "function", "CBR potion resources: missing " .. name)
    end
    local function integer(value, low, high, label)
        assert(type(value) == "number" and value == math.floor(value)
            and value >= low and value <= high, "CBR potion resources: invalid " .. label)
        return value
    end
    return function(name)
        assert(type(name) == "string", "CBR potion resources: expected resource name")
        local stem, extension = name:match("^(.+)%.([^.]+)$")
        assert(stem and #stem <= 8, "CBR potion resources: invalid resource identity")
        for i = 1, #stem do
            local byte = stem:byte(i)
            assert(byte >= 33 and byte <= 126 and not stem:sub(i,i):find("[\\/:.]"),
                "CBR potion resources: invalid resource identity")
        end
        extension = extension:upper()
        assert(extension == "ITM" or extension == "SPL" or extension == "EFF",
            "CBR potion resources: unsupported resource kind")
        local resource = api.EEex_Resource_Fetch(stem:upper(), extension)
        if resource == nil then return nil, "resource is missing: " .. name end
        local buffer = resource:Demand()
        if buffer == nil then return nil, "resource demand failed: " .. name end
        -- A defensive preflight memory/work budget, not an expected file size.
        -- Reject explicitly instead of truncating a large mod-added resource.
        local size = integer(resource.nSize, 0, 16 * 1024 * 1024, "resource size (16 MiB limit)")
        local address = integer(api.EEex_UDToPtr(buffer), 1, 9007199254740991 - size, "buffer pointer")
        local chunks, count = {}, 0
        for offset = 0, size - 1, 2048 do
            local bytes, last = {}, math.min(size, offset + 2048)
            local at = offset
            while at + 4 <= last do
                local value = integer(api.EEex_ReadU32(address + at), 0, 4294967295, "resource dword")
                bytes[#bytes+1] = string.char(value % 256, math.floor(value / 256) % 256,
                    math.floor(value / 65536) % 256, math.floor(value / 16777216) % 256)
                at = at + 4
            end
            while at < last do
                bytes[#bytes+1] = string.char(integer(api.EEex_ReadU8(address + at), 0, 255, "resource byte"))
                at = at + 1
            end
            count = count + 1
            chunks[count] = table.concat(bytes)
        end
        -- Follow EEex's ordinary Demand lifetime. Do not Dump a shared resource
        -- whose buffer another engine object may currently reference.
        return table.concat(chunks)
    end
end
