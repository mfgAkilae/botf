## BotF multiplayer fix v2.1.0

**A desync no longer ends the game.** Until now every sync error was final: "A synchronization error has
occurred. The multiplayer game cannot continue in its current state." With v2.1.0 the game repairs itself: the
host's game is sent to every player and loaded, and the game goes on from there. This takes a few seconds and
shows the normal "please wait" box.

### How to install (Windows)

1. Download **`BotF_MP_fix.exe`**.
2. Put it into your BotF game folder (where `trek.exe` is) and **double-click it**.
   (Or drag `trek.exe` onto `BotF_MP_fix.exe`.)
3. Done. A backup `trek.exe.mpfix_backup` is created automatically.
   **Already using an older version?** Just run the new version the same way. It rebuilds `trek.exe` from the backup.
4. **Every player in your game needs the fix.** The automatic repair only runs when every player has v2.1.0;
   with an older version in the game you get the old error message instead.

To undo: run `BotF_MP_fix.exe trek.exe --restore` from a command prompt in the game folder (or copy
the backup back over `trek.exe`). Going back to v2.0.0: restore first, then run the v2.0.0 patcher (it does not
recognise a v2.1.0 `trek.exe` and leaves it unchanged).

Alternatives: `botf_mpfix.py` (the same patcher as a readable Python 3 script). `BotF_MP_fix.patch` for the
community patcher / Ultimate Editor has every fix **except the automatic repair**: that one needs a new section
in `trek.exe`, which the patch file format cannot add.

Works with all 143 `trek.exe` variants of the "BOTF Most Active 2.0.4" installer (vanilla English and
German in all resolutions, and the mods ECM, ECMS, BOP, MUM, FAW, AAM, FMPM, UCW, UM5, UDM, GALM, PLUS).
No game files are included.

### What is new

- **Automatic repair after a desync (RY).** When the checksums of two players differ, the host saves the game
  and sends it; every player loads it without leaving the session. What everybody entered in the current turn
  is lost (build queues come back from the save), and the game goes on from the host's state. Before it starts,
  the host asks every player whether he can take part; if one does not answer (older version), nobody loads and
  the old error message appears at the next check.
- This also covers the one known cause of a desync that is not fixed directly: a player who drops out in the very
  moment he sends his orders (only some machines received them).
- Smaller things: the test players now also answer diplomatic proposals, and the test tools for leaving players,
  trade routes and diplomacy after the turn timer are new (no change to the game beyond the repair).

### Tested

- A desync made on purpose in a five-player game: found, repaired, the game state equal to the host's on every
  machine, then further turns without a sync error.
- Under play with automatic players (building, fleets, wars, diplomacy, manual tactical combat): a new desync
  every four turns, each one repaired by itself, in a small new game and in a late war game (turn 520).
- A player who drops out while sending his orders (the open point of v2.0.0): repaired at the next turn.
- The host leaves the game: the new host repairs the next desync.
- One player with v2.0.0 in the game: he gets the old error message, the others do not load anything. The host
  leaving or quitting while it waits for the answers: nothing is loaded anywhere.
- The patcher gives the same result as the source on all 143 `trek.exe` variants, upgrades from v2.0.0 and restores
  the original.
- Without a desync the game behaves as in v2.0.0: 44 turns of a war game with agents that also answer diplomatic
  proposals (96 accepted, 76 rejected), live drops of a client, of the host and of a player inside the turn
  calculation, trade routes and treaties between human players.

### Known open points

- The repair keeps the host's state. If the host itself is the one whose game went wrong, the wrong state is kept
  (on every machine, so the game goes on).
- Mods that change game rules (for example "chasing ships away") can cause their own sync errors; the repair
  then runs each time.
- Floating-point results in tactical combat may differ between Intel and AMD processors.

Details, evidence and tools: see the README in the repository.
