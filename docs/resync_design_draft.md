# DRAFT v2: self-healing multiplayer ("resync instead of synchronization error")

Status: design draft, **revised after reviews by Claude Fable and Codex gpt-6-astra**; not implemented.
Addresses refer to trek.exe 2.0.4 EN (the patcher's base). [V] = verified in the disassembly (by the
feasibility study, a review, or re-checked by us), [I] = inference the implementation must confirm.
Section 8 lists what changed against v1 and why.

## 1. Goal

Today a checksum difference after a turn ends the game: the 0x71 comparison shows "synchronization error",
asserts and the process exits (the others see "Disconnected"). Our fixes remove the causes we found, but
unknown causes remain (other CPUs' x87 results, player-drop timing, mods, bugs not found yet).

Goal: on a mismatch every machine takes over the host's game state and the game continues. Players lose at
most the input of the current turn. All players must use the patched program.

## 2. What the game provides, and what stands in the way

- **Transfer** [V]: `FUN_0050de40(slot, flag)` reads a whole save file and sends it to all as 0x72 (flag 0)
  or 0x73 (flag 1); `floor(bytes/466)+1` packets (about 317 for a 148 KB `auto.sav` at turn 180). The 0x72
  receiver (`FUN_0050dd30`) writes `auto.sav` and calls `FUN_0050da70`.
- **Apply** [V] `FUN_0050da70`: keeps the local empire and the session strings 0x5a2928..0x5a2977, loads
  (`FUN_004387f0(-0xd)`), applies the human mask (`FUN_00510ba0`), drops type-2 fleet orders of other humans
  whose task force is empty (`FUN_004569e0`), re-initialises the turn (`FUN_00438740`), rebuilds the screens
  (`FUN_004b9570`, `FUN_004b9180(0)`) and restarts the turn timer (0x50dd14). The client branch needs the
  waiting dialog `[0x597508]` that the 0x89 handler creates; without it `FUN_0050d010` pumps messages
  forever. So the order host → all is always 0x89, then 0x72.
- **Blocker 1 — a load in a running game tears down the network** [V]: with `[0x5a2920] == 1`,
  `FUN_004387f0` calls `FUN_0043d0d0` (0x4388f3), which in multiplayer calls `FUN_0050d670` (0x43d0f2) and
  `FUN_00519b80` (0x43d0f7) → `FUN_0054cf90`: the local DirectPlay player is destroyed or the interface is
  closed and released, 0x5fd97c cleared. The stock path is therefore *not* usable as is (§3.2).
- **Blocker 2 — host identity** [V]: `[0x5a2990]` lies inside the saved block (0x5a28d8.., offset 0xb8) and is
  overwritten by every load of a host-written file; in our test bed all five instances show 1. The reliable
  test is the transport role **`[0x5fd978] == 1`** (`FUN_00519fb0`; set from DPCAPS_ISHOST and on DPSYS_HOST
  at 0x54d908; used by the game for host-only sends such as 0x6b). `FUN_0050da70` itself branches on
  `[0x5a2990]` (0x50dae4), so the resync must steer that branch explicitly.
- **What the running-game teardown resets** [V] (`FUN_0043d0d0`, then the load): the turn state
  `[0x5a291c] = 0`, main RNG, the order list (current-turn orders are skipped in MP and leak, `FUN_00456b20`),
  the order counters (reset, then overwritten from the loaded order ids), Fix W/W3 state, 0x590248, the
  task-force lists (destroyed and rebuilt), the receive slots' *contents* (`FUN_00457e00`: emptied, empire
  0xff) — but **not** the slots' list pointers, the received-checksum table and CRC words 0x5ccfc0 (cleared
  only at turn start by `FUN_00510230`), and the messages parked by our Fix B/L.
- **Message pumps everywhere** [V]: the 0x89 handler, the dialog close in the loader, both checksum
  compare functions (`FUN_0050ffe0` waits for older entries; `FUN_00510260` pumps until the turn number
  matches) and modal dialogs (e.g. "delete current build?") all run nested message loops; a handler can
  therefore run inside a dialog whose caller keeps system/order pointers across the pump.

## 3. Design

### 3.1 Transaction state (data cave)

`rs_phase` (0 idle, 1 requested, 2 transferring, 3 loaded-waiting-for-turn), `rs_gen` (transaction number,
sent in every resync message), `rs_count` / `rs_turn` (rate limit), `rs_parked` (count of parked 0x89/0x72).

### 3.2 Transport-preserving reload

While `rs_phase == 2` the calls at 0x43d0f2 (`FUN_0050d670`) and 0x43d0f7 (`FUN_00519b80`) are skipped; the
rest of `FUN_0043d0d0` (world cleanup, timers `FUN_004b9b30/40`, slot clear `FUN_00457e00`) runs as today.
After the load: release the receive slots the Fix Y way (`FUN_0051b520`, `FUN_0051b450`, pointer 0, empire
0xff), clear 0x5ccfc0 and the CRC words (`FUN_00510230`), reset the timer latch explicitly (0x4b9baf..0x4b9bbc,
0x4b9e55), restore `[0x5a2990]` from `[0x5fd978]`. **This is the first thing to prove** (§6 spike): does the
DirectPlay session, with all player ids, survive a load when these two calls are skipped.

### 3.3 Detection

Both mismatch sites keep their turn-number checks and pumps; the 0x71 handling is changed earlier:

- **Dispatcher** (Fix B cave at 0x50a709): while `rs_phase != 0` drop 0x71, 0x68, 0x74 and 0x85 (stale
  messages of the aborted turn; they carry the same turn number as the loaded state, so the turn tag cannot
  filter them); never drop 0x89; park 0x89/0x72/0x73 while `d_depth > 1` or tactical combat
  (`[0x5a2b74] != 0`) and replay them in order from the main-loop tick (§3.5); treat `rs_phase == 1..2` like
  BUSY for the barrier (so a late 0x68 cannot start a turn).
- **Mismatch** at 0x5100c9 (`FUN_0050ffe0`) and 0x51031f (`FUN_00510260`): instead of the message box and
  assert: if `rs_phase == 0` and the rate limit allows (at most 2 resyncs per 10 turns), set `rs_phase = 1`,
  `rs_gen += 1`; host (`[0x5fd978] == 1`): nothing more (the tick does the work); client: send **0x8a**
  (body: `rs_gen`, current turn) to the host. Then continue at the normal continuation (0x51019e /
  0x510403; Astra named 0x51000b / 0x5103f8 — to be settled by reading both functions once more). Over the
  rate limit: the old error, as today.
- While `rs_phase != 0` the compare functions are skipped as a whole.

### 3.4 Host transaction (main-loop tick)

Hook: the idle path of the main loop, `call 0x402410` at 0x40233c (reached only with `d_depth == 0`), or the
loop top 0x402201 (five one-byte pushes). Condition: host, `rs_phase == 1`, `[0x5a291c] == 0`, no tactical
combat, window active (otherwise the tick does not run — acceptable, it delays). Steps:

1. `rs_phase = 2`; gate END TURN (0x458120) and the turn start (0x458170) while `rs_phase != 0`;
2. save `auto.sav` (`FUN_00438630(-0xd)`, also with autosave off);
3. broadcast 0x89 (`mov eax,0x89; call 0x5199c0`), then `FUN_0050de40(-0xd, 0)` (0x72);
4. apply locally through the receive path: `FUN_0050d070` (dialog), then `FUN_0050da70` with the host branch
   suppressed (`[0x5a2990] = 0` for the call), so the host resets exactly like the clients;
5. post-load reset (§3.2), `rs_phase = 3`.

Clients: the 0x89 handler sets `rs_phase = 2` (also when the client never detected a mismatch itself); the
0x72 load runs with the transport-preserving reload; afterwards `rs_phase = 3`.

`rs_phase` goes back to 0 at the **next turn start** (pstart 0x458215), not in the load tail: a straggler's
late 0x71/0x68 of the old turn are dropped until everybody has started the new turn. Astra recommends
explicit acknowledgements (quiescent / loaded / release) instead of relying on the turn start; to be decided
after the spike — the turn barrier (all players' 0x68) already acts as a "loaded" acknowledgement.

### 3.5 Re-entrancy guard

A load never runs inside a nested pump: 0x89/0x72/0x73 that arrive with `d_depth > 1` are parked (Fix L
buffer) and replayed by the tick in arrival order. A flag around `FUN_0050da70` rejects a second load while
one is running.

### 3.6 Host migration and drops

A DPSYS_HOST message (0x54d908) or a player drop (message 2) during `rs_phase == 1..2` aborts the
transaction: the new host starts a fresh one with `rs_gen + 1`. Unpatched peers: 0x8a and the extra fields are
unknown to them; they keep asserting (document: all players need the patch).

## 4. Consequences for the players

- The input of the current turn is lost on every machine (the load skips current-turn orders); players redo
  it. Build queues come back from the file and are re-sent at the next END TURN (Fix A order).
- Production records sys+0x80..+0xa7: Astra found that current production (+0x80..+0x93) accumulates on every
  machine without an owner check and only the re-arm of the next item is owner-only; Fable could not confirm
  either way. **Must be measured** (dump the records of a foreign system on two instances). Expected
  consequence: at worst the item an owner just re-armed is missing after the resync (consistent on all
  machines, the owner picks it again). Replaying owners' records blindly is unsafe (it recreates the Fix H/M
  pattern).
- A short wait dialog (the existing 0x89 dialog) during the transfer.

## 5. Risks (ranked)

1. Transport teardown on load (§3.2) — the whole design depends on the spike.
2. Re-entrant load from modal dialogs (§3.5).
3. Message races / resync loops (§3.3, rate limit as backstop).
4. Host identity and migration (§2, §3.6).
5. Production-record consistency (§4).
6. Leaks and pool exhaustion: `FUN_00456b20` leaks the skipped orders on every load; the 150 KB message comes
   from pool 0x591798 — measure over many resyncs, fix the leak if needed.
7. Unpatched peers.
8. Code size: about 400–600 bytes of cave code (v1 estimate 300–450 plus guards); free in the code cave about
   1.7 KB after v1.7.0 — enough, but tight; a new PE section may become necessary.

## 6. Plan

1. **Spike** (no full feature): in a running 5-player game on the test bed, trigger the stock 0x89 + 0x72
   path from the host with only the transport-preserving reload patch (§3.2). Check: session alive, player ids
   valid, next END TURN and 0x68/0x71 exchange work, all five in sync for 10 turns. If it fails: look at the
   0x73 late-join path (running clients do not load there) or a custom state transfer.
2. Measure the production records (§4).
3. Implement §3.1–3.6, smallest step first: detection + host push without the client request (host-detected
   mismatch only), then 0x8a, then the guards.
4. Tests on the test bed:
   1. forced divergence on a client (poke system +0x2dc before END TURN): one resync, all continue; `auto.sav`
      CRC equal on all, counters 0x590230.. equal, `[0x5a291c] = 0`, slots empty, next 0x71 clean, 20 turns
      in sync;
   2. divergence on the host;
   3. a fast player ends turn N+1 right before the detection;
   4. detection while a client is in the system screen and in the "delete current build?" dialog;
   5. host with autosave off; 6. player drop and host migration during the transfer;
   7. long run with a forced divergence every 20 turns (leaks, pool, transfer time with and without the
      latency build);
   8. regression: r2test, r3test, mtest, ytest, coltest, optest, tacf.

## 7. Open questions

- Normal continuation addresses of the two compare functions (§3.3).
- Execution hook 0x40233c vs 0x402201 (§3.4).
- Acknowledgement protocol vs. turn-start release (§3.4).
- Production records (§4).
- Whether `FUN_0050d670` (called before the transport close) has side effects the reload needs.

## 8. Changes against v1 (from the reviews)

| v1 said | v2 | Source |
|---|---|---|
| the stock 0x72 path works in a running game | it tears down DirectPlay; transport-preserving reload + spike first | Astra, re-verified 0x43d0f7/0x54cf90 |
| host test open (`[0x5a2990]`) | `[0x5fd978]`; `[0x5a2990]` is part of the save | Fable, Astra |
| slots and 0x590248 not reset by a load | teardown resets 0x590248 and empties the slots, but leaves the list pointers | Fable, Astra |
| clear slots at 0x89 | drop stale 0x68/0x74/0x71/0x85 during the transaction, release slots after the load | Fable, Astra |
| clear `d_resync` in the load tail | release at the next turn start (or acknowledgements) | Fable, Astra |
| host acts at the "Fix B drain point" | main-loop idle path 0x40233c / loop top 0x402201 | Fable, Astra |
| re-entrancy only a risk | park 0x89/0x72/0x73 at depth > 1 or in combat, replay from the tick, load guard | Fable, Astra |
| 0x89 not parked by Fix L (implied) | correct: Fix B/L park 0x68/0x74/0x85/0x72/0x73, not 0x89 | Astra |
| `FUN_004569e0` drops other humans' orders | only type-2 fleet orders with an empty task force | Fable, Astra |
| production progress of non-host systems lost | probably only freshly re-armed items; measure | Astra, Fable |
| timer restarted by the load | true for the full teardown; reset the latch explicitly with the preserving reload | Astra |
| 300–450 bytes | 400–600 bytes | — |
