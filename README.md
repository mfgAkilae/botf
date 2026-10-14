# Star Trek: Birth of the Federation – multiplayer fix

Long multiplayer games of *Star Trek: Birth of the Federation* (MicroProse, 1999) tend to die late:
after many turns the game stops with **"A synchronization error has occurred. The multiplayer game
cannot continue in its current state."** or a player is shown as **"Disconnected"**. The bug was never
fixed officially.

This repository contains a binary patch for `trek.exe` (version 2.0.4 vanilla, all 8 language and
resolution variants, and the mods shipped with "BOTF Most Active 2.0.4"), the tools used to reverse
engineer the game, and a multi-instance test bed that plays real 5-player games automatically.

No game files are included. You need your own copy of the game.

## Installation

1. Download `BotF_MP_fix.exe` from the [latest release](https://github.com/mfgAkilae/botf/releases/latest).
2. Put it into the game folder (next to `trek.exe`) and double-click it, or drop `trek.exe` onto it.
   A backup `trek.exe.mpfix_backup` is created.
   Without the exe: `python release/botf_mpfix.py "C:\Games\BotF\trek.exe"` (Python 3, no
   dependencies). `--check` shows the status, `--restore` brings back the original.
   Alternatively apply `release/BotF_MP_fix.patch` with the community patcher / Ultimate Editor.
   All 143 `trek.exe` variants of "BOTF Most Active 2.0.4" (vanilla EN/DE, all resolutions, and the
   mods ECM, ECMS, BOP, MUM, FAW, AAM, FMPM, UCW, UM5, UDM, GALM, PLUS) are supported.
3. All players should use the patch. Unpatched players can still connect (the network message format
   is unchanged), but the fixes only take full effect when everyone is patched.

## How BotF multiplayer works

BotF runs in **lockstep**: every machine simulates the whole galaxy on its own. Each turn the machines
only exchange the players' orders (message `0x68`) and build queues (`0x74`). After every turn each
machine sends a heartbeat (`0x71`) with the random number generator state and five checksums (task
forces, ships, military sectors, **systems' economy = `crcSolarBld`**, diplomacy). If any of them
differs, the game shows the synchronization error. A failed internal check (assert) ends the game
process, and the other players see "Disconnected".

So any action that changes one machine's copy of the game but not the others' eventually kills the
session. Player reports of the late-game bug almost always show the same signature: random seed equal,
**only `crcSolarBld` (economy) differs**.

## Bugs found and fixed

| | What goes wrong in the original | Evidence | Fix |
|---|---|---|---|
| **N** | **Deleting a build that was bought.** The game asks "industry invested, delete current build?". On YES it cancels the purchase only on the deleting player's machine. This is the only delete path that does not send a "delete order" request. The other machines keep the purchase and later compute different build costs. | **Occurred naturally** in a scripted 5-player game on the original game at turn 331 (`crcSolarBld` only). Replaying the recorded inputs from the turn-320 save reproduces it exactly. | The delete path sends the request like all others. |
| **M** | **Deleting a build the turn processing has just started.** When a build completes, the next queue item is started; its order exists only on the owner's machine until the next turn. If the player deletes it right away, the other machines do not know the order, ignore the delete request and keep the invested industry. The next build then completes a turn earlier there. | Reproduced on the original from a turn-103 save: sync error in the following turn. | The delete request carries the system; a machine that does not find the order resets that system's production anyway. |
| **I** | **Removing and re-adding martial law.** The owner restarts the martial-law turn counter; on the other machines the delete request clears only 2 of its 4 bytes, so their counter keeps running and the system's morale rises a turn early. | Reproduced on the original from a turn-103 save: sync error, `crcSolarBld` only. | The delete request clears the whole counter. |
| E | Turn processing itself sends "delete order" requests that the receiver matches only by a sequence number. These numbers are assigned per machine and drift apart, so a request could hit an unrelated order on one machine. | Reproduced only artificially (injected collision); not observed in natural games. | Turn processing no longer sends these requests (every machine deletes the order itself anyway). |
| A | Build queues (`0x74`) were sent after the orders (`0x68`); the last player's orders already start the turn on the other machines, so queues could be applied in the middle of the calculation. | Trace in the test bed. | `0x74` is sent before `0x68`. |
| B | Orders of a faster player for the *next* turn were applied in the middle of a slower machine's turn calculation. | Trace in the test bed. | Held back while a turn is being calculated, delivered afterwards in order. |
| C | The send loop held the network lock for a whole message (with a 10 ms sleep and a synchronous round trip per 466-byte packet), blocking the receive thread; a failing send was retried forever (freeze when a player was gone). | Static analysis. | Lock only around the shared counters, no sleep, send retry limited to ~5 s. |
| D | Late turns can take minutes without any game traffic; DirectPlay pings only after 35 s of silence and drops a player after 8 lost pings (e.g. expired NAT/firewall mappings). | DirectPlay protocol documentation. | 1-byte keepalive every 10 s (ignored by all receivers, patched or not). |

**Why "late in the game"?** N, M and I are triggered by ordinary actions that big late-game empires
perform constantly: many planets, full build queues, buying, re-planning builds, unrest in conquered
systems. The more of that a game has, the more certain it is that a turn hits one of them.

## Verification

Test bed: five game instances on one PC, each with its own human empire, connected over DirectPlay.
Five independent player agents (`tools/player.py`) play simultaneously like humans: fleets, production,
buying, labour, re-planning builds, clicking around while waiting. An observer (`tools/observer.py`)
compares all games and the heartbeat checksums after every turn and attaches a debugger to catch
crashes.

| Run | Program | Turns | Result |
|---|---|---|---|
| nat5_bug_1306 | original | 200 → 423 (game won) | no break |
| nat5_bug_1401 | original | 200 → 447 (game won) | no break |
| nat5_bug_1402 | original, agents re-plan freshly started builds | 200 → 331 | **sync error at turn 331** (bug N) |
| replay from turn 320 | original | 320 → 331 | sync error at turn 331, reproducible |
| replay from turn 320 | patched (E+I+M+N) | 320 → 334 | in sync |
| nat5_fix_1402 | patched, same agent behaviour as 1402 | 200 → 500 | no break (128 re-planned builds, 311 purchases) |
| martial-law scenario (`tools/r3test.sh`) | original / patched | 103 → 107 | sync error / in sync |
| fresh-build scenario (`tools/mtest.sh`) | original / patched | 103 → 106 | sync error / in sync |

Note for your own tests: loading a multiplayer save heals a divergence that already exists (the host
sends its own state to everybody). A save made after the problem does not show the problem any more.

## Open points

- **Silent exits.** Three times in the long runs a game process ended without `Crash.log` during turn
  processing (once right after a player was eliminated); the other players then see "Disconnected".
  The cause is not found yet; it could not be reproduced on demand. The tracer now logs every exception
  and exit code, and further long runs are in progress.
- Candidates from static analysis that are not tested yet (see `docs/static_audit.md`): losing a
  shipyard while a ship is being built, the morale "production boost" event at morale ≥ 192, ship-class
  refit orders.
- Fixes A–D remove proven ordering races and transport problems; whether they caused disconnects in
  real internet games cannot be proven without real network conditions.
- Mods that change game rules (e.g. the "chasing ships away" patch) are a separate source of desyncs.

## Repository layout

- `release/` – standalone patcher and community `.patch` file (generated by `tools/make_release.py`).
- `tools/netfix.py` – the patch itself (assembly, applied with `tools/pe.py` / Keystone).
- `tools/` – test bed and analysis tools: instance harness (`harness.py`), game setup
  (`newgame5.sh`, `resume5.sh`, `resume_n.sh`), player agents and observer, input replay
  (`replay.py`), debugger-based tracers (`ktrace.py`, `wtrace.py`, `dbg.py`), state and order
  comparison (`autoturn.py`, `ordercmp.py`, `sysdiag.py`).
- `docs/static_audit.md` – multi-agent static audit of the binary with adversarial verification.

## Reproduce the results yourself

Everything runs on one Windows PC with **Git Bash** and **Python 3** (`pip install keystone-engine capstone pillow`).
All paths are relative to the repository root; the defaults can be changed with environment variables.

1. **Game copies.** Create five copies of an installed BotF 2.0.4 (vanilla English, 800x600) in
   `test/A` … `test/E` (or set `BOTF_TEST`). Each copy needs its own windowed-mode configuration
   (dxwnd, `dxwnd.dxw` pointing to *that* copy's `trek.exe`), otherwise the game starts fullscreen.
2. **DirectPlay.** Windows 10/11 ships DirectPlay as an optional feature. Either enable it, or put
   `dplaysvr.exe`, `dplayx.dll`, `dpwsockx.dll` into `dplay/` (or `BOTF_DPLAY`) and `dplayx.dll` +
   `dpwsockx.dll` into each game copy. If hosting fails with *"Can't start session, check network
   tcp/ip settings"*, check `netsh int ipv4 show excludedportrange protocol=tcp`: Windows (Hyper-V / WinNAT)
   may reserve the DirectPlay ports 2300–2400.
3. **Test builds.** From your own `trek.exe` build the two test executables (several instances on one
   desktop, inactive windows keep running, mouse input without taking over your cursor):

   ```
   python tools/build_test.py <your trek.exe> trek_t_bug.exe           # original game logic
   python tools/build_test.py <your trek.exe> trek_t_fix.exe --fix     # with this repository's fix
   ```
4. **Reproduce the natural late-game sync error (bug N)** from the turn-320 save of the 5-player test
   game (3 players left: B Klingons as host, C Federation, E Romulans) by replaying the recorded inputs:

   ```
   bash tools/resume_n.sh saves/nat5_bug_1402_t320 trek_t_bug.exe B C E
   python tools/replay.py turnlog/nat5_bug_1402 320 331 43
   ```

   Expected with `trek_t_bug.exe`: `HEARTBEAT MISMATCH after turn 330` (all games show "A synchronization
   error has occurred"). Repeat with `trek_t_fix.exe`: turns 320–331 stay in sync.
5. **Martial-law (bug I) and fresh-build (bug M) scenarios** from the turn-103 save of the 5-player game:

   ```
   bash tools/r3test.sh trek_t_bug.exe     # then trek_t_fix.exe
   bash tools/mtest.sh  trek_t_bug.exe turnlog/mtest_bug
   ```
6. **Long natural games** with five player agents and the observer (stops on heartbeat mismatch, crash,
   lag or hang; checkpoints every 20 turns):

   ```
   bash tools/newgame5.sh trek_t_bug.exe            # new 5-human game, or resume a checkpoint:
   bash tools/runlong5.sh trek_t_bug.exe turnlog/myrun 1402 300 saves/<checkpoint>
   ```

   The agents click fixed screen positions for each race and need the home-system position on the
   galaxy map (`--home X,Y` in `runlong5.sh`); adjust these for a new galaxy.

Note: the tool set grew during the investigation. Some older scripts (2-player experiments) still use
fixed screen coordinates of one particular game and are kept for reference only.

## License

MIT for the code in this repository (see `LICENSE`). *Star Trek: Birth of the Federation* is © its rights
holders; this project contains none of its files.
