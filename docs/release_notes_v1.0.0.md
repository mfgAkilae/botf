## BotF multiplayer fix v1.0.0

Fixes the late-game **"A synchronization error has occurred"** / **"Disconnected"** problem in
*Star Trek: Birth of the Federation* multiplayer games.

### How to install (Windows)

1. Download **`BotF_MP_fix.exe`**.
2. Put it into your BotF game folder (where `trek.exe` is) and **double-click it**.
   (Or drag `trek.exe` onto `BotF_MP_fix.exe`.)
3. Done. A backup `trek.exe.mpfix_backup` is created automatically.
4. **Every player in your game needs the fix.** Unpatched players can still join, but the game only
   stays in sync if everybody is patched.

To undo: run `BotF_MP_fix.exe trek.exe --restore` from a command prompt in the game folder (or copy
the backup back over `trek.exe`).

Alternatives: `botf_mpfix.py` (same patcher, needs Python 3) or `BotF_MP_fix.patch` for the community
patcher / Ultimate Editor.

Works with all 143 `trek.exe` variants of the "BOTF Most Active 2.0.4" installer: vanilla English and
German in all resolutions, and the mods ECM, ECMS, BOP, MUM, FAW, AAM, FMPM, UCW, UM5, UDM, GALM and
PLUS. No game files are included in this release.

### What it fixes

In multiplayer every computer calculates the whole galaxy itself and only the players' orders are
sent around. If one computer ends up with a slightly different game, the game stops. Three everyday
actions caused exactly that:

- **Deleting a build you had bought.** Only your computer cancelled the purchase. The others kept it
  and calculated different costs a few turns later. This one happened by itself in a 5-player test
  game at turn 331, and the fix keeps the same game running.
- **Deleting a build the game had just started from your queue.** The others kept the invested
  industry and finished your next building a turn early.
- **Removing martial law and putting it back.** The others kept counting and your planet calmed down
  a turn earlier on their machines.

Big late-game empires do these things all the time, which is why games used to die late.
The patch also makes the network more robust: correct message order, no updates in the middle of a
turn calculation, no endless send loop when a player is gone, and a keepalive during long turns.

### Known open points

- Rarely a game closed without an error message during the turn calculation in long test games. The
  cause is still being investigated.
- Mods that change game rules (for example "chasing ships away") can cause their own sync errors.

Details, evidence and tools: see the README in the repository.
