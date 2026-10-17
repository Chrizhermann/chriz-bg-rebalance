-- Inert composition entry point. Preparation does not arm hooks.
-- A future installer supplies inventory data; all semantics are compiled from
-- the engine's current effective resources, not embedded development fixtures.
local M = {}
function M.prepare(api, parts, inventory, report)
    assert(type(report) == "function", "CBR potion startup requires a visible diagnostic callback")
    local ok, lab, manifest = pcall(function()
        assert(type(parts) == "table" and type(parts.resources) == "function"
            and type(parts.compiler) == "table" and type(parts.compiler.build) == "function"
            and type(parts.hash) == "table" and type(parts.hash.sha256) == "function"
            and type(parts.lab) == "table" and type(parts.lab.prepare) == "function",
            "CBR potion startup modules are incomplete")
        local read = parts.resources(api)
        local cached = {}
        local function currentBytes(name)
            local key = name:upper()
            if cached[key] == nil then
                local data, reason = read(key)
                assert(type(data) == "string", reason or ("Cannot read potion resource " .. key))
                cached[key] = data
            end
            return cached[key]
        end
        local registry = parts.compiler.build(inventory, currentBytes, parts.hash.sha256)
        local prepared = parts.lab.prepare(api, parts, registry, report)
        return prepared, registry
    end)
    if not ok then
        pcall(report, tostring(lab))
        error(lab, 0)
    end
    return lab, manifest
end
return M
