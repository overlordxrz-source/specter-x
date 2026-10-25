# ChatGPT recovery without repository access

A ChatGPT session cannot verify the repository by itself. Use the current
Context Brief as a **quoted, owner-supplied snapshot**, not as evidence that the
repository is unchanged.

## Procedure

1. Ask the owner for:
   - the generated [Context Brief](CONTEXT_BRIEF.md), copied in full;
   - its source commit and source hashes;
   - the task/authorization boundary.
2. Read the Brief’s canonical truths, active ADRs, milestone, unresolved
   questions and source list. Do not answer from general memory.
3. If the Brief is older than the task or a source hash is missing, mark the
   context **UNVERIFIED** and ask for the current Brief/commit.
4. Produce a [Context Receipt](CONTEXT_RECEIPT.md). Explicitly separate:
   - what the Brief/source says;
   - what is inferred for the task;
   - what is unknown or inaccessible.
5. If the task would contradict an accepted ADR (for example “all AI compute
   must fit inside the wearable” vs ADR-007), stop and use
   [decision change](DECISION_CHANGE.md). Do not “helpfully” adopt the
   contradiction.
6. Never invent paths, hashes, commit IDs, capability status, hardware receipts,
   calibration, test results or owner approvals.

## Minimal recovery prompt

```text
You are a new SPECTER-X agent with no prior conversation. Use only the attached
Context Brief and the sources it names. First state the source commit and hashes,
then answer the task. Keep measured/inferred/predicted/simulated/unverified/
unknown distinct. If a request assumes all AI compute must fit inside the
wearable, identify the conflict with ADR-007, explain the central/headset/
distributed topology, and say what owner-approved decision change would be
required. Do not claim repository access you do not have.
```

## If repository access is restored

Read `docs/context/CONTEXT_BRIEF.md`, run `python tools/check_context.py`, and
open the relevant canonical sources. Do not paste a chat summary into a canonical
document without review. The repository remains canonical; the Brief is an index.
