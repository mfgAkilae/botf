## BotF multiplayer fix v1.3.0

A crash in manual tactical combat and another sync error fixed in *Star Trek: Birth of the Federation*
multiplayer games.

### How to install (Windows)

1. Download **`BotF_MP_fix.exe`**.
2. Put it into your BotF game folder (where `trek.exe` is) and **double-click it**.
   (Or drag `trek.exe` onto `BotF_MP_fix.exe`.)
3. Done. A backup `trek.exe.mpfix_backup` is created automatically.
   **Already using an older version?** Just run the new version the same way. It rebuilds `trek.exe` from the backup.
4. **Every player in your game needs the fix.**

To undo: run `BotF_MP_fix.exe trek.exe --restore` from a command prompt in the game folder (or copy
the backup back over `trek.exe`).

Alternatives: `botf_mpfix.py` (same patcher, needs Python 3) or `BotF_MP_fix.patch` for the community
patcher / Ultimate Editor.

Works with all 143 `trek.exe` variants of the "BOTF Most Active 2.0.4" installer (vanilla English and
German in all resolutions, and the mods ECM, ECMS, BOP, MUM, FAW, AAM, FMPM, UCW, UM5, UDM, GALM, PLUS).
No game files are included.

### What is new

- **Crash in manual tactical combat.** A ship with an attack order but no target made the game quit with
  "ai\assault.c line 562" (the others saw "Disconnected"). Our automated players ran into it fighting the
  Edo Guardian. Now the ship just holds its position for that round.
- **Monsters after a restart.** The countdown for random monsters belonged to the running program, not to
  the game. After a crash the player who restarted the game got monsters on other turns than everybody
  else, and the game went out of sync again. Now it is reset whenever a game is started or loaded.
- Small correction to the shipyard fix of v1.2.0 (shipyards lost later in the turn, e.g. by sabotage).

Tested with five automated players over more than 100 turns of manual tactical combat (wars, monsters,
diplomacy), plus targeted scenarios that crash or desync the original game.

### Included from earlier versions

- Shipyard loss and ship-class upgrade sync errors (v1.2.0).
- "Disconnected" crash from an unprotected shared heap (v1.1.0).
- Sync-error fixes for deleting builds, martial law, stray delete requests; network robustness (v1.0.0).

### Known open points

- Mods that change game rules (for example "chasing ships away") can cause their own sync errors.
- A few rare cases from a code review are still open (see the README).

Details, evidence and tools: see the README in the repository.
