"""ML64 + Unicorn execution of inert regeneration service generator output.

No game/EEex/native DLL is executed. Windows HeapAlloc/HeapFree/GetProcessHeap
and Lua C API are explicit service substitutes. Pinned native initializer,
list insertion/NewNode/destruction/free-call chain execute as copied code.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys
import tempfile

import probe_native_admission as native

SERVICE=native.BASE+0x3600000
HEAP=0x710000000
REQUEST=native.META+0xB000
SNAPSHOT=native.META+0xC000
LIST=native.ACTOR+0x1A08
HEAP_HANDLE=0x12345000
HEAP_ALLOC=native.FAKE_CALLS+0x600
HEAP_FREE=native.FAKE_CALLS+0x620
GET_HEAP=native.FAKE_CALLS+0x640
LUA_NUMBER=SERVICE+0xF000
LUA_PUSH=SERVICE+0xF020


class ServiceMachine(native.Machine):
    def __init__(self,image,uc,registers,code):
        self.heap_next=HEAP
        self.live={}
        self.heap_calls=[]
        self.free_calls=[]
        self.fail_at=None
        self.fail_free=False
        self.prefill=0xA5
        self.fragment_stop=None
        self.allow_initializer_new=False
        self.lua_status=None
        self.native_callees=set()
        super().__init__(image,uc,registers)
        self.u.mem_map(SERVICE,0x10000)
        self.u.mem_map(HEAP,0x200000)
        self.code={}
        for name,(address,data) in code.items():
            self.u.mem_write(address,data)
            self.code[name]=address-native.BASE
        self.u.mem_write(LUA_NUMBER,b'\xc3')
        self.u.mem_write(LUA_PUSH,b'\xc3')
        self.put(native.BASE+0x58A1B0,'Q',HEAP_ALLOC)
        self.put(native.BASE+0x58A1B8,'Q',HEAP_FREE)
        self.put(native.BASE+0x58A1E8,'Q',GET_HEAP)
        self.run(0x52A3DC)  # Actual CRT initializes the exact shared heap cell.
        native.require(self.get(native.BASE+0x34B8590,'Q')==HEAP_HANDLE,'wrong native heap cell')
        self.put(LIST+0x30,'I',3)

    def allocate_heap(self,size):
        self.heap_calls.append(size)
        if self.fail_at==len(self.heap_calls): return 0
        pointer=self.heap_next
        self.heap_next+=(size+0xFF)&~0xFF
        native.require(self.heap_next<HEAP+0x200000,'bounded synthetic heap exhausted')
        self.u.mem_write(pointer,bytes([self.prefill])*size)
        self.live[pointer]=size
        return pointer

    def on_code(self,uc,address,size,data):
        rva=address-native.BASE
        if address==self.fragment_stop:
            self.returned=True; uc.emu_stop(); return
        if address==GET_HEAP: self.ret(HEAP_HANDLE); return
        if address in (HEAP_ALLOC,HEAP_FREE):
            native.require(self.reg_read('RCX')==HEAP_HANDLE and self.reg_read('RDX')==0,
                           'service used a different heap or exceptional flags')
            native.require(self.reg_read('RSP')%16==8,'Windows call stack misaligned')
            if address==HEAP_ALLOC:
                self.ret(self.allocate_heap(self.reg_read('R8')))
            else:
                pointer=self.reg_read('R8')
                native.require(pointer in self.live,'free of unknown/adopted-twice allocation')
                self.free_calls.append(pointer)
                if self.fail_free: self.ret(0)
                else: self.live.pop(pointer); self.ret(1)
            return
        if rva==0x4F7A88 and self.allow_initializer_new:
            self.ret(self.allocate_heap(self.reg_read('RCX'))); return
        if rva in (0x4F7A88,0x407AF0,0x51A7EC):
            raise AssertionError('unexpected throwing/new-handler allocation path')
        if address==LUA_NUMBER:
            native.require(self.reg_read('RDX')==1 and self.reg_read('R8')==0,'wrong Lua numeric argument ABI')
            self.ret(REQUEST); return
        if address==LUA_PUSH:
            self.lua_status=self.reg_read('RDX'); self.ret(); return
        if rva in (0x4075C0,0x4077F0,0x407890,0x407970,0x1A4750,0x1F8990,0x407930,0x407B40):
            self.native_callees.add(rva)
            return # Execute these native bodies, bypassing generic probe stubs.
        super().on_code(uc,address,size,data)

    def call(self,name):
        before={r:self.reg_read(r) for r in ('RBX','RSI','RDI','RBP','R12','R13','R14','R15')}
        self.run(self.code[name],REQUEST)
        native.require(before=={r:self.reg_read(r) for r in before},'service corrupted a nonvolatile register')
        return self.reg_read('EAX')

    def snapshot(self,mode=3,amount=5):
        self.u.mem_write(SNAPSHOT,bytes([self.prefill])*0x30)
        self.run(self.code['initialize'],SNAPSHOT)
        self.put(SNAPSHOT+8,'I',1)
        self.put(SNAPSHOT+0x18,'HHI',3 if mode==3 else 1,2 if mode==3 else 0,14)
        self.put(SNAPSHOT+0x20,'HHH',mode,0xFFFF,amount)
        self.put(SNAPSHOT+0x28,'i',0)
        self.u.mem_write(REQUEST,b'\0'*0x40)
        self.put(REQUEST,'QIH',SNAPSHOT,83,1 if mode==3 else 0)
        self.put(REQUEST+0x10,'I',3)
        self.put(REQUEST+0x28,'Q',LIST)

    def entries(self):
        result=[]; node=self.get(LIST+8,'Q')
        while node:
            native.require(len(result)<64,'malformed native list')
            result.append((node,self.get(node+0x10,'Q')))
            node=self.get(node,'Q')
        return result


def run_probes(image,uc,registers,module,assembler,directory):
    plan=module.generate(native.BASE)
    code={}
    for i,name in enumerate(('initialize','allocate','insert','dispose')):
        address=SERVICE+i*0x2000
        code[name]=(address,assembler.assemble(plan[name],address,directory,name))
    wrapper=module.luaWrapper(code['allocate'][0])
    wrapper=wrapper.replace('#L(Hardcoded_lua_tointegerx)',str(LUA_NUMBER)).replace('#L(Hardcoded_lua_pushinteger)',str(LUA_PUSH))
    code['lua_allocate']=(SERVICE+0x8000,assembler.assemble(wrapper,SERVICE+0x8000,directory,'lua_allocate'))
    for rva,hexadecimal in module.expected.items():
        native.require(image[rva:rva+len(hexadecimal)//2]==bytes.fromhex(hexadecimal),'native service signature drift')
    cases=[]
    for fill in (0,0x7F,0xA5):
        p=ServiceMachine(image,uc,registers,code); p.prefill=fill
        p.allow_initializer_new=True; p.fragment_stop=native.BASE+0x1BECC3
        p.run(0x1BEC70)
        original=p.read(p.reg_read('RBX'),0x30)
        p.fragment_stop=None; p.allow_initializer_new=False
        p.u.mem_write(SNAPSHOT,bytes([fill])*0x30)
        p.run(p.code['initialize'],SNAPSHOT)
        native.require(p.read(SNAPSHOT,0x30)==original,'initializer did not preserve every native initialized/padding byte')
        cases.append({'case':'initializer_all48bytes','prefill':fill,'equal':True})
    for mode in (2,3):
        p=ServiceMachine(image,uc,registers,code); p.snapshot(mode)
        state=p.read(SNAPSHOT,0x30); before=p.read(LIST,0x40)
        native.require(p.call('allocate')==0,'valid service allocation failed')
        cache,pool=p.get(REQUEST+0x18,'Q'),p.get(REQUEST+0x20,'Q')
        expected=bytearray(state)
        struct.pack_into('<I',expected,8,0)
        struct.pack_into('<H',expected,0x1A,1 if mode==3 else 0)
        struct.pack_into('<i',expected,0x28,83)
        native.require(p.read(cache,0x30)==expected and p.read(LIST,0x40)==before,'detached allocation changed fields/list')
        native.require(p.heap_calls==[0x30,0x10+3*0x18],'wrong allocation class sizes')
        native.require(p.call('insert')==0,'native first insertion failed')
        native.require(p.entries()==[(p.get(REQUEST+0x38,'Q'),cache)],'native adoption wrong')
        native.require(p.get(REQUEST+0x18,'Q')==p.get(REQUEST+0x20,'Q')==0,'adopted pointers remain caller-owned')
        native.require(p.get(LIST+0x28,'Q')==pool,'pool not adopted')
        p.run(0x1F8990,LIST)
        native.require(not p.live and not p.entries(),'native ClearAll did not free adopted cache and pool on same heap')
        cases.append({'case':'allocate_adopt_native_destroy','mode':mode,'all_fields_preserved':True})
    p=ServiceMachine(image,uc,registers,code); p.snapshot(2)
    caches=[]
    for index in range(4):
        p.snapshot(2); native.require(p.call('allocate')==0,'batch allocation failed')
        cache=p.get(REQUEST+0x18,'Q'); caches.append(cache)
        if index==2: p.put(REQUEST+0x30,'Q',p.entries()[1][0])
        native.require(p.call('insert')==0,'batch insertion failed')
    native.require([c for _,c in p.entries()]==[caches[0],caches[2],caches[1],caches[3]],'native middle/tail order changed')
    native.require(0x407890 in p.native_callees and 0x4077F0 in p.native_callees,'native insertion not executed')
    p.run(0x1F8990,LIST)
    native.require(not p.live,'pool exhaustion/adoption leaked native allocations')
    cases.append({'case':'existing_pool_middle_tail_and_pool_exhaustion','same_order':True,'native_freed_all':True})
    for fail in (1,2):
        p=ServiceMachine(image,uc,registers,code); p.snapshot(); p.fail_at=fail
        before=p.read(LIST,0x40); original=p.read(native.ACTIVE,0x158)
        result=p.call('allocate')
        native.require(result==(2 if fail==1 else 3) and not p.live,'allocation failure leaked or wrong status')
        native.require(p.read(LIST,0x40)==before and p.read(native.ACTIVE,0x158)==original,'failed allocation wrote live state')
        native.require(p.get(REQUEST+0x18,'Q')==p.get(REQUEST+0x20,'Q')==0,'failed request owns hidden allocation')
        cases.append({'case':'allocation_failure','allocation_number':fail,'no_reconstruction_write':True})
    p=ServiceMachine(image,uc,registers,code); p.snapshot(); p.fail_at=2; p.fail_free=True
    native.require(p.call('allocate')==4 and p.get(REQUEST+0x18,'Q') in p.live,'cleanup failure hid detached cache')
    native.require(not p.entries(),'cleanup failure inserted cache')
    cases.append({'case':'cleanup_failure_retains_explicit_ownership','no_list_write':True})
    for offset,fmt,value in ((8,'i',0),(0xC,'H',3),(0x10,'I',0),(0x10,'I',0x80000000)):
        p=ServiceMachine(image,uc,registers,code); p.snapshot(); p.put(REQUEST+offset,fmt,value)
        native.require(p.call('allocate')==1 and not p.heap_calls,'invalid request reached allocator')
        cases.append({'case':'invalid_request','offset':offset,'value':value,'no_allocation':True})
    p=ServiceMachine(image,uc,registers,code); p.snapshot()
    native.require(p.call('allocate')==0,'dispose setup failed')
    native.require(p.call('dispose')==0 and not p.live,'detached dispose did not use matching native destructor/free')
    native.require(0x1A4750 in p.native_callees,'native destructor was bypassed')
    cases.append({'case':'detached_dispose_native_destructor','same_heap_freed':True})
    p=ServiceMachine(image,uc,registers,code); p.snapshot(); p.fail_at=1
    native.require(p.call('lua_allocate')==1 and p.lua_status==2,'EEex Lua C wrapper ABI changed')
    cases.append({'case':'EEex_Lua_CFunction_wrapper','failure_status_returned':2})
    return {'cases':cases,'generated_code_sizes':{name:len(data) for name,(_,data) in code.items()},
            'limits':['Windows heap and Lua C API are service stubs; no native DLL or game process execution.',
                      'Pinned code must be validated before installing lifecycle hooks; wrappers/generator are not installed.',
                      'Valid caller-owned request/snapshot/list/node pointers are a required service ABI precondition.',
                      'Heap corruption/OS instrumentation/native hook failures are not emulated.']}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--exe',type=Path,required=True)
    parser.add_argument('--python-libs',type=Path,required=True)
    parser.add_argument('--ml64',type=Path,required=True)
    parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    sys.path.insert(0,str(args.python_libs))
    root=Path(__file__).resolve().parents[3]
    sys.path.insert(0,str(root))
    import pefile,unicorn
    from unicorn import x86_const
    from lupa.luajit21 import LuaRuntime
    from tests import test_potion_generated_trampoline as assembler
    assembler.ML64=str(args.ml64)
    data=args.exe.read_bytes()
    native.require(hashlib.sha256(data).hexdigest()==native.SHA256,'unreviewed executable')
    module=LuaRuntime(unpack_returned_tuples=True).execute(Path(__file__).with_name('CBRPQRegenServices.lua').read_text())
    directory=Path(tempfile.mkdtemp(prefix='cbr-regen-native-services-'))
    result=run_probes(pefile.PE(data=data).get_memory_mapped_image(),unicorn,x86_const,module,assembler,directory)
    result['exe_sha256'],result['generated_assembly_directory']=native.SHA256,str(directory)
    output=json.dumps(result,indent=2)+'\n'
    if args.output: args.output.write_text(output,encoding='utf-8')
    else: print(output)


if __name__=='__main__': main()
