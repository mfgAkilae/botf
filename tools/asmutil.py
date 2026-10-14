"""Keystone/Capstone helpers for 32-bit x86 patches."""
from keystone import Ks, KS_ARCH_X86, KS_MODE_32
from capstone import Cs, CS_ARCH_X86, CS_MODE_32

_ks = Ks(KS_ARCH_X86, KS_MODE_32)
_cs = Cs(CS_ARCH_X86, CS_MODE_32)


def asm(code, addr):
    enc, _ = _ks.asm(code, addr)
    return bytes(enc)


def disasm(data, addr):
    return ['%08x  %-20s %s %s' % (i.address, i.bytes.hex(), i.mnemonic, i.op_str) for i in _cs.disasm(data, addr)]


def call_rel(src, dst):
    import struct
    return b'\xe8' + struct.pack('<i', dst - (src + 5))


def jmp_rel(src, dst):
    import struct
    return b'\xe9' + struct.pack('<i', dst - (src + 5))
