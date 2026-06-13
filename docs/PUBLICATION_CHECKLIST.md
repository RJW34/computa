# Publication Checklist

- [ ] README explains what this project is, what currently works, and how to run it.
- [ ] AGENTS.md describes setup, test commands, safety constraints, and project state for future agents.
- [ ] `.env.example` exists for required configuration and contains placeholders only.
- [ ] No `.env`, credential, key, cookie, token, runtime, backup, capture, or generated artifact files are tracked unless intentionally documented.
- [ ] `gitleaks detect --source . --redact=100 --no-banner` is clean on current tree and history.
- [ ] Any historical secret exposure has been rotated/revoked and history has been rewritten or the public repo has been recreated from a clean tree.
- [ ] License choice is explicit before public release.
- [ ] Smoke tests or verification commands are documented and pass.
