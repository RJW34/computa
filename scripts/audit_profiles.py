"""One-off profile audit.

Runs every profile in the catalog through the static validators that the
real ProfileApplier would run before touching system state:

  1. Profile prerequisites (capability + multi-monitor)
  2. ProfileLinter (static handler/setting validation)
  3. RollbackGuard (online netcode safety)
  4. StabilityGate (aggressive-setting gating)
  5. NetworkScopeManager (per-profile network filtering)
  6. Profile contract validation (profile.validate_settings)
  7. Handler preflight (no side effects)

Does NOT call handler.apply(). Does NOT mutate state.

Outputs a per-profile verdict and a summary block.
"""

from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from abso.core.applier import ProfileApplier  # noqa: E402
from abso.profiles.catalog import PROFILE_CATALOG  # noqa: E402


def _fmt_handlers(handlers: list[str]) -> str:
    if not handlers:
        return "(none)"
    return ", ".join(handlers)


def audit_profile(
    applier: ProfileApplier,
    profile_id: str,
) -> dict[str, Any]:
    """Audit a single profile. Returns a verdict dict."""
    verdict: dict[str, Any] = {
        "id": profile_id,
        "ok": True,
        "errors": [],
        "warnings": [],
        "notices": [],
        "handlers": [],
        "scope_flags": {},
    }

    # Instantiate and collect profile metadata
    try:
        profile = applier._get_profile(profile_id)
    except Exception as e:
        verdict["ok"] = False
        verdict["errors"].append(f"Profile load failed: {e}")
        return verdict

    verdict["display_name"] = profile.display_name
    verdict["handlers"] = [h.__class__.__name__ for h in profile.get_handlers()]
    verdict["scope_flags"] = {
        "is_online_profile": getattr(profile, "is_online_profile", False),
        "is_emulator_profile": getattr(profile, "is_emulator_profile", False),
        "has_hdr": "hdr" in profile_id.lower(),
        "requires_gsync": getattr(profile, "requires_gsync", False),
    }

    # 1. Prerequisites (capability + multi-monitor). This is the same entry
    #    point the transaction uses before creating any backup.
    try:
        prereq_err = applier.validate_profile_prerequisites(profile_id)
        if prereq_err:
            verdict["ok"] = False
            verdict["errors"].append(f"Prerequisites: {prereq_err}")
    except Exception as e:
        verdict["ok"] = False
        verdict["errors"].append(f"Prerequisite check crashed: {e}")

    # 2. Static lint
    try:
        lint = applier._linter.lint(profile)
        for err in lint.errors:
            verdict["ok"] = False
            verdict["errors"].append(f"Lint[{err.code}]: {err.message}")
        for warn in lint.warnings:
            verdict["warnings"].append(f"Lint[{warn.code}]: {warn.message}")
    except Exception as e:
        verdict["ok"] = False
        verdict["errors"].append(f"Linter crashed: {e}")

    # Collect settings the same way the applier does
    try:
        settings_map = applier._collect_settings(profile)
    except Exception as e:
        verdict["ok"] = False
        verdict["errors"].append(f"Settings collection crashed: {e}")
        return verdict

    # 3. RollbackGuard
    try:
        rb = applier._rollback_guard.check(profile, settings_map)
        for v in rb.violations:
            msg = f"RollbackGuard[{v.code}]: {v.message}"
            # In block mode, a violation would abort a real apply — treat as error
            if applier._rollback_guard.mode == "block":
                verdict["ok"] = False
                verdict["errors"].append(msg)
            else:
                verdict["warnings"].append(msg)
    except Exception as e:
        verdict["ok"] = False
        verdict["errors"].append(f"RollbackGuard crashed: {e}")

    # 4. StabilityGate
    try:
        _, gate = applier._stability_gate.process(profile, settings_map, None)
        if gate.blocked_count:
            verdict["notices"].append(
                f"StabilityGate blocked {gate.blocked_count} aggressive setting(s)"
            )
    except Exception as e:
        verdict["ok"] = False
        verdict["errors"].append(f"StabilityGate crashed: {e}")

    # 5. Network scope
    try:
        _ = applier._network_scope.apply_scope(profile, settings_map)
    except Exception as e:
        verdict["ok"] = False
        verdict["errors"].append(f"NetworkScopeManager crashed: {e}")

    # 6. Profile contract + 7. Handler preflight (no side effects)
    try:
        from abso.core.config import ConfigManager
        cfg = ConfigManager()
        final = applier._finalize_handler_settings(
            profile, profile_id, settings_map, cfg.get_profile_overrides(profile_id)
        )
        contract_violations = applier._validate_profile_contract(
            profile_id, profile, final
        )
        for v in contract_violations:
            verdict["ok"] = False
            verdict["errors"].append(f"ProfileContract: {v}")

        preflight_failures = applier._run_handler_preflight(profile_id, profile, final)
        for p in preflight_failures:
            verdict["ok"] = False
            verdict["errors"].append(f"Preflight: {p}")
    except Exception as e:
        verdict["ok"] = False
        verdict["errors"].append(f"Contract/preflight crashed: {e}")

    # Scope sanity: HDR profiles should include ColorProfileSettingsHandler
    hdr_claim = verdict["scope_flags"]["has_hdr"]
    has_color = "ColorProfileSettingsHandler" in verdict["handlers"]
    if hdr_claim and not has_color:
        verdict["warnings"].append(
            "Scope check: profile id suggests HDR but ColorProfileSettingsHandler not in handler chain"
        )

    return verdict


def main() -> int:
    applier = ProfileApplier()
    profile_ids = list(PROFILE_CATALOG.keys())

    results = [audit_profile(applier, pid) for pid in profile_ids]

    # Per-profile table
    clean: list[dict[str, Any]] = []
    issues: list[dict[str, Any]] = []
    for r in results:
        if r["ok"] and not r["warnings"]:
            clean.append(r)
        else:
            issues.append(r)

    print("=" * 80)
    print(f"PROFILE AUDIT - {len(results)} profiles ({len(clean)} clean / {len(issues)} with issues)")
    print("=" * 80)

    if clean:
        print()
        print("CLEAN:")
        for r in clean:
            print(f"  * {r['id']:<32} {len(r['handlers'])} handlers")

    if issues:
        print()
        print("WITH ISSUES:")
        for r in issues:
            tag = "FAIL" if not r["ok"] else "warn"
            print()
            print(f"  [{tag}] {r['id']}  ({r.get('display_name', '?')})")
            for e in r["errors"]:
                print(f"      ERROR: {e}")
            for w in r["warnings"]:
                print(f"      WARN:  {w}")
            for n in r["notices"]:
                print(f"      note:  {n}")

    # Aggregate summary by issue type
    error_kinds: dict[str, int] = defaultdict(int)
    warn_kinds: dict[str, int] = defaultdict(int)
    for r in results:
        for e in r["errors"]:
            key = e.split(":", 1)[0]
            error_kinds[key] += 1
        for w in r["warnings"]:
            key = w.split(":", 1)[0]
            warn_kinds[key] += 1

    print()
    print("=" * 80)
    print("ISSUE BREAKDOWN")
    print("=" * 80)
    if error_kinds:
        print("Errors by kind:")
        for k, c in sorted(error_kinds.items(), key=lambda x: -x[1]):
            print(f"  {c:>3}  {k}")
    else:
        print("No errors.")
    if warn_kinds:
        print("Warnings by kind:")
        for k, c in sorted(warn_kinds.items(), key=lambda x: -x[1]):
            print(f"  {c:>3}  {k}")
    else:
        print("No warnings.")

    # Exit code = number of failed profiles (capped at 255)
    return min(255, sum(1 for r in results if not r["ok"]))


if __name__ == "__main__":
    sys.exit(main())
