"""Minimal PE helpers: VA <-> file offset, section table, byte patching with verification."""
import struct, sys


class PE:
    def __init__(self, path):
        self.path = path
        self.data = bytearray(open(path, 'rb').read())
        d = self.data
        e = struct.unpack_from('<I', d, 0x3c)[0]
        assert d[e:e + 4] == b'PE\0\0'
        nsec = struct.unpack_from('<H', d, e + 6)[0]
        opt = struct.unpack_from('<H', d, e + 20)[0]
        self.image_base = struct.unpack_from('<I', d, e + 24 + 28)[0]
        self.sections = []
        so = e + 24 + opt
        for i in range(nsec):
            name = d[so:so + 8].rstrip(b'\0').decode('latin1')
            vsize, rva, rsize, raw = struct.unpack_from('<IIII', d, so + 8)
            chars = struct.unpack_from('<I', d, so + 36)[0]
            self.sections.append((name, rva, vsize, raw, rsize, chars, so))
            so += 40

    def va2off(self, va):
        rva = va - self.image_base
        for name, srva, vsize, raw, rsize, chars, _ in self.sections:
            if srva <= rva < srva + max(vsize, rsize):
                if raw == 0 or rva - srva >= rsize:
                    raise ValueError('VA %x in virtual-only part of %s' % (va, name))
                return raw + (rva - srva)
        raise ValueError('VA %x not mapped' % va)

    def off2va(self, off):
        for name, srva, vsize, raw, rsize, chars, _ in self.sections:
            if raw <= off < raw + rsize:
                return self.image_base + srva + (off - raw)
        raise ValueError('offset %x not mapped' % off)

    def read(self, va, n):
        o = self.va2off(va)
        return bytes(self.data[o:o + n])

    def patch(self, va, old, new):
        old = bytes.fromhex(old) if isinstance(old, str) else old
        new = bytes.fromhex(new) if isinstance(new, str) else new
        o = self.va2off(va)
        cur = bytes(self.data[o:o + len(old)])
        if cur != old:
            raise ValueError('mismatch at %x: have %s want %s' % (va, cur.hex(), old.hex()))
        self.data[o:o + len(new)] = new
        return o

    def save(self, path):
        open(path, 'wb').write(self.data)

    def _hdr(self):
        d = self.data
        e = struct.unpack_from('<I', d, 0x3c)[0]
        return e, e + 24

    def info(self):
        d = self.data
        e, opt = self._hdr()
        return {
            'section_alignment': struct.unpack_from('<I', d, opt + 32)[0],
            'file_alignment': struct.unpack_from('<I', d, opt + 36)[0],
            'size_of_image': struct.unpack_from('<I', d, opt + 56)[0],
            'size_of_headers': struct.unpack_from('<I', d, opt + 60)[0],
            'dll_characteristics': struct.unpack_from('<H', d, opt + 70)[0],
            'characteristics': struct.unpack_from('<H', d, e + 22)[0],
        }

    def add_section(self, name, size, chars=0xE0000020):
        """Append a new section of `size` bytes (zero-filled). Returns its VA."""
        d = self.data
        e, opt = self._hdr()
        inf = self.info()
        sa, fa = inf['section_alignment'], inf['file_alignment']
        nsec = struct.unpack_from('<H', d, e + 6)[0]
        opt_size = struct.unpack_from('<H', d, e + 20)[0]
        sh = e + 24 + opt_size + 40 * nsec
        first_raw = min(s[3] for s in self.sections if s[3])
        if sh + 40 > first_raw or sh + 40 > inf['size_of_headers']:
            raise ValueError('no room for section header')
        last_rva_end = max(s[1] + max(s[2], s[4]) for s in self.sections)
        rva = (last_rva_end + sa - 1) // sa * sa
        raw = (len(d) + fa - 1) // fa * fa
        rsize = (size + fa - 1) // fa * fa
        d.extend(b'\0' * (raw - len(d)))
        d.extend(b'\0' * rsize)
        hdr = name.encode()[:8].ljust(8, b'\0') + struct.pack('<IIIIIIHHI', size, rva, rsize, raw, 0, 0, 0, 0, chars)
        d[sh:sh + 40] = hdr
        struct.pack_into('<H', d, e + 6, nsec + 1)
        struct.pack_into('<I', d, opt + 56, (rva + size + sa - 1) // sa * sa)
        self.sections.append((name, rva, size, raw, rsize, chars, sh))
        return self.image_base + rva

    def write(self, va, data):
        o = self.va2off(va)
        self.data[o:o + len(data)] = data


if __name__ == '__main__':
    p = PE(sys.argv[1])
    print('image base %x' % p.image_base)
    for s in p.sections:
        print('%-8s rva=%06x vsize=%06x raw=%06x rsize=%06x chars=%08x' % s[:6])
