# Fix G check: just before the system screen block at 0x4f7647 (at 0x4f763c) a stub makes the stored system one
# that belongs to no empire (system 1, owner 0x23), the state player B crashed in; then F1 and F2 on an own system.
import sys, struct, time; sys.path.insert(0,'tools'); import harness as H
from asmutil import asm, jmp_rel
STUB, PAR = 0x69e260, 0x69e2e0
st=H.load_state(); x='C'; p=st[x]; hw=H.main_window(p)
def key(vk):
    H.user32.PostMessageW(hw,0x100,vk,1); time.sleep(0.05); H.user32.PostMessageW(hw,0x101,vk,0xC0000001); time.sleep(1.5)
code = asm(f'''
    mov eax, dword ptr [ebp+0x224]
    cmp dword ptr [{PAR:#x}], 0
    je done
    push ecx
    mov ecx, dword ptr [0x595da8]
    mov word ptr [ecx+0x1c], 1
    pop ecx
    mov dword ptr [{PAR:#x}], 0
done:
    jmp 0x4f7642
''', STUB)
assert H.readmem(p, 0x4f763c, 6) == bytes.fromhex('8b8524020000')
H.writemem(p, STUB, code); H.writemem(p, PAR, struct.pack('<I', 1))
H.writemem(p, 0x4f763c, jmp_rel(0x4f763c, STUB) + b'\x90')
key(0x70); ui=struct.unpack('<I',H.readmem(p,0x595da8,4))[0]
H.writemem(p, ui+0x1c, struct.pack('<h', 16)); key(0x71)
print('alive after F2:', H.pid_alive(p), 'injected:', H.pid_alive(p) and struct.unpack('<I',H.readmem(p,PAR,4))[0] == 0)
if H.pid_alive(p):
    print('shown system', struct.unpack('<h',H.readmem(p,ui+0x1c,2))[0])
    key(0x70); key(0x72); key(0x71); print('alive after F1,F3,F2:', H.pid_alive(p))
