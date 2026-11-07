Found while checking #77: the `ui-tests` CI job has never really run. Both runs started by hand on the #74 branch (release: run 42318761541, ubuntu: run 42318764958) failed in **every** job, including the environments that existed before #74. All failed in the same way:

```
    from .session import Session, SessionError
ModuleNotFoundError: No module named 'pytest'
```

**1. The `uitest` driver needs pytest on the host.** `uitest` says "Host needs only python3 (stdlib) and docker", but `hostrun` → `session` → `preconditions`, and `preconditions.py` does `import pytest` at the top. It is used only inside `require()`. It works locally only because pytest is installed there. The GitHub runner runs `./uitest` with plain python3.
- Fix: import pytest inside `require()`, and add a framework test that imports `hostrun` with pytest blocked, so this can't come back.

**2. `ui-tests` never runs automatically in this fork.** Its `workflow_run` trigger has `branches: [master]`, but the fork's builds run on `stickleprojects` (the default branch). `gh run list --workflow ui-tests.yaml --event workflow_run` is empty. Every "success" in the history is `framework-tests`, with `ui-tests` skipped.
- Fix: add `stickleprojects` to `workflow_run.branches` (keep `master` for upstream).

Until both are fixed, CI says nothing about the game UI tests, and #73/#74's CI changes can't be checked on GitHub.

Suggested priority: HIGH (blocks verification of #76/#77).
