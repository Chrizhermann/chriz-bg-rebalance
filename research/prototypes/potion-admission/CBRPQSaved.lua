-- Pure future linked-effect save metadata. No hooks, files, engine or saves.
-- Caller must provide the EXACT native serialized subset/order on export and
-- freshly decoded effects on import. Native marshal filters need their own
-- context hook; EEex.IsMarshallingCopy() is not that filter contract.
local M = {}
-- Native Marshal allocates/returns a signed32 byte count, with264 bytes per V2
-- effect. Occurrences are not bounded by an ITM/SPL header's16-bit effect count.
local MAX_EFFECTS=math.floor(2147483647/0x108)
local function check(ok, message)
    if not ok then error("CBR potion saved provenance: " .. message, 0) end
end
local function int(value, max)
    return type(value)=="number" and value==math.floor(value) and value>=1 and value<=max
end
local function dense(value, label)
    check(type(value)=="table", "invalid "..label)
    local count=0
    for k in pairs(value) do check(int(k,#value), "invalid "..label.." index"); count=count+1 end
    check(count==#value, "sparse "..label)
    return #value
end
local function safeString(value, maximum, label)
    check(type(value)=="string" and #value>0 and #value<=maximum
        and not value:find("\0",1,true), "invalid "..label)
    return value
end
local function metadata(value)
    check(type(value)=="table", "invalid owner metadata")
    return {
        source=safeString(value.source,8,"owning item"),
        key=safeString(value.key,128,"logical effect key"),
    }
end

function M.fingerprint(body)
    check(type(body)=="string" and #body>=0xD4, "truncated live effect projection")
    local ranges={{0x10,0x30},{0x38,0x50},{0x54,0x70},{0x80,0xD4}}
    local pieces={}
    for _,range in ipairs(ranges) do pieces[#pieces+1]=body:sub(range[1]+1,range[2]) end
    -- Native CopyFromBase uppercases these three operands and clears all bytes
    -- following their first NUL. SourceRes+94 is copied verbatim, without this.
    for _,offset in ipairs({0x30,0x70,0x78}) do
        local raw=body:sub(offset+1,offset+8)
        local value=(raw:match("^[^%z]*")):gsub("[a-z]",string.upper)
        pieces[#pieces+1]=value..string.rep("\0",8-#value)
    end
    return (table.concat(pieces):gsub(".",function(c) return string.format("%02x",c:byte()) end))
end

local function group(records)
    local groups, identities={},{ }
    local count=dense(records,"native effect list")
    check(count<=MAX_EFFECTS,"native effect list exceeds signed marshal byte range")
    for i=1,count do
        local record=records[i]
        check(type(record)=="table" and record.identity~=nil and not identities[record.identity],
            "missing or duplicate native lifetime")
        identities[record.identity]=true
        local key=M.fingerprint(record.body)
        local list=groups[key] or {}; groups[key]=list
        list[#list+1]=record
    end
    return groups
end

function M.export(records, owners)
    check(type(owners)=="table", "missing lifetime ownership map")
    local result={version=1,groups={}}
    for fingerprint,list in pairs(group(records)) do
        local owned={}
        for occurrence,record in ipairs(list) do
            if owners[record.identity]~=nil then owned[occurrence]=metadata(owners[record.identity]) end
        end
        if next(owned) then result.groups[fingerprint]={count=#list,owned=owned} end
    end
    return result
end

function M.restore(records, saved, verify)
    check(type(saved)=="table" and saved.version==1 and type(saved.groups)=="table", "unsupported schema")
    check(saved.invalid==nil,"saved ownership was explicitly invalidated")
    check(type(verify)=="function", "missing current-manifest verifier")
    local current,result=group(records),{}
    for fingerprint,entry in pairs(saved.groups) do
        check(type(fingerprint)=="string" and #fingerprint==384 and fingerprint:match("^[0-9a-f]+$"),
            "invalid saved effect projection")
        check(type(entry)=="table" and int(entry.count,MAX_EFFECTS) and type(entry.owned)=="table",
            "invalid saved occurrence group")
        local list=current[fingerprint]
        check(list~=nil and #list==entry.count, "saved effect occurrences no longer match")
        for occurrence,value in pairs(entry.owned) do
            check(int(occurrence,#list), "invalid saved occurrence")
            local owner=metadata(value)
            local record=list[occurrence]
            check(verify(record,owner)==true, "saved owner differs from current manifest")
            result[record.identity]=owner
        end
    end
    -- Return a new map only after complete validation; never partially import.
    return result
end
return M
