## BotF multiplayer fix v1.6.1

Fixes a crash in the system screen that ended a test game with "Disconnected".

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

- **System screen crash.** When the system screen showed a system that no longer belonged to the player
  (lost to a minor race, rebels or nobody), the game crashed and everybody else saw "Disconnected". The screen
  now switches to one of the player's own systems. Found by the test agents in a new 5-player game (turn 179).

### Included from earlier versions

- Player leaving after ending the turn, colonize crash, wormholes, conquer/liberate, stations, checksums
  (v1.6.0); messages during turn processing, turn timer in dialogs, delete requests (v1.5.0); AUTO in tactical combat,
  monster state after a restart (v1.4.0); tactical combat crash (v1.3.0); shipyard loss and ship-class upgrade
  (v1.2.0); "Disconnected" heap crash (v1.1.0); sync errors when deleting builds, martial law, stray delete
  requests, and network robustness (v1.0.0).

### Known open points

- Mods that change game rules (for example "chasing ships away") can cause their own sync errors.
- In games with three or more humans, the machines may notice a dropped player at different times; and
  floating-point results in tactical combat may differ between Intel and AMD processors. Neither is fixed
  (see the README).

Details, evidence and tools: see the README in the repository.
