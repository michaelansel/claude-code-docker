# Agent Mode

Agent mode runs a named agent defined in `~/.claude-docker/agents.yaml`. There are two patterns for long-running agents: **c3po auto** (legacy) and **trigger-based** (recommended).

## c3po auto (legacy)

Without a `triggers` block, an agent with no `prompt` defaults to `/c3po auto`. In this mode, Claude stays running inside the container indefinitely, polling its c3po inbox in a loop and processing messages as they arrive.

```yaml
# agents.yaml — legacy c3po auto (no prompt, no triggers)
ithaca:
  workspace: ~/Code/ithaca
```

**Tradeoffs:**
- Simple to set up — no configuration beyond the workspace
- Claude runs continuously, even when idle → consumes tokens just to stay alive
- Long-running sessions accumulate context, which eventually degrades quality or hits limits
- Session must be manually restarted when it stalls or the container exits

## Trigger-based (recommended)

With a `triggers` block, claude-docker manages the restart loop on the host. The container runs once per trigger, does its work, and exits. Claude is only alive when there is work to do.

```yaml
# agents.yaml — trigger-based
ithaca:
  workspace: ~/Code/ithaca
  prompt: "Check your c3po inbox and handle any pending tasks. Commit your work before exiting."
  triggers:
    - type: c3po
```

**Tradeoffs:**
- Zero idle token cost — Claude only runs when a trigger fires
- Each session starts fresh with no memory of previous runs (see [Session Memory](#session-memory))
- Requires a `prompt` that tells Claude what to do on each run

### When to use each trigger type

**`c3po`** — fires when a message arrives in the agent's c3po inbox. Use this for agents that receive tasks from other agents or from you via `/c3po send`.

**`script`** — fires when a shell command exits 0. Use this for agents that should wake on external state changes (e.g. new commits, a file appearing, a queue becoming non-empty). The command runs in the agent's workspace directory.

```yaml
ithaca:
  workspace: ~/Code/ithaca
  prompt: "Process pending tasks and commit your work before exiting."
  triggers:
    - type: c3po
    - type: script
      command: python3 lib/check-queue.py
```

Multiple triggers run in parallel — the first to fire starts the container; the others are cancelled.

### post_run

Commands under `post_run` run on the host after each container exit, before the next trigger wait. Use this for cleanup, notifications, or syncing state.

```yaml
ithaca:
  workspace: ~/Code/ithaca
  prompt: "..."
  triggers:
    - type: c3po
  post_run:
    - bash scripts/notify.sh
```

Failures are logged but the loop continues.

## Session Memory

Trigger-based agents start each run with a fresh Claude session — no memory of previous runs. This is by design: it keeps context windows small and prevents quality degradation over time.

To preserve state across runs, agents should write to files or git before exiting:
- Commit work to git
- Write a `SESSION_NOTES.md` or similar handoff file
- Use structured files (JSON, YAML) for task queues or status

A good prompt acknowledges this:

```
Check your c3po inbox and handle any pending tasks.
Read SESSION_NOTES.md for context from previous runs.
Update SESSION_NOTES.md with what you did and what's next.
Commit all work before exiting.
```

## Migrating from c3po auto to triggers

The change is small — add `prompt` and `triggers` to the agent's config:

**Before:**
```yaml
ithaca:
  workspace: ~/Code/ithaca
```

**After:**
```yaml
ithaca:
  workspace: ~/Code/ithaca
  prompt: "Check your c3po inbox and handle any pending tasks. Commit your work before exiting."
  triggers:
    - type: c3po
```

**What changes:**
- Claude no longer runs continuously — it only wakes when a message arrives
- Each run starts with a fresh session (no accumulated context)
- The container exits cleanly after each run; claude-docker restarts it on the next trigger

**What stays the same:**
- Other agents can still send messages to this agent via c3po — it will appear offline between runs, but messages are queued and delivered when it wakes
- `claude-docker agent run ithaca` is the same command to start it

## Debugging

Run once without entering the trigger loop:

```bash
claude-docker agent run ithaca --once
```

This is useful for testing your prompt or verifying the agent starts correctly.
