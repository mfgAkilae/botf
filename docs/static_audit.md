# Late-game MP desync (trek_en_orig.exe): ranked root causes

## Verdict

- **No single cause is proven at runtime.** All ranked causes below come from static analysis only.
- **The Fix E path cannot cause the dominant report signature** (vanilla, same seed, only crcSolarBld differs). That path is minor-range kill requests whose seqno drifts per machine. Its seqnos lie in 0xd5555552+, so it can never kill an order of a system owned by a major empire (owner < 5). Major empires have separate seqno counters, and the order search filters by emp. Its effect is crcTF/TF divergence. Fix E is still valid hardening.
- **The best explanation is one root:** the production record at sys+0x80..0x93 is local to each machine.
  - The owner writes it from the UI and from owner-only "re-arm" code (code that creates the next production order).
  - The other machines (receivers) zero it, through the mode-2 kill reset and through FUN_00444500.
  - Processing re-derives it from the order only inside the production loop (FUN_00460db0).
  - A static scan of all processing code that runs before the production snapshot at 0x462471 found exactly two readers of this record: FUN_0043f66c (0x43fa14) and FUN_00445a10 (0x445a28 and 0x445a78). FUN_004432d0 also reads it, but only for the UI.
  - Word +0x86 is the one field that survives both the mode-2 reset and the production rewrite.
- **Three confirmed consumers of that root produce exactly the reported signature** (only crcSolarBld differs, seed equal, late game): R1, R2 and R3 below.
- **Two new mechanisms came out of this synthesis.** Both are static only and still need a verifier pass:
  - R2 arm B: an owner-only replacement order is created before the production snapshot.
  - R4: FUN_0044a360 re-creates production orders on every machine with each machine's own seqno.

## Corrections to the known facts and memory notes

1. **Heartbeat timing.** The heartbeat is computed at 0x458233, after FUN_00458260 returns. That function has already done the turn increment at 0x45856b, the local GUI recompute at 0x458696 and busy=0 at 0x4586d8. So the CRCs describe the state after the whole turn-N processing, labelled N+1. The memory note "right after busy=1 at turn start" is wrong. Confirmed by 3 verifiers.
   - FUN_00510230 at 0x458224 wipes the heartbeat slots, so a heartbeat stored while busy=-1 is never compared.
   - Line 118 means the heartbeat was compared on arrival while idle.
   - Line 182 means it was compared after this machine's own processing; the remote machine finished first.
   - Lines 94 and 159 are turn-number asserts.
2. **"Seed equal, only crcSolarBld differs"** means: the hashed idx-1 block sys+0x298..0x2ef of a system with owner < 5 diverged during that processing, with no change in the number of main RNG draws. The input that caused it can be older and unhashed: sys+0x80..0xa7, credits, the order list.
3. **Mistake in the "idwrap" safe note.** It says "no machine creates non-search orders with a remote human's emp". FUN_0044a360 does exactly that (see R4).
4. **Evidence that R2 is an oversight.** FUN_00440bc0 already defers MP production re-arm for conquered systems through FUN_004618c0 (0x441072..0x441089). FUN_00461640 processes that list after the production snapshot, at 0x46252f. So the developers knew that owner-only order creation before the snapshot is a hazard. FUN_00445a10 and FUN_00445840 lack this deferral.

## Ranked candidates

### Tier 1: matches the dominant report signature

**R1. Morale "production boost" reads the asymmetric production kind (FUN_0043f66c)**
- **Status:** confirmed by code (2 confirmed, 1 plausible). Frequency in real games is unverified.
- **Mechanism:**
  1. After a build completes on a human system (sys+4==2), FUN_00444500 zeroes sys+0x80.. on every machine. Only the owner then re-arms the next item (FUN_0046138c). The UI path is the same: the owner writes the record, receivers get the mode-2 reset. Result for the next turn: owner kind 1/2/3, receivers kind 0.
  2. FUN_00461cd0 runs the morale pass at 0x461e30 (FUN_00461100 → FUN_0043f2c0 → FUN_0043f66c) before the production loop at 0x4624af.
  3. When the morale level is 2/3 and the cooldown sys+0x2f4 is 0, the game draws rand%100 at 0x43f697. This draw is identical on all machines.
  4. A roll of 41..min(50, morale−151) switches on [sys+0x80] (0x43fa14, table 0x43f650):
     - The owner sets +0x84 to the full cost (kind 1/3 at 0x43fa47, kind 2 at 0x43fb61).
     - Receivers take the default path 0x43fa4e and add stale stack data G, roughly morale − race base, about 60..100. G is the same on every receiver.
  5. FUN_00460940 / FUN_004603a0 then add industry. The owner completes the build; receivers complete only if G + industry ≥ cost.
  6. Structure and upgrade completion use no RNG (BFS check). The owner-only structure changes +0x2a8 and labor, so crcSolarBld fails at the end of that turn, or one turn later if no workers are assigned. Kind 3 (ships) would also change crcShip/crcTF.
- **Why late game:** it needs morale ≥ 192. That only comes from the cumulative empire morale modifier at empire+0xb4 (morale.bin events added by FUN_00439f90: battle wins, memberships; never reset). Morale decays by ceil(5%) toward the cap, so in practice it tops out around 195, which gives about 3–5% per attempt. It also needs a multi-turn build (upgrades, expensive late buildings). Early systems sit near the race base (≤127) and never reach this branch.
  - Rough estimate: 40 capped human systems, one attempt every 4–8 turns each, roughly one desync per 10–30 late turns.
  - The test bed never had morale ≥ 192.
- **Test:**
  1. Two instances, A is the owner. At a turn boundary, poke on both machines and for all of A's systems: word +0x2dc = 196 and +0x2f4 = 0. Re-poke +0x2f4 = 0 every turn. Identical pokes keep the CRC equal.
  2. Script A to change several systems to expensive multi-turn builds every turn.
  3. Trace 0x43fa14 (EAX = kind) and [ESP+0x348] on both machines.
  4. Expect a crcSolarBld-only mismatch within about 5–20 turns.
  5. Deterministic variant: breakpoint at 0x43f6b2 on both machines and set EDX = 45 for system S.
  6. Prevalence check, needed before trusting the rank: decode +0x2dc and empire+0xb4 from long saves (savlib.py). If no human system reaches ≥ 192 by turn 200 or later, demote R1.
- **Fix (Fix G):**
  - At 0x43fa0e, replace the 6-byte `LEA ECX,[EDX+0x80]` with `JMP cave` + NOP.
  - Cave: `CMP dword [0x5a2924],0` / `JZ L` / `CMP dword [EDX+4],2` / `JE 0x43f6e1` / `L: LEA ECX,[EDX+0x80]` / `JMP 0x43fa14`.
  - Effect: human-controlled systems in MP skip the boost and its event. The RNG draw (0x43f697) and the cooldown increment (0x43fa07) still happen, and no RNG is reachable from the skipped code.
  - Risk: a small gameplay loss in MP only. AI systems are unaffected, because their record is the same on all machines.

**R2. Shipyard loss: owner-only kill (arm A) and owner-only re-arm before the production snapshot (arm B)**
- **Arm A status:** confirmed by code (2 confirmed, 1 plausible).
  1. Any loss of a shipyard unit (category 0x12) goes FUN_00445840 → 0x4459b1 → FUN_00445a10.
  2. 0x445a28 checks `CMP [sys+0x80],3`. Only where that holds does it run a wildcard production kill (FUN_004638d0 pattern, mode 0, at 0x445a54).
  3. In the processing right after the owner started a new ship (queue advance through FUN_0046138c, or a UI pick in FUN_004f3330), the owner has 3 and receivers have 0.
  4. So the owner kills the ship order and the receivers keep it. FUN_00441460 at 0x461f66 then sets sys+0x2d4: 0 on the owner, 1 on receivers.
  5. Result: crcSolarBld-only at the end of the same processing, seed equal.
- **Arm B status:** new in this synthesis, static only.
  - The same path also runs in steady state, where all machines have 3. Every machine kills and memsets. Then only the owner (0x445aad) re-arms: FUN_0046138c from the queue head, or FUN_004616f0 + FUN_0044d830.
  - FUN_00445840 at 0x4459c7..0x4459dc does the same owner-only FUN_004616f0 when the queue is empty.
  - Both add an order (FUN_00457b9c at 0x46141b / 0x4617c2) before the production snapshot at 0x462471, since the triggers run earlier: combat 0x45840b, scrap 0x461d43, unrest 0x461e30.
  - The snapshot (FUN_00456cd0) includes the new order, and nothing in production checks the order's generation. So the owner gains one extra turn of progress on the replacement build; receivers get it through 0x68 next turn.
  - Result:
    - The owner completes one turn earlier: crcSolarBld-only, seed equal, at that completion.
    - If the replacement is cheap enough to finish in turn N, it exists only on the owner, because the order is killed locally and never sent.
    - If the replacement is trade goods, only credits drift (latent).
- **Triggers:** combat bombardment (FUN_00466cf0 0x4671a4 with a random building, 0x4678ab), scrap orders, and unrest/rebellion (FUN_0043fb90).
  - Sabotage and random events run after production. They do not open arm A and do not cause a head start.
  - The invasion at 0x4688e4 only removes structure id 5.
- **Why late game:** wars bombarding human core worlds, unrest in conquered systems, many shipyard systems with long queues. The test bed never destroyed or scrapped a shipyard.
- **Test (deterministic, uses scrap):**
  - **Arm A:** queue [cheap ship, ship, structure]. After the first ship completes, check +0x80 (A=3, B=0). A scraps one shipyard unit and presses TURN. Expect a mismatch at the end of processing, [S+0x2d4] A=0 / B=1, and B still holding the ship order.
  - **Arm B:** steady multi-turn ship, queue [ship, multi-turn structure Z]. Scrap and press TURN. Expect no immediate mismatch, but [S+0x84] A = industry and B = 0, and a mismatch when Z completes on A. With a cheap Z, Z exists on A only.
- **Fix (Fix H):**
  - **H1 (arm A):**
    - At 0x445a28, replace 9 bytes with `EB 13` (JMP 0x445a3d) + NOPs.
    - Move 0x445a49..0x445a5a (18 bytes) to a cave: `MOV EDX,EBX; MOV ECX,EAX; PUSH EBX; OR EBX,-1; CALL 0x463820` (ship-only pattern, any class) `; POP EBX; MOV EAX,ECX; MOV EDX,1; CALL 0x4576c4` (mode 1, kills all matches, no kill request) `; JMP 0x445a5b`.
    - Effect: all machines kill exactly the ship orders. The +0x80 test at 0x445a78 still guards the memset and the owner re-arm.
  - **H2 (arm B, preferred):**
    - When MP && busy==1, the owner does not re-arm at 0x445aad or 0x4459c7. Instead it appends the system to a cave list.
    - Hook the CALL FUN_00461640 at 0x46252f. After it, for each listed system with owner==local, run the original re-arm (FUN_0044dc70 → FUN_0046138c, or FUN_004616f0 + FUN_0044d830). This mirrors the developers' own FUN_004618c0 deferral but keeps the queue-head semantics.
    - Risk: about 80 bytes of cave code. The system's owner must be re-checked when the list is processed.
  - **H2-alt (simpler safety net):** in the production loop at 0x4624ad, skip type-0 orders with emp == local and seqno ≥ the local counter [0x590230+local*4] saved at busy=1.
    - It does not protect readers that run before the loop (e.g. +0x2d4 if the re-armed auto-pick is a ship).
    - First verify the node layout of the FUN_00456cd0 snapshot list.

**R3. Martial-law counter word sys+0x86 survives the receivers' mode-2 reset**
- **Status:** confirmed by code (2 confirmed, 1 plausible).
- **Mechanism:**
  1. FUN_0045fce0 (action 7, all machines) increments +0x86 (0x45fd15..0x45fd20). Once it reaches the race threshold (FUN_0043a6d4: 3/4/5), it raises morale +0x2dc every turn (0x45fd87), which is inside crcSolarBld.
  2. When the owner removes martial law from the queue head (FUN_004fd7b8) and later re-selects it (FUN_004f3840), the owner's record gets +0x86 = 0.
  3. The receivers' mode-2 reset (0x45774a..0x45777d) clears word +0x84 but not +0x86. Nothing else clears it until a completion (FUN_00444500), a conquest, or init.
  4. Receivers therefore reach the threshold early. The result is crcSolarBld-only (+0x2dc), seed equal. Later the martial-law flags +0x2e0..0x2ef also differ.
- **Why late game:** martial law needs morale below the cap, which mostly means conquered systems after wars. Players toggle it there. The trigger is a player action, not a size threshold.
- **Test:** as specified in the audit. Cardassian (threshold 3): two turns of martial law, remove it, re-select it. +0x86 then reads A=1, B=3. Expect a mismatch at the end of that turn.
- **Fix (Fix I), in place, no cave:**
  - Rewrite 0x45774a..0x457786 (61 bytes) to: `01 C2` (ADD EDX,EAX); `C7 82 80 00 00 00 00000000`; `C7 82 84 00 00 00 00000000` (a dword, so it also clears +0x86); `C7 82 88 00 00 00 FF7FFF7F` (+0x88 and +0x8a); `66 C7 82 90 00 00 00 FF FF`; `66 C7 82 98 00 00 00 00 00`; NOP padding.
  - Use immediates, not EBP: body[0] may be 2 on this path.
  - Risk: low. Only FUN_0045fce0 reads +0x86, and the owner's records always start at 0. This is narrower than the "Fix F" that was dropped earlier.

### Tier 2: real late-game desyncs or disconnects with a different signature

**R4. FUN_0044a360 (ship-class refit) re-creates human production orders on every machine with per-machine seqnos**
- **Status:** new, static only.
- **Mechanism:**
  1. Research completion (0x458490 → FUN_00453820 → FUN_00452560 → 0x4526a9) refits the ships of an empire to the successor class.
  2. If that empire is human (mask test at 0x44a45e, no owner==local gate), then for every system of the empire it kills the old-class ship order (mode 0, the same on all machines). It then adds the pattern node as the new order (0x44a4ea..0x44a4f8, FUN_00457b9c, which appends with no dedupe). That node's seqno comes from FUN_0045748c with this machine's own counter for that empire.
  3. The owner's counter is ahead, because of UI patterns and the local recompute. So the owner holds O and receivers hold R ≠ O.
  4. The next 0x68 delivers O. The merge (dedupe on seqno and type) keeps both on receivers.
  5. Receivers now process two orders for the same system: double progress and extra ships. That shows up as crcShip/crcTF and probably a different seed (ship naming uses the RNG via FUN_00475440).
  6. If R happens to equal the seqno of a live owner order, R is dropped at the merge and nothing diverges.
- **Why late game:** it needs successive ship-class techs while human systems are building the superseded class and the empire owns at least one ship of that class. That is common in long wars.
- **Test:**
  1. Human A owns a class-X ship, and system S is producing class X.
  2. Poke A's research symmetrically on both machines so that X's successor completes next turn.
  3. After processing, dump the order lists. Expect O on A and R on B. At the next turn start B should hold both. Later a crcShip/crcTF mismatch should follow.
- **Fix (Fix J):**
  - Move 0x44a4ea..0x44a4fc (19 bytes) to a cave: `MOV AL,[ESP+0x130]; CMP AL,5; JAE add; CMP AL,[0x5a2b2a]; JNE skip; add: <original 19 bytes>; skip: JMP 0x44a4fd`.
  - Receivers then only kill. The replacement is created after the production loop anyway, so every machine first processes O at N+1.
  - Alternative: give the new order the killed order's seqno.

**R5. MP turn timer ends the turn inside a modal dialog**
- **Status:** plausible (2 plausible, 1 refuted on the late-game lens). Only applies with TIMELIMIT on (default off).
- **Mechanism:**
  1. Callback 0x4b9e50 runs from every FUN_00402410 pump and calls FUN_00458120 at 0x4b9f74, including inside the yes/no box FUN_00500350 used by FUN_004fd7b8 (production change).
  2. The orders are broadcast while the box is open. After the player confirms, the production change (kill request, mode-1 kill, new order, write to +0x80) is never sent.
  3. If another human has not ended the turn yet, the machines process different production. Result: crcSolarBld-only, seed equal.
  4. Rarer path: after an auto-end, a displayed tactical combat unpauses the timer (0x4701c7, gated by [0x5b54ec]). A later modal dialog held open for the full time limit (e.g. the intel blame dialog FUN_00506910) then triggers a mid-processing end-turn.
- **Test:** TIMELIMIT = 1. On Y, open the production-change confirm box and let the timer expire while X is still playing. Confirm, then let X end the turn. Breakpoint at 0x4b9f74 to check that the call stack is inside FUN_00500350.
- **Fix (Fix K):** let the callback call FUN_00458120 only when busy==0 and the DispatchMessage depth is 0 (reuse Fix E's depth counter). Otherwise retry on the next tick. In FUN_0046fd80, unpause only if the timer was running before combat.

**R6. Message 0x85 (host closes the options dialog) is a fatal assert on clients still processing**
- **Status:** confirmed by code (1 confirmed, 1 plausible, 1 refuted on the late-game lens).
- **Mechanism:**
  1. FUN_004cdb80 sends 0x85 every time the host closes the options dialog (OK or ESC) while the host is idle, even if no option changed.
  2. On the client, FUN_0050d390 asserts busy != 1 at 0x50d39d (conninit.c line 617).
  3. The reliable window is a client sitting in the local-only intel blame dialog during processing (FUN_0047f7d0 → FUN_0047d9b4 → FUN_00506910 at 0x47dc7a). That dialog pumps messages with busy==1.
- **Symptom:** a disconnect with conninit.c in Crash.log, not a hartbeat.c error.
- **Test:** Y keeps the blame dialog open during processing. Host X finishes processing, opens options and presses ESC. Y should crash.
- **Fix (Fix L):** park 0x85 while busy==1, using the Fix B mechanism. Keep it ordered before any parked 0x68/0x74 from the same sender. Do not simply drop the assert: the payload sets [0x5a2b68] (combat mode), which processing reads at 0x4719c3, so applying it mid-processing would itself desync.

### Supporting items (not causes; use them for diagnosis)

- **Order list → crcSolarBld map (survives, plausible).** The economy pass derives idx-1 fields from the order list: +0x2d4 (FUN_00441460), martial-law flags +0x2e0..0x2ef (FUN_0043f2c0, exactly one action-7 order), buy cost +0x2c2 (FUN_0045fed0/FUN_00460940), scrap. So a major-empire type-0 order that exists on only one machine gives crcSolarBld-only in that turn.
  - The usual source (minor-range wrong kills) cannot feed this.
  - Changes made on a receiver before TURN are healed by the merge, so tests must inject after 0x45821f.
- **Unhashed carriers (survives, plausible).** Credits and +0x84 have no CRC and no resync, so they delay any earlier divergence until a BUY, debt or completion decision differs. MP has no local-only credits writer: the cheat is disabled at 0x401a08, and the UI calls to FUN_0043a434 use idx 0.
- **Diagnostics (recommended first engineering step):**
  - Extend observer.py so that, once per turn at an aligned point (break at 0x458233 on all instances), it diffs sys+0x80..0x99, +0x298..0x2f4, credits, and the order lists (seqno/emp/type/body). That shows the first divergence before it reaches a CRC.
  - Optionally put a CRC of these into heartbeat bytes 8..0x1b. Both comparers must then stop zeroing those bytes (FUN_0050ffe0 and FUN_00510260 at 0x5102e2..0x5102fe). This breaks compatibility with unpatched peers.

### Not explained

- **battle.c line 909 eventListCRC (turn 402):** no surviving mechanism explains it. Untested lead: combat uses x87 FSIN/FCOS (0x51fce0, 0x520d70, 0x532b60), whose results can differ between Intel and AMD CPUs. The economy uses only FSQRT/FRNDINT, so this cannot affect crcSolarBld.

## Refuted (one line each)

- **Inactive-window nested turn start / dropped next-turn orders:** impossible. The all-human 0x70 barrier in FUN_00470e50 runs every MP turn (0x45840b → 0x46b956 → 0x46ffa7), so an inactive player only stalls everyone.
- **Asynchronous player-drop handling:** only a secondary cascade after a drop, needing 3 or more humans. The AI takeover draws the RNG (0x407662), so the seed would differ. Latent side bugs remain: the [0x59056c] double decrement (battle.c 416), and a non-host that receives 0x66 before its own DESTROY skips the AI takeover.
- **DPSYS_SESSIONLOST ignored / endless send retry:** real robustness defects, but a drop does not make broadcasts fail (the group send returns 0 and the local player is kept). Not the reported signature.
- **Trade-route first-match lookup:** FUN_004612c0 (0x4583d4) applies and then deletes all subtype-7 orders before income is computed.
- **Race id ≥ 32 aliasing (0x4665b0, 0x449176, 0x4497bd):** real, and the confirmed source of the processing-time kill requests behind Fix E. But minor-range seqnos cannot hit major orders, so the effect is crcTF, not crcSolarBld-only. Fix E covers it.
- **Intel subversion kill requests:** the target is owner-numbered and already dead everywhere ("Failed to Kill order"). FUN_004490b0 acts on a brand-new TF.
- **crcSolarBld scratch buffer [0x58fd20] never resized:** latent. It needs an earlier, smaller MP galaxy in the same process, and the result is an access violation or heap damage, not a clean CRC mismatch.
- **No message pumping during processing or sends:** cosmetic "Not Responding" only; no state change.
- **16-bit task-force id overflow:** about 2–8 ids per turn were measured, nowhere near 32768, and the effect would be the same on all machines.
- **Reassembly key lacks the sender:** false; header +0x20 is the sender's DPID.
- **Upgrade +0x84/+0x90 16-bit overflow:** deterministic, apart from a corner case of about 1e-6 probability.
- **Uninitialized ship cost in FUN_0045fed0:** unreachable; the ship count is asserted to be 125 (0x46fc2d) and every id matches its index.
- **Previously refuted, unchanged:** receive-list orphans, SmartHeap, heartbeat slot overflow, idle-UI RNG, FPU control word, edits after TURN, labor/build/buy UI paths, order-list iteration order.

## Suggested order of work

1. Add the observer diff of record, block, credits and order list. Then run the R2 scrap tests (arm A and arm B) and the R3 test. These are deterministic and need no game patching.
2. Measure how many human systems reach morale ≥ 192 in long saves, then run the R1 test with pokes.
3. Run the R4 refit test.
4. Implement Fix I (in place), Fix G, Fix H1+H2 and Fix J. A/B each one against its test, then run long 5-human games with the observer.
5. Fix L and Fix K are cheap hardening.

## Analysis scripts (scratchpad)

Folder: `C:\Users\Stephan\AppData\Local\Temp\claude\E--dev-botf\849e8cd5-4ad3-4f6d-944f-0923dfe94ab2\scratchpad\`

- `rngbfs.py`: RNG reachability.
- `addpaths.py`: order-creation paths before the production snapshot.
- `addpaths2.py`: order-creation paths after the snapshot.
- `recread.py`: readers of sys+0x80..0x93 before production.