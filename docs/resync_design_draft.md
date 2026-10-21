# DRAFT v10: self-healing multiplayer ("resync instead of synchronization error")

Status: design draft after eight review rounds (Claude Fable, Codex gpt-6-astra); the spike of section 7 is
implemented in a test build and run (results and findings in §7.1); the protocol is not implemented. v10 adds the
spike's findings to the normative sections (section 16). Sections 1–8 are normative; the appendix (sections
9–16) is non-normative history.
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
  the timer (0x50dd14), sets session-descriptor flags (0x50dab0 → `SetSessionDesc` 0x54c989, which can fail;
  the result is recorded but ignored by the caller — consequence on clients [I]), `[0x5a2afc] = 0`. Host
  branch (0x50dae4, `[0x5a2990] == 1`) re-broadcasts; client branch requires the transfer dialog `[0x597508]`
  (`FUN_0050d010` asserts while it is missing, closes it and pumps twice). `FUN_0050d070` creates that dialog
  (its `[0x5a2990]` test only selects the dialog text, 0x50d07c..0x50d0b7).
- **Mask input** [V]: `edx = [0x5a2994]` at 0x50da88, tested at 0x50dcc0. 0 → local pre-load mask
  `[0x5a2b28]`; ≠ 0 → load first (0x50dce7), then mask `= [0x5a2998]` from the file (0x50dcf8). `[0x5a2998]`
  is offset 0xc0 of the saved block. `[0x5a2994]` is also read post-turn (0x458238), in the dispatcher (0x50aa74)
  and by lobby code. A lobby resume sets it while the saved game is distributed; in the running resumed game it
  was 0 again (spike §7.1, finding C; cleared at 0x50fa15 [I]). The resume path additionally skips `FUN_0043a0a0`
  (0x50dbb6..0x50dbc9 → `FUN_0044d300`, which can restart production).
- **Teardown on load** [V]: with `[0x5a2920] == 1`, `FUN_004387f0` calls `FUN_0043d0d0` (0x4388f3), which in
  multiplayer calls `FUN_0050d670` (0x43d0f2, only when `[0x5b1a88] != 0`: lobby score messages) and
  `FUN_00519b80` (0x43d0f7 → `FUN_0054cf90`: DestroyPlayer / Close / Release, `[0x5fd97c] = 0`). No other call
  in the load is known to close the transport — the call-site audit covered the two named calls, the universal
  negative is [I]; transport survival without these two calls is a runtime question.
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
  the main thread; in-order delivery per sender pair is a DirectPlay property (observed in the spike, §7.1).
- **Production** [V]: progress accumulates on every machine without an owner check (0x4624af); only the re-arm
  of the next item is owner-dependent (0x4616e4). The production records at system +0x80..+0xa7 (current and
  last) have an owner form and a non-owner form between turns (mode 1 / mode 2 kill difference, outside every
  CRC; spike finding E): a file carries its writer's forms, and after a load every machine holds the host's.

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
requirements use P and nothing else.

**Control traffic and the mute filter** (round 8, Astra): `FUN_00510600` runs at 0x50a6ef, before any of our
dispatch code, and drops a message when the **receiver's local** `[0x5a2b50]` marks the receiver's own empire or
the sender's — after a divergence a member's local mask can disagree with the host's P, so a FREEZE or ABORT
could be discarded before P is even checked. Therefore resync controls are decoded **before** the filter: a cave
at 0x50a6ef (`e8 0c 5f 00 00`) performs, for message 0x400, the stock type lookup once (the call otherwise made at
0x50a704) and keeps its result; types 0x8a..0x93 go to the resync handler without `FUN_00510600`, authorised by
sender id (player table) and, once frozen, membership in P; every other type runs `FUN_00510600` as before and
continues behind 0x50a704 with the cached lookup result, so the lookup still runs exactly once. The exact
continuation layout of 0x50a6f4..0x50a709 is verified in the spike [I].

### 3.4 Target turn and the host's decision

Each machine records `own71 = [0x5a2918]` at the compare-loop gate 0x510002 (first iteration; it runs after the
own 0x71 send at 0x50ffec). REQ carries T = the requester's own71. The host keeps `rs_last71[emp]` (§4.1).

Host, on REQ (or own mismatch with T = own71):
- T incompatible with the host's own turn (the host's `[0x5a2918]` is neither T − 1 nor T — lockstep allows at
  most one turn of difference, so anything else is impossible or stale) → NACK(requester id, seq);
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

Deadlines belong to phases: armed by the named event, **disarmed when the owning phase is left** (and all of a
machine's resync deadlines on NACK, RELEASE or terminal completion), checked in the loop-top step and in the TICK
handler, never extended by duplicates. Expiry only records terminal work; the pump-progress rule (§4.3) makes
sure that work runs.

| Deadline | Who | Armed at | Disarmed at | Length |
|---|---|---|---|---|
| D_req | requester | REQ sent | FREEZE or NACK | 330 s (D_complete + 30 s) |
| D_complete | host | phase 1 entered | FREEZE sent | 300 s |
| D_quiet | host | FREEZE sent | all QUIET received | 60 s |
| D_loaded | host | SNAPINFO sent | all LOADED received | 300 s |
| D_member | every member of P (host included) | FREEZE received/sent | RELEASE | 660 s (covers D_quiet + D_loaded + transfer) |
| D_abort | a machine that sent FAIL | FAIL sent | ABORT received | 30 s |

**Terminal handling** (round 8, Astra): first send FAIL (client) or ABORT (host; applied locally too), then a
dedicated **terminal helper** runs from the loop-top step (or the TICK handler when the loop top is not reached):
it shows the stock "synchronization error" message with its own valid arguments (the string id 0x4bd through
`FUN_0048b2e0` and the message box `FUN_005004a4`, as at 0x5100c9..0x5100e4) and then enters the stock fatal route
(`FUN_005081b0` → 0x402880 / 0x402920, which writes Crash.log and exits, as after 0x510190). It does not reuse the
frame-dependent checksum diagnostic code of `FUN_0050ffe0`. ABORT is terminal: no new transaction in that game. A
pending ABORT always has priority over LOADED.

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

- 0x8a..0x93: decoded before the mute filter (§3.3) and handled at any depth (state changes only).
- 0x89, 0x72 during a transaction (or the spike): **queued as (wParam, lParam) pairs**, exactly like the Fix B
  park; the receive record stays in the pool (records survive the type lookup and parking until consumption,
  0x54d7a2, 0x566c30, 0x54dd84 [V]). Every queued record has exactly one owner, the queue; the queue is
  bounded (4 entries) and an overflow is a FAIL. The Fix B flush never reposts these entries. 0x73 during a
  transaction: its record is consumed and dropped. 0x72 without a SNAPINFO of the current epoch → FAIL.
- At the loop-top step, one entry per iteration is re-dispatched through `FUN_0050a6e0(eax = 0x400,
  edx = wParam, ebx = lParam)` with a **one-shot pass token**: the cave compares the arriving (wParam, lParam)
  with the token, **clears the token before** calling the stock handler and lets only that notification through;
  a notification that arrives in a pump inside the stock handler follows the normal queue rules (no nested apply).
  0x89 → `FUN_0050cfd0` creates the dialog; its branch does not consume the record (0x50a897..0x50a8a8 [V]), so
  the loop-top step retires that record afterwards through the stock record release (exactly once). 0x72 →
  `FUN_0050dd30` with the hooks of §4.4, which consumes its record.

### 4.3 Loop-top step and TICK

- **Loop-top step** (hook 0x402201, five pushes replayed, all registers preserved): checks deadlines, performs
  the host's steps (§4.5), re-dispatches one queued entry, sends LOADED after a successful apply.
- **TICK** = window message `WM_APP + 0x92`, intercepted in the window proc at 0x401507: checks deadlines with
  all registers preserved, returns eax = 0 through 0x401613; any other message replays the cmp and continues at
  0x40150d. Posted by a rate-limited helper (push 0, push 0, push WM_APP+0x92, push `[0x5a074c]`, call
  `[0x57462c]`) from the Fix D rxwait cave and from the receive drain loop (0x54d9e5, replaying
  `bb 01 00 00 00`), only while `rs_phase != 0`.
- **Pump override / pump-progress rule** (round 8, Astra): the nested pump waits again when the window is
  inactive and its queue is empty, and several resync paths pump — the 0x89 handler (0x50cff9), the dialog close
  (0x50d04a..0x50d05a), the turn start of a phase-1 machine below T (0x45820b) — so a queued 0x89, a rejection
  cleanup or a host finishing turn T could stall with an inactive window. The override at 0x4024d8 therefore
  jumps to 0x402512 (stock idle exit) whenever **`rs_guard`** is set, else replays the cmp and continues at
  0x4024de. `rs_guard` is set while `rs_phase != 0` (covers phase-1 turn completion, re-dispatch, apply,
  cleanup and terminal work) and during the spike; it is never set outside a transaction, so normal play is
  unchanged. `[0x5a28d4]` is never written. Every path that must report sends FAIL **before** any cleanup that
  pumps.

### 4.4 Apply (every machine; the host calls it directly, §4.5)

Raw-buffer check at 0x50dd76 (client only): compare edx (length) and the CRC32 of [eax..eax+edx) with
SNAPINFO. Mismatch → `FUN_00492e60(eax = buffer)`, skip both calls, jump to 0x50dd80; send FAIL; then (pumps
allowed, `rs_guard` set) close the transfer dialog if it exists (the stock close of `FUN_0050d010`); terminal per
§3.6. Match → run the original
call to `FUN_0050dd90`; at 0x50dd7b the call goes to the **apply helper**:

1. acquire `rs_apply` (re-entry guard; resync handlers only set flags while it is held); save `[0x5a2994]`;
2. ensure the transfer dialog exists exactly once (`FUN_0050d070` only if `[0x597508] == 0`);
3. set `[0x5a2990] = 0` and `[0x5a2994] = 1`; reset the file-open and tail flags;
4. call `FUN_0050da70` — inside it: `FUN_0043d0d0` skips 0x43d0f2 and 0x43d0f7 while `rs_apply` is held (call
   hooks); the file-open flag at 0x4387fb (reproduce `cmp eax,1` / `je 0x438805`, record eax == 1); the tail flag
   at 0x4389c0 (call `FUN_0051c9c0`, set the flag, continue at 0x4389c5); `FUN_0050d010` closes the dialog; the
   **incident guard** at 0x44ce41 (spike finding D): the load resets the incident list (`FUN_0044b8e0` from
   0x43897b: `[0x58fd70] = [0x58fd74] = 0`) while an open incident popup survives, and the screen switch of the
   apply (0x50dc8c → `FUN_004b9180` → `FUN_005001b0` → `FUN_0044ce40`) advances the NULL list
   (`FUN_0051b7a0` → access violation at 0x51b7a1); with an empty list the advance ends the incident sequence
   the stock way (0x44ce6b); **production restart** (spike finding E): at the end of the resume branch
   (0x50dd00, after the load and the restore of the local empire and the mask) `FUN_0043a0a0(local empire)` when
   the local empire's bit is in `[0x597504]` — the call every machine of a stock lobby resume makes at 0x50dbc9,
   which the forced resume branch skips; the info box guard at 0x4e990e (the assert's ignore path 0x4e992c)
   stays as a safety net;
5. **common cleanup, every exit**: restore `[0x5a2994]`; `[0x5a2990] = [0x5fd978]`; release the receive slots
   the Fix Y way; `FUN_00510230`; enable the turn UI (`FUN_004b9110`) when the load has reset the turn state
   (`[0x5a291c] == 0`) and it is still disabled (`[0x594d20]` or `[0x593250]`, set by `FUN_004b90a0` at END TURN;
   spike finding A); release `rs_apply`;
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
- Production: progress is replicated; each owner re-derives its own systems' production records from the loaded
  state like after a stock lobby resume (`FUN_0043a0a0`, spike finding E); open is only the item an owner
  re-armed in the last turn.
- A wait dialog during the transfer.

## 6. Risks (ranked)

1. Transport survival without the two teardown calls — passed in the spike (§7.1).
2. Per-sender in-order delivery (fence) — observed in the spike (§7.1), also across a multi-fragment 0x72.
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
No protocol; the test tool drives a small state machine through poke-able fields.

**Prerequisite**: a place for the code and data. The existing patcher only uses the fixed caves (code 0x516e60,
data 0x6896e0); the spike runs in a test build whose shim section (`build_test.py`, `.tstshim`) is enlarged for
the spike code and data. New-section support for the release patcher (all 143 variants) is a separate
prerequisite of the implementation, not of the spike.

**Data**: `sp_state` (0 IDLE, 1 PREPARE, 2 ARMED, 3 SEND, 4 DRAIN, 5 DONE), `sp_len`, `sp_crc` (expected values;
the host writes its own, the tool copies them into every client), `rs_guard`, `rs_apply`, `sp_token`
(one-shot pass: wParam, lParam), `sp_saved_2994`, `sp_queue[4]` (wParam, lParam), `sp_flag_open`,
`sp_flag_tail`, `sp_log[]` (CRC words + RNG + mask per apply, failures), RNG buffer 0x120 bytes.

**States** (all machines; the tool writes `sp_state`)
1. PREPARE (host only): at its loop top the host writes `[0x5a2998] = [0x5a2b28]`, saves `auto.sav`, computes
   length/CRC32 into `sp_len`/`sp_crc`, logs and **stops** (`sp_state` stays 1).
2. ARMED (all machines): the tool copies `sp_len`/`sp_crc` from the host into every client and sets `sp_state = 2`
   everywhere; from now on `rs_guard` is set and 0x89/0x72 are queued, compares are skipped (0x510002) and timer
   END TURN is deferred (Fix K cave).
3. SEND (host): the tool sets 3 on the host; at its loop top the host sends 0x89 (`mov eax,0x89; call 0x5199c0`)
   and `FUN_0050de40(eax = -0xd, edx = 0)`, applies its own file directly (§4.4 helper) and sets 4. The tool posts a
   wake-up to an inactive host before setting 3.
4. DRAIN (clients, entered with the first queued entry): the loop-top step re-dispatches one queued entry per
   iteration with the one-shot token (§4.2), retires the 0x89 record, applies the 0x72 through the §4.4 hooks;
   gates stay active until the queue is empty and the apply finished (or failed); then 5.
5. DONE: log, clear `rs_guard`, reset the flags, the token and the queue; `sp_state = 0`. Every failure path
   (raw-buffer mismatch, missing flag, queue overflow) logs and ends in DONE with the same reset.

**Patch sites**

| Site | Original bytes | Spike behaviour |
|---|---|---|
| 0x402201 | `56 56 56 56 53` | loop-top step: PREPARE / SEND on the host, DRAIN re-dispatch, DONE reset |
| 0x50a6ef | `e8 0c 5f 00 00` | not needed in the spike (no control messages); reserved for §3.3 |
| 0x50a709 | `66 89 04 24 8b 04 24` | queue 0x89/0x72 while `sp_state` is 2..4; the one-shot token passes exactly the re-dispatched entry |
| 0x50dd76 | `e8 15 00 00 00` | raw-buffer check against `sp_len`/`sp_crc` (failure: free once, skip, 0x50dd80, log, close dialog) |
| 0x50dd7b | `e8 f0 fc ff ff` | apply helper (§4.4 steps 1–6, LOADED replaced by logging) |
| 0x43d0f2, 0x43d0f7 | `e8 79 05 0d 00`, `e8 84 ca 0d 00` | skip while `rs_apply` |
| 0x4387fb | `83 f8 01 74 05` | file-open flag |
| 0x4389c0 | `e8 fb 3f 0e 00` | tail flag |
| 0x4e990e | `bd 5c 1a 58 00` | info box guard (safety net, added after the live runs, finding E) |
| 0x50dd00 | `e9 c9 fe ff ff` | production restart `FUN_0043a0a0(local empire)` in the resume branch (finding E) |
| 0x4024d8 | `3b 35 d4 28 5a 00` | idle exit while `rs_guard` |
| 0x510002 | `83 bd c0 cf 5c 00 ff` | skip compares while `sp_state` is 2..4 |
| 0x4b9f6a (existing Fix K cave) | — | defer timer END TURN while `sp_state` is 2..4 |
| 0x44ce41 | `a1 74 fd 58 00` + `e8 55 e9 0c 00` | incident guard (added after the live run, finding D) |

Overwritten bytes ≈ 56 (+ the Fix K condition); helper code ≈ 500–700 bytes; data ≈ 0x120 + 80 bytes. The CRC32
is our own small bitwise routine.

**Procedures** (each starts from IDLE on all five)
1. Idle: poke a divergence on client C (e.g. system +0x2dc); PREPARE, ARMED, SEND.
2. Waiting: one client has ended its turn (−1) before ARMED.
3. BUSY: SEND while a client processes a turn (its 0x72 is parked by Fix B, reposted, then queued).
4. System screen open on a client; focus changes during the apply; inactive windows on host and a client.
5. Two transfers in a row; a lobby-resumed game (`[0x5a2994] = 1` before and after).
6. Wrong `sp_crc` on one client (rejected, buffer freed once, dialog closed, no load); missing file on the host.

**Acceptance**: DirectPlay ids and the session unchanged; `[0x597504]` equals the loaded `[0x5a2b28]` before
`FUN_00510ba0`; CRC words and RNG equal on all five after every apply; real orders, queues and 10 turns in sync
afterwards; production fields of host-owned, client-owned and third-party systems compared; wParam of every
received 0x400 logged against the player table; arrival order of numbered test messages from two senders with
artificial delay logged; queue empty and every record consumed exactly once (pool counters before/after).

### 7.1 Spike results (2026-10-17)

Implementation: `tools/spike_resync.py` (patch module, `build_test.py --fix --spike`), driver `tools/spike.py`,
runs under play `tools/spike_live.sh` (agents pause during a transfer, as END TURN would be gated). About 3.7 KB
code and 0x7a00 bytes data in the enlarged shim section, chained into the Fix B and Fix K caves. Test bed: five
instances on one computer, small spiral galaxy. Procedures 1, 2, 4, 5 and 6 were repeated with the final build.

| Procedure | Result |
|---|---|
| 1 idle, divergence poked on a client | passed: 0.3 s per transfer (48–98 KB save); the divergence is healed (full state compare 0 differences), then turns in sync |
| 2 a client waiting (BUSY −1) | passed after finding A |
| 3 a client BUSY (`--slowend`: after the last turn phase) | queue and apply passed (0x89 and 0x72 queued during the turn processing, applied afterwards); finding B |
| 4 system screen open; host and client inactive; focus changes | passed |
| 5 two transfers in a row; lobby-resumed game | passed; finding C |
| 6 wrong CRC32 on a client; host file missing | passed: rejected, buffer freed once, dialog closed, no load, a second transfer heals the client; the host fails before sending and the clients are reset from ARMED |
| order evidence | 2 × 100 numbered messages from two senders, also with 40 ms per packet: in order per sender on every receiver (interleaved up to 17 times); the host's multi-fragment 0x72 is dispatched before the messages it sent afterwards |
| under play (five agents: builds, buys, labor, fleets, diplomacy, combat) | findings D, E, F; snapshot variant (run 8): four transfers, 26 turns, 14 turns in sync after the last transfer; final build (runs 9 and 10, one game): six transfers at turns 4, 7, 9, 12, 15 and 18, 29 turns, 11 turns in sync after the last; no heartbeat mismatch, no crash (the agents skip the diplomacy screen in a transfer turn, finding F) |

Acceptance after every passed apply: DirectPlay ids, player table, session strings and transport object
unchanged; `[0x597504]` equals the loaded `[0x5a2b28]`; CRC words and normalised RNG equal on all five; full
state compare (systems including the production fields, empires) without differences apart from each owner's
production records of its own systems (finding E, as after a stock resume); queue empty, token clear; every
0x89/0x72 queued once and re-dispatched once, every 0x89 record retired once; receive list length unchanged.
With 40 ms per packet on the host a transfer takes 7–10 s.

Findings:
- **A turn UI**: END TURN disables the turn UI (`FUN_004b90a0`, flags `[0x594d20]`/`[0x593250]`) and only the end
  of the turn processing enables it again (`FUN_004b9110`); a machine that had ended the turn kept a dead END TURN
  button after the load. Fixed in the helper (§4.4 step 5).
- **B stale 0x71**: a machine still in its turn processing when the others apply sends its own 0x71 of that turn
  afterwards; every other machine compares it at once (idle, 0x510487) against the RNG after the load (the load
  re-initialises it) and shows the stock synchronization error (0x51031f). Confirms the per-sender fence for 0x71
  (§3.5) and the phase-1 rule (FREEZE only after 0x71-complete), which the spike leaves out.
- **C resume flag**: `[0x5a2994]` was 0 in a running lobby-resumed game; the helper's save/restore also keeps a
  forced 1 (§2 corrected).
- **D incident popup**: the load resets the incident list while an incident popup stays open; the apply's screen
  switch advances the NULL list (access violation 0x51b7a1, two clients died). Guard at 0x44ce41 (§4.4).
- **E owner production records**: system +0x80..+0xa7 differs between owner and non-owners between turns. After
  the load (host's save made at PREPARE) an owner held the host's non-owner form of its own systems and died in
  its own UI: galaxy-map info box (infobox.c line 1161, 0x4e9923, three clients) and system screen (redifice.c
  line 267, structure id 0x7fff). Four variants:
  1. keep each owner's current records across the load — desynchronised: two turns later the owner had one
     building more (crcSolarBld, system Manu), its record held the effect of current-turn input that the load
     drops everywhere else;
  2. take the host's forms and guard the info box — the system screen asserted next;
  3. turn-start configuration: the host transfers its turn-start save, every machine takes a snapshot of its
     own systems' records at its turn start and the load's tail hook writes it back (`--spike-snapshot`). Run 8:
     four transfers under play, 26 turns in sync, no UI assert;
  4. **stock restart** (kept, the default): a stock lobby resume runs the non-resume branch of `FUN_0050da70` on
     every machine (breakpoints at 0x50dae4, 0x50dcc4 and 0x50dbc9 during `resume5.sh`) and calls
     `FUN_0043a0a0(local empire)` at 0x50dbc9, which derives each owner's records from the loaded state; the
     spike's forced resume branch skipped that call. The same call at the end of the resume branch (0x50dd00)
     needs no snapshot and no turn-start save. Runs 9 and 10 (one game): six transfers under play (turns 4, 7, 9,
     12, 15, 18), 29 turns, in sync, no UI assert, the info box guard never needed.
- **F diplomacy items**: after a transfer, a click in the diplomacy screen (F5) copied 0x48c bytes from a freed
  object (`FUN_004c81f0` from `FUN_004c2f40`, access violation 0x4c820b): the screen's items point to order
  bodies (`FUN_004c5340` builds them from the current turn's orders), and the load replaces the order list. Not
  fixed in the spike (the agents skip the diplomacy screen in a transfer turn); open in §8.
- **G turn phases**: the turn processing is synchronous across machines (phase messages 0x6a..0x70); a client
  can only lag behind the host after the last phase (0x4586d6), which is where `--slowend` delays.
- Right after an apply the CRC word 0x597614 (`FUN_00466360`, list `[0x5b5390]`) is 0 on every machine; the
  next turn computes it normally.

### 7.2 Automatic start (2026-10-18)

The spike no longer needs the driver: a heartbeat mismatch starts the transfer.

- **Detection**: the two branches into the stock "synchronization error" box (0x5100c9 in the turn-end compare
  loop, 0x51031f in the compare of a late 0x71; string 0x4bd is used nowhere else) jump to a shared check. In
  multiplayer with `sp_state == 0`, outside the quiet window and without `sp_fallback`, the box is skipped,
  `sp_detect = 1`, and the loop continues at 0x51000b / 0x5103f8. While a transfer runs, mismatches are ignored.
- **Host** (transport role `[0x5fd978] == 1`; `[0x5a2990]` is 1 on every machine of a lobby-resumed game, a first
  live run with it started five transfers at once): at the loop top, with `sp_detect` set and not calculating, it
  runs PREPARE, broadcasts **ARM** (message 0x8a, 12 bytes: epoch, length, CRC32 of the save), sets itself ARMED
  and goes to SEND on the next iteration. One retry if PREPARE fails, then `sp_fallback`.
- **Clients**: ARM is decoded at the dispatcher head 0x50a6ef, before the mute filter, at any depth; it sets
  `sp_len`/`sp_crc`, `rs_guard` and ARMED (newer epoch only, not on the host); the existing queue/DRAIN/apply path
  loads the save that follows from the same sender. A client that detected a mismatch and gets no ARM within
  120 s sets `sp_fallback` (the next mismatch shows the stock box); a client ARMED for 300 s without data resets.
- **Quiet window** (finding B): after DONE the mismatches of the loaded turn are ignored (`sp_quiet` = that turn,
  cleared when the turn changes).
- **Finding F fixed**: after a successful apply every machine closes an open proposal panel (`FUN_004c8290`) and
  runs the stock per-turn UI refresh of the turn end (`FUN_004b8c20`: system screen, galaxy map including the
  task-force panel, diplomacy lists via `FUN_004c3e40`, turn-results window). The diplomacy items no longer point
  to freed order bodies: a proposal sent before a transfer disappears from the list (the host's save does not
  have it), where the old build kept showing it from freed memory.
- **Agents** (`tools/player.py --spike-json`) hold their input while `sp_state` or `rs_guard` is set, and play
  diplomacy in transfer turns again (`--skip-dipl-after-resync` restores the old behaviour).

Results (test build `build_test.py --fix --spike`, five instances):
- `tools/spike.py auto --diverge C:5 --turns 3` (from `saves/five_1201_t103`): the mismatch is detected, the host
  starts one transfer, every client applies once, state equal to the host, three more turns in sync.
- `tools/spike_auto_live.sh` (agents with assault and diplomacy, 24 turns, a divergence on a random client every 4
  turns): 5 of 5 divergences healed by themselves, 34 to 57 s after the injection; the observer saw no heartbeat
  mismatch between them; no crash.

Still open: the per-sender fence and FREEZE/RELEASE of the full protocol (section 3); a host that has already
ended the next turn may not compare a slow client's late 0x71 (the clients then fall back after 120 s); the
release patcher needs a new PE section for this code (about 5 KB).

### 7.3 Release (Fix RY, v2.1.0)

The automatic path of 7.2 is part of the release patch (`tools/resync.py`, applied by `netfix.apply`):

- **Section**: `netfix.apply` appends `.mpfix` (code 0x1400, data 0x400 bytes; read/write/execute). In all 143
  `trek.exe` variants of the installer the sections end at RVA 0x29d000 + 0x1000, so the new section lands at
  0x69e000 everywhere and the code needs no relocation. `release/botf_mpfix.py` carries the section (zlib, base64),
  checks the layout (end of the sections, file size, free header slot) and appends it; the community `.patch`
  file cannot add a section and is generated without RY.
- **Release vs. test build**: the release has no log ring, no received-message rings, no test messages and no
  snapshot variant (about 4 KB of code less); `build_test.py --fix --spike` builds the instrumented variant. The
  data fields keep their names, so `tools/spike.py status/auto` works with both (`<exe>.json`).
- **Handshake (new)**: a client answers ARM with **ACK** (0x8b, 4 bytes: epoch). The host sends 0x89 and the
  file only when every remaining human player answered (player mask without the local empire and without players
  marked gone by Fix LV). Without all answers after 30 s it broadcasts **CANCEL** (0x8c: epoch); every machine ends
  the transfer without a load and lets its next mismatch show the stock error (`sp_fallback`). This keeps a game
  with a player who has an older patch (or none) where it was: such a player ignores 0x8a..0x8c (ids above 0x89
  are not handled by the stock dispatcher), shows the stock error himself, and the others do not load a game he
  never gets.
- **Transfer identity**: a client accepts an ARM unless it carries the epoch *and* the sender of the last one it
  took. After a host migration the new host counts on from its own epoch; the sender alone already makes its ARM
  new for the clients.
- **Session boundary**: outside a multiplayer game (`[0x5a2924]` or `[0x5a2920]` is 0: menus, lobby) and with no
  transfer running, the per-game state (fallback, detection, epoch, sender, quiet window) is cleared, so a later
  game in the same process starts fresh (found by the final review).
- **Aborts**: a transfer that has received nothing yet (PREPARE, or ARMED with an empty queue) ends without a load
  as soon as the multiplayer game is gone on that machine (the teardown clears the player mask, which the host's
  ACK wait would otherwise take for "everybody answered"; found by the second review round). A client ARMED by an
  ARM ends without a load when that ARM's sender is no longer in the player table (the host left; the new host
  starts its own transfer at the next mismatch), otherwise after 300 s.

Tests with the release build (`build_test.py --fix`), all in `tools/ryregress.sh`:
- `tools/spike.py auto --diverge C:5 --turns 3` from `saves/five_1201_t103`: detected, one transfer, every client
  applied once, state equal to the host, three more turns in sync.
- `tools/rymixed.py` (E runs `--noresync`, a divergence on C): E shows the stock error at once; the host gets ACK
  from B, C and D (mask 0x0e, missing 0x10), sends CANCEL after 30 s; A..D end without a load, `sp_fallback` set.
- `tools/ryabort.py session`: the host's in-game flag cleared during its ACK wait: abort (F_SESSION), no CANCEL,
  no load anywhere, session state cleared. `tools/ryabort.py kill`: the host killed during its ACK wait: every
  client leaves ARMED without a load once the host is gone from the player table (77 s, the DirectPlay leave time).
- `tools/rymigrate.py`: one transfer with A as host, A killed, DirectPlay makes D the host, a divergence on B: D
  transfers, every machine applied twice, two more turns in sync.
- `tools/porders.sh` (a leaver's orders reached only some machines): the mismatch of the next turn is repaired
  (ACK from B, C, D; E is marked gone), three turns in sync.
- Under play (`tools/spike_auto_live.sh`, agents with wars, diplomacy and fleets, small galaxy): five injected
  divergences, five repairs (39–51 s after the injection), no heartbeat mismatch seen by the observer.
- Late war game (`TACTICAL=1 tools/spike_auto_live.sh ... saves/war17d_t520`, manual tactical combat): every
  injected divergence repaired (65–102 s: a machine still in its turn calculation, for example in the intel blame
  dialog, loads after it has finished). A first run had stalled because the test agents held all input during a
  transfer, also the blame dialog of the turn calculation; they now answer it (`tools/player.py`).
- Patcher: all 143 variants patched by `botf_mpfix.py` are byte-identical to `netfix.apply`; an upgrade from
  v2.0.0 rebuilds from the backup; `--restore` gives back the original. The v2.0.0 patcher refuses a v2.1.0 file
  (unknown size) and leaves it unchanged. The release `trek.exe` (EN 800x600) starts into the main menu with the
  section mapped at 0x69e000.

## 8. Open questions

- The terminal helper (§3.6) and the reordered lookup at 0x50a6ef (§3.3) — verify after the spike, before the
  protocol is implemented.
- New PE section support in the patcher (all variants): done in v2.1.0 (7.3).
- Exact deadline values: the spike measured 0.3 s per transfer (48–82 KB save) on one computer and 7–10 s with
  40 ms per packet on the host (`--latency 40`); D_loaded (300 s) and D_member (660 s) have ample margin.
- UI state that refers to objects the load frees or resets: findings A, D and F were found only under play.
  Finding F is fixed by the stock per-turn UI refresh after the apply (7.2); the audit of the per-turn caches found
  the galaxy map's task-force panel as a second stale pointer, covered by the same refresh.

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

## 15. Changes against v8 (review round 8, Astra)

| v8 | v9 | Source |
|---|---|---|
| global `rs_pass` while the stock handler runs | one-shot token cleared before the stock handler; nested notifications follow the queue rules (the 0x89 handler pumps) | Astra (rank 1) |
| record ownership implicit | the queue owns each record; bounded (4), overflow = FAIL; the 0x89 record (not consumed by its branch) retired once by the loop-top step | Astra (rank 1) |
| pump override only during the apply | `rs_guard` for the whole transaction: 0x89 dispatch, dialog close, phase-1 turn completion and terminal work cannot stall with an inactive window; FAIL is sent before any pumping cleanup | Astra (rank 2) |
| "the mute filter cannot drop control traffic between members of P" | false: the filter uses the receiver's local mask; controls are decoded before `FUN_00510600` by a cave at 0x50a6ef that does the type lookup once | Astra (rank 3) |
| stock error "replicated from 0x5100c9..0x5100e0" | that range only prepares arguments; dedicated terminal helper: message box with own arguments, then the stock fatal route (`FUN_005081b0` → 0x402880/0x402920) | Astra (rank 4) |
| deadlines with start events only; non-requesting clients unbounded | deadlines owned by phases, disarmed on exit, cancelled on NACK/RELEASE/terminal; D_member for every member from FREEZE to RELEASE | Astra (rank 5) |
| incompatible T left to time out | REQ with T not in {host turn, host turn + 1} → NACK | Astra |
| spike trigger saved, sent and applied in one step | staged states PREPARE / ARMED / SEND / DRAIN / DONE with reset on every exit; spike in the enlarged test shim section | Astra (rank 6) |
| `SetSessionDesc` "harmless" [V]; "no other call closes the transport" [V] | consequence [I]; universal negative [I] | Astra |

## 16. Changes against v9 (spike)

| v9 | v10 | Source |
|---|---|---|
| `[0x5a2994]` "stays 1 in a lobby-resumed game" | 0 in the running resumed game | spike, finding C |
| helper cleanup without UI | turn UI enabled again after the load | spike, finding A |
| load hooks: teardown, file-open flag, tail flag | plus incident guard at 0x44ce41, production restart `FUN_0043a0a0` at 0x50dd00, info box guard at 0x4e990e as a safety net | spike, findings D and E |
| production "replicated" | owner and non-owner forms of +0x80..+0xa7; each owner re-derives its own like after a stock lobby resume | spike, finding E |
| transport survival, per-sender order: risks for the spike | observed in the spike | spike |
| deadline values open | 0.3 s per transfer on one computer, 7–10 s with 40 ms per packet | spike |
