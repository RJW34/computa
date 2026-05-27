# Contributing

ABSO is primarily a personal-use tool. External contributions are welcome but small and focused.

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
pre-commit install
```

Use the `.venv` name — the build/deploy tooling (`build.py`, `CLAUDE.md`) refers
to `.\.venv\Scripts\python.exe`.

## Conventions

- Python 3.11+ with type hints.
- Black + Ruff (enforced by pre-commit).
- pytest on pre-push.
- Never modify state outside the registry allowlist.
- Every settings handler must implement `detect/audit/apply/backup/restore`.
- Profiles must declare `is_online_profile` and `optimization_target`.

## Testing

The integration test suite touches real Windows state. Only run integration tests on a non-production machine, with admin and explicit `-m integration`. Unit tests are safe.
