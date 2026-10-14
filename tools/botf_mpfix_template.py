#!/usr/bin/env python3
"""BotF multiplayer fix - patcher for trek.exe (Star Trek: Birth of the Federation).

Usage:
    python botf_mpfix.py <path\\to\\trek.exe>            check and patch (backup: trek.exe.mpfix_backup)
    python botf_mpfix.py <path\\to\\trek.exe> --check    show status only
    python botf_mpfix.py <path\\to\\trek.exe> --restore  restore the backup

Tested with all 134 trek.exe variants of "BOTF Most Active 2.0.4" (vanilla EN/DE, all resolutions,
ECM, BOP, MUM, FAW, AAM, FMPM, UCW, UM5, UDM, GALM, PLUS).
All players should use the patch; unpatched players can still join.

Contents (details in README.md):
  A  Build queues (msg 0x74) are sent before the orders (msg 0x68).
  B  Orders/queues of a faster player for the next turn are held back while this machine is
     still calculating the current turn instead of being applied in the middle of it.
  C  The send loop no longer blocks the receive thread; a failing send no longer loops forever
     (freeze when a player is gone); no 10 ms pause per packet.
  D  A keepalive every 10 s keeps the connection open during long turn calculations.
  E  Turn processing no longer sends "delete order" requests (they could hit an unrelated order).
  I  Removing and re-adding martial law no longer leaves a stale counter on the other machines.
  M  Deleting a build that the turn calculation had just started also resets production on the
     other machines.
  N  Deleting a BOUGHT build now tells the other machines (they kept the purchase -> sync error).
"""
import os, shutil, sys

# (file offset, original bytes, patched bytes)
PATCH = [
#PATCH_DATA#
]
SLEEP_OFF = #SLEEP_OFF#          # push 0x0a -> push 0x00 (identical to the community packet.patch)
CAVE = (0x116260, 0x117200)       # must be zero before patching


def status(d):
    if len(d) != 1781248 or d[:2] != b'MZ':
        return 'unknown', 'Not a known trek.exe (size %d).' % len(d)
    orig = all(d[o:o + len(a) // 2] == bytes.fromhex(a) for o, a, b in PATCH)
    done = all(d[o:o + len(b) // 2] == bytes.fromhex(b) for o, a, b in PATCH)
    if done:
        return 'patched', 'The multiplayer fix is already installed.'
    if orig and not any(d[CAVE[0]:CAVE[1]]):
        return 'original', 'Unmodified, compatible trek.exe.'
    bad = [hex(o) for o, a, b in PATCH if d[o:o + len(a) // 2] != bytes.fromhex(a)]
    return 'incompatible', 'Unexpected bytes at offsets: ' + ', '.join(bad[:8])


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    path = sys.argv[1]
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
    for o, a, b in PATCH:
        d[o:o + len(b) // 2] = bytes.fromhex(b)
    if d[SLEEP_OFF] == 0x0a and d[SLEEP_OFF - 1] == 0x6a:
        d[SLEEP_OFF] = 0x00
    open(path, 'wb').write(d)
    st2, _ = status(d)
    print('Done.' if st2 == 'patched' else 'ERROR while patching!')
    return 0 if st2 == 'patched' else 1


if __name__ == '__main__':
    sys.exit(main())
