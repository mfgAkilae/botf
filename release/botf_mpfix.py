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
    (0x001632, '2eff15ec455700', 'e8294e11009090'),
    (0x0017ca, '2eff15ec455700', 'e8914c11009090'),
    (0x001909, '2eff15ec455700', 'e8524b11009090'),
    (0x056b4a, '66c7840284', '01c2c78280'),
    (0x056b54, 'c784028000', '0000c78284'),
    (0x056b5f, '66c7840288000000ff7f66c784028a', '00c78288000000ff7fff7f66c78290'),
    (0x056b72, '7f66c7840290000000ffff66c78402980000000000', 'ff66c7829800000000009090909090909090909090'),
    (0x056bdb, '578b31568b7904', 'e930f90b009090'),
    (0x056d46, '8b0d24295a00', 'e855f70b0090'),
    (0x056dcb, '8b4424048b51148b008902', 'e800f70b00909090909090'),
    (0x057556, 'e6e1ffffe82154', '2654ffffe8e1e1'),
    (0x057615, 'c7051c295a0001000000', 'e866ee0b009090909090'),
    (0x057ad6, '31ff893d1c295a00', 'e835e80b00909090'),
    (0x0fcd30, '909df5ff', '4c980100'),
    (0x109b09, '668904248b0424', 'e992c700009090'),
    (0x116260, '00000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000', '6031f63b35e496680073248b04f5f4966800508b04f5f0966800506800040000ff354c075a00ff152c46570046ebd4c705e49668'),
    (0x116299, '0000', '61c3'),
    (0x1162a0, '000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000', '668904248b042481f900040000753f833d1c295a00017415833de496680000742de82d000000e895ffffffeb1c6683f86874086683f8747402eb13833de496680017730ae80a000000e97438ffffe91d38ffff50a1e49668008934c5f0966800893cc5f4966800ff05e496680058c300c7051c295a'),
    (0x11631a, '0000000000000000', 'e841ffffff31ffc3'),
    (0x116330, '0000000000000000000000000000000000000000000000000000', '8954243489442428606800866800ff154845570061c705e09668'),
    (0x11634f, '00000000', 'e9f67003'),
    (0x116360, '00000000000000000000000000000000000000000000', '606800866800ff15ac445700616800866800e9827203'),
    (0x116380, '00000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000', '833de096680000753d56befa00000050525351e8784c030083f80174114e74186a14ff1594455700595b5a58ebe183c4105eb801000000c383c4105ec705e096680001000000b801000000c3'),
    (0x1163d0, '0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000', '60a130075a0085c07420833d7cd95f000074176a0168e89668006a006a00ff35c4d85f00508b08ff516861c3'),
    (0x116400, '00000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000', '833d48075a0001752260ff15fc43570089c22b15ec96680081fa10270000720aa3ec966800e8a6ffffff6168e803000057ff15c04557003d02010000750b833d48075a00017507ebb7e9d66a0300e9da6a03'),
    (0x116460, '000000000000000000000000000000000000000000000000', 'ff05b0976800ff742404ff15ec455700ff0db0976800c204'),
    (0x116480, '0000000000000000000000000000000000000000000000', 'c7051c295a000100000050a1b0976800a3b497680058c3'),
    (0x1164a0, '000000000000000000000000000000000000000000000000000000000000000000', '8b0d24295a00833d1c295a0001751150a1b09768003b05b497680058750231c9c3'),
    (0x1164d0, '0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000', '8b4424088b5114508b008902588378100075218b501485d2741a538b1a85db740583fb02750d0fb75a0481cb00004b4b89590c5b8b5114c3'),
    (0x116510, '000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000', '8b410c89c281e20000ffff81fa00004b4b754a25ffff0000663b05bc365a00733c69c0280300000305c8365a00c78080'),
    (0x116547, '000000', 'c78084'),
    (0x116551, '0000000000000000000000000000000000000000000000', 'c78088000000ff7fff7f66c78090000000ffff66c78098'),
    (0x11656d, '0000000000000000000000000000', '31c0578b31568b7904e96706f4ff'),
    (0x116580, '0000000000000000000000000000000000000000000000', '5052833d24295a00007405e8b007f4ff5a58e92d05f4ff'),
    (0x14cf13, '6aff572eff15c04557003d020100007409', 'e9e894fcff909090909090909090909090'),
    (0x14d442, '8954243489442428', 'e9e98efcff909090'),
    (0x14d573, '99daff', '098efc'),
    (0x14d5f4, '6800866800', 'e9678dfcff'),
    (0x19e81c, '00', '02')
]
SLEEP_OFF = 0x14d5ce          # push 0x0a -> push 0x00 (identical to the community packet.patch)
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
    for o, a, b in PATCH:
        d[o:o + len(b) // 2] = bytes.fromhex(b)
    if d[SLEEP_OFF] == 0x0a and d[SLEEP_OFF - 1] == 0x6a:
        d[SLEEP_OFF] = 0x00
    open(path, 'wb').write(d)
    st2, _ = status(d)
    print('Done.' if st2 == 'patched' else 'ERROR while patching!')
    return 0 if st2 == 'patched' else 1


if __name__ == '__main__':
    rc = main()
    if getattr(sys, 'frozen', False):         # keep the console window open after a double-click
        input(chr(10) + 'Press Enter to close.')
    sys.exit(rc)
