-- Inert pinned-build Win64 service generator. No JIT, installation, native call,
-- runtime registration or autoload. Each generated service takes one request
-- pointer in RCX and returns a status DWORD in EAX (zero=success).
-- Request: +00 snapshotPtr; +08 remaining:i32; +0C phase:u16;
-- +10 poolCount:u32; +18 detachedCache; +20 detachedPool;
-- +28 listPtr; +30 successorNode(0=tail); +38 adoptedNode. Size0x40.
local M={}
M.expected={
    [0x1BEC8A]="89700cb8ffffffff894314488d057c9e3d00488903b80500000066894312c743200000ffff66448973244c897318897328897308eb03",
    [0x4075C0]="48895c2408574883ec20488bda4533c0488b5110488bf9e8b402000048895810488b4f104885c9741248890148894710488b5c24304883c4205fc3488b5c243048894708488947104883c4205fc3",
    [0x4077F0]="48895c24084889742410574883ec20498bf0488bfa488bd94885d275464c8b4108e87a00000048897010488b4b084885c974184889410848894308488b5c2430488b7424384883c4205fc34889431048894308488b5c2430488b7424384883c4205fc3488b52084c8bc7e83100000048897010488b4f084885c97405488901eb0448894308488b5c2430488b742438488947084883c4205fc3",
    [0x407890]="48895c24084889742410574883ec204883792000498bf8488bf2488bd975468b53304883c12841b818000000e82f020000448b43304883c0104183e8014963c8488d1449488d04d0781b660f1f440000488b4b20488908488943204883e8184183e80179eb488b4320488b0848894b2048897008488b742438488938ff4318488b5c243048c74010000000004883c4205fc3",
    [0x1A4750]="40534883ec20488d05e3423f00488bd9488901f6c201740aba30000000e81e9f2b00488bc34883c4205bc3",
    [0x52A3DC]="4883ec28ff1502fe05004885c0488905a0e1f8020f95c04883c428c3",
    [0x51E486]="488b0d03a1f9024c8bc333d2ff1518bd0600",
    [0x51E41E]="4c8bc133d2488b0d66a1f902ff1588bd0600",
}
local function integer(v,low,high,name)
    assert(type(v)=="number" and v==math.floor(v) and v>=low and v<=high,"invalid "..name)
    return v
end
local function address(v) return "0"..string.format("%X",v).."h" end
local prolog=[[push rbx
push rsi
push rdi
push r12
push r13
sub rsp, 20h
mov rbx, rcx
]]
local epilog=[[add rsp, 20h
pop r13
pop r12
pop rdi
pop rsi
pop rbx
ret
]]
function M.generate(base)
    integer(base,0x10000,9007199254740991-0x3500000,"image base")
    local function at(rva) return address(base+rva) end
    local function heapCall(iat,size)
        return "mov rax, "..at(0x34B8590).."\nmov rcx, qword ptr [rax]\nxor edx, edx\n"..
            size.."\nmov rax, "..at(iat).."\ncall qword ptr [rax]\n"
    end
    local initialize="mov rax, "..at(0x598B18)..[[

mov qword ptr [rcx], rax
mov dword ptr [rcx+08h], 0
mov dword ptr [rcx+0Ch], 0
mov word ptr [rcx+12h], 5
mov dword ptr [rcx+14h], -1
mov qword ptr [rcx+18h], 1
mov dword ptr [rcx+20h], 0FFFF0000h
mov word ptr [rcx+24h], 1
mov dword ptr [rcx+28h], 0
ret
]]
    local allocate=prolog..[[
test rbx, rbx
jz allocate_bad
cmp qword ptr [rbx+18h], 0
jne allocate_bad
cmp qword ptr [rbx+20h], 0
jne allocate_bad
cmp qword ptr [rbx+38h], 0
jne allocate_bad
mov r13, qword ptr [rbx]
test r13, r13
jz allocate_bad
mov eax, dword ptr [rbx+08h]
test eax, eax
jle allocate_bad
mov r12d, dword ptr [rbx+10h]
test r12d, r12d
jle allocate_bad
mov rax, ]]..at(0x598B18)..[[

cmp qword ptr [r13], rax
jne allocate_bad
cmp word ptr [r13+12h], 5
jne allocate_bad
cmp dword ptr [r13+08h], 1
jne allocate_bad
cmp dword ptr [r13+0Ch], 0
jne allocate_bad
cmp dword ptr [r13+28h], 0
jne allocate_bad
movzx eax, word ptr [r13+20h]
sub eax, 2
cmp eax, 1
ja allocate_bad
movsx eax, word ptr [r13+18h]
test eax, eax
jle allocate_bad
movzx ecx, word ptr [rbx+0Ch]
cmp ecx, eax
jae allocate_bad
mov rax, ]]..at(0x34B8590)..[[

cmp qword ptr [rax], 0
je allocate_bad
]]..heapCall(0x58A1B0,"mov r8d, 30h")..[[
test rax, rax
jz allocate_cache_failed
mov rsi, rax
mov r8, r12
imul r8, 18h
add r8, 10h
]]..heapCall(0x58A1B0,"; r8 already holds the detached node-pool size")..[[
test rax, rax
jz allocate_pool_failed
mov rdi, rax
mov qword ptr [rdi], 0
; Snapshot restore includes every padding byte. The cache has no registration
; or owning-pointer ctor work: the initialized native fields are all scalars.
movdqu xmm0, xmmword ptr [r13]
movdqu xmm1, xmmword ptr [r13+10h]
movdqu xmm2, xmmword ptr [r13+20h]
movdqu xmmword ptr [rsi], xmm0
movdqu xmmword ptr [rsi+10h], xmm1
movdqu xmmword ptr [rsi+20h], xmm2
mov dword ptr [rsi+08h], 0
mov eax, dword ptr [rbx+08h]
mov dword ptr [rsi+28h], eax
mov ax, word ptr [rbx+0Ch]
mov word ptr [rsi+1Ah], ax
mov qword ptr [rbx+18h], rsi
mov qword ptr [rbx+20h], rdi
xor eax, eax
jmp allocate_done
allocate_pool_failed:
]]..heapCall(0x58A1B8,"mov r8, rsi")..[[
test eax, eax
jnz allocate_pool_cleaned
mov qword ptr [rbx+18h], rsi
mov eax, 4
jmp allocate_done
allocate_pool_cleaned:
mov eax, 3
jmp allocate_done
allocate_cache_failed:
mov eax, 2
jmp allocate_done
allocate_bad:
mov eax, 1
allocate_done:
]]..epilog
    local insert=prolog..[[
test rbx, rbx
jz insert_bad
mov rsi, qword ptr [rbx+28h]
mov rdi, qword ptr [rbx+18h]
test rsi, rsi
jz insert_bad
test rdi, rdi
jz insert_bad
cmp qword ptr [rbx+38h], 0
jne insert_bad
mov r12, qword ptr [rbx+20h]
test r12, r12
jz insert_bad
mov r13d, dword ptr [rbx+10h]
test r13d, r13d
jle insert_bad
cmp dword ptr [rsi+30h], r13d
jne insert_bad
cmp qword ptr [rsi+20h], 0
je insert_adopt_pool
; Existing free nodes suffice. Dispose the unused detached reserve before
; insertion; failure leaves both request pointers owned by the caller.
]]..heapCall(0x58A1B8,"mov r8, r12")..[[
test eax, eax
jz insert_free_failed
mov qword ptr [rbx+20h], 0
jmp insert_call
insert_adopt_pool:
mov rax, qword ptr [rsi+28h]
mov qword ptr [r12], rax
mov qword ptr [rsi+28h], r12
mov rax, r13
dec rax
imul rax, 18h
lea rdx, [r12+rax+10h]
insert_build_free:
mov rcx, qword ptr [rsi+20h]
mov qword ptr [rdx], rcx
mov qword ptr [rsi+20h], rdx
sub rdx, 18h
dec r13d
jnz insert_build_free
mov qword ptr [rbx+20h], 0
insert_call:
mov rcx, rsi
mov rdx, qword ptr [rbx+30h]
test rdx, rdx
jz insert_tail
mov r8, rdi
mov rax, ]]..at(0x4077F0)..[[

call rax
jmp insert_adopted
insert_tail:
mov rdx, rdi
mov rax, ]]..at(0x4075C0)..[[

call rax
insert_adopted:
mov qword ptr [rbx+38h], rax
mov qword ptr [rbx+18h], 0
xor eax, eax
jmp insert_done
insert_free_failed:
mov eax, 2
jmp insert_done
insert_bad:
mov eax, 1
insert_done:
]]..epilog
    local dispose=prolog..[[
test rbx, rbx
jz dispose_bad
mov rcx, qword ptr [rbx+18h]
test rcx, rcx
jz dispose_pool
mov edx, 1
mov rax, ]]..at(0x1A4750)..[[

call rax
mov qword ptr [rbx+18h], 0
dispose_pool:
mov r8, qword ptr [rbx+20h]
test r8, r8
jz dispose_ok
]]..heapCall(0x58A1B8,"; r8 is detached node pool")..[[
test eax, eax
jz dispose_free_failed
mov qword ptr [rbx+20h], 0
dispose_ok:
xor eax, eax
jmp dispose_done
dispose_bad:
mov eax, 1
jmp dispose_done
dispose_free_failed:
mov eax, 2
dispose_done:
]]..epilog
    return {initialize=initialize,allocate=allocate,insert=insert,dispose=dispose,
        requestSize=0x40,cacheSize=0x30,nodeSize=0x18,poolHeaderSize=0x10,
        imageBase=base,heapCell=base+0x34B8590,heapAllocIAT=base+0x58A1B0,heapFreeIAT=base+0x58A1B8,
        note="No native calls/JIT performed. Caller must verify pinned signatures and valid request buffers."}
end
function M.luaWrapper(serviceAddress)
    integer(serviceAddress,1,9007199254740991,"service address")
    -- Existing EEex JITNearAsLuaFunction/ExposeToLua accepts a lua_CFunction.
    -- This wrapper takes a caller-validated exact numeric request-buffer pointer
    -- and returns the service status. It is generated only, never installed here.
    return [[push rbx
sub rsp, 20h
mov rbx, rcx
mov edx, 1
xor r8d, r8d
call #L(Hardcoded_lua_tointegerx)
mov rcx, rax
mov rax, ]]..address(serviceAddress)..[[

call rax
mov edx, eax
mov rcx, rbx
call #L(Hardcoded_lua_pushinteger)
mov eax, 1
add rsp, 20h
pop rbx
ret
]]
end
function M.plan(api)
    assert(type(api)=="table" and type(api.EEex_GetImageBase)=="function" and
        type(api.EEex_ReadU8)=="function","native service inspection API unavailable")
    local base=api.EEex_GetImageBase()
    integer(base,0x10000,9007199254740991-0x3500000,"image base")
    for rva,hex in pairs(M.expected) do
        for i=1,#hex,2 do
            assert(api.EEex_ReadU8(base+rva+(i-1)/2)==tonumber(hex:sub(i,i+1),16),
                "regeneration native service: unsupported/patched native dependency")
        end
    end
    return M.generate(base)
end
return M
