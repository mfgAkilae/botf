## BotF multiplayer fix v1.1.0

Fixes the **"Disconnected"** problem in long *Star Trek: Birth of the Federation* multiplayer games:
a player's game suddenly closed without any error message, and everybody else saw "Disconnected".

### How to install (Windows)

1. Download **`BotF_MP_fix.exe`**.
2. Put it into your BotF game folder (where `trek.exe` is) and **double-click it**.
   (Or drag `trek.exe` onto `BotF_MP_fix.exe`.)
3. Done. A backup `trek.exe.mpfix_backup` is created automatically.
   **Already using v1.0.0?** Just run the new version the same way. It rebuilds `trek.exe` from the backup.
4. **Every player in your game needs the fix.**

To undo: run `BotF_MP_fix.exe trek.exe --restore` from a command prompt in the game folder (or copy
the backup back over `trek.exe`).

Alternatives: `botf_mpfix.py` (same patcher, needs Python 3) or `BotF_MP_fix.patch` for the community
patcher / Ultimate Editor.

Works with all 143 `trek.exe` variants of the "BOTF Most Active 2.0.4" installer (vanilla English and
German in all resolutions, and the mods ECM, ECMS, BOP, MUM, FAW, AAM, FMPM, UCW, UM5, UDM, GALM, PLUS).
No game files are included.

### What is new: the "Disconnected" crash

The game uses two workers at the same time: one receives the network messages from the other players,
the other runs the game itself. Both take memory from the same shelf. That shelf had no lock. Once in a
while both workers grabbed the same piece of memory at the same moment. Shortly after, the game
crashed silently, usually while loading a picture or a sound. For the other players this looked like
a lost connection.

Every message is another chance for this to happen. That is why it hit long games with big empires
much more often than short ones.

The fix is one byte: the shelf now has the same lock that the game's other network memory already had.

How we know it works:

- In the 5-player test games the old version lost a player every 30–50 turns from the same save.
  With the fix the same game ran 160 turns without a crash.
- In a stress test the network side asks for memory thousands of times per second. The old version lost
  all 5 games within 3 turns, with exactly the same crash points as in normal play. With the fix,
  50 turns ran without a single crash.

### Also included (from v1.0.0)

- Sync-error fixes: deleting a bought build, deleting a freshly started build, removing and re-adding
  martial law, and stray "delete order" requests.
- Network robustness: message order, no updates in the middle of a turn calculation, no endless send
  loop when a player is gone, keepalive during long turns.

### Known open points

- Mods that change game rules (for example "chasing ships away") can cause their own sync errors.

Details, evidence and tools: see the README in the repository.
