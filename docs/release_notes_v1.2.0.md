## BotF multiplayer fix v1.2.0

Two more sync errors fixed in *Star Trek: Birth of the Federation* multiplayer games. Both came from a
review of the game code and were then reproduced in real 5-player test games.

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

- **Losing a shipyard while it builds a ship.** When a shipyard was scrapped, bombarded or lost to unrest,
  the owner's computer started the next build in the list a turn ahead of everybody else. A turn later
  the owner finished it early and the game stopped with a sync error. Now every computer starts it at
  the same time.
- **A ship class becomes obsolete through research.** The build order is switched to the new class. The
  other computers made their own copy of the new order and then received the owner's copy too, so they
  built the ships twice. Now only the owner creates the order.

Both were reproduced on the original game and stay in sync with the fix. A new 300-turn test game in a
small galaxy with five automated players (wars, diplomacy, about 250 ships ordered per player, monsters
and random events) ran without a single sync error or crash.

### Included from earlier versions

- **"Disconnected" crash** (v1.1.0): the network thread and the game no longer share memory without a lock.
- Sync-error fixes (v1.0.0): deleting a bought build, deleting a freshly started build, removing and
  re-adding martial law, stray "delete order" requests.
- Network robustness (v1.0.0): message order, no updates in the middle of a turn calculation, no endless
  send loop when a player is gone, keepalive during long turns.

### Known open points

- Mods that change game rules (for example "chasing ships away") can cause their own sync errors.

Details, evidence and tools: see the README in the repository.
