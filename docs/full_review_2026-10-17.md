# Full multiplayer code review, 2026-10-17

Static review of the multiplayer code of trek.exe 2.0.4 EN with all fixes of v1.7.0 applied, split into eight
areas (network and session, turn cycle and checksums, orders, economy, strategic military, tactical battles,
diplomacy/intelligence/events, computer empires/per-process state/UI). Four rounds, one agent per area each:

1. Codex gpt-6-astra, effort xhigh (four areas restarted after the provider's content filter stopped them);
2. Codex gpt-6.1-sol, effort xhigh, given round 1's findings to confirm or refute and asked for new ones;
3. Claude Sonnet, effort xhigh, given rounds 1 and 2;
4. Claude Fable, effort xhigh, given rounds 1 and 2 (rounds 3 and 4 ran in parallel and did not see each other).

Material: Ghidra pseudocode, disassembly, `tools/netfix.py`. Sections 1 to 3 are static; section 4 lists the
runtime checks done since.
Ratings: **code** = the chain is confirmed in the code; **plausible** = one step needs a runtime check;
**spec.** = speculative. In the round columns: ✓ confirmed, ✗ refuted, ? unsure, + new aspect, – not in that
agent's area or not examined.

## 1. Findings of rounds 1 and 2, with the verdicts of rounds 3 and 4

| Id | Area | Finding | R1 | R2 | Sonnet | Fable |
|---|---|---|---|---|---|---|
| R1 | UI / orders | **Research (F4) after END TURN**: allocation edits pending when the order list is sent are committed later without a turn-state check (`FUN_004d2780`: order changed at 0x4d27f7 / added at 0x4d283e, allocations written at 0x4d281b); the merge takes the owner's changed list (0x455f12). Only the owner researches with the new allocations. Same pattern as Fix IN. | code | ✓ | ✓ (only the timer reaches it: END TURN is a galaxy-screen button) | ✓ (the timer qualifier is too narrow, see N2) |
| R2 | intel | **Intel orders deleted on any elimination**: `FUN_0047fa90` (from 0x43b370 → `FUN_0047f6d0`) selects all intel orders (empire 0xff) and deletes the originals (0x47fba5); the owner already wrote the new allocations on commit (`FUN_0047f190`). Kind-0 priority and kind-2 blame orders are always lost. `EBX=1` instead of `ESI` at 0x47fb6e. | code | ✓ | ✓✓ (two agents) | ✓✓ |
| R3 | Fix B | **Replay order**: parked notifications are reposted behind newer ones already in the window queue; a slow client can apply host options (0x85) A after B. | code | ✓ | ✓✓ | ✓✓ |
| R4 | Fix B | **Park capacity**: with 23 parked notifications the next protected message runs while busy (0x85 → assert conninit.c:617). | code | ✓ | ✓✓ | ✓✓ |
| S1 | Fix H | **Re-arm capacity** `MAX_REARM = 16`: when full both hooks fall back to the owner-only restart before the production snapshot. | – | code | ✓ (+ N8) | ✓✓ |
| S3 | Fix U | **AUTO protection limited to 2,048 battle records** (ships plus projectile slots). | – | code | ✓ | ✓ |
| R7 | Fix U | **AUTO second pass** (`FUN_00478370` at 0x477eb8) changes same-side order-10 ships without ownership check. | code | ✓ | ✓ | ✓ |
| R5 | battles | **Battle barriers** `FUN_00473bb0` / `FUN_004742a0` require exact mask equality (0x473d5c, 0x474357); a leaver's acknowledged bit stays → endless wait. | code | ✓ | ✓✓✓ | ✓ (+ same exact-mask wait in `FUN_00470e50`, 0x470ed9) |
| R6 | battles | **Battle result counter** `[0x59056c]`: receipt and departure both decrement → early completion or assert battle.c:416. | code | ✓ | ✓✓✓ | ✓ |
| S4 | UI / fleets | **Task-force reorganisation dialog** stays usable after END TURN; callbacks change the ship's task-force id (+0x50, in the ship CRC) only locally. | – | code | ? (unclear whether the map lock covers the dialog) | ✓ (not limited to a timed END TURN, see N2) |
| R8 | lobby | Unknown DPID maps to empire 5 in the filter (0x510694); with minor 5 eliminated join notifications are dropped. | code | ✓ | ✓ | ✓ (also 0x402 notifications) |
| R9 | lobby | Lobby host change destroys the receive list and critical section while notifications are queued. | code | ✓ | ✓ | ✓ |
| R10 | economy | Upgrade at exactly 65,535 accumulated industry consumes the owner-dependent +0x90. | code | ✓ | ✓ | ✓ |
| S2 | economy | Empire morale average sums 16-bit → assert morale.c:102 (164 systems at morale 200). | – | code | ✓ | ✓ |
| R11 | turn | `FUN_004562c0` starts the turn even when the 0x68 payload was discarded; the turn start pumps before busy=1 → nested turn start. | plausible | ? | ✓ + natural triggers (N3, N5); ?? (two agents unsure) | ✓ + natural triggers (N4, N5, N14) |
| R12 | UI | LOAD from the Escape menu inside the turn tears down state below the active turn frame. | plausible | ? | ? | ? (in-game LOAD closes the session → "Disconnected"; only the pre-busy pump is exposed) |
| R13 | military | Monster spawn loops forever on a full map (0x44b2b0); colonize event reads a removed task force's id (0x469d19). Same on every machine. | code | ✓ | ✓✓ | ✓ |
| S5 | load | Periodic computer credit bonuses (difficulty 4/5) not re-registered after a load (symmetric). | – | code | ? (no scheduled bonus found) | ? (symmetric, no desync) |
| S6 | lobby | Unconsumed records (0x80 and others); hot-join cases (join after start is disabled). | – | code / plausible | ✓ (harmless leak) | ✓ (harmless leak) |

No earlier finding was refuted.

## 2. New findings of rounds 3 and 4

| Id | Area | Finding | Rating | Found by |
|---|---|---|---|---|
| N1 | UI / random events | **F6 is a leftover debug key**: `FUN_00401910` sets `[0x5a2b6c] |= 4` (0x401ad7) with only "game running" checked — no multiplayer, cheat-flag or turn-state test (F9–F11 have them). The random-event step `FUN_0044cbe0` (0x44cbe4) then spawns a random monster (`FUN_0044b220`, several main-RNG draws) and resets the countdown `[0x58fdb0]` on that machine only → seed mismatch at the next heartbeat. One accidental key press, random events on. | code | Sonnet ×2, Fable |
| N2 | UI / orders | **Order-changing screens after END TURN**: production (`FUN_004f3330/3520/3840/3b90`), queue (`FUN_004fd7b8`), scrap (`FUN_004fab30`), labor (`FUN_004f1694` → `FUN_0043dd70`), fleet map (`FUN_004dd5a0`), diplomacy proposal/withdrawal (`FUN_004c8070`, `FUN_004c7f60`, `FUN_004c7ff0`), research (R1), reorganisation (S4): none tests `[0x5a291c]`; only the F-keys are gated. An order created or killed after the send exists only on the sender for one turn. **Contested**: Sonnet (area 8) found the END TURN lock (`FUN_004b90a0` → lock callbacks 0x4d96a0, 0x4f7080, 0x4c41a0 plus an input overlay, unlocked by `FUN_004b9110`) to be a real input blocker for the galaxy, system and diplomacy screens, and an earlier runtime test found the system screen locked after TURN. Decisive runtime check needed per screen (and with the turn timer). | code (guards missing) / contested (reachability) | Fable ×4, Sonnet ×2; contra Sonnet area 8 |
| N3 | turn | **Second END TURN while waiting**: `FUN_00458120` has no "already ended" guard; a second call (double click, timer plus click) re-sends 0x68/0x74. The 0x68 carries no turn number (the header seed is ignored, `FUN_00507a80` = `ret`): a duplicate dispatched in the pre-busy pumps starts a nested turn (R11); one filed after the merge becomes the sender's orders for the next turn on some receivers (stale orders, permanent off-by-one). Open: whether the TURN button stays clickable. Fix: return at 0x458143 when `[0x590248] != 0`; skip `FUN_00458170` at 0x456321 when the payload was discarded. | plausible | Sonnet, Fable ×2 |
| N4 | turn | **Inactive window while waiting**: the two pumps of `FUN_00458170` before busy=1 (0x4581e6, 0x458203) block in WaitMessage while the window is inactive (alt-tab), but still dispatch network notifications, and Fix B does not park (busy = −1): a fast player's 0x74 for the next turn replaces build queues before this machine processed the current turn, his 0x68 starts a nested turn (two turns processed). Our test build forces the window active, so the test bed cannot see it. | plausible | Fable |
| N5 | leave / drop | **Player-leave timing** (new mechanisms in the known-open area): a DESTROYPLAYER dispatched in the pre-busy pumps runs `FUN_0050d730` → `FUN_00458170` nested (two turns, 0x50d8a4); a leaver's last 0x68 is merged on machines whose barrier completed first and dropped where the DESTROYPLAYER came first (Fix Y frees the slot) → divergence instead of the former hang; the takeover `FUN_0043a160` draws the RNG at arrival time and is skipped on machines that already marked the empire eliminated; the host's 0x66/0x67 table/mask broadcast can overwrite the receiver's mask mid-turn. Fix direction: apply a leave at a fixed point (host game message "player left as of turn T", or park 0x402/0x66/0x67 while busy and replay at the flush). | code (mechanisms) / plausible (timing) | Fable, Sonnet |
| N6 | battles | **Tactical task-force array not zeroed**: `[0x597860]` (n×0x74) is allocated at 0x520ef3 with `FUN_00492f10` (no clearing; Fix F only clears the unit array). +0x24..+0x3b (three doubles) is never written but read by the RETREAT handler `FUN_0056c1f8` (ai\retreat.c, 0x56c2cb..0x56c358) as an aim point → heap residue steers units differently per machine → eventListCRC assert (battle.c 909). Needs a battle with two or more humans and an order-10 unit. Fix: reuse Fix F's zeroing helper at 0x520ef3. | code (uninitialised read) / plausible (impact) | Sonnet |
| N7 | economy | **Shipyard loss, arm A still open**: `FUN_00445a10` decides at 0x445a28 (`cmp [sys+0x80],3`) whether to kill the system's ship order (mode 0, no request). +0x80 is the owner form: after a ship completion with another ship queued (or a ship picked in the UI) the owner has 3, the others 0 → the owner kills, the others keep building. The earlier conclusion "arm A harmless" (R2 test in steady state, where the record is 3 everywhere) does not cover this window. Fix: decide from the order list (equal everywhere), let every machine kill. | code | Sonnet ×2 |
| N8 | Fix H | **Fix H run without revalidation**: `rearm_run` executes kind-1 entries (`FUN_004616f0` + `FUN_0044d830`) without re-checking the system; when the system changes hands to a computer empire in the same invasion step its queue is freed (+0xa8 = 0) → null dereference at 0x44d84b on every machine. With a ship-only queue arm A and arm B are both queued → duplicate trade-goods orders (symmetric). | code (rare) | Sonnet |
| N9 | battles | **Battle-list CRC 0x70 stored before the turn-start reset**: a fast machine's 0x70 can arrive while a slow one is still in the pre-busy pumps (screen fade); `FUN_00475290` then wipes it → both machines wait forever. Contested: Sonnet (area 6) places the only effective reset at the end of the previous turn. | plausible / contested | Fable |
| N10 | battles | **Human eliminated before the battle phase of the same turn** (rebellion/incident paths before `FUN_0046fd80`): his machine still opens the battle and blocks in the barrier; his 0x6e orders are applied on the others at dispatch time (the 0x6e handler does not filter the human mask). | plausible (rare) | Fable, Sonnet |
| N11 | military | **Invading a system whose native minor race is already eliminated**: `FUN_00466cf0` writes the race's contact record through a null pointer (0x4679a1 / 0x467fe0 → address 0x3c) → crash on every machine. Trigger: a minor home bombarded to extinction, then a fleet with the invade mission arrives. | code (crash, same everywhere) | Fable |
| N12 | RNG | **Float RNG shuffle table survives a new game**: `FUN_00507d10` re-seeds only `[0x596bac]`/`[0x596bc0]`; the ran1 table index `[0x596bc4]` is never reset, so a process that already generated a galaxy skips the 40-step warm-up → different galaxy than freshly started processes (second game without restarting trek.exe). Loads restore the whole block (fine). | code (mechanism) / plausible | Fable |
| N13 | Fix IN | **Fix IN also skips the intel panel hide** (its `ret` covers the hide at 0x4bcb93..0x4bcba7) and drops the slider edits silently (symmetric, UI only). | code | Sonnet |
| N14 | turn | **Timer auto-end inside processing**: with a turn limit, the timer callback can fire inside a battle-barrier loop at DispatchMessage depth 0 (Fix K passes) → `FUN_00458120` mid-turn, busy overwritten with −1, nested turn start. Fix: Fix K also defers while `[0x5a291c] != 0`. | plausible | Fable |
| N15 | checksums | **Detection gap**: a 0x71 that arrives while the receiver waits (busy −1) is stored and wiped at the next turn start, never compared on that machine. Detection only. | code | Fable ×2, Sonnet |
| N16 | Fix C | The patched send gives up after 5 s of failures; receivers keep a partial record → the game hangs like before the fix (robustness). | code | Sonnet |
| N17 | various | Speculative or harmless: task-force redirect with two persisting orders (`FUN_004dd5a0`); path freed by a foreign path id (0x46c212); loader resets the shared order counter for minor orders (`FUN_00456bb0`); minor/monster orders all have seqno 0 (one per type survives the merge, symmetric); AI-only/auto-resolve battle results applied after an unstable sort; tactical replay file `.tac` write failure asserts locally; empty 0x74 for a player without systems asserts (pdqueue.c:418); a combat dialog closed with Escape might never set its result. | spec. | Fable, Sonnet |
| N18 | memory | Leaks without desync: Fix EL/Y free slot lists without the order-body callback 0x457f80; the merge's duplicate drop frees neither node nor body; the military re-plan overwrites path ids without freeing. | code | Fable, Sonnet |

Notes from rounds 3 and 4: the Fix W comment is wrong about ship names (the ship CRC zeroes the first 0x28 bytes,
so names are not checksummed; the RNG-draw argument stands); Fix G now always replaces a foreign system on the F2
screen with the player's first own system (behaviour change, no desync); eliminations after the diplomacy phase
never clean up the dead empire's treaties (symmetric).

**Coverage limit (Sonnet, area 8):** `decomp.c` lacks about 200 KB of code (417 functions only in `asm.txt` plus
gaps in neither file), among them roughly half of the computer-empire code (0x402d00..0x437400) and most screen
handlers. Earlier reviews that worked from the pseudocode covered those parts only partially; rounds 3 and 4 read
the gaps they needed in raw disassembly. A complete export of these ranges is a prerequisite for another AI/UI pass.

## 3. Suggested order

1. **Small, high-confidence fixes**: N1 (F6, three agents), N6 (zero the tactical task-force array), the capacity
   and replay bugs in our own fixes (R4, R3, S1, N8, S3, R7), N13.
2. **Runtime checks that decide the scope**: N2 per screen (decides R1, S4 and the diplomacy/production cases), N7
   (shipyard arm A in the completion window), N3 (second END TURN), N4 (inactive window; needs a build without the
   forced-active patch).
3. R2 (intel vs elimination), R1/S4 depending on N2.
4. Leave/drop during a turn or battle: R5, R6, N5, N10, N14.
5. Lobby/resume: R8, R9, N12.
6. Rare or the same on every machine: R10, S2, N11, R13, N9.

Each fix needs an A/B runtime test like the earlier ones before a release. The 32 agent reports
(`astra_area*.md`, `sol_area*.md`, `sonnet_area*.md`, `fable_area*.md`) are kept with the test-bed logs
(`turnlog/fullreview_2026-10-17/` in the working directory), not in the repository.

## 4. Runtime results

All tests with five human players in the test bed (one machine, five instances), A/B against the build without the
fix. Commands are in `tools/`.

- **N1 (F6 debug key): reproduced, fixed (Fix F6).** In an AI war at turn 178 an agent's F6 desynced the game
  (countdown 40 vs 54). A/B from a turn-520 checkpoint (`tools/f6test.sh`): heartbeat mismatch at turn 521 without
  the fix (countdown 39 on the presser), in sync with it (countdown 73 everywhere).
- **N6 (tactical task-force array): fixed without a reproduction** (Fix F now also zeroes the array at 0x520ef3).
  A reproduction needs a battle with two or more human players and an order-10 retreat.
- **N2 (order screens after END TURN): refuted for the reachable screens.** The player agents (`tools/player.py
  --waitact`) kept giving orders while they waited for the others, from turn 520 of a war game: 53 fleet courses,
  26 fleet missions, 59 labor changes, about 120 build-list picks, buys and diplomacy proposals. A probe compared
  the player's own orders (without the local kill requests) and own system records before and after every action:
  no change while waiting. The same probe before END TURN saw the fleet, production and diplomacy changes (positive
  control). On the galaxy map the military view shows no task forces while the player waits. The END TURN lock
  therefore blocks these screens. Still open: the turn timer (END TURN forced while a screen is open, R1 and S4),
  the task-force reorganisation dialog and the research screen.
- **N7 (shipyard loss, arm A): reproduced, fixed (Fix HA).** `tools/n7test.sh`: at Cardassia a second Heavy
  Cruiser is queued and the current one bought; after the turn only the owner records the next ship (+0x80: owner 3,
  the others 0, shown by `tools/cur80.py`). The owner then scraps the Union Shipyard. Without the fix the heartbeat
  differs at the end of that turn: the owner killed the ship order and builds the next structure, the other four
  put 3163 industry into the ship. Fix HA decides from the order list on every machine (kill pattern "ship, any
  class" for human players' systems in multiplayer): in sync for three turns, and the owner's checksums are the same
  as without the fix. The earlier arm-B test (`tools/r2test.sh`) stays in sync with Fix HA.
- **N3 (second END TURN): refuted.** Three more clicks on TURN while the player waits do not reach
  `FUN_00458120` again (breakpoint trace: one call for four clicks; the END TURN lock disables the button). The
  turn timer cannot end the turn a second time either: once the player ended the turn `FUN_004b9ae0` sets
  `[0x59306c]`, and on expiry the timer callback skips the END TURN call when that flag is set (0x4b9ee5).
- **N4 (inactive window while waiting): refuted with the fix build.** `tools/n4test.py`: B ends the turn and goes
  inactive (`[0x5a28d4] = 0`), the others end the turn. They start the processing (busy 1) but do not finish it
  while B stays in the pump, so nobody can send next-turn queues or orders to B. When B becomes active again all
  five finish the turn in sync.
- **R3/R4 (Fix B replay order and capacity): not reachable in practice.** Each player sends exactly one 0x74 and
  one 0x68 message per turn (one buffer each, `FUN_0044d580`, `FUN_00456340`), so at most eight game messages can
  be parked during one processing; the capacity is 23. A 0x68 replayed before the same sender's 0x74 still finds
  the 0x74 dispatched in the two pumps of `FUN_00458170` before busy is set. Not changed.
- **N8 (Fix H restart without revalidation): fixed (static).** The deferred restart of the second kind (empty
  queue) now checks that the system still belongs to a human player and still has a queue. Tested: the arm-A test
  and an empty-queue scrap at Cardassia (the restart runs from Fix H's list on every machine) stay in sync.
- **R2 (intel orders deleted on elimination): reproduced, fixed (Fix IE).** `tools/r2intel.py` runs the
  elimination cleanup `FUN_0047f6d0` on every game in the research step (before the intel phase). A left the intel
  screen with 60/0/40 (record already written on A): without the fix A keeps 60/0/40 and B..E keep the old 50/50
  (the intel records are not in a heartbeat checksum, so the difference stays latent until it changes an intel
  result). Fix IE keeps the intel orders in multiplayer and passes the right category in the loop at 0x47fb6e:
  all five games then hold 60/0/40, and an allocation against the eliminated empire moves to security on every
  machine (60/0/0/0/20/0/0/0/20 becomes 100/0/... everywhere).
- **S3 and R7 (Fix U): fixed (static).** The AUTO wrapper's bitmap now covers 16384 units. While AUTO runs, a flag
  (first use of the free DGROUP tail at 0x5a1600) makes the AI's second pass (0x477ea7) skip ships of other owners.
  Regression: a manual battle B vs E with AUTO on E (`tools/tactest.sh`, wrapper hit once) ends without a crash and
  the next turn is in sync. The second-pass guard itself was not reached in that battle.
- **N12 (ran1 table after a new game): refuted.** `FUN_00507d10` clears the table and its index with
  `memset(0x596bc4, 0, 0x84)` at 0x507d1c (and the second generator at 0x596c48); the pseudocode hid the arguments.
- **N14 (timer inside processing): refuted.** The timer restarts only at the start of a turn (`FUN_0043d220`), on a
  load and when the host's options change the strategic timer; during processing the "turn ended" flag
  `[0x59306c]` is set and the expiry skips END TURN. A timer change by the host would clear that flag for a player
  who already ended the turn, but the strategic-timer arrows do nothing in a running multiplayer game (tested on
  the host: the value stays "None").
- **N13 (Fix IN skips the panel hide): fixed.** The skip path now hides the intel panel like the normal path.
- **S2 (16-bit morale sum): fixed (Fix MS, static).** The sum is 32 bits wide; the checksums of three turns from
  `saves/five_1201_t103` are the same with and without the fix.
- **N11 (invading a system of an extinct minor race): fixed (Fix MI, static).** The null-pointer write is skipped.
- **R10 (upgrade at exactly 65,535) and R13 (monster spawn on a full map, colonize event id): left open.** Both
  need very rare states (a build costing more than 65,535 industry with exactly 65,535 invested; no free sector on
  the whole map), and a fix would need more than a local patch (owner-form +0x90 at build start; abort path with
  cleanup in `FUN_0044b220`). R13 behaves the same on every machine.
- **R1 (research commit after a timed END TURN): reproduced, fixed (Fix RS).** A game with a one-minute strategic
  timer (`NEWGAME_TIMER=1 tools/newgame5.sh`; the timer arrows ignore posted clicks, so the script sets the
  stored setting). `tools/r1timer.py`: B opens the research screen, the timer ends B's turn, B changes the
  allocations; the screen is closed (by the player or by the game when processing starts) and commits. Without the
  fix only B researches with 40/12/12/12/12/12, the others keep 17/17/17/17/16/16 (the research record is not in a
  heartbeat checksum). With Fix RS the commit is skipped while the turn is not idle and all five keep the old
  values; a commit while idle (leaving with F1) still reaches every game.
- **S4 (task-force reorganisation after a timed END TURN): reproduced, fixed (Fix RD).** `tools/s4redeploy.py`
  in a game with a one-minute timer: B opens the REDEPLOY dialog of a task force at Qo'nos, the timer ends B's
  turn, the dialog stays usable and B drags the destroyer into the task force. Without the fix the ship's
  task-force id changes on B only and the heartbeat checksum differs at the end of the turn. With Fix RD (the
  dialog's three state-changing callbacks do nothing in multiplayer while the turn is not idle) the drag is only
  drawn, nothing changes, all five stay in sync; a drag while idle is still turned into orders at END TURN.
