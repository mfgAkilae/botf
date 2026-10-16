# DRAFT v3: self-healing multiplayer ("resync instead of synchronization error")

Status: design draft after two review rounds (Claude Fable, Codex gpt-6-astra); not implemented. Round 2
verdict of both reviewers on v2: "needs another revision"; v3 integrates all round-2 findings (section 9).
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
- **Hidden mask input** [V] (Fable): the client branch tests **EDX** at 0x50dcc0. EDX ≠ 0 → mask
  `[0x597504] = [0x5a2998]`; EDX = 0 → `[0x5a2b28]`. EDX is whatever `FUN_0050dd90` left (undefined).
  `[0x5a2998]` is written only in resume mode; in a fresh game it is 0, and `FUN_00510ba0(0)` would turn every
  human into a computer empire. → EDX must be pinned to 0 and `[0x5a2998]` set (§3.4).
- **Teardown on load** [V]: with `[0x5a2920] == 1`, `FUN_004387f0` calls `FUN_0043d0d0` (0x4388f3), which in
  multiplayer calls `FUN_0050d670` (0x43d0f2: score/"game over" lobby messages, no game state) and
  `FUN_00519b80` (0x43d0f7 → `FUN_0054cf90`: DestroyPlayer / Close / Release, CoUninitialize, `[0x5fd97c] = 0`).
  Nothing else in the load, `FUN_00438740` or `FUN_0050da70` touches the transport; the player table 0x5a29f8
  comes back from the host's file of the same session. Timers are torn down (0x43d0d6/0x43d0db) and recreated
  (0x50dd14), so no extra latch reset is needed.
- **Host identity** [V]: `[0x5a2990]` lies in the saved block (0x5a28d8, size 0xdc0; offset 0xb8) and is
  overwritten by every load of a host-written file. Transport role: **`[0x5fd978] == 1`** (`FUN_00519fb0`).
- **Load resets** [V]: turn state `[0x5a291c] = 0` (in the load, 0x43cf9a), RNG, order list (current-turn
  orders skipped and leaked, `FUN_00456b20`), counters (reset, then overwritten from loaded ids), Fix W/W3
  state, 0x590248, slot contents (pointers kept — harmless, `FUN_004560e0` reuses 0xff slots). **Not reset:**
  checksum table and CRC words (`FUN_00510230`; called at turn start and from `FUN_0043d6c0`), the Fix B/L
  parking buffer.
- **Compare functions** [V]: continuations after the error path are **0x51000b** (`FUN_0050ffe0`) and
  **0x5103f8** (`FUN_00510260`); 0x51019e/0x510403 would re-run the RNG compares and re-enter the error. Their
  turn-number checks (0x510058..0x51007c, 0x5102a1..0x5102c6) are **fatal asserts**, not waiting loops: a
  turn skew between machines must be handled before these functions run. `FUN_00510260` stores without
  comparing whenever `[0x5a291c] != 0` (also −1 "waiting").
- **Who detects** [V/I]: the slowest machine detects in `FUN_0050ffe0`; a host that already ended its turn sits
  at `[0x5a291c] = −1` (0x4581a1) and only stores incoming 0x71.
- **Message pumps** [V]: timer-driven END TURN can enter turn start at depth 0 and pump a network handler at
  depth 1 (0x4b9f74, 0x4581ee, 0x45820b); a load at depth 1 can still invalidate an active caller.
- **Fix B/L parking** [V]: at most 23 entries; on overflow the handler runs anyway; the flush reposts and
  clears the count; newer arrivals can overtake reposted ones.
- **Bodies**: 0x89 sent with `FUN_005199c0` has no body [V]; any broadcast with body goes through
  `FUN_00519960(eax=id, edx=body, ebx=len)` [V]. Unpatched peers ignore unknown ids (dispatcher returns 0) [V].
- **Production** [V] (Astra): progress of the current build accumulates on every machine without an owner check
  (0x4624af, 0x460940..0x4609f0); only the re-arm of the next item is owner-dependent (0x4616e4).

## 3. Protocol

### 3.1 New messages (all via `FUN_00519960`, broadcast; ignored by non-addressees)

| Id | From → to | Body | Meaning |
|---|---|---|---|
| 0x8a REQ | any → host | turn, local CRC words | "I saw a mismatch" |
| 0x8b PREPARE | host → all | epoch, turn, file length, file CRC32 | start transaction `epoch`, freeze |
| 0x8c QUIET | all → all | epoch | "I am frozen at the main-loop top" |
| 0x8d LOADED | all → all | epoch, CRC of my loaded state | "I applied the snapshot" |
| 0x8e RELEASE | host → all | epoch | "resume play" |
| 0x8f ABORT | host → all | epoch | "transaction failed: old error" |

Snapshot transfer stays the stock 0x89 (dialog) + 0x72 (file). The host assigns the epoch (monotonic counter
in its data cave); clients never invent one. Acks are broadcast so that every machine sees every other
machine's QUIET/LOADED (needed for the per-sender fence, §3.4).

### 3.2 Phases (per machine)

`rs_phase`: 0 idle → 1 requested (mismatch seen, REQ sent) → 2 frozen (PREPARE received, QUIET sent) →
3 transferring (0x89/0x72 being applied) → 4 loaded (LOADED sent, waiting for RELEASE) → 0.
Host additionally: waits for QUIET from all humans in the mask before sending 0x89/0x72; waits for LOADED
from all before RELEASE; checks every LOADED CRC against its own; mismatch or timeout (60 s) → ABORT → old
error on all machines.

### 3.3 What is blocked in which phase

| | 1 requested | 2 frozen | 3 transferring | 4 loaded | after RELEASE |
|---|---|---|---|---|---|
| END TURN (0x458120), turn start (0x458170), timer expiry | allowed | blocked | blocked | blocked | allowed |
| incoming 0x71 | dropped | dropped | dropped | dropped | accepted (new epoch's turns) |
| incoming 0x68 / 0x74 / 0x85 | normal | dropped | dropped | **per-sender fence** | accepted |
| compare functions | skipped | skipped | skipped | skipped | normal |

Per-sender fence (phase 4 and after RELEASE): a 0x68/0x74/0x85 from sender S is dropped until this machine
has received S's LOADED for the current epoch. DirectPlay guaranteed messages are ordered per sender pair [I],
so everything S sent before loading arrives before S's LOADED and is discarded; everything after is valid.
This closes the stale-0x68 race (Fable hole 4) without tagging ordinary messages.

## 4. Mechanics

### 4.1 Detection hooks

At 0x5100c9 and 0x51031f: multiplayer, `rs_phase == 0`, rate limit OK → `rs_phase = 1`, send REQ (host:
handle locally), continue at **0x51000b / 0x5103f8**. Rate limit enforced by the host: at most 2 accepted
transactions per 10 turns (sliding); over the limit the host answers ABORT → old error. In the dispatcher
(Fix B cave 0x50a709), before the compare functions can run: drop 0x71 while `rs_phase != 0` (avoids the
turn-number asserts on skewed machines).

### 4.2 Safe point

All destructive work (sending QUIET, applying 0x89/0x72) happens only at the **main-loop top 0x402201**
(five one-byte pushes replayed in the cave; also runs when the window is inactive). 0x40233c was considered
(Fable's preference) but needs an active window and an empty queue. The resync messages (0x89, 0x72, 0x73
during a transaction) go into a **dedicated bounded queue** (own buffer, explicit payload ownership, no
execution on overflow → ABORT), not into the Fix B/L buffer; the Fix B flush must not repost them. Entries
are applied in arrival order at the loop top, one per iteration, with a re-entry flag around `FUN_0050da70`.

### 4.3 Host steps (at the loop top, `[0x5a291c] != 1`, i.e. idle or waiting)

1. receive REQ (or own detection) → epoch += 1, PREPARE(epoch, turn, len, crc) — length/CRC of the file saved
   in step 3, so step 3 runs first; order: save, then PREPARE;
2. freeze itself (phase 2), wait for QUIET of all humans (timeout → ABORT);
3. before saving: `[0x5a2998] = [0x5a2b28]` (both in the saved block); save `auto.sav` (`FUN_00438630(-0xd)`,
   also with autosave off);
4. broadcast 0x89, then `FUN_0050de40(-0xd, 0)`;
5. apply its own file through the same client path as everybody (§4.4);
6. collect LOADED; all CRCs equal → RELEASE; else ABORT.

A host waiting at −1 is fine: the load resets `[0x5a291c]` to 0 and drops its sent current-turn orders like
everybody's.

### 4.4 Apply on every machine (including the host)

At the loop top, phase 3: `FUN_0050d070` for the dialog if 0x89 was queued, then `FUN_0050da70` with
- `[0x5a2990] = 0` and `[0x5a2994] = 0` for the call (client branch, no re-broadcast);
- **EDX = 0** pinned at the call (mask from `[0x5a2b28]` = the host's saved mask);
- the transport-preserving reload: `FUN_0043d0d0` skips 0x43d0f2 and 0x43d0f7 while phase == 3;
afterwards: `[0x5a2990] = [0x5fd978]`, slots released the Fix Y way, `FUN_00510230`, LOADED(epoch, CRC of
the five CRC words + RNG block) broadcast, phase 4. A load that returns early (`FUN_004387f0` can return
before applying, 0x4387fb..0x438804) → ABORT.

### 4.5 Membership changes

Handled on the main thread: host migration in `FUN_00510b30` (system message 4), drops in `FUN_0050d730`
(message 2). During phases 1–4: the transaction is aborted **before** the drop handler may start a turn
(`FUN_0050d730` can call `FUN_00458170`); the new host (`[0x5fd978]`) may start a fresh transaction with a
higher epoch. The rate-limit counter is host-local (lost on migration — acceptable).

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
4. Mask/branch pinning (§2) — EDX and `[0x5a2998]`.
5. Membership changes during the transaction (§4.5).
6. Production consistency (§5).
7. Leaks (`FUN_00456b20`, pools 0x591798 / receive pool) and the Fix C send-retry exhaustion that returns
   success (0x54e172) — measure; the file CRC in PREPARE + LOADED CRC catch a broken transfer.
8. Code size: 0.8–1.2 KB of cave code (protocol, queue, hooks) — more than the ~1.7 KB left after v1.7.0
   allows comfortably; plan a new PE section in the patcher (affects all 143 variants).

## 7. Plan

1. **Spike** (minimal, test build only): host-initiated transfer without the protocol: at the loop top on the
   host send 0x89 + 0x72; every machine applies at its loop top with EDX = 0, `[0x5a2998]` set, client branch
   forced, transport-preserving reload. Acceptance: DirectPlay ids unchanged, 0x68/0x74/0x71 exchange works,
   10 synchronized turns, human mask unchanged.
2. Production measurement (§5).
3. Protocol §3–4 step by step: REQ/PREPARE/QUIET, then LOADED/RELEASE, then fence, then aborts/migration.
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
