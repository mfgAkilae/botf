## BotF multiplayer fix v1.6.0

A hang when a player leaves, a colonization crash and several smaller multiplayer problems fixed in
*Star Trek: Birth of the Federation*, found by focused code reviews and reproduced in the five-player test bed.

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

- **A player leaves after ending the turn.** The others waited for ever for the next turn. Now the turn
  goes on with the players who are still in the game.
- **Colony ship destroyed before it could colonize.** If combat destroyed the colony ship of a fleet with a
  colonize order while other ships survived, the game crashed ("Disconnected" for everybody else). The order
  is now dropped.
- **Wormholes.** A fleet that flies through a wormhole could come out in different places on different
  machines (the position depended on each player's map view).
- **Conquer or liberate.** Changing that choice for an invasion that is already running was ignored.
- **Eliminated empires.** Some of their stations were left on the map.
- The ship name list is reset when a game is loaded, and two turn checksums now cover all of their data, so
  a divergence is found earlier.

### Included from earlier versions

- Messages during turn processing, turn timer in dialogs, delete requests (v1.5.0); AUTO in tactical combat,
  monster state after a restart (v1.4.0); tactical combat crash (v1.3.0); shipyard loss and ship-class upgrade
  (v1.2.0); "Disconnected" heap crash (v1.1.0); sync errors when deleting builds, martial law, stray delete
  requests, and network robustness (v1.0.0).

### Known open points

- Mods that change game rules (for example "chasing ships away") can cause their own sync errors.
- In games with three or more humans, the machines may notice a dropped player at different times; and
  floating-point results in tactical combat may differ between Intel and AMD processors. Neither is fixed
  (see the README).

Details, evidence and tools: see the README in the repository.
