#!/usr/bin/env python3
"""BotF multiplayer fix - patcher for trek.exe (Star Trek: Birth of the Federation).

Usage:
    python botf_mpfix.py <path\\to\\trek.exe>            check and patch (backup: trek.exe.mpfix_backup)
    python botf_mpfix.py <path\\to\\trek.exe> --check    show status only
    python botf_mpfix.py <path\\to\\trek.exe> --restore  restore the backup

Tested with all 143 trek.exe variants of "BOTF Most Active 2.0.4" (vanilla EN/DE, all resolutions,
ECM, ECMS, BOP, MUM, FAW, AAM, FMPM, UCW, UM5, UDM, GALM, PLUS).
All players should use the patch; unpatched players can still join.

Contents (details in README.md of https://github.com/mfgAkilae/botf):
  Network and turn order: A (queues before orders), B (messages held back during the turn calculation),
  C (send loop), D (keepalive), L (options/load held back), K (turn timer in dialogs), HB (checksums
  compared while waiting).
  Orders and production: E, V (delete requests), I (martial law), M, N (deleted builds), H, HA (shipyard
  loss), J (ship-class refit), MS (morale sum, vanilla only: the mods already have their own).
  Players leaving: Y, EL, LV (leave takes effect at the same point everywhere), BL (leave during a battle).
  Turn ended or timer: IN (intel), RS (research), RD (task-force redeploy), OP (options), F6 (debug key).
  Combat: T, U (AUTO), F (combat memory cleared), MI (invading an extinct minor race), X (wormholes),
  W/W2/W3 (counters reset on load), O, P, Q, G, CA, Z, IE (intel orders on elimination), S (heap lock),
  MV (the movie thread no longer reads the code area).
"""
import base64, os, shutil, struct, sys, zlib

# (file offset, original bytes, patched bytes, group): group 0 is required, group 1 (Fix MS) is applied only where
# all of its original bytes are found (the mods of the installer already changed that code)
PATCH = [
#PATCH_DATA#
]
SLEEP_OFF = #SLEEP_OFF#          # push 0x0a -> push 0x00 (identical to the community packet.patch)
CAVE = (0x116260, 0x117200)       # must be zero before patching
ORIG_SIZE = 1781248               # every trek.exe of the installer
# Fix RY (automatic resync) lives in a new section appended to the file; its contents are zlib + base64 below.
SECTION = #SECTION#


def sections(d):
    """(name, virtual size, virtual address, raw size, raw offset) of every section, PE header offset, table offset"""
    e = struct.unpack_from('<I', d, 0x3c)[0]
    n = struct.unpack_from('<H', d, e + 6)[0]
    st = e + 24 + struct.unpack_from('<H', d, e + 20)[0]
    secs = [(bytes(d[st + 40 * i:st + 40 * i + 8]).rstrip(b'\0').decode('latin1'),) + struct.unpack_from('<IIII', d, st + 40 * i + 8)
            for i in range(n)]
    return secs, e, st


def section_blob():
    blob = zlib.decompress(base64.b64decode(SECTION['data']))
    assert len(blob) == SECTION['rsize']
    return blob


def add_section(d):
    """append the resync section; the layout is the same in every trek.exe of the installer (checked here)"""
    secs, e, st = sections(d)
    opt = e + 24
    sa = struct.unpack_from('<I', d, opt + 32)[0]
    end = max(s[2] + max(s[1], s[3]) for s in secs)
    rva = (end + sa - 1) // sa * sa
    sh = st + 40 * len(secs)
    if (rva != SECTION['rva'] or len(d) != ORIG_SIZE or sh + 40 > struct.unpack_from('<I', d, opt + 60)[0]
            or any(d[sh:sh + 40])):
        raise ValueError('unexpected file layout (sections end at %#x, file size %d)' % (rva, len(d)))
    d[sh:sh + 40] = (SECTION['name'].encode().ljust(8, b'\0') +
                     struct.pack('<IIIIIIHHI', SECTION['vsize'], rva, SECTION['rsize'], len(d), 0, 0, 0, 0, SECTION['chars']))
    struct.pack_into('<H', d, e + 6, len(secs) + 1)
    struct.pack_into('<I', d, opt + 56, (rva + SECTION['vsize'] + sa - 1) // sa * sa)
    d.extend(section_blob())


def status(d):
    if d[:2] != b'MZ' or len(d) not in (ORIG_SIZE, ORIG_SIZE + SECTION['rsize']):
        return 'unknown', 'Not a known trek.exe (size %d).' % len(d)
    req = [(o, a, b) for o, a, b, g in PATCH if g == 0]
    opt = [(o, a, b) for o, a, b, g in PATCH if g == 1]
    is_a = lambda e: d[e[0]:e[0] + len(e[1]) // 2] == bytes.fromhex(e[1])
    is_b = lambda e: d[e[0]:e[0] + len(e[2]) // 2] == bytes.fromhex(e[2])
    orig = all(is_a(e) for e in req)
    done = all(is_b(e) for e in req) and (all(is_b(e) for e in opt) or not all(is_a(e) for e in opt))
    has_sec = any(s[0] == SECTION['name'] for s in sections(d)[0])
    if done and has_sec and len(d) == ORIG_SIZE + SECTION['rsize'] and d[ORIG_SIZE:] == section_blob():
        return 'patched', 'The multiplayer fix is already installed.'
    if orig and not has_sec and len(d) == ORIG_SIZE and not any(d[CAVE[0]:CAVE[1]]):
        return 'original', 'Unmodified, compatible trek.exe.'
    bad = [hex(e[0]) for e in req if not is_a(e)]
    return 'incompatible', 'Unexpected bytes at offsets: ' + ', '.join(bad[:8])


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    if args:
        path = args[0]
    else:                                     # double-click: look next to the patcher / in the current folder
        here = os.path.dirname(os.path.abspath(sys.executable if getattr(sys, 'frozen', False) else __file__))
        cands = [os.path.join(d, 'trek.exe') for d in (here, os.getcwd())]
        path = next((c for c in cands if os.path.exists(c)), None)
        if not path:
            print(__doc__)
            print('No trek.exe found next to the patcher. Put it into the game folder or drop trek.exe on it.')
            return 2
    if os.path.isdir(path):
        path = os.path.join(path, 'trek.exe')
    backup = path + '.mpfix_backup'
    if '--restore' in sys.argv:
        if not os.path.exists(backup):
            print('No backup found:', backup)
            return 1
        shutil.copy2(backup, path)
        print('Original restored:', path)
        return 0
    d = bytearray(open(path, 'rb').read())
    st, msg = status(d)
    if st == 'incompatible' and os.path.exists(backup) and '--check' not in sys.argv:
        b = bytearray(open(backup, 'rb').read())
        if status(b)[0] == 'original':
            print('%s: older version of the fix detected, using the backup as the base.' % path)
            d, st, msg = b, 'original', 'Unmodified, compatible trek.exe (from backup).'
    print('%s: %s' % (path, msg))
    if '--check' in sys.argv or st != 'original':
        return 0 if st in ('original', 'patched') else 1
    if not os.path.exists(backup):
        shutil.copy2(path, backup)
        print('Backup created:', backup)
    opt_ok = all(d[o:o + len(a) // 2] == bytes.fromhex(a) for o, a, b, g in PATCH if g == 1)
    for o, a, b, g in PATCH:
        if g == 0 or opt_ok:
            d[o:o + len(b) // 2] = bytes.fromhex(b)
    if not opt_ok:
        print('Fix MS left out: this trek.exe already has its own morale sum (mod).')
    if d[SLEEP_OFF] == 0x0a and d[SLEEP_OFF - 1] == 0x6a:
        d[SLEEP_OFF] = 0x00
    try:
        add_section(d)
    except ValueError as ex:
        print('ERROR: cannot add the resync section:', ex)
        return 1
    open(path, 'wb').write(d)
    st2, _ = status(d)
    print('Done.' if st2 == 'patched' else 'ERROR while patching!')
    return 0 if st2 == 'patched' else 1


if __name__ == '__main__':
    rc = main()
    if getattr(sys, 'frozen', False):         # keep the console window open after a double-click
        input(chr(10) + 'Press Enter to close.')
    sys.exit(rc)
