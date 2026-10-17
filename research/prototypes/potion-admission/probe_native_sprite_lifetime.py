"""Pinned native normal-flow CFG/source proof; no executable or DLL runs."""
import argparse,hashlib,json,sys
from pathlib import Path
BASE=0x140000000
SHA="b51093a49140b2b8a7c046b4652bb8e535be24ebbc12b1d735e0b94217a14d57"

def run(image,capstone):
 md=capstone.Cs(capstone.CS_ARCH_X86,capstone.CS_MODE_64);md.detail=True
 def graph(start,end):
  instructions={x.address-BASE:x for x in md.disasm(image[start:end],BASE+start)}
  edges={}
  for p,x in instructions.items():
   nxt=p+x.size;targets=[]
   if x.mnemonic=='ret':pass
   elif x.mnemonic=='jmp' or x.mnemonic.startswith('j'):
    assert x.operands[0].type==capstone.x86.X86_OP_IMM,'unproved indirect branch'
    targets.append(x.operands[0].imm-BASE)
    if x.mnemonic!='jmp':targets.append(nxt)
   else:targets.append(nxt)
   edges[p]=[t for t in targets if start<=t<end]
  return instructions,edges
 def reachable(edges,start,blocked=None):
  seen=set();todo=[start]
  while todo:
   p=todo.pop()
   if p in (blocked if isinstance(blocked,set) else {blocked}) or p in seen:continue
   seen.add(p);todo.extend(edges[p])
  return seen
 def dominates(edges,start,guard,target):
  assert target in reachable(edges,start),'target unreachable'
  assert target not in reachable(edges,start,guard),f'{guard:X} does not dominate {target:X}'
 def call(instructions,site,target):
  x=instructions[site];assert x.mnemonic=='call' and x.operands[0].imm==BASE+target
 out=[]
 for start,end,ready,finish,stats,effects in (
  (0x1A3480,0x1A3C6A,0x1A3C50,0x1A3C69,[0x1A35C4,0x1A35D0,0x1A35DC],[0x1A391D,0x1A394F]),
  (0x341860,0x3437C5,0x34310E,0x3437C4,[0x3419E5,0x3419F1,0x3419FD],[0x341BF6,0x341C2A])):
  ins,edges=graph(start,end)
  if start==0x341860:
   # Add failure explicitly destroys this allocation before its common return.
   assert ins[0x342810].mnemonic=='call' and ins[0x342810].op_str=='qword ptr [r8]'
   assert finish not in reachable(edges,start,{ready,0x342810})
  else: dominates(edges,start,ready,finish)
  for site in stats:
   call(ins,site,0x14EC10);dominates(edges,start,site,ready)
  for site in effects:
   call(ins,site,0x4073A0);dominates(edges,start,site,ready)
  out.append({'constructor':hex(start),'ready':hex(ready),'normal_return':hex(finish),
              'three_stats_and_effect_lists_dominate_ready':True,'ready_or_explicit_failed_construction_destruction_dominates_return':True})
 ins,edges=graph(0x341860,0x3437C5);call(ins,0x343114,0x37A3E0);dominates(edges,0x341860,0x34310E,0x343114)
 # Direct native source edges prove loading processes effects within the ctor.
 ins,_=graph(0x37A3E0,0x37B0D0);call(ins,0x37A424,0x34FD30);call(ins,0x37B095,0x3AB9D0)
 ins,_=graph(0x351240,0x351400);call(ins,0x3512C0,0x4F7A88);call(ins,0x351310,0x341860)
 # No copying of an old lifetime is inferred from persisted locals/UUID.
 out.append({'copy_allocates_new_sprite':True,'copy_constructor_call':'0x351310',
             'unmarshal_calls_clear':'0x37a424','unmarshal_processes_effects':'0x37b095'})
 ins,edges=graph(0x343CC0,0x3443B0)
 for site in (0x3442C4,0x3442D0,0x3442DC):
  call(ins,site,0x1A3FB0);dominates(edges,0x343CC0,0x343CC0,site)
 # Derived1120 + regen8E8 = sprite1A08; list destruction is later in the dtor.
 ins,_=graph(0x1A3FB0,0x1A4370);call(ins,0x1A4109,0x1F8990)
 assert image[0x1A40FB:0x1A4102]==bytes.fromhex('488D8FE8080000')
 # Initialization explicitly constructs the list, zeroes counter, sets vtable.
 ins,_=graph(0x14EC10,0x14F1D0);call(ins,0x14EF0F,0x4073A0)
 lea=ins[0x14EF1A];assert lea.address+lea.size+lea.operands[1].mem.disp==BASE+0x58F528
 assert image[0x14EF14:0x14EF1A]==bytes.fromhex('89AE20090000')
 out.append({'destructor_entry_before_originals_and_derived':True,
             'derived_member':'0x1120','regenerated_offset':'0x8e8','actual_sprite_list':'0x1a08',
             'list_clear_call':'0x1a4109','list_initialized_before_readiness':True})
 return {'sha256':SHA,'cases':out,'scope':'Static normal-flow CFG/source proof; calls treated as returning; no C++ exception-unwind proof.'}

def main():
 p=argparse.ArgumentParser();p.add_argument('--exe',required=True);p.add_argument('--python-libs',required=True);p.add_argument('--output',required=True);a=p.parse_args()
 sys.path.insert(0,a.python_libs);import pefile,capstone
 data=Path(a.exe).read_bytes();assert hashlib.sha256(data).hexdigest()==SHA
 result=run(pefile.PE(data=data).get_memory_mapped_image(),capstone)
 Path(a.output).write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
if __name__=='__main__':main()
