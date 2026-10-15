## BotF multiplayer fix v1.5.0

More rare multiplayer problems fixed in *Star Trek: Birth of the Federation*, found by ten systematic code
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

- **Host changes options while others still calculate.** Closing the options dialog on the host sent a
  message that crashed players who were still calculating the turn ("conninit.c line 617"). Such messages,
  and loading a multiplayer save, now wait until the turn is finished everywhere.
- **Turn time limit with an open dialog.** The timer could end your turn while a "delete build?" box was
  open; what you clicked afterwards was never sent. The timer now waits until the dialog is closed.
- **Delete requests** now only remove an order of the empire that sent them.

### Included from earlier versions

- AUTO in tactical combat, monster state after a restart (v1.4.0); tactical combat crash (v1.3.0); shipyard
  loss and ship-class upgrade (v1.2.0); "Disconnected" heap crash (v1.1.0); sync errors when deleting builds,
  martial law, stray delete requests, and network robustness (v1.0.0).

### Known open points

- Mods that change game rules (for example "chasing ships away") can cause their own sync errors.
- A player dropping out of a game with three or more humans, and possible floating-point differences between
  Intel and AMD processors in tactical combat, are not fixed (see the README).

Details, evidence and tools: see the README in the repository.
