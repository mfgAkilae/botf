"""Disassemble trek.exe ranges (capstone).
usage: disasm.py <va_hex>:<count> ...   (env EXE = other exe; default ../trek_en_orig.exe)"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pe import PE
import capstone

p = PE(os.environ.get('EXE', os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'trek_en_orig.exe')))
md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
for arg in sys.argv[1:]:
    a, n = arg.split(':'); a = int(a, 16); n = int(n)
    code = bytes(p.data[p.va2off(a):p.va2off(a) + n * 8])
    for k, i in enumerate(md.disasm(code, a)):
        if k >= n:
            break
        print('%x  %-8s %s' % (i.address, i.mnemonic, i.op_str))
    print('--')
