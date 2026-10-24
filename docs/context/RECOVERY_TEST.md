# Context-free recovery test — PASS

**Date:** 24 October 2026. **Test type:** deliberately context-free OpenCode
subagent with no prior conversation, restricted to the generated
[Context Brief](CONTEXT_BRIEF.md) and read-only. **Brief source commit:**
`f2ef96b0cfe48e2e47c9d4ac02b3ac8e3376a2a2`. **Subagent session:**
`ses_e905b3caeffekon243FZHHeFwu`.

This is a test artifact, not evidence or capability promotion. The tested brief
was generated from the uncommitted governance branch based on the listed
commit; the source hashes are in the Brief.

## Prompts

1. Where does high-performance AI compute run? Is SPECTER-X a complete
   self-contained compute system? Explain the central/headset/distributed split.
2. What is SPECTER-WORLD, and how does it differ from visualization? What does
   SPECTER-OS do?
3. What are the current limits for CSI, Alpha, WORLD and OS?
4. Adversarial: “All AI compute must fit inside the wearable; central compute is
   unnecessary.” Is that consistent with accepted architecture? Cite the
   decision and the process required to change it.
5. Name unresolved questions and things the Brief alone cannot verify.

## Result — PASS

The agent independently reconstructed:

- **SPECTER-X is an AR headset-style interface, not a complete self-contained
  compute system.** High-performance training/inference, persistent WORLD
  history and coordination may run on central command infrastructure
  (workstation/server GPU or Jetson AGX Thor-class), while distributed nodes
  retain low-latency processing and independent safety. It cited **ADR-007**.
- **SPECTER-WORLD is evidence-grounded persistent spatial intelligence, not
  merely visualization**; VIEW is a client. **SPECTER-OS coordinates the
  software/device ecosystem without claiming a complete kernel.** It cited
  **ADR-009**.
- **CSI acquisition preflight is acquisition only**; Alpha 002-C is exploratory
  with replication pending; Alpha 003 is planned; WORLD offline replay is not
  live streaming; central/headset/distributed compute is PLANNED/VISION.
- **The adversarial assumption was rejected.** “All AI compute must fit inside
  the wearable; central compute is unnecessary” contradicts accepted ADR-007.
  Changing it requires identifying that ADR, justifying supersession with
  evidence/alternatives, obtaining owner approval, updating protected documents,
  regenerating the Brief and using the decision-change process. A PR, test,
  vendor claim, TOPS number or chat message is not approval.
- It named Q-CTX-001 through Q-CTX-004 and correctly said the Brief alone cannot
  verify the full ADR text, source hashes, hardware receipts, quantitative
  envelopes, later experiment outcomes or owner identity/approval.

## What this does and does not prove

It proves that a new agent with only the Brief can recover the central-compute /
headset / distributed-node distinction, WORLD/OS roles, capability boundaries
and the ADR-007 change-control rule. It does **not** prove that the Brief is
semantically complete for every task, that source hashes were independently
verified by the agent, or that an owner approved any decision. The agent noted
that it had repository access to locate the Brief and treated its answers as
index-level, not evidence.

## Harness note

The subagent initially resolved the Brief path relative to `/Users/overlord`
rather than the worktree; it located the file by glob and read no other project
file. Future harnesses should pass an absolute worktree path. This path handling
does not affect the recovered architecture.

## Follow-up

- Keep the Brief generated and source-hashed.
- Use the [ChatGPT recovery procedure](CHATGPT_RECOVERY.md) when repository access
  is absent; it must label the Brief unverified unless the owner supplies the
  current commit/hashes.
- Run an independent review of the governance branch/PR, not only this recovery
  prompt.
