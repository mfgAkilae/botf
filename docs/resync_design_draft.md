# DRAFT v5: self-healing multiplayer ("resync instead of synchronization error")

Status: design draft after four review rounds (Claude Fable, Codex gpt-6-astra); not implemented. Round 4
verdict on v4: Fable "spike: go after the table fixes; protocol: one more revision"; Astra "needs another
revision; the spike remains worthwhile". v5 integrates all round-4 findings (section 11); sections 9 and 10
keep the round-2 and round-3 changes.
Addresses: trek.exe 2.0.4 EN. [V] = verified in the disassembly (by a reviewer or by us), [I] = inference.

## 1. Goal

Today a checksum difference after a turn ends the game ("synchronization error", assert, exit; the others see
"Disconnected"). Goal: on a mismatch every machine takes over the host's game state and the game continues.
Players lose at most the input of the current turn. All players must use the patched program.

## 2. Facts the design builds on

- **Transfer** [V]: `FUN_0050de40(slot, flag)` sends a whole save file as 0x72 (flag 0) or 0x73;
  `floor(bytes/466)+1` packets. The 0x72 receiver writes `auto.sav` (`FUN_0050dd90`) and calls `FUN_0050da70`.
- **Apply** [V] `FUN_0050da70`: keeps the local empire and the session strings 0x5a2928..0x5a2977, loads
  (`FUN_004387f0(-0xd)`), applies a human mask (`FUN_00510ba0`), drops type-2 orders of other humans whose task
  force is missing (`FUN_004569e0`), re-initialises the turn (`FUN_00438740`), rebuilds the screens, restarts
  the timer (0x50dd14), sets session-descriptor flags (`thunk_FUN_0054c900`, harmless on clients) and
  `[0x5a2afc] = 0`. Its host branch (0x50dae4, `[0x5a2990] == 1`) re-broadcasts 0x89 and a file; its client
  branch needs the 0x89 dialog `[0x597508]` (missing dialog → assert path via `FUN_005081b0`).
- **Mask input** [V] (corrected in round 3): `FUN_0050da70` loads `edx = [0x5a2994]` (resume flag) at
  0x50da88 and keeps it until the test at 0x50dcc0. `[0x5a2994] == 0` → the **local pre-load** mask
  `[0x5a2b28]` (0x50dcc4), load at 0x50dba0; `≠ 0` → load first (0x50dce7), then mask `= [0x5a2998]` **from
  the host's file** (0x50dcf8, `[0x5a2928+0x70]`). `[0x5a2998]` is offset 0xc0 of the saved block and 0 in a
  fresh game. → The resync uses the resume path: the host writes `[0x5a2998] = [0x5a2b28]` before saving,
  every machine applies with `[0x5a2994] = 1` (§4.4).
- **Teardown on load** [V]: with `[0x5a2920] == 1`, `FUN_004387f0` calls `FUN_0043d0d0` (0x4388f3), which in
  multiplayer calls `FUN_0050d670` (0x43d0f2: score/"game over" lobby messages, no game state) and
  `FUN_00519b80` (0x43d0f7 → `FUN_0054cf90`: DestroyPlayer / Close / Release, CoUninitialize, `[0x5fd97c] = 0`).
  No other call in the load or `FUN_00438740` closes the transport; `FUN_0050da70` itself reads/writes the
  session descriptor (0x50dab0 → 0x54c989), so transport survival stays experimental. The player table
  0x5a29f8 comes back from the host's file of the same session. Timers are torn down (0x43d0d6/0x43d0db) and recreated
  (0x50dd14), so no extra latch reset is needed.
- **Host identity** [V]: `[0x5a2990]` lies in the saved block (0x5a28d8, size 0xdc0; offset 0xb8) and is
  overwritten by every load of a host-written file. Transport role: **`[0x5fd978] == 1`** (`FUN_00519fb0`).
- **Load resets** [V]: turn state `[0x5a291c] = 0` (in the load, 0x43cebd), RNG, order list (current-turn
  orders skipped and leaked, `FUN_00456b20`), counters (reset, then overwritten from loaded ids), Fix W/W3
  state, 0x590248, slot contents (pointers kept — harmless, `FUN_004560e0` reuses 0xff slots). **Not reset:**
  checksum table and CRC words (`FUN_00510230`; called at turn start and from `FUN_0043d6c0`), the Fix B/L
  parking buffer.
- **Compare functions** [V]: continuations after the error path are **0x51000b** (`FUN_0050ffe0`) and
  **0x5103f8** (`FUN_00510260`); 0x51019e/0x510403 would re-run the RNG compares and re-enter the error. Their
  turn-number checks (0x510058..0x51007c, 0x5102a1..0x5102c6) are **fatal asserts**, not waiting loops: a
  turn skew between machines must be handled before these functions run. `FUN_00510260` stores without
  comparing whenever `[0x5a291c] != 0` (also −1 "waiting").
- **Who detects** [V] (corrected in round 4): `FUN_00458170` sets BUSY (0x458215), merges (0x45821f), clears
  the checksum state (0x458224), runs the **whole turn processing** `FUN_00458260` (0x458229, ends with
  `[0x5a291c] = 0` at 0x4586d8 where Fix B's cave clears BUSY), then `FUN_00475290` (0x45822e) and only then
  `FUN_0050ffe0` (0x458233), whose first call sends this machine's 0x71 (`FUN_005104d0` at 0x50ffec) before it
  compares. Detection is therefore **post-turn, BUSY = 0**, still inside `FUN_00458170` (called from the 0x68
  handler 0x456321 or from END TURN). A 0x71 that arrives while `[0x5a291c] != 0` is stored for that later
  compare (0x510285/0x510492); one that arrives while idle is compared at once in `FUN_00510260` and **not**
  stored (returns at 0x510487) — the table 0x5ccfc0 cannot tell the host who has sent.
- **Resume-flag readers** [V]: `[0x5a2994]` is also read at every turn start (0x458238 → `FUN_0050fbd0`), in the
  dispatcher (0x50aa74) and in lobby join/rejoin handlers; it is written only by lobby code. In a lobby-resumed
  game it stays 1 for the whole game. The resync must save and restore it, not clear it.
- **Fresh vs. resume apply** [V]: the only other difference is `FUN_0043a0a0` (0x50dbb6..0x50dbc9, fresh path
  only), which walks the local empire's system list with callback 0x43a150 → `FUN_0044d300`, which can restart or
  adjust production (0x44d342..0x44d366). Skipping it suits a running-game snapshot; production preservation is
  an acceptance condition (§5).
- **Barrier mask** [V]: own `[0x590248]` | receive slots 0x5b4870 with non-null payload (0x4561c0..0x4561cb) —
  the slot release after the load is load-bearing for the barrier.
- **Message pumps** [V]: timer-driven END TURN can enter turn start at depth 0 and pump a network handler at
  depth 1 (0x4b9f74, 0x4581ee, 0x45820b); a load at depth 1 can still invalidate an active caller.
- **Fix B/L parking** [V]: at most 23 entries; on overflow the handler runs anyway; the flush reposts and
  clears the count; newer arrivals can overtake reposted ones.
- **Bodies**: 0x89 sent with `FUN_005199c0` has no body [V]; any broadcast with body goes through
  `FUN_00519960(eax=id, edx=body, ebx=len)` [V 0x519960..0x519989: returns 0 when `[0x5fd97c] == 0`, clobbers
  eax/edx/ebx, DPID_ALLPLAYERS excludes the sender]. Unpatched peers ignore unknown ids [V].
- **Send ordering** [V/I]: every message is split into ⌊len/466⌋+1 fragments (0x54dfc0) and sent with
  DPSEND_GUARANTEED (flags 1, 0x54bc23/0x54bc57); the receiver posts a message only after full reassembly
  (0x54d7a2..0x54d7da). Our Fix C releases the send lock between fragments, but all game messages are sent
  synchronously from the main thread (only Fix D's unreliable, ignored keepalive comes from the receive
  thread), so one machine's game messages leave in order. In-order *delivery* per sender pair is a DirectPlay
  property the binary cannot prove [I]; the stock multi-fragment 0x72 already relies on it; the spike checks it.
- **Pumps outside the loop top** [V]: modal dialogs (`FUN_00500350`, `FUN_005004a4`), tactical-combat sync
  loops (0x473d12..0x473d7c: send 0x86, pump, wait for the human acknowledgement mask; the 0x86 receiver
  asserts on a battle-index mismatch, 0x50ae0c/0x473ed3) and `FUN_0050d010` (pumps twice before the load)
  never pass 0x402201. With an inactive window the outer loop sleeps in WaitMessage (0x402330) and a posted
  message wakes it; the **nested** pump `FUN_004024c0` (0x4024c8..0x402510) drains and goes back to WaitMessage
  without returning to its caller.
- **Receive-thread tick** [V]: Fix D already wakes the receive thread every 1000 ms (rxwait); PostMessage
  through IAT_POSTMSG is what the Fix B flush uses; an unknown message id falls through the stock switch.
- **Production** [V] (Astra): progress of the current build accumulates on every machine without an owner check
  (0x4624af, 0x460940..0x4609f0); only the re-arm of the next item is owner-dependent (0x4616e4).

## 3. Protocol

### 3.1 New messages (all via `FUN_00519960`, broadcast; ignored by non-addressees)

| Id | From → to | Body | Meaning |
|---|---|---|---|
| 0x8a REQ | any → host | last applied epoch, turn, local CRC words | "I saw a mismatch" |
| 0x8b FREEZE | host → all | epoch, turn | start transaction `epoch`, install the gates |
| 0x8c QUIET | all → all | epoch | "my freeze gates are active" (sent by the dispatcher on FREEZE) |
| 0x8d SNAPINFO | host → all | epoch, file length, file CRC32 | metadata of the file that follows (0x89 + 0x72) |
| 0x8e LOADED | all → all | epoch, recomputed CRC words + normalised RNG | "I applied the snapshot" (sent at the loop top) |
| 0x8f RELEASE | host → all | epoch | "resume play" |
| 0x90 ABORT | host → all | epoch | "transaction failed: old error" |
| 0x91 NACK | host → requester | requester's epoch | "no transaction for you" (stale REQ): back to phase 0 |
| 0x92 TICK | receive thread → own window | — | wake-up during a transaction; consumed by the dispatcher |

Snapshot transfer stays the stock 0x89 (dialog) + 0x72 (file). The host assigns the epoch (monotonic counter
in its data cave); clients never invent one. Acks are broadcast so that every machine sees every other
machine's QUIET/LOADED (needed for the per-sender fence, §3.4).

### 3.2 Phases (per machine)

`rs_phase`: 0 idle → 1 requested (mismatch seen, REQ sent) → 2 frozen (FREEZE received: gates set, Fix B
parked 0x68/0x74/0x85 freed with their payloads, QUIET sent — all inside the dispatcher, at any depth) →
3 transferring (SNAPINFO, 0x89, 0x72 received; 0x89/0x72 queued and applied at the next loop top) → 4 loaded
(LOADED sent, waiting for RELEASE) → 0. FREEZE moves 0 → 2 and 1 → 2 (several requesters join the same
transaction); a duplicate FREEZE/SNAPINFO of the same epoch is ignored. NACK moves 1 → 0. ABORT/FREEZE that
arrive inside the pumps of `FUN_0050d010` only set a flag that is acted on after the apply.

**When the host freezes** (round 4, Fable): the host sends FREEZE only after it holds a 0x71 for the current
turn from **every** human in the mask (own per-sender bitmask, set in the 0x71 handler and by the stored
entries, cleared at `FUN_00510230`; timeout several minutes with the wait dialog). Every machine has then
finished the turn's processing — including tactical combats and their 0x86 exchange — and sits in the input
phase (0 or −1). The barrier for the next turn cannot complete, because the requester (and the host) block
END TURN from phase 1 on. This makes the freeze a safe point without draining running combats.

**Requests** (round 4): REQ carries the requester's last applied epoch. Host: a REQ while a transaction runs is
merged into it; a REQ with an older epoch than the host's last completed one is stale → NACK (the requester
returns to phase 0 and its next compare decides again); otherwise a new transaction starts. No silent drop.

Host additionally: waits for QUIET from all humans in the mask before saving and sending SNAPINFO + 0x89 +
0x72; waits for LOADED from all before RELEASE; compares every LOADED set with its own; mismatch → ABORT.
**Timeouts** are checked at the loop top **and** in the dispatcher on every TICK (so they also run inside
nested pumps): client phase 1 without FREEZE or NACK 60 s; 0x71-complete before FREEZE several minutes; QUIET
60 s; LOADED several minutes, all with the visible wait dialog. Any timeout → ABORT → the old error on every
machine. **ABORT is terminal**: no new transaction in that game after a failure, drop or migration — a failed
transaction falls back exactly to today's behaviour.

### 3.3 What is blocked in which phase

| | 1 requested | 2 frozen | 3 transferring | 4 loaded | after RELEASE |
|---|---|---|---|---|---|
| END TURN (0x458120), turn start (0x458170), timer expiry | **blocked** | blocked | blocked | blocked | allowed |
| incoming 0x71 | stored for the host's 0x71-complete check, not compared | dropped | dropped | **per-sender fence** | **per-sender fence** |
| incoming 0x68 / 0x74 / 0x85 / 0x86 | normal | dropped | dropped | **per-sender fence** | **per-sender fence** |
| local input that creates orders | allowed (the load drops it) | allowed (the load drops it) | — | blocked until RELEASE | allowed |
| compare functions | skipped | skipped | skipped | skipped | normal |

Per-sender fence (phase 4 and after RELEASE, **independent of the local phase**): a 0x68/0x74/0x85/0x86/0x71
from sender S is dropped until this machine has received S's LOADED for the current epoch. This also covers
the round-4 race "S's old 0x71 arrives at C after the host's RELEASE". DirectPlay guaranteed messages are ordered per sender pair [I],
so everything S sent before loading arrives before S's LOADED and is discarded; everything after is valid.
This closes the stale-0x68 race (Fable hole 4) without tagging ordinary messages.

## 4. Mechanics

### 4.1 Detection hooks

At 0x5100c9 and 0x51031f: multiplayer, `rs_phase == 0`, rate limit OK → `rs_phase = 1`, send REQ (host:
handle locally), continue at **0x51000b / 0x5103f8**. Rate limit enforced by the host: at most 2 accepted
transactions per 10 turns (sliding); over the limit the host answers ABORT → old error. In the dispatcher
(Fix B cave 0x50a709), before the compare functions can run: while `rs_phase != 0` an incoming 0x71 never
reaches `FUN_00510260` (avoids the turn-number asserts on skewed machines); in phase 1 the host only records
the sender in its 0x71-complete bitmask, in phases 2–4 and behind the fence it is dropped (§3.3).

### 4.2 Safe point and wake-up

The load (applying 0x89/0x72) happens only at the **main-loop top 0x402201** (`56 56 56 56 53`, five one-byte
pushes replayed in the cave; esi/ebx preserved). QUIET is sent from the dispatcher (§3.2), so a machine inside
a modal dialog or a tactical combat (their own pumps never pass 0x402201) freezes at once and applies when it
returns to the loop. With an inactive window the loop sleeps in WaitMessage (0x402330) and passes 0x402201
only when a message arrives, so during a transaction the receive thread posts a wake-up message once per
second (TICK, payload-free, from the Fix D rxwait loop through IAT_POSTMSG, consumed by the dispatcher). The
apply's own nested pump (`FUN_0050d010` → `FUN_004024c0`) does not return to its caller while the window is
inactive, so the apply helper sets the game's "active" flag `[0x5a28d4] = 1` for the duration of the apply and
restores it afterwards [I — test "inactive-window apply" in the spike]. 0x40233c was considered but needs an
active window and an empty queue. The resync messages (0x89, 0x72, 0x73
during a transaction) go into a **dedicated bounded queue** (own buffer, explicit payload ownership, no
execution on overflow → ABORT), not into the Fix B/L buffer; the Fix B flush must not repost them. Entries
are applied in arrival order at the loop top, one per iteration, with a re-entry flag around `FUN_0050da70`.

### 4.3 Host steps (at the loop top, `[0x5a291c] != 1`, i.e. idle or waiting)

1. receive REQ (or own detection, post-turn) → phase 1, END TURN blocked; wait until the 0x71 of the turn has
   arrived from every human in the mask (§3.2); then epoch += 1, install the state, FREEZE(epoch, turn), freeze
   itself (phase 2);
2. wait for QUIET of all humans (timeout → ABORT);
3. at its loop top: `[0x5a2998] = [0x5a2b28]` (both in the saved block); save `auto.sav`
   (`FUN_00438630(-0xd)`, also with autosave off); send SNAPINFO(epoch, file length, CRC32);
4. broadcast 0x89, then `FUN_0050de40(-0xd, 0)`;
5. apply its own file through the same path as everybody: `FUN_0050d070` **unconditionally** (the broadcast
   does not reach the sender), then §4.4;
6. collect LOADED; all sets equal → RELEASE; else ABORT.

A host waiting at −1 is fine: the load resets `[0x5a291c]` to 0 and drops its sent current-turn orders like
everybody's.

### 4.4 Apply on every machine (including the host)

At the loop top, phase 3, one guarded **apply helper** for host and clients alike (the host never passes the
stock 0x72 receiver, so the helper is called from the tick): `FUN_0050d070` for the dialog (host:
unconditionally); check the received file against SNAPINFO's length and CRC32 (mismatch → ABORT); save
`[0x5a2994]` and `[0x5a28d4]`; then `FUN_0050da70` with
- `[0x5a2990] = 0` (client branch, no re-broadcast) and `[0x5a2994] = 1` (resume path: the mask comes from
  the host's file, `[0x5a2998]`), both set before the call — the branch is chosen before the load overwrites
  them (0x50dae4, 0x50da88);
- `[0x5a28d4] = 1` so that the nested pump returns (§4.2);
- the transport-preserving reload: `FUN_0043d0d0` skips 0x43d0f2 and 0x43d0f7 while phase == 3;
- a re-entry flag that covers all resync handlers while `FUN_0050da70` and its pumps run;
afterwards: restore `[0x5a2994]` and `[0x5a28d4]`, `[0x5a2990] = [0x5fd978]`, slots released the Fix Y way
(load-bearing for the barrier), `FUN_00510230`, then **recompute** with an own helper that replicates the stock
sequence of `FUN_005104d0` without its send (0x510592): `FUN_00508080` (esi = destination: copies the RNG block
0x596bac/0x120), `FUN_00447b40` (eax = 0x597610, edx = 0x597612, ebx = 0x597614), `FUN_0043db00` → 0x597616,
`FUN_0045d570` → 0x597618, then zero the copied RNG at +4..+0x14 (edx = 0 before those stores; stock code at
0x510547..0x510577, receiver 0x5102e2..0x5102fe); broadcast LOADED(epoch, those values); phase 4. The file
check before the load uses a **file-open flag** at 0x4387fb (head of the load: `FUN_00438b60` opened the
file); success of the whole load is a flag set at the end of the load tail (around 0x4389c0); missing → ABORT.
**Assert** (logged in the spike): `[0x597504]` equals the loaded `[0x5a2b28]` before `FUN_00510ba0` — if the
host forgot `[0x5a2998]`, `FUN_00510ba0` would turn every human into a computer empire (`FUN_0043a160`).

### 4.5 Membership changes

Handled on the main thread: host migration in `FUN_00510b30` (system message 4), drops in `FUN_0050d730`
(message 2). During phases 1–4 the transaction is aborted (terminal, old error) **before** the drop handler
mutates membership, the human mask, AI ownership and the receive state (0x50d83c, 0x50d870..0x50d894) or
starts a turn (0x50d8a4). The member set is fixed at FREEZE (human mask and DirectPlay ids); resync messages
from non-members are ignored. An unexpected 0x73 in a running game keeps its stock, non-loading handling.

## 5. Consequences for the players

- Input of the current turn is lost everywhere; build queues return from the file and are re-sent at the next
  END TURN.
- Production: progress is replicated (§2); the open question is only the next item an owner re-armed in the
  last turn. **Acceptance gate**: measure host/owner/third-party records, queues and orders around unfinished
  builds, completion, purchase, deletion, the snapshot, the reload and the next END TURN.
- A wait dialog during the transfer; if the host window is inactive the transaction still runs (loop top).

## 6. Risks (ranked)

1. Transport survival with the preserving reload (§4.4) — spike first.
2. Re-entrancy (§4.2) — dedicated queue, loop-top only.
3. Protocol races and deadlocks (§3) — phases with acks, per-sender fence, timeouts.
4. Mask/branch selection (§2) — resume path with `[0x5a2998]` from the host's file.
5. Membership changes during the transaction (§4.5).
6. Production consistency (§5).
7. Leaks (`FUN_00456b20`, pools 0x591798 / receive pool) and the Fix C send-retry exhaustion that returns
   success (0x54e172) — measure; the file CRC in SNAPINFO + the LOADED values catch a broken transfer.
8. Code size: 0.8–1.2 KB of cave code (protocol, queue, hooks) — more than the ~1.7 KB left after v1.7.0
   allows comfortably; plan a new PE section in the patcher (affects all 143 variants).

## 7. Plan

1. **Spike** (test build only, no protocol, all players deliberately idle): a poke-able trigger byte makes the
   host transfer its state; every machine applies at its loop top. Patch sites:

   | Site | Bytes (verified) | Purpose |
   |---|---:|---|
   | 0x402201 | 5 (`56 56 56 56 53`, no jump targets inside) | loop-top tick: host transfer on the trigger, call the apply helper for queued 0x89/0x72; replay the pushes, full register preservation |
   | 0x50a709 (existing Fix B cave, 7 original bytes) | — | divert 0x89/0x72 into a 2-entry owned queue (also when they were parked while BUSY and reposted at 0x4586d6); consume TICK |
   | 0x50dd7b | 5 (`e8 f0 fc ff ff`) | stock 0x72 apply call → the guarded apply helper (caller pops ebp/edi/esi/ecx/ebx afterwards: preserve them; eax free) |
   | 0x43d0e0 (7: `83 3d 24 29 5a 00 00`, flags consumed by `je` at 0x43d0e7) or 0x43d0f2 + 0x43d0f7 (2 × 5) | 7–10 | skip the lobby report and the transport close during the reload (the 7-byte variant must set flags or jump to 0x43d0fc) |
   | 0x4387fb | 5 (`83 f8 01 74 05`) | file-open flag (head of the load) |
   | around 0x4389c0 | 5 | load-success flag (end of the load tail) |

   Helpers: the guarded apply (§4.4: dialog, file check, `[0x5a2994]`/`[0x5a28d4]` save/set/restore,
   `[0x5a2990]`, re-entry flag, Fix Y slot release, `[0x5a2990] = [0x5fd978]`), the host trigger (mask into
   `[0x5a2998]`, save, 0x89, `FUN_0050de40`, own apply), the four-call CRC/RNG logger. About 32 overwritten
   bytes plus helper code and ~24 data bytes. Acceptance: a client poked into
   divergence before the transfer ends up with the host's state (CRC words and RNG logged and equal on all
   five); local empires and the human mask unchanged; DirectPlay ids and the session unchanged; a corrupted
   file is rejected; real orders and queues work afterwards and 10 turns stay in sync; the same with one
   machine at −1 when the transfer starts, one with the system screen open, two transfers in a row (transport
   state, pool counters), and once from a lobby-resumed game (`[0x5a2994] = 1` before and after the apply);
   `[0x597504]` equals the loaded `[0x5a2b28]` before `FUN_00510ba0` (logged on every machine); a 0x72 that
   arrives while BUSY (parked, reposted, then diverted); apply with an inactive window; a missing and a
   truncated file (rejected, no load); production fields of a few systems (host, owner, third party) compared
   before and after; ordinary traffic (0x68/0x74/0x71) after repeated loads; log the arrival order of numbered
   test messages from two senders with artificial delay (evidence for per-sender ordering, not a proof).
2. Production measurement (§5).
3. Protocol §3–4 step by step: REQ/FREEZE/QUIET/NACK, then SNAPINFO/LOADED/RELEASE, then fence, then aborts/migration.
4. Tests: forced divergence on a client and on the host (poke system +0x2dc), fast player before detection,
   detection with system screen / "delete build?" dialog open, autosave off, drop and migration in each phase,
   turn timer on (expiry during phases 2–4), inactive host window, long run with a forced divergence every
   20 turns (leaks, pools, transfer time, latency build), regression (r2test, r3test, mtest, ytest, coltest,
   optest, tacf).

## 8. Open questions

- DirectPlay per-sender ordering of guaranteed messages (assumed for the fence) — confirm in the spike.
- New PE section in the patcher vs. squeezing into the cave.
- Whether a dropped human's slot needs special handling across a resync (Fix EL already releases it).

## 9. Changes against v2 (review round 2)

| v2 | v3 | Source |
|---|---|---|
| END TURN gated until turn start, rs_phase cleared at turn start | explicit phases with QUIET/LOADED acks and RELEASE (was circular → deadlock) | Astra, Fable |
| host tick needs `[0x5a291c] == 0` | `!= 1`; a waiting host (−1) must act | Fable, Astra |
| drop 0x68/0x74 in phase 3 | blocked only while frozen; per-sender fence after load (no legit orders lost) | Fable, Astra |
| park at `d_depth > 1` in the Fix L buffer | apply only at loop top 0x402201, dedicated bounded queue | Astra |
| `[0x5a2990] = 0` around the host's call | client branch forced on every machine; EDX pinned to 0; `[0x5a2998]` set | Fable (verified), Astra |
| continuations 0x51019e/0x510403 vs 0x51000b/0x5103f8 open | 0x51000b / 0x5103f8 | Fable, Astra |
| turn-number "pumps" in the compare functions | fatal asserts; drop 0x71 in the dispatcher during a transaction | Astra |
| epoch carried in 0x89 | 0x89 has no body; host-assigned epoch in new messages 0x8a..0x8f | Astra, Fable |
| no failure path | file CRC, LOADED CRCs, timeouts, ABORT → old error | Astra |
| migration via 0x54d908 | main-thread handlers `FUN_00510b30` / `FUN_0050d730`, abort before a turn can start | Fable |
| explicit timer-latch reset | not needed (timers torn down and recreated) | Fable |
| `FUN_0050d670` open | lobby score messages only, skip | Fable, Astra |
| 400–600 bytes | 0.8–1.2 KB, likely a new PE section | — |

## 10. Changes against v3 (review round 3)

| v3 | v4 | Source |
|---|---|---|
| EDX undefined, pin it to 0 | EDX = `[0x5a2994]` (0x50da88); use the resume path `[0x5a2994] = 1` with `[0x5a2998]` from the host's file | Astra (re-verified), Fable |
| "mask = host's saved mask" with EDX = 0 | that path uses the local pre-load mask; the resume path uses the file | Fable, Astra |
| LOADED hashes the CRC words right after `FUN_00510230` | that hashes zeros; recompute the five CRCs with the stock code, RNG with stock normalisation | Astra |
| QUIET only at the loop top | QUIET from the dispatcher (gates active); only the load waits for the loop top; LOADED timeout minutes | Fable (gap A), Astra |
| no wake-up | 1-s wake-up message from the receive thread during a transaction | Fable (gap B), Astra |
| phase 1 unbounded, END TURN allowed | phase 1 blocks END TURN; client timeout for PREPARE | Fable (gap C) |
| fence relies on DirectPlay ordering | same, plus: game messages are sent synchronously from the main thread, so Fix C's lock release does not interleave them; confirm ordering in the spike | Fable, Astra, us |
| Fix B parked messages survive | freed with their payloads at PREPARE | Astra |
| ABORT, then a new host may restart | ABORT is terminal; member set fixed at PREPARE; drop handler intercepted before it mutates state | Astra |
| REQ rules missing | ignored during a transaction, stale ones after RELEASE dropped | Fable, Astra |
| host's own apply implicit | `FUN_0050d070` unconditionally (no local 0x89) | Fable |
| load failure via eax | via a flag set in the load tail | Fable, Astra |
| turn-state reset at 0x43cf9a | 0x43cebd | Astra |
| "nothing else touches the transport" | the apply reads/writes the session descriptor (0x54c989): survival is experimental | Astra |
| detection timing unclear | at the turn start of the last machine whose barrier completes (BUSY = 1, inside a pump) | Fable |
| spike with EDX pin and few checks | patch-site table (~25–30 bytes) and an acceptance list that proves the load, the ordering and repeated transfers | Fable, Astra |

## 11. Changes against v4 (review round 4)

| v4 | v5 | Source |
|---|---|---|
| detection at turn start, BUSY = 1 | post-turn: `FUN_00458260` (0x458229) runs before `FUN_0050ffe0` (0x458233), which first sends 0x71; BUSY = 0 | Astra, Fable (both verified) |
| QUIET as the barrier before loading | the host freezes only after it holds the turn's 0x71 from every human: everybody has finished the turn incl. combats; no draining of running combats needed | Fable (proposal), Astra (problem) |
| fence for 0x68/0x74/0x85 only, from phase 4 | per sender, independent of the local phase, also 0x71 and 0x86 (race: old 0x71 after RELEASE) | Astra, Fable |
| PREPARE sent twice (with and without metadata) | FREEZE and SNAPINFO separated; duplicates of the same epoch ignored | Astra |
| stale REQ dropped silently (requester times out → terminal) | REQ carries the last applied epoch; stale → NACK back to phase 0; concurrent REQs merged | Fable, Astra |
| wake-up only at the loop top | TICK also checks timeouts in the dispatcher; `[0x5a28d4] = 1` during the apply so the nested pump returns | Astra |
| `[0x5a2994] = 0` after the apply | save and restore (a lobby-resumed game keeps 1; it is read every turn start) | Fable |
| "recompute with 0x5104eb..0x510523" | not callable: own helper replicating `FUN_00508080`, `FUN_00447b40`, `FUN_0043db00`, `FUN_0045d570` + normalisation, without the send | Fable, Astra |
| 0x4387fb as load success | file-open flag (head); success flag at the end of the load tail (~0x4389c0) | Fable, Astra |
| host applies through 0x50dd7b | one guarded apply helper for all, called from the tick (the host never receives its own 0x72) | Fable |
| no check of the mask before `FUN_00510ba0` | logged assertion `[0x597504]` == loaded `[0x5a2b28]` | Fable |
| resume path "only mask differs" | also skips `FUN_0043a0a0` → `FUN_0044d300` (production restart): acceptance condition | Astra, Fable |
| acceptance list | + BUSY-parked 0x72, inactive-window apply, missing/truncated file, production compare, traffic after repeated loads, two-sender ordering evidence | Astra, Fable |
