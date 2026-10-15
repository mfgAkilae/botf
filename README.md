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
   Already on v1.0.0? Just run the new version; it rebuilds `trek.exe` from the backup.
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
| **S** | **Two threads share one unprotected heap ("Disconnected").** The network receive thread allocates memory for every incoming game message with `malloc`, while the game's main thread uses the same memory pool all the time. That pool (SmartHeap default pool, flags at `0x5a0a1c`) was created without the "serialize" flag that the game's other network pools have, so it takes no lock. Now and then both threads get the same memory block; the heap breaks and the process dies a few moments later, mostly while loading a picture or sound from `stbof.res`. No `Crash.log` is written; the other players see "Disconnected". | Caught with a debugger in the test bed: the heap handed out a block that was still in use, 56 ms later the receive thread crashed. Several silent exits in long runs, all in the same memory structures. See [Verification](#verification). | The default pool is created with the serialize flag (1 byte), so SmartHeap locks it. |
| **N** | **Deleting a build that was bought.** The game asks "industry invested, delete current build?". On YES it cancels the purchase only on the deleting player's machine. This is the only delete path that does not send a "delete order" request. The other machines keep the purchase and later compute different build costs. | **Occurred naturally** in a scripted 5-player game on the original game at turn 331 (`crcSolarBld` only). Replaying the recorded inputs from the turn-320 save reproduces it exactly. | The delete path sends the request like all others. |
| **M** | **Deleting a build the turn processing has just started.** When a build completes, the next queue item is started; its order exists only on the owner's machine until the next turn. If the player deletes it right away, the other machines do not know the order, ignore the delete request and keep the invested industry. The next build then completes a turn earlier there. | Reproduced on the original from a turn-103 save: sync error in the following turn. | The delete request carries the system; a machine that does not find the order resets that system's production anyway. |
| **I** | **Removing and re-adding martial law.** The owner restarts the martial-law turn counter; on the other machines the delete request clears only 2 of its 4 bytes, so their counter keeps running and the system's morale rises a turn early. | Reproduced on the original from a turn-103 save: sync error, `crcSolarBld` only. | The delete request clears the whole counter. |
| **H** | **Losing a shipyard while it builds a ship** (scrap order, bombardment, unrest). Every machine cancels the ship, but only the owner starts the next queue item right away, before the production step of the same turn. The owner's next build therefore gets one turn of progress more and finishes a turn early. | Reproduced on the original from a turn-103 save (`tools/r2test.sh`: scrap the Union Shipyard at Cardassia): sync error at turn 106 (`crcSolarBld`). | The restart is queued and runs after the production step on every machine, as the game already does for conquered systems. |
| **J** | **Research makes a ship class obsolete** while a system builds it. Every machine replaces the build order, but each one numbers the new order with its own counter. The owner then sends its order too, and the other machines keep both: ships are built twice. | Reproduced on the original (`tools/r4inject.py` runs the refit inside a normal turn on all five games): sync error at turn 106. | Only the owner creates the replacement order; the others receive it with the next orders message. |
| **T** | **Manual tactical combat: an attack order without a target ends the game.** The combat AI for a ship with order Charge/Assault asserts that its target is a unit (`aissault.c` line 562) before it checks for "no target". The tactical-combat agent hit it against the Edo Guardian: the Romulan player's game wrote `Crash.log` and quit, the others saw "Disconnected". | Reproduced deterministically from the turn-293 save (`tools/tacedo.sh`: send the task force into Rubicun, fight, end the first combat round). | Both asserts (ship and monster) take the existing no-target branch: the unit holds its position for that round. |
| **W** | **Random-monster countdown (and two monster name counters) belong to the program, not to the game.** It starts at 75 when `trek.exe` starts and is never reset or saved. After a crash the restarted player has 75, the others (who reload the save in their running game) have their own value: monsters appear on one machine only. | Instance A started with a different countdown on the turn-103 save: sync error at turn 105 on the original, in sync with W. Found by a static code review. | Countdown and name counters are reset when a game is started or loaded (the same function already resets the Borg state); the economy-checksum buffer, which a larger galaxy loaded later in the same program overran, is re-created. |
| **U** | **AUTO in manual tactical combat also orders an allied computer empire's ships**, but only on the machine that ticked AUTO; the other machines let the computer order them, with extra combat random numbers. The battle checksum then fails (`battle.c` line 909), a crash we had in a player report from turn 402. | Static code review (two independent reviews); regression-tested: AUTO in a B-vs-E battle stays in sync. A battle with an allied computer empire was not reproduced in the test bed. | AUTO marks the units of other owners as "ordered" for that call, so it orders only the player's own units. |
| **L** | **Messages that change the game arrive while another machine still calculates the turn.** When the host closes the options dialog, message 0x85 reaches clients that may still be processing; they quit with `conninit.c` line 617 ("turnState != TURN_PROCESS"). Loading a multiplayer save (0x72/0x73) had the same timing problem and replaced the game under a running turn. | Reproduced: host broadcasts its options during a tactical combat (`tools/opt85.sh`): B and E crash on the original; with L no crash and in sync. | These messages are held back during turn processing (the Fix B mechanism) and applied in arrival order afterwards. |
| **K** | **Turn timer inside a dialog.** With a turn time limit, the timer can end the turn while a modal dialog such as "delete current build?" is open; confirming it afterwards changes orders that were already sent. | Static review. Measured: the message-dispatch depth is 1 while that dialog is open, so the guard applies; the full expiry was not reproduced (the timer cannot be switched on in a running game and our lobby automation did not set it). | Expiry is deferred while a dialog is open and taken on the next tick. |
| **V** | **Delete requests matched by number only.** A request carries only the target's sequence number, and those numbers differ between machines; a machine without the target could delete an unrelated order. | Static review; regression: martial-law and fresh-build delete scenarios stay in sync. | The match also requires the requesting empire (players can only delete their own orders). |
| **Y** | **A player leaves after ending the turn.** His orders wait in a receive slot; when he drops, the slot is emptied but stays marked as used, and the turn barrier waits for every used slot. The remaining players wait for ever. | Reproduced (`tools/ytest.sh`): E ends the turn and is killed; after the drop A–D end the turn: the original hangs, with Y the turn is calculated and A–D stay in sync for 3 more turns. Found by a static code review. | The slot is released like at the end of a turn; in addition the barrier only waits for human players still in the game. |
| **Q** | **A colonize order whose colony ship was destroyed in combat** (other ships of the fleet survive): the colonize step looks up the missing ship and reads through a null pointer: crash, everybody else sees "Disconnected". | Reproduced by injection (`tools/coltest.sh`, `tools/colinject.py`: the first colonize of a new game finds no colony ship): both games of the original crash in turn 1; with Q the order is dropped and the game stays in sync. Found by a static code review. | A missing colony ship takes the existing "cannot colonize" exit before anything is changed. |
| **X** | **Wormholes.** The exit position of a fleet that flies through a wormhole was converted with the local galaxy-map view (scroll and zoom of that player's screen), so the fleet could come out in different sectors on different machines. | Static code review; regression only (no wormhole in our test galaxies). | The conversion gets a fixed view, the same on every machine. |
| W3 | The ship name list belongs to the program and was not reset on load (same class as W). | Static code review; regression only. | Reset when a game is loaded. |
| P | **Changing conquer/liberate on a running invasion is lost.** At End Turn the game only sends a fleet order when something it compares has changed; the conquer/liberate choice was compared for one mission type only. The old choice was executed (on every machine, so no sync error). | Static code review (found independently by two reviews). | The choice is compared for the invasion mission as well. |
| O | **Stations of an eliminated empire.** Removing them skipped the station after each deleted one, so stations of a dead empire stayed on the map (on every machine). | Static code review. | The removal loop re-checks the same slot after a delete. |
| Z | **Checksums with gaps** (detection only): the military-sector checksum covered only one eighth of its data, and the diplomacy checksum sorted its records with a broken compare function. A divergence there was noticed late or, in theory, a false sync error was possible. | Static code review; regression: long runs stay in sync with the full checksum. | Correct length and compare function. |
| E | Turn processing itself sends "delete order" requests that the receiver matches only by a sequence number. These numbers are assigned per machine and drift apart, so a request could hit an unrelated order on one machine. | Reproduced only artificially (injected collision); not observed in natural games. | Turn processing no longer sends these requests (every machine deletes the order itself anyway). |
| A | Build queues (`0x74`) were sent after the orders (`0x68`); the last player's orders already start the turn on the other machines, so queues could be applied in the middle of the calculation. | Trace in the test bed. | `0x74` is sent before `0x68`. |
| B | Orders of a faster player for the *next* turn were applied in the middle of a slower machine's turn calculation. | Trace in the test bed. | Held back while a turn is being calculated, delivered afterwards in order. |
| C | The send loop held the network lock for a whole message (with a 10 ms sleep and a synchronous round trip per 466-byte packet), blocking the receive thread; a failing send was retried forever (freeze when a player was gone). | Static analysis. | Lock only around the shared counters, no sleep, send retry limited to ~5 s. |
| D | Late turns can take minutes without any game traffic; DirectPlay pings only after 35 s of silence and drops a player after 8 lost pings (e.g. expired NAT/firewall mappings). | DirectPlay protocol documentation. | 1-byte keepalive every 10 s (ignored by all receivers, patched or not). |

**Why "late in the game"?** N, M and I are triggered by ordinary actions that big late-game empires
perform constantly: many planets, full build queues, buying, re-planning builds, unrest in conquered
systems. The more of that a game has, the more certain it is that a turn hits one of them. S is a
matter of chance per message: every turn of every player is another chance to hit the race, so the
longer a game runs, the more likely one machine drops out.

## Verification

Test bed: five game instances on one PC, each with its own human empire, connected over DirectPlay.
Five independent player agents (`tools/player.py`) play simultaneously like humans: production, buying,
labour, re-planning builds, diplomacy (gifts, friendship, affiliation, membership, declarations of war),
fleets (the agent finds its own task forces on the galaxy map by the race emblem, sets courses and gives
missions such as attack, raid, colonize, terraform, train crew), clicking around while waiting. An observer (`tools/observer.py`)
compares all games and the heartbeat checksums after every turn and attaches a debugger to catch
crashes.

For bug S the natural crash rate is about one silent exit per 30–50 turns of a 5-player game. The heap
stress build (`tools/build_test.py --heapstress N`) makes the race frequent: the network receive thread
does N `malloc`/`free` pairs every millisecond, like a burst of incoming messages. The crashes it
produces without S have the same addresses as the natural ones (`0x548417` inflate cleanup, `0x5491c5`
inflate, `0x53016f`/`0x530176` inside SmartHeap's allocator).

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
| nat5_fix_2001 / 2101 / 2201 | patched v1.0.0 (A–N, without S), from the turn-200 save | 200 → 210 / 210 / 236 | **silent exit** of one game each time (2101: possibly caused by the tracer) |
| nat5_fixs_2301 | v1.1.0 (with S), same save | 200 → 360 | no break, no heap anomaly (two players eliminated on the way) |
| heap stress, `--heapstress 4` (2502, 2504) | without S | 200 → 203 / never reached the game | **all 5 games crashed within 3 turns**; in 2504 six crashes while loading the save or in the lobby |
| heap stress, `--heapstress 4` (2503) | with S | 200 → 250 | no crash, in sync |
| shipyard scenario (`tools/r2test.sh`) | original / with H | 103 → 108 | sync error at 106 / in sync |
| refit scenario (`tools/r4inject.py`) | original / with J | 103 → 107 | sync error at 106 / in sync |
| Edo Guardian combat (`tools/tacedo.sh`) | original / with T | 293, first combat round | `assault.c:562` crash / no crash, in sync to 295 |
| monster countdown (A started with 2) | original / with W | 103 → 107 | sync error at 105 / in sync |
| war5_tac2..5: manual tactical combat, 5 humans | v1.2.0 + T | 280 → 390 | no break; ~80 tactical combat rounds (B, C, E), monsters, wars |
| war5_01: new small spiral galaxy, 5 humans | v1.2.0 | 0 → 300 | no break: per player ~250 ships ordered, ~100 purchases, up to 400 fleet courses and 200 missions, ~100 diplomatic actions on three players, 16 declarations of war, monsters and random events on |
| player drop after ending the turn (`tools/ytest.sh`) | original / v1.6 | 103 → 107 | turn barrier hangs for ever / in sync |
| colonize without colony ship (`tools/coltest.sh`) | original / v1.6 | new 2-player game | both games crash in turn 1 / 7 turns in sync (4 colonizations) |
| war5_v15c/d: 5 humans, manual tactical combat for all races | v1.5.0 | 160 → 200 | no break |
| war5_q / col_q | v1.6 candidate | 200 → 220 / 20 → 31 | no break |
| war5_v16: 5 humans, manual tactical combat for all races | v1.6.0 | 220 → 370 | no break (66 tactical combat rounds) |
| ai2_v16 / ai2b_v16: new games, 2 humans + 3 computer empires | v1.6.0 | 0 → 63 / 0 → 66 | no break; both ended when the computer empires eliminated a human player |

Note for your own tests: loading a multiplayer save heals a divergence that already exists (the host
sends its own state to everybody). A save made after the problem does not show the problem any more.

## Open points

- **Silent exits (the "Disconnected" symptom) – explained and fixed by S.** How it was found:
  - Several times in the long runs a game process ended without `Crash.log`; the other players then
    saw "Disconnected". Caught with the debugger attached: access violations in the resource loader
    (`0x513de2`, the unchecked copy of the inflate window in `FUN_00513dc0`), in the inflate cleanup
    (`0x548417`, freeing a broken Huffman table list) and in inflate itself (`0x5491c5`, table pointer
    `0x15e`). The archive is fine and every load runs on the main thread, so the heap was already broken.
  - A heap tracer (`tools/ktrace.py`, `HEAPTRACE=1`) watches every `MemAllocPtr`/`MemFreePtr` call.
    It reported a block handed out by `malloc` while it was still in use, and 56 ms later the network
    receive thread crashed at `0x54e2d5` (run `nat5_fix_2201`, turn 236).
  - `HEAPTID=1` lists which thread uses which pool: only the main thread and the receive thread use
    SmartHeap. The receive thread allocates one list node per incoming game message with `malloc`
    (`0x566cb0` → `0x51b2b0` → `0x51d760`) from the default pool, which had flags `0x8000` and no
    critical section. The other pools the receive thread uses have `0x8002` (serialized).
  - Tracer note: a breakpoint that is removed for a single step lets other threads pass unseen, which
    produces fake double frees. `ktrace.py` therefore emulates the instruction at the heap breakpoints.
- Static audit candidate R1 (morale "production boost" event, `docs/static_audit.md`): the owner and the
  other machines really compute different values in that event, but in seven forced scenarios
  (`tools/r1test.sh`, `tools/r1force.py`) the build still completed in the same turn everywhere, so no
  sync error. Not changed.
- Not exercised by the agents yet: intelligence and research allocation (their sliders did not react to
  simulated input), invasions.
- Not fixed (rare, not reproducible on one PC): a player dropping out is handled at different points on each
  machine when the machines notice the drop at different times (needs three or more humans; on one PC the
  remaining four stayed in sync, `tools/droptest.sh`); x87 `FSIN/FCOS` in combat geometry might differ
  between Intel and AMD processors; task-force ids are 16 bit (needs about 32,000 created task forces).
- A manual save made during a turn does not contain that turn's orders (orders are only saved at turn
  boundaries); the autosave is not affected.
- About thirty focused code reviews with three different models (tactical combat, session/lifecycle, turn
  processing, user-interface writes, intelligence/minor races, save/load and per-program state, computer
  empires, order application, reachable asserts, network transport and checksums, fleets and movement,
  diplomacy and random events, colonization, invasion, bombardment, outposts and starbases) found no further
  candidates beyond the fixes listed above.
- Stations (outposts, starbases) are not part of any turn checksum, so a station-only divergence would show
  up late. No cause for such a divergence was found; not changed.
- Fixes A–D remove proven ordering races and transport problems; whether they caused disconnects in
  real internet games cannot be proven without real network conditions.
- Mods that change game rules (e.g. the "chasing ships away" patch) are a separate source of desyncs.

## Repository layout

- `release/` – standalone patcher and community `.patch` file (generated by `tools/make_release.py`).
- `tools/netfix.py` – the patch itself (assembly, applied with `tools/pe.py` / Keystone).
- `tools/` – test bed and analysis tools: instance harness (`harness.py`), game setup
  (`newgame5.sh`, `resume5.sh`, `resume_n.sh`), player agents and observer, input replay
  (`replay.py`), debugger-based tracers (`ktrace.py` with `HEAPTRACE=1` / `HEAPTID=1` for heap checks,
  `crashcatch.py`, `wtrace.py`, `dbg.py`), state and order comparison (`autoturn.py`, `ordercmp.py`,
  `sysdiag.py`).
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
   Fleet play needs one race emblem per player cut from your own screenshots of the galaxy map
   (MILITARY view): `tpl/emblem/<A..E>.png` (22x20, normal map) and `tpl/emblem/<A..E>_small.png` (14x12,
   large map); `tpl/` is not part of the repository because it contains game graphics.

7. **Heap race (bug S)** with the stress builds, from the turn-200 save of the 5-player game:

   ```
   python tools/build_test.py <your trek.exe> trek_t_stress_old.exe --fix --nofixs --heapstress 4
   python tools/build_test.py <your trek.exe> trek_t_stress_new.exe --fix --heapstress 4
   python tools/crashcatch.py turnlog/stress_old &      # debugger on every game from its start
   HEAPTRACE=0 bash tools/runlong5.sh trek_t_stress_old.exe turnlog/stress_old 1 50 saves/nat5_bug_1301_t200
   ```

   Expected without S: games die within a few turns (often already while loading), `crashcatch` logs
   access violations in SmartHeap or inflate. With `trek_t_stress_new.exe` the 50 turns run through.
   Stop the catcher with `touch turnlog/stress_old/catch.stop`.

Note: the tool set grew during the investigation. Some older scripts (2-player experiments) still use
fixed screen coordinates of one particular game and are kept for reference only.

## License

MIT for the code in this repository (see `LICENSE`). *Star Trek: Birth of the Federation* is © its rights
holders; this project contains none of its files.
