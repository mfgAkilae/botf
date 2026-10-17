# Full multiplayer code review, 2026-10-17

Static review of the multiplayer code of trek.exe 2.0.4 EN with all fixes of v1.7.0 applied, split into eight
areas (network and session, turn cycle and checksums, orders, economy, strategic military, tactical battles,
diplomacy/intelligence/events, computer empires/per-process state/UI). Two independent rounds:

1. Codex gpt-6-astra, effort xhigh (four areas restarted after the provider's content filter stopped them);
2. Codex gpt-6.1-sol, effort xhigh, given round 1's findings to confirm or refute and asked for new ones.

Material: Ghidra pseudocode, disassembly, `tools/netfix.py`. Nothing below is runtime-confirmed yet. "code" =
the chain is confirmed in the code; "plausible" = one step needs a runtime check.

## Findings

| Id | Area | Finding | Round 1 | Round 2 |
|---|---|---|---|---|
| R1 | UI / orders | **Research (F4) after a timed END TURN**: allocation edits pending when the turn timer expires are not committed before the order list is sent (`FUN_00458120` at 0x4b9f74 → `FUN_00456340`); leaving the screen later commits them without a turn-state check (`FUN_004d2780`: order changed at 0x4d27f7 / added at 0x4d283e, allocations written at 0x4d281b), and the merge takes the owner's changed list (0x455f12). Only the owner researches with the new allocations. Same pattern as Fix IN. Needs a turn time limit. | code | confirmed |
| R2 | intel | **Intel orders deleted on any elimination**: `FUN_0047fa90` (from 0x43b370 → `FUN_0047f6d0`) selects all intel orders (empire 0xff) and deletes the originals (0x47fba5). The owner already wrote the new allocations on commit (`FUN_0047f190`), the others keep the old ones. Also `EBX=1` instead of `ESI` at 0x47fb6e. | code | confirmed |
| R3 | Fix B | **Replay order**: parked notifications are reposted behind newer ones already in the window queue; a slow client can apply host options (0x85) A after B (`FUN_0050d390` writes combat mode 0x50d3ea and random events 0x50d3f8). | code | confirmed |
| R4 | Fix B | **Park capacity**: when 23 notifications are parked, the next protected message is dispatched while busy (`cmp d_count, MAX_DEFER-1; jae go`); 0x85 then hits the assert conninit.c:617 (0x50d3b5). | code | confirmed |
| S1 | Fix H | **Re-arm capacity**: `MAX_REARM = 16`; when full both hooks fall back to the original owner-only restart before the production snapshot (0x445ab5 → 0x445abc), i.e. the bug Fix H fixes (e.g. 17+ shipyards scrapped in one turn). | — | code |
| S3 | Fix U | **AUTO protection limited to 2,048 battle records** (ships plus projectile slots, count without clamp at 0x520e19); allied computer ships beyond index 2047 get orders locally (large battles, ~100 heavily armed ships). | — | code |
| R7 | Fix U | **AUTO second pass** (0x477bf6..0x477c26, `FUN_00478370` at 0x477eb8) changes same-side ships with order 10 without an ownership check (allied human units). | code | confirmed |
| R5 | battles | **Battle barriers** `FUN_00473bb0` / `FUN_004742a0` require exact mask equality (0x473d5c, 0x474357); a player who leaves after acknowledging keeps his bit → endless wait on some machines. | code | confirmed |
| R6 | battles | **Battle result counter** `[0x59056c]`: result receipt (0x4750df/0x4750f3) and departure (`FUN_0046fd60`) both decrement without tracking the player → early completion or assert battle.c:416. | code | confirmed |
| S4 | UI / fleets | **Task-force reorganisation dialog** stays usable after a timed END TURN; its callbacks (0x4fe020, 0x4fe500) change the ship's task-force id (+0x50, part of the ship CRC) only locally. Needs a turn time limit. | — | code |
| R8 | lobby | Unknown DPID maps to empire 5 in the filter (0x510694); with minor 5 eliminated join notifications are dropped → resume of such a save stalls in the lobby. | code | confirmed |
| R9 | lobby | Lobby host change destroys the receive list and its critical section (0x566d50..0x566d62) while notifications are still queued. | code (timing) | confirmed |
| R10 | economy | Upgrade at exactly 65,535 accumulated industry consumes the owner-dependent field +0x90 (0x460574..0x4605b1) → completion one turn apart (rare). | code | confirmed |
| S2 | economy | Empire morale average sums 16-bit (0x46118c, `MOVSX` 0x4611c2): 164 systems at morale 200 → assert morale.c:102 on every machine (extreme). | — | code |
| R11 | turn | `FUN_004562c0` starts the turn even when the 0x68 payload was discarded; the turn start pumps before busy=1 → nested turn start possible; natural trigger not established. | plausible | unsure |
| R12 | UI | LOAD from the Escape menu inside the turn tears down state below the active turn frame. | plausible | unsure |
| R13 | military | Monster spawn loops forever on a fully occupied map (0x44b2b0); colonize event reads a removed task force's id (0x469d19). Same on every machine. | code | confirmed |
| S5 | load | Periodic computer credit bonuses (difficulty 4/5) are not re-registered after a load (no desync: every machine loads). | — | code |
| S6 | lobby | 0x80 leaks its receive record; hot-join with stale autosave; departed pending joiner blocks — join after start is normally disabled. | — | code / plausible |

Areas both rounds found clean apart from the above: transport, fragments, every dispatcher branch, resume transfer;
order creation/packing/receipt and types 0–9; production loop, queues, buy, scrap, labor, structures, trade;
movement, missions, stations, monsters, strategic combat ordering; diplomacy, minor races, events; AI planners and
save/load content.

## Suggested order

1. Our own fixes: R4 and R3 (Fix B queue), S1 (Fix H capacity), S3 and R7 (Fix U).
2. Normal-play desyncs: R2 (intel vs elimination), R1 and S4 (timer: commit or lock the screens before sending).
3. Player-leaves-during-battle: R5, R6.
4. Lobby/resume: R8, R9.
5. Rare/extreme: R10, S2, R13, R11, R12.

Each fix needs an A/B runtime test like the earlier ones before a release.
