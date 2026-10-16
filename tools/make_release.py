"""Generate release artefacts for the BotF multiplayer fix.
  release/botf_mpfix.py              standalone patcher (Python 3, no dependencies)
  release/BotF_MP_fix.patch  patch file in the community 'bof patcher' / UE format
  release/vanilla/*.exe              patched vanilla trek.exe (all 8 installer variants)
"""
import glob, os, sys, hashlib, shutil
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pe import PE
import netfix

BASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
REL = os.environ.get('BOTF_RELEASE', os.path.join(BASE, 'release'))   # output folder
SRC = os.environ.get('BOTF_VANILLA', os.path.join(BASE, 'vanilla_src'))   # unpacked installer: trek,1.exe .. trek,8.exe
VARIANTS = {  # installer source name -> description (from install_script.iss)
    'trek,1.exe': 'EN_800x600', 'trek,2.exe': 'DE_800x600',
    'trek,3.exe': 'EN_1024x768', 'trek,4.exe': 'DE_1024x768',
    'trek,5.exe': 'EN_1366x768', 'trek,6.exe': 'DE_1366x768',
    'trek,7.exe': 'EN_1920x1080', 'trek,8.exe': 'DE_1920x1080',
}
SLEEP_OFF = None


def diff_runs(a, b):
    runs = []
    for i in range(len(a)):
        if a[i] != b[i]:
            if runs and i <= runs[-1][1] + 4:      # merge close changes
                runs[-1][1] = i
            else:
                runs.append([i, i])
    return [(s, bytes(a[s:e + 1]), bytes(b[s:e + 1])) for s, e in runs]


def main():
    os.makedirs(os.path.join(REL, 'vanilla'), exist_ok=True)
    ref = PE(os.path.join(SRC, 'trek,1.exe'))
    patched = PE(os.path.join(SRC, 'trek,1.exe'))
    info = netfix.apply(patched)
    entries = diff_runs(ref.data, patched.data)
    sleep_off = ref.va2off(0x54e1ce)
    core = [e for e in entries if not (e[0] <= sleep_off < e[0] + len(e[1]))]
    sleep = [e for e in entries if e[0] <= sleep_off < e[0] + len(e[1])]
    assert len(sleep) == 1 and len(sleep[0][1]) == 1

    # ---- community .patch file -----------------------------------------------------------
    lines = [
        'NAME: Multiplayer network/desync fix (message order, mid-turn messages, send loop, keepalive, kill requests, production/buy/martial-law/shipyard/refit desyncs, heap race, tactical combat crash, monster state, tactical AUTO, held-back options/load, timer, delete requests)',
        'AUTHOR: Claude (Anthropic) for Stephan, 2026-10-15',
        'DESC: A) production queues (msg 0x74) are sent before the orders (msg 0x68) at end of turn.',
        'DESC: B) orders/queues of a faster player that arrive while this machine is still calculating',
        'DESC:    the turn are parked and handled after the calculation instead of in the middle of it.',
        'DESC: C) DPMP send loop no longer blocks the receive thread for a whole message; a failing',
        'DESC:    IDirectPlay::Send is retried ~5 s instead of forever (freeze when a player was gone).',
        'DESC: D) 1-byte keepalive every 10 s from the receive thread keeps idle links alive during long turns.',
        'DESC: E) turn processing no longer sends "kill order" requests (type 9). Every machine already deletes',
        'DESC:    the order itself; the other machines matched the request by a sequence number that differs',
        'DESC:    per machine and could delete an unrelated order -> desync, more likely the longer the game runs.',
        'DESC: I) cancelling martial law and re-selecting it no longer leaves a stale turn counter on the other',
        'DESC:    machines (their morale rose a turn early -> sync error).',
        'DESC: M) deleting a build that the turn calculation had just started now also resets production on the',
        'DESC:    other machines (they kept the invested industry -> next build finished early -> sync error).',
        'DESC: N) deleting a BOUGHT build now tells the other machines (they kept the purchase -> sync error).',
        'DESC: S) the memory manager now locks its default heap: the network thread and the game used it at',
        'DESC:    the same time, which could hand out one memory block twice -> a game quit silently and the',
        'DESC:    others saw "Disconnected", mostly in long games (crash while loading graphics or sounds).',
        'DESC: H) losing a shipyard (scrapped, bombarded, unrest) no longer lets the owner restart production a turn',
        'DESC:    ahead of the other machines (the owner finished the next build early -> sync error).',
        'DESC: J) a ship class made obsolete by research no longer creates a second copy of the replacement build',
        'DESC:    order on the other machines (they built ships twice -> sync error).',
        'DESC: T) manual tactical combat: a ship with an attack order but no target no longer ends the game with',
        'DESC:    "ai\assault.c line 562" (seen against the Edo Guardian); the ship holds position for that round.',
        'DESC: W) the random-monster countdown is reset when a game is started or loaded; a player who restarted',
        'DESC:    the game after a crash used to get monsters on other turns than the rest (sync error).',
        'DESC: W2) the same reset also covers the monster name counters (ship checksum) and the economy',
        'DESC:    checksum buffer, which overflowed when a larger galaxy was loaded after a smaller game.',
        'DESC: U) the AUTO box in manual tactical combat orders only your own ships, no longer those of an',
        'DESC:    allied computer empire (the other machines let the computer order them -> battle.c line 909).',
        'DESC: L) messages that change the game while another machine still calculates the turn are held back',
        'DESC:    until it has finished: host options (no more "conninit.c line 617" crash) and loading a saved game.',
        'DESC: K) with a turn time limit, the turn is no longer sent while a dialog (e.g. "delete build?") is open.',
        'DESC: V) a "delete order" request only matches an order of the empire that sent it.',
        'DESC: X) a fleet that flies through a wormhole comes out at the same place on every machine (the exit',
        'DESC:    position no longer depends on the local galaxy-map scroll and zoom).',
        'DESC: Y) a player who leaves after ending the turn no longer blocks the others for ever; only human',
        'DESC:    players still in the game are waited for.',
        'DESC: W3) the ship name list is reset when a game is loaded, like the monster counters.',
        'DESC: Z) the military-sector and diplomacy checksums cover all of their data (detection only).',
        'DESC: O) all stations of an eliminated empire are removed (one of two neighbours was left over).',
        'DESC: P) changing conquer/liberate of a running invasion is no longer lost.',
        'DESC: Q) a colonize order of a fleet whose colony ship was destroyed in combat no longer crashes.',
        'DESC: G) the system screen no longer crashes when it shows a system the player does not own.',
        'DESC: OP) closing the options dialog while waiting no longer switches random events or manual combat on one machine.',
        'DESC: F) monsters in tactical combat no longer decide on leftover memory (combat units start zeroed).',
        'DESC: CA) conquering the last system of an empire when it is its original capital no longer crashes.',
        'DESC: EL) orders of an eliminated player are no longer merged; IN) intel changes after END TURN are ignored.',
        'DESC: Wire format unchanged (works with unpatched players); full effect when all players use it.',
        'DESC: Uses the free code area 0x516e60-0x517750 (file 0x116260) and .bss 0x6896e0-0x689800.',
        'DESC: Also apply the community "packet.patch" (Sleep 10 -> 0 in the send loop) if not yet done.',
        'DESC: patch file name: BotF_MP_fix.patch',
        'TAG: fix',
        '',
        '# >>  = vanilla/original value',
        '# <<  = new value',
        '',
    ]
    for off, old, new in core:
        for k in range(0, len(old), 16):
            lines.append('>> 0x%06x %s' % (off + k, ' '.join('%02X' % x for x in old[k:k + 16])))
        for k in range(0, len(new), 16):
            lines.append('<< 0x%06x %s' % (off + k, ' '.join('%02X' % x for x in new[k:k + 16])))
        lines.append('')
    open(os.path.join(REL, 'BotF_MP_fix.patch'), 'w', newline='\r\n').write('\n'.join(lines))

    # ---- standalone patcher ---------------------------------------------------------------
    tpl = open(os.path.join(os.path.dirname(__file__), 'botf_mpfix_template.py'), encoding='utf-8').read()
    data = ',\n'.join('    (0x%06x, %r, %r)' % (o, a.hex(), b.hex()) for o, a, b in core)
    so, sa, sb = sleep[0]
    tpl = tpl.replace('#PATCH_DATA#', data).replace('#SLEEP_OFF#', '0x%06x' % so)
    open(os.path.join(REL, 'botf_mpfix.py'), 'w', encoding='utf-8', newline='\n').write(tpl)

    # ---- patched vanilla executables ------------------------------------------------------
    for name, desc in VARIANTS.items():
        p = PE(os.path.join(SRC, name))
        netfix.apply(p)
        out = os.path.join(REL, 'vanilla', 'trek_%s_mpfix.exe' % desc)
        p.save(out)
        print('%-28s sha256 %s' % (os.path.basename(out), hashlib.sha256(p.data).hexdigest()[:16]))
    print('patch entries', len(core), '+ sleep', hex(so))


if __name__ == '__main__':
    main()
