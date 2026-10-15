## BotF multiplayer fix v1.4.0

Three more rare multiplayer problems fixed in *Star Trek: Birth of the Federation*, found by systematic code
reviews.

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

- **AUTO in tactical combat with a computer ally.** Ticking AUTO also gave orders to the ships of an allied
  computer empire, but only on your machine. The other machines let the computer command those ships, so the
  battle went out of sync and a game quit with "battle.c line 909". AUTO now only commands your own ships.
- **Monster names after a restart.** Like the monster countdown fixed in v1.3.0, two counters for monster
  names belonged to the running program; after a restart new monsters got different names and the ship
  checksum failed. They are now reset when a game is started or loaded.
- **Loading a larger galaxy after a smaller game** in the same session could overrun an internal buffer and
  crash the game later. The buffer is now re-created for every game.

### Included from earlier versions

- Tactical combat crash and monster countdown (v1.3.0); shipyard loss and ship-class upgrade (v1.2.0);
  "Disconnected" heap crash (v1.1.0); sync errors when deleting builds, martial law, stray delete requests,
  and network robustness (v1.0.0).

### Known open points

- Mods that change game rules (for example "chasing ships away") can cause their own sync errors.
- A few rare cases are still open (turn time limit with an open dialog, options changed by the host while a
  client calculates, a player dropping out with three or more humans); see the README.

Details, evidence and tools: see the README in the repository.
