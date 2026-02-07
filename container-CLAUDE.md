# Container Agent Instructions

## Git Configuration

Git is not configured in this container (no user.name, user.email, no SSH keys, no credentials). Do not attempt git write operations (commit, push, branch, tag, etc.) as they will fail.

Git read operations (status, diff, log, blame, show) are fine and encouraged.

## Default Behavior

Prefer read-only operations: read files, search code, analyze, and report findings. Do not modify files unless explicitly instructed to make changes.

When instructed to make changes: make the code changes but do NOT commit. Leave changes uncommitted for the caller to review and commit.
