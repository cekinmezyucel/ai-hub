# Security

No secret belongs in this repo. Layers, strongest first: no secrets exist, GitHub push protection,
the gitleaks CI scan (`.github/workflows/gitleaks.yml`), the local hook (`.githooks/pre-commit`).

Turn the hook on once per clone: `git config core.hooksPath .githooks` (needs `brew install gitleaks`).

## If a secret leaks

Pushed means leaked, even if you delete it a minute later.

1. **Rotate first.** Revoke the secret where it was issued and create a new one.
2. Check where it was used while it was public (provider logs, audit logs).
3. Only then remove it from the history (`git filter-repo`), if it is still needed. This does not undo the leak.
4. Write down what happened and which layer missed it, in an Issue.

To report a problem, open a private advisory on the repo's Security tab.
