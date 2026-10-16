# DRAFT v8: self-healing multiplayer ("resync instead of synchronization error")

Status: design draft after seven review rounds (Claude Fable, Codex gpt-6-astra); not implemented. Round 7
verdict on v7: Fable "text-only revision; spike can start once the queue model, the failure free, the 0x89
semantics and the host trigger are specified"; Astra "needs another revision (progress blocker, contradictory
failure handling, membership, addressing)". v8 is a **consistent rewrite of the normative part** (sections
1–8) that integrates all round-7 findings; the appendix (sections 9–14) is non-normative review history.
Addresses: trek.exe 2.0.4 EN. [V] = verified in the disassembly (by a reviewer or by us), [I] = inference.

Terms used throughout: **loop-top step** = our code at the main-loop hook 0x402201; **TICK** = the private
window message that wakes the main loop (it never applies anything); **participant set P** = the frozen set of
players of a transaction (§3.3); **target turn T** = the turn value the transaction is about (§3.4).

## 1. Goal

Today a checksum difference after a turn ends the game ("synchronization error", assert, exit; the others see
"Disconnected"). Goal: on a mismatch every machine takes over the host's game state and the game continues.
Players lose at most the input of the current turn. All players must use the patched program. A failed resync
ends the game exactly like today.

## 2. Facts the design builds on

- **Transfer** [V]: `FUN_0050de40(slot, flag)` sends a whole save file as 0x72 (flag 0) or 0x73;
  ⌊bytes/466⌋+1 packets. The stock 0x72 receiver `FUN_0050dd30(eax = lParam, edx = wParam)` (dispatched at
  0x50aa10) allocates the buffer and reads the body (0x50dd39..0x50dd74: eax = ecx = buffer, edx = ebp =
  length), calls `FUN_0050dd90` at 0x50dd76 (writes `auto.sav`, frees the buffer with `FUN_00492e60(eax)` at
  0x50ddd0, parses and rewrites `gameInfo`) and `FUN_0050da70` at 0x50dd7b; 0x50dd80 pops ebp/edi/esi/ecx/ebx
  and returns.
- **Apply** [V] `FUN_0050da70`: keeps the local empire and the session strings 0x5a2928..0x5a2977, loads
  (`FUN_004387f0(-0xd)`), applies a human mask (`FUN_00510ba0`), drops type-2 orders of other humans whose task
  force is missing (`FUN_004569e0`), re-initialises the turn (`FUN_00438740`), rebuilds the screens, restarts
  the timer (0x50dd14), sets session-descriptor flags (0x50dab0, harmless on clients), `[0x5a2afc] = 0`. Host
  branch (0x50dae4, `[0x5a2990] == 1`) re-broadcasts; client branch requires the transfer dialog `[0x597508]`
  (`FUN_0050d010` asserts while it is missing, closes it and pumps twice). `FUN_0050d070` creates that dialog
  (its `[0x5a2990]` test only selects the dialog text, 0x50d07c..0x50d0b7).
- **Mask input** [V]: `edx = [0x5a2994]` at 0x50da88, tested at 0x50dcc0. 0 → local pre-load mask
  `[0x5a2b28]`; ≠ 0 → load first (0x50dce7), then mask `= [0x5a2998]` from the file (0x50dcf8). `[0x5a2998]`
  is offset 0xc0 of the saved block. `[0x5a2994]` is also read post-turn (0x458238), in the dispatcher (0x50aa74)
  and by lobby code; it stays 1 in a lobby-resumed game. The resume path additionally skips `FUN_0043a0a0`
  (0x50dbb6..0x50dbc9 → `FUN_0044d300`, which can restart production).
- **Teardown on load** [V]: with `[0x5a2920] == 1`, `FUN_004387f0` calls `FUN_0043d0d0` (0x4388f3), which in
  multiplayer calls `FUN_0050d670` (0x43d0f2, only when `[0x5b1a88] != 0`: lobby score messages) and
  `FUN_00519b80` (0x43d0f7 → `FUN_0054cf90`: DestroyPlayer / Close / Release, `[0x5fd97c] = 0`). No other call
  in the load closes the transport; transport survival without these two calls is a runtime question.
- **Host identity** [V]: `[0x5a2990]` is in the saved block (offset 0xb8) and overwritten by every load;
  transport role = `[0x5fd978] == 1` (`FUN_00519fb0`).
- **Load resets** [V]: `[0x5a291c] = 0` (0x43cebd), RNG, order list (current-turn orders skipped and leaked,
  `FUN_00456b20`), order counters, Fix W/W3 state, 0x590248, receive-slot contents (pointers kept). Not reset:
  checksum table/CRC words (`FUN_00510230`), Fix B/L parking, the send counter `[0x5a075c]`.
- **Turn end and detection** [V]: `FUN_00458170` sets BUSY (0x458215), merges, clears the checksum state
  (0x458224), runs the turn `FUN_00458260` (0x458229; increments the turn at 0x45856b; ends with
  `[0x5a291c] = 0`), then `FUN_0050ffe0` (0x458233), which first **sends its own 0x71** (0x50ffec) and then
  compares the stored entries (loop gate 0x510002, turn assert 0x510058..0x51007c, mismatch 0x5100c9, next
  entry 0x51000b, epilogue 0x51002d). Everything that pumps (autosave, combat, reports) precedes the send.
  Incoming 0x71: `FUN_00510260(eax = lParam, edx = wParam)` (0x50ad70); body copied to esp+0x400 before
  0x510278 (turn at +0 = sender's turn value, empire byte at +0x124), ebx = wParam; idle → compared at once and
  not stored (0x510487); not idle → stored per sender (0x510492..0x5104be) and wiped at the next turn start.
  Turn assert 0x5102a1, mismatch 0x51031f, epilogue 0x5103f8.
- **Sender identity** [V]: wParam = wire header +0x20 = sender's player id `[0x5fd8c4]`; lParam = header +0x10
  = sender's counter `[0x5a075c]`. The dispatcher's first call `FUN_00510600(eax = wParam)` (0x50a6ef) looks the
  id up in the player table 0x5a29f8 (5 × 0x34, id +0x28, empire byte +0x2c) and drops the message when the
  **local** empire or the sender's empire has its bit in `[0x5a2b50]` (0x510606..0x510669). `[0x5a2b50]` is set
  by `FUN_0043cad0` (elimination, [I]) and is in the saved block (offset 0x278). The DirectPlay idFrom is
  discarded (0x54d791). At the Fix B hook (0x50a709) wParam is in esi.
- **Window messages** [V]: the window proc (ebp = HWND, ecx = uMsg, esi = wParam, edi = lParam,
  0x4014f7..0x401503) routes only 0x400/0x402 to the dispatcher; 0x401507 `81 f9 13 01 00 00`; 0x401613 restores
  the frame and returns eax (`ret 0x10`). PostMessage = `[0x57462c]`, main window = `[0x5a074c]`. Fix D wakes the
  receive thread every 1000 ms (rxwait); a continuous receive stream stays in the drain loop (head 0x54d9e1).
- **Pumps** [V]: the nested pump `FUN_004024c0` returns only when `[0x5a28d4] != 0` after an empty PeekMessage
  (0x4024d8 `3b 35 d4 28 5a 00` + `75 32` → 0x402512 = idle exit, eax = 1); `[0x5a28d4]` belongs to the
  WM_ACTIVATEAPP handler `FUN_00401cc0`. A machine with an inactive window hangs in its turn start (stock). The
  outer loop top 0x402201 = `56 56 56 56 53`; modal dialogs and the combat pump never pass it.
- **Send ordering** [V/I]: fragments are sent with DPSEND_GUARANTEED; all game messages leave synchronously from
  the main thread; in-order delivery per sender pair is a DirectPlay property (assumed, checked in the spike).
- **Production** [V]: progress accumulates on every machine without an owner check (0x4624af); only the re-arm
  of the next item is owner-dependent (0x4616e4).

## 3. Protocol

### 3.1 Messages (all broadcast through `FUN_00519960(eax = id, edx = body, ebx = len)`; the sender does not
receive its own broadcast, so every sender also applies its own message locally)

| Id | From | Body | Meaning |
|---|---|---|---|
| 0x8a REQ | any participant | requester id, request seq, last applied epoch, T | "I saw a mismatch at turn T" |
| 0x8b FREEZE | host | epoch, T, P (empire mask + player ids) | start transaction; everybody gates |
| 0x8c QUIET | every member of P | epoch, own P view | "my gates are installed" |
| 0x8d SNAPINFO | host | epoch, file length, file CRC32 | expected values for the raw-buffer check |
| 0x8e LOADED | every member of P | epoch, CRC words + normalised RNG, own P view | only after a successful apply |
| 0x8f RELEASE | host | epoch | resume play |
| 0x90 ABORT | host | epoch | terminal: stock error on every machine |
| 0x91 NACK | host | requester id, request seq | "no transaction for this request": requester back to phase 0 |
| 0x93 FAIL | any member | epoch (0 before FREEZE), reason | "my check, load or deadline failed": host sends ABORT |

Snapshot transfer is the stock 0x89 (dialog) + 0x72 (file). Ids 0x8a..0x93 are new network message ids
(dispatched through the 0x50a709 cave; unpatched peers ignore them). TICK is not a network message (§4.3).

### 3.2 Phases (per machine)

0 idle → 1 requested → 2 frozen → 3 transferring → 4 loaded → 0 (RELEASE) or terminal (ABORT / local failure).

- 0 → 1: own mismatch (§4.1): send REQ, start D_req.
- 0 → 2 and 1 → 2: accepted FREEZE (epoch new, this machine in P): install the gates (§3.5), purge Fix B parked
  0x68/0x74/0x85 (freeing their records), send QUIET; duplicates of the same epoch are ignored.
- 1 → 0: NACK addressed to this requester (id and seq match).
- 2 → 3: SNAPINFO of the current epoch received (host: after sending it).
- 3 → 4: successful apply (§4.4), LOADED sent.
- 4 → 0: RELEASE of the current epoch (host: after sending it).
- any → terminal: ABORT, own deadline expiry, own check/load failure (§3.6).

### 3.3 Participant set P

Fixed by the host at FREEZE: every empire that is human in `[0x5a2b28]`, not set in `[0x5a2b50]`, and has a
player-table entry with a non-zero id. P (empire mask + player ids) travels in FREEZE; every member echoes its
own view in QUIET and LOADED; any difference, a FREEZE that does not contain the receiving machine although it
is human and alive, or a membership state the host cannot classify → ABORT. All completion, QUIET and LOADED
requirements use P and nothing else. The stock mute filter (`FUN_00510600`) only drops traffic in which the
local or the sender's empire is marked in `[0x5a2b50]`; such empires are never in P, so resync control traffic
between members of P passes it.

### 3.4 Target turn and the host's decision

Each machine records `own71 = [0x5a2918]` at the compare-loop gate 0x510002 (first iteration; it runs after the
own 0x71 send at 0x50ffec). REQ carries T = the requester's own71. The host keeps `rs_last71[emp]` (§4.1).

Host, on REQ (or own mismatch with T = own71):
- a transaction is running → merge (the requester is a member; nothing to send);
- the request's last applied epoch is older than the host's last completed epoch → NACK(requester id, seq);
- otherwise → host phase 1 with this T, D_complete started.

In phase 1 the gates allow a machine to finish turns up to T but not beyond: END TURN (0x458120) and turn start
(0x458170) are allowed only while the machine's `[0x5a2918]` < T (a machine that is still behind — typically the
host waiting for a late 0x68 — completes turn T with its normal traffic); at `[0x5a2918]` ≥ T they are blocked.
**0x71-complete** := own71 == T and `rs_last71[e] == T` for every empire e in P except the host's own. Then the
host sends FREEZE(epoch, T, P), installs its own gates and marks its own QUIET.

### 3.5 Gates (from FREEZE until RELEASE; phase 1 gates per §3.4)

| | phase 1 | phases 2–3 | phase 4 | after RELEASE |
|---|---|---|---|---|
| END TURN 0x458120, turn start 0x458170, timer END TURN (Fix K cave 0x4b9f6a) | allowed below T, blocked at ≥ T | blocked | blocked | allowed |
| incoming 0x71 | recorded; not compared | recorded; dropped | recorded; per-sender fence | recorded; per-sender fence |
| incoming 0x68 / 0x74 / 0x85 / 0x86 | normal | dropped | per-sender fence | per-sender fence |
| compare functions | skipped (gate 0x510002; 0x510278 → 0x5103f8) | skipped | skipped | normal |

Local UI input is not gated: orders made before the load are dropped by the load; orders made after it belong
to the new turn and are legitimate (END TURN stays blocked until RELEASE).

**Per-sender fence**: armed by an accepted FREEZE for each member S ≠ self of P; a 0x68/0x74/0x85/0x86/0x71
from S (key = wParam) is dropped until S's LOADED of the current epoch has been received; checked before any
queue that can reorder (Fix B park); stays active after RELEASE until it opens; reset on new game / lobby
entry. Correct under per-sender in-order delivery (spike).

### 3.6 Deadlines and termination

All deadlines count from the named event, are checked in the loop-top step and in the TICK handler, and are not
extended by duplicates:

| Deadline | Who | Starts at | Length |
|---|---|---|---|
| D_req | requester | REQ sent | 330 s (D_complete + 30 s margin) |
| D_complete | host | phase 1 entered | 300 s |
| D_quiet | host | FREEZE sent | 60 s |
| D_loaded | host | SNAPINFO sent | 300 s |
| D_abort | any machine after sending FAIL | FAIL sent | 30 s |

On ABORT, on own deadline expiry and 30 s after an own FAIL the machine raises the **stock error** from the
loop-top step by replicating the sequence of 0x5100c9..0x5100e0 (`eax = 0x4bd`, `ebx = -1`, `call 0x48b2e0`,
dialog with `[0x5cd5f8]`; to be verified in the spike). Before that a client sends FAIL(epoch or 0, reason) so
the host can ABORT the others. The host applies its own RELEASE and ABORT locally. ABORT is terminal: no new
transaction in that game. A pending ABORT always has priority over LOADED.

Rate limit (host only): at most 2 accepted transactions per 10 turns; a further REQ → ABORT.

## 4. Mechanics

### 4.1 Hooks for detection and evidence

- **Compare-loop gate** 0x510002 (`83 bd c0 cf 5c 00 ff`): first iteration records own71; while `rs_phase != 0`
  jump to 0x51002d; else replay the cmp and continue at 0x510009.
- **Mismatch** 0x5100c9 and 0x51031f: multiplayer and `rs_phase == 0` → phase 1, REQ, continue at 0x51000b
  (the gate then ends the loop) / 0x5103f8.
- **0x71 ledger** at 0x510278: overwrite only the 7-byte `cmp [0x5a2920],0` (`83 3d 20 29 5a 00 00`); cave:
  `FUN_005105d0(eax = ebx)` → record (0 → skip the ledger), require record byte +0x2c == body byte
  `[esp+0x524]`, `rs_last71[emp] = [esp+0x400]`; if `rs_phase != 0` or the fence blocks this sender, jump to
  0x5103f8 (restoring any cave pushes); else replay the cmp and jump to 0x51027f (the intact `je`). Ledger
  initialised per session, never cleared at a turn start.

### 4.2 Dispatch of resync traffic (the 0x50a709 cave, extended Fix B)

- 0x8a..0x93: handled here (state changes only; at any depth).
- 0x89, 0x72 during a transaction (or the spike): **queued as (wParam, lParam) pairs**, exactly like the Fix B
  park; the receive record stays in the pool. The Fix B flush never reposts these entries. 0x73 during a
  transaction: dropped (its record freed). 0x72 without a SNAPINFO of the current epoch → FAIL.
- At the loop-top step, one entry per iteration is re-dispatched through `FUN_0050a6e0(eax = 0x400,
  edx = wParam, ebx = lParam)` with `rs_pass = 1` so the cave lets it through; the stock handlers then run
  (0x89 → `FUN_0050cfd0` creates the dialog; 0x72 → `FUN_0050dd30` with the hooks of §4.4).

### 4.3 Loop-top step and TICK

- **Loop-top step** (hook 0x402201, five pushes replayed, all registers preserved): checks deadlines, performs
  the host's steps (§4.5), re-dispatches one queued entry, sends LOADED after a successful apply.
- **TICK** = window message `WM_APP + 0x92`, intercepted in the window proc at 0x401507: checks deadlines with
  all registers preserved, returns eax = 0 through 0x401613; any other message replays the cmp and continues at
  0x40150d. Posted by a rate-limited helper (push 0, push 0, push WM_APP+0x92, push `[0x5a074c]`, call
  `[0x57462c]`) from the Fix D rxwait cave and from the receive drain loop (0x54d9e5, replaying
  `bb 01 00 00 00`), only while `rs_phase != 0`.
- **Pump override** at 0x4024d8: if `rs_apply` jump to 0x402512 (stock idle exit), else replay the cmp and
  continue at 0x4024de. `[0x5a28d4]` is never written.

### 4.4 Apply (every machine; the host calls it directly, §4.5)

Raw-buffer check at 0x50dd76 (client only): compare edx (length) and the CRC32 of [eax..eax+edx) with
SNAPINFO. Mismatch → `FUN_00492e60(eax = buffer)`, skip both calls, jump to 0x50dd80; close the transfer
dialog if it exists (the stock close of `FUN_0050d010`); send FAIL; terminal per §3.6. Match → run the original
call to `FUN_0050dd90`; at 0x50dd7b the call goes to the **apply helper**:

1. acquire `rs_apply` (re-entry guard; resync handlers only set flags while it is held); save `[0x5a2994]`;
2. ensure the transfer dialog exists exactly once (`FUN_0050d070` only if `[0x597508] == 0`);
3. set `[0x5a2990] = 0` and `[0x5a2994] = 1`; reset the file-open and tail flags;
4. call `FUN_0050da70` — inside it: `FUN_0043d0d0` skips 0x43d0f2 and 0x43d0f7 while `rs_apply` is held (call
   hooks); the file-open flag at 0x4387fb (reproduce `cmp eax,1` / `je 0x438805`, record eax == 1); the tail flag
   at 0x4389c0 (call `FUN_0051c9c0`, set the flag, continue at 0x4389c5); `FUN_0050d010` closes the dialog;
5. **common cleanup, every exit**: restore `[0x5a2994]`; `[0x5a2990] = [0x5fd978]`; release the receive slots
   the Fix Y way; `FUN_00510230`; release `rs_apply`;
6. **only on success** (both flags set, no pending ABORT): recompute — `FUN_00508080` (esi = dedicated 0x120-byte
   buffer; reload esi afterwards), `FUN_00447b40` (eax = 0x597610, edx = 0x597612, ebx = 0x597614),
   `FUN_0043db00` → 0x597616, `FUN_0045d570` → 0x597618, zero buffer dwords +4..+0x14 — and send LOADED;
   phase 4;
7. on failure: FAIL, terminal per §3.6 (never LOADED).

### 4.5 Host steps (loop-top step)

1. phase 1 until 0x71-complete (§3.4); then FREEZE, own gates, own QUIET marked; phase 2;
2. QUIET from every member of P (D_quiet);
3. `[0x5a2998] = [0x5a2b28]`; save `auto.sav` with `FUN_00438630(eax = -0xd)` (also with autosave off); length
   and CRC32 of that file; SNAPINFO; phase 3;
4. `mov eax,0x89; call 0x5199c0` (no body); `FUN_0050de40(eax = -0xd, edx = 0)`;
5. own apply: the helper of §4.4 from step 1, called directly in the same step (no raw-buffer check; the host
   validated its own file in step 3);
6. LOADED from every member of P with equal values (D_loaded) → RELEASE (applied locally); mismatch, FAIL or
   deadline → ABORT (applied locally).

### 4.6 Membership changes

Host migration (`FUN_00510b30`, system message 4) and drops (`FUN_0050d730`, message 2) during phases 1–4 abort
the transaction (terminal) **before** the drop handler mutates membership, the human mask, AI ownership or the
receive state (0x50d83c, 0x50d870..0x50d894) or starts a turn (0x50d8a4).

## 5. Consequences for the players

- Input of the current turn is lost everywhere; build queues come back from the file and are re-sent at the
  next END TURN.
- Production: progress is replicated; open is only the item an owner re-armed in the last turn (acceptance:
  compare host/owner/third-party records, queues and orders before and after).
- A wait dialog during the transfer.

## 6. Risks (ranked)

1. Transport survival without the two teardown calls — spike.
2. Per-sender in-order delivery (fence) — spike.
3. Re-entrancy — queue + loop-top step + `rs_apply`.
4. Protocol races — phases, target turn, deadlines, fence.
5. Membership changes — abort before mutation.
6. Production consistency — acceptance measurement.
7. Leaks (`FUN_00456b20`, pools) — measure over repeated transfers.
8. Code size: protocol + helpers + data (0x120-byte RNG buffer, queue, ledger, deadlines) ≈ 1–1.5 KB; the code
   cave has ~1.7 KB left after v1.7.0 → use a **new PE section** (the patcher must support it for all 143
   variants).

## 7. Spike (test build only, self-contained)

Purpose: prove (1) transport survival, (2) a correct apply on every machine, (3) per-sender ordering evidence.
No protocol; every step is triggered by poking test fields with the debugger tools.

**Data** (new section or test shim section): `sp_trigger` (dword), `sp_len`, `sp_crc` (expected values,
written into every client by the test tool before the trigger), `rs_apply`, `rs_pass`, `sp_saved_2994`,
`sp_queue[2]` (wParam, lParam), `sp_flag_open`, `sp_flag_tail`, `sp_log[]` (CRC words + RNG per apply), RNG
buffer 0x120 bytes.

**Patch sites**

| Site | Original bytes | Spike behaviour |
|---|---|---|
| 0x402201 | `56 56 56 56 53` | loop-top step: host with `sp_trigger` → host steps 3–5 of §4.5 (SNAPINFO replaced by logging len/CRC32), clear the trigger; re-dispatch one queued entry |
| 0x50a709 | `66 89 04 24 8b 04 24` | queue 0x89/0x72 while `sp_trigger` is set on any machine or entries are queued; pass through when `rs_pass` |
| 0x50dd76 | `e8 15 00 00 00` | raw-buffer check against `sp_len`/`sp_crc` (failure: free, skip, 0x50dd80, close dialog, log) |
| 0x50dd7b | `e8 f0 fc ff ff` | apply helper (§4.4 steps 1–6, LOADED replaced by logging) |
| 0x43d0f2, 0x43d0f7 | `e8 79 05 0d 00`, `e8 84 ca 0d 00` | skip while `rs_apply` |
| 0x4387fb | `83 f8 01 74 05` | file-open flag |
| 0x4389c0 | `e8 fb 3f 0e 00` | tail flag |
| 0x4024d8 | `3b 35 d4 28 5a 00` | pump override while `rs_apply` |
| 0x510002 | `83 bd c0 cf 5c 00 ff` | skip compares while `rs_apply` or entries are queued |
| 0x4b9f6a (existing Fix K cave) | — | defer timer END TURN while `rs_apply` |

Overwritten bytes ≈ 56 (+ the Fix K condition); helper code ≈ 400–600 bytes; data ≈ 0x120 + 64 bytes.
The CRC32 is our own small bitwise routine (no stock one is used).

**Procedures**
1. Idle: all five idle; poke a divergence on client C (e.g. system +0x2dc); the tool writes `sp_len`/`sp_crc`
   into every client after the host has saved (two-step trigger: host saves and logs, tool copies the values,
   host sends); post a wake-up to the host if its window is inactive.
2. Waiting: one client has ended its turn (−1) when the trigger fires.
3. BUSY: a 0x72 arrives while a client processes (parked by Fix B, reposted, then queued).
4. System screen open on a client; focus changes during the apply; inactive-window apply.
5. Two transfers in a row; a lobby-resumed game (`[0x5a2994] = 1` before and after).
6. Missing and truncated file (rejected, no load, buffer freed once, dialog closed).

**Acceptance**: DirectPlay ids and the session unchanged; `[0x597504]` equals the loaded `[0x5a2b28]` before
`FUN_00510ba0`; CRC words and RNG equal on all five after every apply; real orders, queues and 10 turns in sync
afterwards; production fields of host-owned, client-owned and third-party systems compared; wParam of every
received 0x400 logged against the player table; arrival order of numbered test messages from two senders with
artificial delay logged.

## 8. Open questions

- Replicating the stock error from the loop-top step (§3.6) — verify in the spike.
- New PE section support in the patcher (all variants).
- Exact deadline values after the spike's transfer-time measurements.

---

# Appendix: review history (non-normative)

The tables below record what earlier drafts said and why it changed. They describe superseded designs
(EDX pinning, PREPARE, silent REQ drops, forced activation, "eliminated humans always send 0x71", …) and
are **not** part of the design; sections 1–8 above are authoritative.

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

## 12. Changes against v5 (review round 5)

| v5 | v6 | Source |
|---|---|---|
| 0x71-complete bitmask cleared at `FUN_00510230` | never-cleared `rs_last71[emp]` = turn from body +0, recorded by a hook at 0x510278 for every 0x71 in every phase (the stock clear would lose a fast peer's 0x71); sender/empire checked against the player table | Fable, Astra |
| "the table cannot tell who has sent" | it can for stored 0x71 (per sender, turn at +0); only idle compares are not stored | Fable |
| 0x71-complete = "everybody in the input phase" | 0x71 proves simulation progress (all pumping steps precede the send), not quiescence; FREEZE installs gates, the load waits for each loop top | Astra, Fable |
| membership from the host's mask | fixed at FREEZE from the mask and connected DirectPlay ids; QUIET/LOADED carry each machine's mask; disagreement → ABORT; eliminated humans still send 0x71 | Astra, Fable |
| requester timeout 60 s | same minutes as the host's 0x71-complete wait plus a margin | Astra |
| fence armed in phase 4 | lifecycle: armed by an accepted FREEZE per epoch and sender, checked before any reordering queue, parked entries purged, active after RELEASE, reset on new game/lobby, no inheritance by AI takeover | Astra, Fable |
| sender identity of the fence implicit | open: receive-record idFrom (to be found in the spike) or per-type body decoder | Fable |
| no client failure message | 0x93 FAIL → host ABORT; LOADED recorded in every phase ≥ 2; own LOADED marked locally | Fable, Astra |
| force `[0x5a28d4] = 1` during the apply | leave it to the activation handler; scoped override of the nested pump at 0x4024d8 while the apply flag is set | Astra (Fable proposed a re-assert variant; rejected because it can swallow a real activation change) |
| `[0x5a2990] = 0` before `FUN_0050da70` only | also before `FUN_0050d070` (it has a host branch) | Fable |
| timer during the apply not covered | timer END TURN blocked while the apply flag is set (dialog pump runs the timer at depth 0) | Fable |
| CRC helper contracts partly stated | verified contracts (ESI dest + reload, EAX/EDX/EBX pointers, AX results, dedicated RNG buffer) | Astra, Fable |
| success flag "around 0x4389c0" | 0x4389c0 `e8 fb 3f 0e 00`; tail flag means "ran to the end", SNAPINFO check is the guard; 0x4387fb reproduces cmp + branch | Astra, Fable |
| TICK through the Fix B cave | needs its own window-message route before the network-id lookup at 0x50a704 | Astra |
| "0x458238 every turn start" | post-turn | Fable |
| spike table without exact bytes / helpers | exact original bytes for every site, 0x4024d8 override, file length + CRC32 logged by the trigger, idle preconditions | Astra, Fable |

## 13. Changes against v6 (review round 6)

| v6 | v7 | Source |
|---|---|---|
| sender identity of the fence open | settled: wParam = wire header +0x20 = sender's player id `[0x5fd8c4]`, matched by `FUN_00510600` against player-table +0x28, empire +0x2c; esi at 0x50a709, ebx at 0x510278; DirectPlay idFrom is discarded; no body decoder | Fable, Astra (both verified) |
| file checked against SNAPINFO inside the apply | checked against the **raw buffer at 0x50dd76**, before `FUN_0050dd90` writes, frees, parses and rewrites the archive; failure frees once and exits via 0x50dd80 | Astra (P1) |
| mismatch continues at 0x51000b only | gate per compare iteration at 0x510002 → epilogue 0x51002d while a transaction is active (0x51000b goes on to the next entry) | Astra (P1) |
| 0x510278 hook details | exact bytes, stack layout (body esp+0x400, empire esp+0x524, ebx = wParam), mapping via `FUN_005105d0`, resume at 0x51027f, ledger initialised per session | Fable, Astra |
| scoped pump override "one pump decision" | `3b 35 d4 28 5a 00` + `75 32`; override jumps to the stock idle exit 0x402512; outer loop and combat pump need nothing | Fable, Astra |
| TICK hook site open, "unknown ids fall through" | private `WM_APP + 0x92` intercepted in the window proc at 0x401507 (other ids never reach the dispatcher); posted from rxwait and the receive drain loop; Fable's 0x400/magic-lParam variant at 0x50a6ef documented as alternative | Astra, Fable |
| "eliminated humans always send 0x71" | not established; the host waits only for eligible members (in the mask, not dead in `[0x5a2b50]`, in the player table) and aborts on unclassifiable states | Astra |
| transitions implicit | host marks its own QUIET and LOADED, enters phase 3 before the transfer; apply guard before any dialog work; failure cleans up and sends FAIL, never LOADED; only success enters phase 4; QUIET/LOADED carry the mask | Astra |
| send counter not mentioned | `[0x5a075c]` is outside the saved block: (sender, counter) stay unique across a resync | Fable |
| spike acceptance "search the receive record" | log wParam of every 0x400 against the player table | Fable |

## 14. Changes against v7 (review round 7)

| v7 | v8 | Source |
|---|---|---|
| sections accumulated patches from six rounds; history mixed with the design | consistent rewrite of sections 1–8; history moved to this non-normative appendix; "loop-top step" vs "TICK" separated | Fable, Astra |
| phase 1 blocks turn start → a host still waiting for a late 0x68 can never finish turn T | REQ carries the target turn T; in phase 1 machines may finish turns up to T, not beyond; own completion recorded at the compare-loop gate (own71) | Astra (P1) |
| apply cleanup "on every exit" led into recompute + LOADED; dialog possibly created twice | common cleanup vs. success-only recompute/LOADED; failure sends FAIL, never LOADED; pending ABORT has priority; dialog created only if `[0x597508] == 0`; raw-buffer failure closes the dialog | Astra (P1), Fable |
| three membership definitions | one participant set P (human, not in `[0x5a2b50]`, player-table entry) fixed at FREEZE, carried in FREEZE and echoed in QUIET/LOADED; the stock mute filter cannot drop control traffic between members of P | Astra (P1) |
| NACK with only an epoch, deadlines "several minutes", client "ABORT" | REQ/NACK carry requester id + seq; concrete deadline table with start events; client failure = FAIL + local stock error; host applies RELEASE/ABORT locally; stock error replicated from the loop-top step | Astra (P1), Fable |
| queue model unspecified / contradictory | (wParam, lParam) pairs like the Fix B park, re-dispatched through `FUN_0050a6e0` with `rs_pass` so the stock receiver runs with the 0x50dd76/0x50dd7b hooks; 0x73 dropped during a transaction; 0x72 before SNAPINFO → FAIL | Fable |
| raw-buffer failure "frees exactly once" | `FUN_00492e60(eax = buffer)`, skip both calls, jump to 0x50dd80 | Fable, Astra (verified) |
| 0x510278 hook overwrote 13 bytes but resumed at 0x51027f | overwrite only the 7-byte cmp, resume at the intact `je` 0x51027f | Astra |
| TICK said to be handled "in the dispatcher" | TICK only in the window proc (0x401507); timeouts checked in the loop-top step and the TICK handler | Fable |
| "local input blocked until RELEASE" without a hook | removed with rationale (pre-load orders are dropped by the load; post-load orders are legitimate; END TURN stays blocked) | Fable |
| `FUN_0050d070` "host branch" | only selects the dialog text | Fable |
| teardown 0x43d0f2 unconditional; `[0x5a2b50]` "dead" as [V] | gated by `[0x5b1a88]`; "dead" is [I] (setter `FUN_0043cad0`), word in the saved block | Fable |
| rate limit checked on the detecting machine | host only | Fable |
| spike relied on §4.4 and the protocol; 35–40 bytes | self-contained spike: data layout, patch table with behaviour, two-step trigger with expected len/CRC written by the test tool, procedures for idle/waiting/BUSY, ≈ 56 overwritten bytes | Astra (P2), Fable |
| risk 8 arithmetic | ≈ 1–1.5 KB with data → new PE section | Fable, Astra |
