## BotF multiplayer fix v2.0.0

The biggest update so far: a full code review of the whole multiplayer code with four AI models, every
finding checked in the five-player test bed, and eleven new fixes. Players can now leave a game, also in the
middle of a battle, without stopping or desynchronising the others.

### How to install (Windows)

1. Download **`BotF_MP_fix.exe`**.
2. Put it into your BotF game folder (where `trek.exe` is) and **double-click it**.
   (Or drag `trek.exe` onto `BotF_MP_fix.exe`.)
3. Done. A backup `trek.exe.mpfix_backup` is created automatically.
   **Already using an older version?** Just run the new version the same way. It rebuilds `trek.exe` from the backup.
4. **Every player in your game needs the fix.**

To undo: run `BotF_MP_fix.exe trek.exe --restore` from a command prompt in the game folder (or copy
the backup back over `trek.exe`).

Alternatives: `botf_mpfix.py` (the same patcher as a readable Python 3 script) or `BotF_MP_fix.patch` for the
community patcher / Ultimate Editor. The README explains how to rebuild all of them from `tools/netfix.py`.

Works with all 143 `trek.exe` variants of the "BOTF Most Active 2.0.4" installer (vanilla English and
German in all resolutions, and the mods ECM, ECMS, BOP, MUM, FAW, AAM, FMPM, UCW, UM5, UDM, GALM, PLUS).
No game files are included.

### What is new

Players leaving:
- **A player who leaves during a battle** no longer freezes the game for the others (they waited for ever for
  his combat round or his battle results), and every machine now takes over his empire for the computer in
  the same way (before, only the machine that noticed the leave first did it: sync error one turn later).
- **A player who leaves** now takes effect at the same point of the game on every machine, even though the
  machines notice it up to a minute apart.

Sync errors (each one reproduced in the test bed, then fixed):
- **Losing a shipyard** right after a ship was started (scrapped, bombarded, unrest): the other machines kept
  building the ship.
- **An empire is eliminated** while a player had just changed his intelligence settings: they stayed on his
  machine only.
- **With a turn timer**: research changes and task-force redeployment made after the timer ended the turn were
  applied on your machine only.
- **The F6 key** (a leftover debug key) spawned a monster on the machine of the player who pressed it.
- **A desync could go unnoticed** on a machine whose player had already ended the next turn; it is now
  detected everywhere.

Crashes:
- **Invading a system whose native race has died out** crashed every game.
- **Very large empires** (about 164 systems at high morale) crashed every game (vanilla `trek.exe`; the mods
  already had their own fix).
- The patch's code area was also read by the movie player (found by a reviewer of the patch, thank you!).

### Included from earlier versions

- Options while waiting, monsters in tactical combat, conquering a capital, eliminated players, intel after
  END TURN (v1.7.0); system screen crash (v1.6.1); player leaving after ending the turn, colonize crash,
  wormholes, conquer/liberate, stations, checksums (v1.6.0); messages during turn processing, turn timer in
  dialogs, delete requests (v1.5.0); AUTO in tactical combat, monster state after a restart (v1.4.0);
  tactical combat crash (v1.3.0); shipyard loss and ship-class upgrade (v1.2.0); "Disconnected" heap crash
  (v1.1.0); sync errors when deleting builds, martial law, stray delete requests, and network robustness
  (v1.0.0).

### Tested

Five game instances on one PC with automatic players (building, buying, labour, fleets and invasions,
wars, diplomacy, intelligence, manual tactical combat, orders while waiting for the others): 60 turns of a
late war game, a new 120-turn war game, and further runs with a simulated slow network. No sync error and
no crash. All 143 `trek.exe` variants patch cleanly, and an upgrade from v1.7.0 gives the same result.

### Known open points

- Mods that change game rules (for example "chasing ships away") can cause their own sync errors.
- A player who drops out in the very moment he sends his orders can still desync the game (only some machines
  received them).
- Floating-point results in tactical combat may differ between Intel and AMD processors.
- Coming next, tested but not in this release: an automatic resync that heals a desync by itself (the host
  sends its game and everybody loads it).

Details, evidence and tools: see the README in the repository.
