# DRAFT: self-healing multiplayer ("resync instead of synchronization error")

Status: design draft v2 (after reviews by Claude Fable and Codex gpt-6-astra), not implemented. Addresses refer to trek.exe 2.0.4 EN (the patcher's base). Statements
marked [V] were verified in the disassembly during the feasibility study; [I] are inferences that the
implementation must confirm first.

## 1. Goal

Today a checksum difference after a turn ends the game: the 0x71 comparison shows "synchronization error",
asserts and the process exits (other players see "Disconnected"). Fixes A–Z remove the causes we found, but
unknown causes remain (other CPUs' x87 results, player-drop timing, mods, bugs not found yet).

Goal: on a mismatch the session takes over the host's game state on every machine and continues. Players lose
at most the input of the current turn. All players must use the patched program.

## 2. What the game already provides

- **State transfer** [V]: `FUN_0050de40(slot, flag)` reads a whole save file and sends it as message 0x72
  (flag 0) or 0x73 (flag 1) to all players. The receivers write it to `auto.sav` (`FUN_0050dd90`) and, for
  0x72, call `FUN_0050da70`, which loads it (`FUN_004387f0(-0xd)`), restores the session block
  0x5a2928..0x5a2978, applies the human mask (`FUN_00510ba0`), drops pending orders of other humans
  (`FUN_004569e0`), re-initialises the turn (`FUN_00438740`), rebuilds the screens (`FUN_004b9570`,
  `FUN_004b9180(0)`) and restarts the turn timer. Size about 150 KB (turn 180, 5 players), about 317 packets.
- **Client acceptance in a running game** [V]: the client branch of `FUN_0050da70` requires the waiting dialog
  `[0x597508]`, which the 0x89 handler (`FUN_0050cfd0` → `FUN_0050d070`) creates. Sequence host → all:
  0x89, then 0x72.
- **The load resets** [V]: turn state `[0x5a291c] = 0` (`FUN_0043ce50`), main RNG (`FUN_00507ab0`), the
  per-computer order counters 0x590230..0x590244 (`FUN_00456a70`), the order list from the file
  (`FUN_00456b20` skips orders of the current turn in MP), Fix W/W3 state (`FUN_00450020`).
- **Not reset by a load** [V]: receive slots 0x5b4870 (4 × 8 bytes: list, empire byte), "my orders sent"
  0x590248, the received-checksum table 0x5ccfc0 (cleared at turn start by `FUN_00510230`), parked messages of
  Fix B/L.

## 3. Design

### 3.1 Detection (two hooks)

| Site | When | Today |
|---|---|---|
| 0x5100c9 in `FUN_0050ffe0` | end of the local turn processing, comparing all received 0x71 | message box + assert |
| 0x51031f in `FUN_00510260` | a 0x71 arrives while idle and differs | message box + assert |

New behaviour at both sites (multiplayer only): set `d_resync = 1` (data cave), log the turn, and

- host: set `d_resync_run = 1` (performed later, 3.3);
- client: send the new message **0x8a** (empty body) to the host;

then continue at the normal continuation of the function (no message box, no assert). While `d_resync != 0`
both compare sites are skipped.

### 3.2 Messages (dispatcher hook in the Fix B cave at 0x50a709)

- **0x8a** request (client → host): on the host set `d_resync = d_resync_run = 1`; ignored on clients and
  when a resync is already running.
- **0x89** (existing, host → all): additionally set `d_resync = 1`, discard parked 0x68/0x74 (Fix B list) and
  clear the receive slots (see 3.4).
- **0x71** while `d_resync != 0`: dropped (late checksums of the aborted turn).
- **0x72** (existing): handled by the original code (load).

### 3.3 Host execution point

The host performs the resync only at a safe point: in the main loop (`d_depth == 0`, no modal dialog, the
Fix K counter), turn state idle (`[0x5a291c] == 0`), not inside a tactical combat. Hook: the Fix B
dispatcher drain point after turn processing, or the main loop tick (to be chosen; [I]).

Steps:
1. save the current state: `FUN_00438630(-0xd)` → `auto.sav` (also when the host disabled autosave);
2. clear the receive slots, 0x590248 and the parked Fix B/L messages (3.4);
3. broadcast 0x89 exactly like 0x50db25..0x50db3d;
4. `FUN_0050de40(-0xd, 0)` → 0x72 to all;
5. apply the same state locally through the client path (`FUN_0050d070`, then `FUN_0050da70` with the host
   flag temporarily cleared), so that the host's order counters, order list and slots are reset exactly like
   the clients';
6. `d_resync = d_resync_run = 0` after the load; the clients clear `d_resync` in their load tail.

### 3.4 State that must be cleared on every machine

- receive slots 0x5b4870 (destroy lists like `FUN_00455ec0`: `FUN_0051b520`, `FUN_0051b450`, pointer 0,
  empire 0xff), 0x590248 = 0;
- Fix B parked messages and the Fix L parked 0x85/0x72/0x73 except the resync's own 0x72;
- received checksum table 0x5ccfc0 (memset like `FUN_00510230`).

### 3.5 Host identity

`FUN_0050da70` treats `[0x5a2990] == 1` as host [V], but in our test bed all five instances showed
`[0x5a2990] = 1` while running. **Open:** find the reliable host test (DirectPlay host player id, the lobby
creator flag, or the sender of 0x6b/0x85) before implementing 3.1/3.3.

## 4. Consequences for the players

- The input of the current turn is lost on every machine (orders of turn N+1 are dropped by the load); players
  redo it. Build queues come back from the file and are re-sent at the next END TURN (Fix A order).
- The production records sys+0x80..+0x99 are only correct on the owner's machine; after the load everybody
  has the host's copy (0 for systems the host does not own). The owner sees no build in progress and must pick
  one again. Consistent on all machines, but a loss of progress for the current item. Possible improvement
  (later): each owner re-sends his records as orders after the load.
- A short "waiting" dialog (the existing 0x89 dialog) during the ~150 KB transfer.

## 5. Risks and open points

1. Host identity (3.5).
2. Mismatch detected inside a modal dialog or screen on a client: only the flag and 0x8a happen there; the load
   happens later at the host's safe point, and the client applies 0x72 through the normal handler, which today
   also runs inside message pumps (Fix L parks 0x72 while busy). Check whether `FUN_0050da70` is safe inside a
   modal dialog's pump on a client.
3. A slow client still processing turn N gets 0x89/0x72 parked (Fix L) and then reaches its own compare: it
   must see `d_resync` and skip.
4. Several clients request at once; the host detects the mismatch itself later: one resync only (`d_resync_run`).
5. Player drop or host migration (message 4 sets `[0x5a2990]`) during the transfer.
6. Memory: the 150 KB message comes from pool 0x591798 (`FUN_00492ed0`); repeated resyncs and the known leak
   in `FUN_00456b20` (skipped orders not freed) must be measured.
7. Turn timer: restarted by `FUN_0050da70` [V]; check the client timer.
8. Unpatched peers: still assert. The patcher should refuse mixed games? (No version handshake today; the
   Version string compare `FUN_0050f5c0` only checks the program version.)
9. Code size: about 300–450 bytes of cave code, a few data bytes. Free in the code cave: about 1.7 KB.
10. A divergence that repeats every turn (e.g. a mod) would cause a resync every turn: limit to N resyncs per
    M turns, then fall back to the old error.

## 6. Test plan (5 instances on one PC)

1. Forced divergence: poke a checksummed value (e.g. system +0x2dc) on client C before END TURN → expect one
   resync, all continue, `auto.sav` identical on all (CRC), counters 0x590230.. equal, `[0x5a291c] = 0`,
   slots empty, next 0x71 clean, 20 more turns in sync.
2. Divergence on the host → the host state wins, same checks.
3. A fast player ends turn N+1 immediately before the detection → no error, his input is redone.
4. Detection while a client sits in the system screen and in the "delete current build?" dialog → no crash.
5. Host with autosave off.
6. Player drop during the transfer.
7. Long run with a forced divergence every 20 turns: memory/pool, transfer time with Fix C (no send sleep) and
   with the latency build.
8. Regression: all existing scenario tests (r2test, r3test, mtest, ytest, coltest, optest, tacedo) unchanged.

## 7. Review results (Fable, Astra) and required changes

Both reviews: the transfer itself (0x89 + 0x72, `FUN_0050de40`, `FUN_0050da70`) is reusable, but the draft
is **not implementable unchanged**. Verified corrections and the changes they require:

1. **P0 — a load in a running game tears down the network session** (Astra; re-verified): with `[0x5a2920]
   == 1`, `FUN_004387f0` calls `FUN_0043d0d0` (0x4388f3), which in multiplayer calls `FUN_00519b80`
   (0x43d0f7) → `FUN_0054cf90`: destroys the local DirectPlay player or closes and releases the interface,
   clears 0x5fd97c. Change: a *transport-preserving reload*: while a resync runs, skip `call 0x50d670` and
   `call 0x519b80` in `FUN_0043d0d0` (0x43d0f2/0x43d0f7) and keep the rest of the world cleanup. Must be
   tested first (does the session survive, do the other players' DirectPlay ids stay valid).
2. **Host test (3.5) resolved:** `[0x5a2990]` lies inside the saved block (0x5a28d8.., offset 0xb8) and is
   overwritten by every load of a host-written file — that is why all instances show 1. The reliable test is
   the transport role `[0x5fd978] == 1` (`FUN_00519fb0`; set from DPCAPS_ISHOST and on DPSYS_HOST at
   0x54d908; used by the game for host-only sends). The internal host branch of `FUN_0050da70` (0x50dae4)
   must be steered explicitly (host reload takes the receive/apply path). Note: Fix OP and `FUN_0050d730`
   also read `[0x5a2990]`; for OP this is harmless because the broadcast at 0x4cdc5c uses the same flag.
3. **Corrections to section 2:** the running-game teardown (`FUN_0043d0d0` → `FUN_00457e00`) *does* reset
   0x590248 and empties the receive slots, but leaves the list pointers set (release them the Fix Y way after
   the load). `FUN_004569e0` drops only type-2 fleet orders of other humans with an empty task force. The
   order counters are reset and then overwritten from the loaded order ids. `FUN_00510230` clears both the
   local CRC words and the received table. A client that gets 0x72 without 0x89 hangs in the `FUN_0050d010`
   pump: never drop or reorder 0x89.
4. **Re-entrancy (both, P0/P1):** 0x89 and 0x72 handlers run inside whatever message pump is active (modal
   dialogs such as "delete current build?" keep system/order pointers across their pump). Change: park
   0x89/0x72/0x73 while `d_depth > 1` or during tactical combat (`[0x5a2b74] != 0`) and replay them, in order,
   from the main-loop tick; add a re-entry guard around the load.
5. **Message races (both, P1):** stale 0x68/0x74 of the aborted turn carry the same turn number as the loaded
   state, late 0x71 trigger a second compare, late 0x85 change options, a late 0x68 can complete the barrier
   and start a turn. Change: a resync *transaction*: from detection until the first turn start after the load
   drop 0x68/0x74/0x71/0x85, treat a pending resync like BUSY in the Fix B hook, gate END TURN
   (0x458120/0x458170), release slots after the load, clear `d_resync` at the next turn start (pstart), not
   in the load tail. Astra recommends a generation number and acknowledgements (quiescent / loaded / release)
   instead of a single flag; the 0x8a request should carry the turn number to drop stale requests.
6. **Execution point:** the main-loop idle path. Fable: hook `call 0x402410` at 0x40233c (reached only with
   `d_depth == 0`); Astra: the loop top at 0x402201 (five one-byte pushes). Not the Fix B drain point (depth
   ≥ 1). Turn start pumps before setting BUSY, so `busy == 0` alone is not a safe gate.
7. **Detection hooks:** the compare functions also pump messages (`FUN_0050ffe0` waits for older table entries,
   `FUN_00510260` pumps until the turn matches) and assert the turn number before the compare. The 0x71 drop
   must happen in the dispatcher, and while a resync runs the whole compare function must be skipped. Normal
   continuations: 0x51019e / 0x510403 (Fable), 0x51000b / 0x5103f8 (Astra) — to be settled.
8. **Production records (§4):** the reviews disagree with the draft and with each other. Astra: current
   production sits in sys+0x80..0x93 and accumulates on every machine without an owner check; only the
   owner re-arms the next item, so the host lacks only freshly re-armed non-host work. Fable: check
   empirically. Action: dump sys+0x80..+0x99 of a foreign system on two instances before deciding; keep
   "consistent, progress of a fresh item may be lost" as the documented consequence.
9. **Resources:** `FUN_00456b20` leaks the skipped current-turn orders on every load; the 150 KB message comes
   from pool 0x591798. Measure in a long run with repeated resyncs; fix the leak if it grows.
10. **Timer:** with a transport-preserving reload the full timer teardown/recreate path may not run; reset the
    stopped/expired latch explicitly (Astra: 0x4b9baf..0x4b9bbc, 0x4b9e55).
11. **Host migration** (DPSYS_HOST, message 4) during the transfer: abort the transaction.

Revised risk ranking: (1) transport teardown on load, (2) re-entrant load from modal dialogs, (3) message
races / resync loops, (4) host identity, (5) production-record consistency, (6) leaks and pool exhaustion,
(7) host migration, (8) unpatched peers (add a version check to 0x8a/0x89).

Next step before any implementation: a spike on the test bed — trigger the stock 0x89 + 0x72 path in a
running 5-player game with the transport-preserving teardown patch only, and check that the session, the
player ids and the next turns survive. If that fails, the design needs a different transfer (e.g. the 0x73
late-join path, which does not load on running clients).
