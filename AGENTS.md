# AgentRace Development Instructions

## 1. Project Objective

This repository is used for an internal AgentRace game competition.

The final program will be built and started locally. After the process is running, a human will take over and participate in the actual competition.

The primary engineering objective is:

> Implement the requirements correctly, robustly, and reproducibly, with correctness taking precedence over development speed or code simplicity.

A crash, protocol violation, incorrect behavior, malformed output, timeout, or other serious runtime bug may directly cause a competition loss.

Therefore, never treat "the code compiles" or "the happy path works" as sufficient evidence that the task is complete.

---

## 2. Source of Truth

Repository information has the following roles.

### `AI Spec/`

`AI Spec/` contains pure-text interpretations of the official competition documents.

For routine development, this directory is the primary requirements source.

Before implementing behavior related to competition rules, interfaces, protocols, input/output formats, timing, scoring, or constraints:

1. Read the relevant documents under `AI Spec/`.
2. Locate the exact requirement.
3. Do not rely on assumptions or memory when the repository contains an explicit specification.

If multiple AI Spec documents appear inconsistent:

* do not silently choose one;
* inspect surrounding context;
* record the ambiguity in `docs/STATUS.md`;
* resolve it before implementing behavior that could affect competition correctness.

### `Official/`

`Official/` contains original competition materials and may contain multimodal content.

Access to multimodal content may trigger the corporate gateway.

Therefore:

* Do NOT proactively inspect `Official/`.
* Do NOT read images from `Official/`.
* Do NOT upload, transmit, encode, or otherwise send images or multimodal materials outside the local environment.
* Do NOT use external services to interpret Official materials.
* Only inspect a specific Official text file when it is genuinely necessary to resolve an important ambiguity that cannot be resolved from `AI Spec/`.
* If access to Official material is required and may involve multimodal content, stop and request human intervention instead of taking the risk automatically.

For normal development, treat `AI Spec/` as the working requirements source.

---

## 3. Required Engineering Workflow

For any non-trivial implementation task, follow this sequence:

Requirements
→ Design
→ Implementation
→ Focused Tests
→ Integration Tests
→ Review
→ Documentation Update

Do not skip directly from requirements to large-scale implementation when architecture or protocol behavior is still unclear.

Before modifying unfamiliar code:

* inspect the relevant implementation;
* inspect callers and callees;
* inspect related data structures;
* inspect existing tests;
* understand how the program is built and executed.

Do not guess repository structure or API behavior when it can be inspected locally.

---

## 4. Correctness Policy

Correctness is the highest priority.

Never:

* invent competition rules that are not present in the specification;
* silently ignore requirements that are difficult to implement;
* weaken validation merely to make a test pass;
* remove safety checks without understanding why they exist;
* hide exceptions or failures that could affect runtime correctness;
* claim that behavior is verified when it has not actually been executed or tested;
* make broad unrelated refactors during a correctness-critical change;
* introduce unnecessary dependencies;
* change public interfaces without verifying all callers;
* assume external input is valid unless the specification guarantees it.

Prefer minimal, understandable changes over clever abstractions.

When multiple solutions are possible, prefer the solution with:

1. simpler runtime behavior;
2. fewer hidden assumptions;
3. easier verification;
4. clearer failure handling;
5. lower probability of competition-time failure.

---

## 5. Testing Requirements

Every competition-critical behavior should be tested where practical.

At minimum consider:

* normal inputs;
* boundary values;
* malformed inputs;
* empty inputs;
* maximum/minimum values;
* duplicated inputs;
* unexpected ordering;
* failure paths;
* timeout behavior;
* resource cleanup;
* repeated execution;
* initialization and shutdown;
* protocol serialization/deserialization;
* integration between major modules.

For concurrency, networking, state machines, resource management, or timing-sensitive behavior, explicitly inspect:

* race conditions;
* deadlocks;
* stale state;
* partial reads/writes;
* retries;
* duplicate messages;
* lost messages;
* incorrect ordering;
* timeout cleanup;
* exception cleanup.

Tests must not merely duplicate the implementation logic.

A passing test suite is evidence, not proof. After tests pass, still compare implementation behavior against the specification.

Never report a test as PASS unless the corresponding command actually completed successfully.

---

## 6. Competition Requirement Coverage

Before considering the implementation complete, perform a specification coverage review.

For each competition-critical requirement, determine:

Requirement
→ Implementation location
→ Verification/test location

Explicitly search for:

* unimplemented requirements;
* partially implemented requirements;
* behavior inconsistent with the specification;
* requirements with no verification;
* hidden assumptions;
* runtime failure modes;
* protocol incompatibilities;
* timeout risks;
* crash risks.

Do not assume that existing code is correct merely because it looks reasonable or because its tests pass.

---

## 7. Documentation and Recovery

The development process must remain recoverable across Codex sessions.

Maintain the following files:

* `docs/STATUS.md`
* `docs/DESIGN.md`
* `docs/TEST_PLAN.md`

### `docs/STATUS.md`

This is the authoritative development checkpoint.

Keep it concise and current.

Update it whenever a meaningful development phase is completed or when important new information is discovered.

It should contain:

* current phase;
* completed work;
* current implementation state;
* verified tests;
* known risks;
* unresolved questions;
* next actions.

Do not turn STATUS.md into a chronological chat transcript.

The purpose is that a completely new Codex session can read:

* `AGENTS.md`
* `docs/STATUS.md`
* relevant `AI Spec/`
* current Git state

and safely continue development.

### `docs/DESIGN.md`

Record architectural decisions that materially affect the implementation.

Document:

* module responsibilities;
* data flow;
* important state;
* protocol handling;
* algorithms;
* important trade-offs;
* assumptions;
* decisions that would otherwise need to be rediscovered.

Do not fill it with implementation trivia.

### `docs/TEST_PLAN.md`

Maintain:

* required test categories;
* concrete test cases;
* test commands;
* test status;
* scenarios that cannot yet be tested;
* final competition-readiness checks.

---

## 8. Git Safety

Treat Git as the persistent engineering checkpoint.

Before large modifications, inspect the current Git state.

Do not:

* delete unrelated user changes;
* overwrite unrelated work;
* use destructive Git operations unless explicitly requested;
* rewrite Git history;
* force push;
* reset user work merely to simplify implementation.

Use `git diff` frequently to inspect the actual scope of changes.

Do not automatically create commits unless the user has asked Codex to manage commits.

When a stable checkpoint is reached, report that it is suitable for a human-created Git commit.

---

## 9. Scope Control

Do not perform unrelated cleanup while implementing competition requirements.

Avoid:

* cosmetic refactors unrelated to correctness;
* unnecessary file renaming;
* dependency upgrades without a concrete need;
* replacing working infrastructure simply because another approach appears cleaner.

If a refactor is necessary for correctness, explain why in `docs/DESIGN.md`.

---

## 10. Logging

When adding logs inside a function, use the following format whenever practical:

`[函数名] 日志信息`

Examples:

`[init_game] 初始化完成`
`[handle_message] 收到消息`
`[connect_server] 连接失败: ...`

Logs should help diagnose competition-time failures.

Avoid excessive logging in hot paths if it may materially affect performance or timing.

Never log secrets, credentials, or unnecessarily large payloads.

---

## 11. Completion Criteria

A development task is not complete merely because implementation code exists.

Before declaring the overall AgentRace implementation complete:

1. Re-read all relevant `AI Spec/` requirements.
2. Check specification coverage against the implementation.
3. Run the complete available test suite.
4. Run competition-related integration tests.
5. Inspect failures, warnings, and logs.
6. Inspect the final Git diff.
7. Perform an independent code review focused on correctness.
8. Update `docs/STATUS.md`.
9. Record any residual risk that cannot be locally verified.

If something cannot be verified locally, state that explicitly instead of assuming it works.

---

## 12. Priority Order

When instructions or goals appear to compete, use this priority:

1. Competition correctness and safety.
2. Explicit requirements in `AI Spec/`.
3. Existing external/public interface compatibility.
4. Tests and reproducibility.
5. Existing repository conventions.
6. Simplicity and maintainability.
7. Development speed.

When uncertain about competition-critical behavior, investigate before implementing.
