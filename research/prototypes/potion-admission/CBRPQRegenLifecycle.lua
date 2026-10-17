-- Inert lifecycle descriptor generator, BG2EE2.7.3.0 / EEex1.3.0.
-- No install/JIT, callback registration, memory write, native call or autoload.
-- The separate composer must use CBRPQWatchdog.withPreservation while passing
-- these descriptors to EEex_HookBeforeRestoreWithLabels. No CALL is relocated.
local M = {}
M.expectedExecutableSha256 = "b51093a49140b2b8a7c046b4652bb8e535be24ebbc12b1d735e0b94217a14d57"
-- key, RVA, full context signature, replay length, function-entry alignment
M.guards = {
    {"updateEnter",0x226500,"48896C2410488974241857415641574883EC20",5,8},
    {"naturalDeath",0x1A5D40,"C7430801000000F7E9448D0411",7,0},
    {"beforeRemove",0x22655E,"488BD5488BCEE807141E00",6,0},
    {"updateExit",0x22658B,"488B6C2448488B7424504883C420415F415E5FC3",5,0},
    {"clear",0x1F8990,"48895C2408574883EC20",5,8},
    {"removeType",0x2265A0,"488B41084885C07422",7,8},
    {"replace",0x226480,"48895C24084889742410574883EC20",5,8},
    {"listDestroy",0x150E90,"48895C2408574883EC20",5,8},
    {"cacheDestroy20",0x1A46C0,"40534883EC20488D0573433F00",6,8},
    {"cacheDestroy40",0x1A46F0,"40534883EC20488D0543433F00",6,8},
    {"cacheDestroy28",0x1A4720,"40534883EC20488D0513433F00",6,8},
    {"cacheDestroy30",0x1A4750,"40534883EC20488D05E3423F00",6,8},
    {"cacheDestroy38",0x1A4780,"40534883EC20488D05B3423F00",6,8},
    {"copy",0x1DCAE9,"4883C4205BC3",5,0},
    {"appendOwned",0x1BEDE5,"488B5C2430418BC6488B6C2438",5,0},
    {"appendNonempty",0x4075F0,"488B5C24304883C4205FC3",5,0},
    {"appendEmpty",0x407608,"4883C4205FC3",5,0},
    -- Context guards only; all original CALLs remain at their original RVAs.
    {"appendCall",0x1BEDD6,"488D8D081A0000488BD3E8DB872400"},
    {"copyResult",0x1DCAB6,"488BC20FB74B1A"},
    {"counter",0x22657E,"FF4638488B5C2440EB03FF4138"},
    {"tailSet",0x4075E9,"48890148894710"},
    {"emptySet",0x407600,"4889470848894710"},
}
local callbackKeys={"updateEnter","naturalDeath","beforeRemove","updateExit","clear","removeType",
    "replace","listDestroy","cacheDestroy","copy","appendOwned","append"}
-- All twelve native persistent-cache vtables in the pinned class family.
-- Names in the function database can alias (regeneration shares color's dtor).
M.vtables={
    {0x58F528,0x150E90}, {0x598A40,0x1A46C0}, {0x598A58,0x1A4720},
    {0x598A70,0x1A4720}, {0x598A88,0x1A4720}, {0x598AA0,0x1A4750},
    {0x598AB8,0x1A4750}, {0x598AD0,0x1A4720}, {0x598AE8,0x1A4750},
    {0x598B00,0x1A4780}, {0x598B18,0x1A4750}, {0x598B30,0x1A4780}, {0x598B48,0x1A46F0},
}
function M.validate(api,config,watchdog)
    assert(type(api.EEex_HookIntegrityWatchdog_Load)=="boolean", "regen lifecycle: watchdog state unavailable")
    if api.EEex_HookIntegrityWatchdog_Load then
        assert(type(watchdog)=="table" and type(watchdog.validate)=="function" and
            type(watchdog.withPreservation)=="function", "regen lifecycle: watchdog preservation helper required")
        watchdog.validate(api)
    end
    for _,name in ipairs({"EEex_GetImageBase","EEex_ReadU8","EEex_GenLuaCall","EEex_FlattenTable"}) do
        assert(type(api[name])=="function","regen lifecycle: missing API "..name)
    end
    assert(type(config)=="table" and type(config.callbacks)=="table","regen lifecycle: callbacks required")
    local names={}
    for _,key in ipairs(callbackKeys) do
        local name=config.callbacks[key]
        assert(type(name)=="string" and name:match("^[%a_][%w_]*$"),"regen lifecycle: invalid callback "..key)
        assert(type(api[name])=="function","regen lifecycle: callback must exist: "..name)
        names[key]=name
    end
    local base=api.EEex_GetImageBase()
    assert(type(base)=="number" and base>0 and base==math.floor(base) and base<9007199250000000,
        "regen lifecycle: invalid image base")
    for _,g in ipairs(M.guards) do
        for i=1,#g[3],2 do
            assert(api.EEex_ReadU8(base+g[2]+(i-1)/2)==tonumber(g[3]:sub(i,i+1),16),
                "regen lifecycle: unsupported/previously patched site "..g[1])
        end
    end
    for _,pair in ipairs(M.vtables) do
        local value=base+pair[2]
        for i=0,7 do
            assert(api.EEex_ReadU8(base+pair[1]+i)==value%256,"regen lifecycle: unsupported vtable")
            value=math.floor(value/256)
        end
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
    local suffix="_cbrpq_regen_"..key
    return api.EEex_FlattenTable({{save},api.EEex_GenLuaCall(name,{args=args,labelSuffix=suffix}),
        {"call_error"..suffix..": #ENDL",restore}})
end
-- Restrict the generic AddTail observation to this concrete list class before
-- entering Lua. Every flags/RAX path is preserved, including the skip path.
local function listGuard(api,base,key,body)
    return api.EEex_FlattenTable({{
        "pushfq #ENDL push rax #ENDL #STACK_MOD(16) #ENDL mov rax, ",base+0x58F528,
        " #ENDL cmp qword ptr ds:[rdi], rax #ENDL jnz skip_cbrpq_regen_"..key.." #ENDL",
        "pop rax #ENDL popfq #ENDL #STACK_MOD(-16) #ENDL"},body,{
        "jmp done_cbrpq_regen_"..key.." #ENDL skip_cbrpq_regen_"..key..": #ENDL #STACK_MOD(16) #ENDL",
        "pop rax #ENDL popfq #ENDL #STACK_MOD(-16) #ENDL done_cbrpq_regen_"..key..": #ENDL"}})
end
-- Callback contract: raw numeric pointers only, all returns ignored.
-- updateEnter(list,sprite,delta,originalEntryRSP), updateExit(list,originalEntryRSP)
-- naturalDeath(cache), beforeRemove(list,cache,currentNode)
-- clear(list), replace(list,sourceList), removeType(list,low16Type), listDestroy(list)
-- cacheDestroy(cache), copy(oldCache,newCache)
-- appendOwned(original,cache,sprite), append(list,cache,node,nativeReturnAddress)
-- The composer must pair EVERY observed update (including unowned sentinels),
-- translate raw list to an independently validated sprite/list lifetime, and
-- invalidate state on callback errors. Native execution always continues.
-- Generic append occurs BEFORE appendOwned. Use nativeReturnAddress==base+1BEDE5
-- to defer that observation to appendOwned (whose onAppend also notifies order).
-- Recovery-service appends require staged-allocation recognition, not ordinary
-- onNativeAppend reentry. Copy callback is lineage only, not append/adoption.
-- Existing original-effect destruction/reset transport must also be supplied.
function M.prepare(api,config,watchdog)
    local v=M.validate(api,config,watchdog)
    local n,b=v.callbacks,v.base
    local a={
        updateEnter=callback(api,n.updateEnter,"updateEnter",{reg("rcx"),reg("rdx"),
            calculated("mov eax, r8d"),calculated("lea rax, qword ptr ss:[rsp+#LAST_FRAME_TOP(160)]")}),
        naturalDeath=callback(api,n.naturalDeath,"naturalDeath",{reg("rbx")}),
        beforeRemove=callback(api,n.beforeRemove,"beforeRemove",{reg("rsi"),reg("rbx"),reg("rbp")}),
        updateExit=callback(api,n.updateExit,"updateExit",{reg("rsi"),
            calculated("lea rax, qword ptr ss:[rsp+#LAST_FRAME_TOP(216)]")}),
        clear=callback(api,n.clear,"clear",{reg("rcx")}),
        removeType=callback(api,n.removeType,"removeType",{reg("rcx"),calculated("movzx eax, dx")}),
        replace=callback(api,n.replace,"replace",{reg("rcx"),reg("rdx")}),
        listDestroy=callback(api,n.listDestroy,"listDestroy",{reg("rcx")}),
        copy=callback(api,n.copy,"copy",{reg("rbx"),reg("rdx")}),
        appendOwned=callback(api,n.appendOwned,"appendOwned",{reg("rdi"),reg("rbx"),reg("rbp")}),
    }
    for _,size in ipairs({20,40,28,30,38}) do
        local key="cacheDestroy"..size
        a[key]=callback(api,n.cacheDestroy,key,{reg("rcx")})
    end
    for _,key in ipairs({"appendNonempty","appendEmpty"}) do
        -- RAX is the adopted node. Read it before argument builders overwrite
        -- RAX by using saved volatile RAX at originalRSP-16 (our save layout).
        a[key]=listGuard(api,b,key,callback(api,n.append,key,{reg("rdi"),
            calculated("mov rax, qword ptr ss:[rsp+#LAST_FRAME_TOP(144)] #ENDL mov rax, qword ptr ds:[rax+10h]"),
            calculated("mov rax, qword ptr ss:[rsp+#LAST_FRAME_TOP(144)]"),
            calculated("mov rax, qword ptr ss:[rsp+#LAST_FRAME_TOP(200)]")}))
    end
    local descriptors={}
    for _,g in ipairs(M.guards) do
        if g[4] then descriptors[#descriptors+1]={key=g[1],address=b+g[2],restoreSize=g[4],
            stackMod=g[5],assembly=a[g[1]],labels=g[5]==8 and {{"stack_mod",8}} or {}} end
    end
    return {base=b,descriptors=descriptors,watchdog=v.watchdog}
end
return M
