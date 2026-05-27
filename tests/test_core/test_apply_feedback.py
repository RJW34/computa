"""Tests for shared apply/restore feedback helpers."""

from types import SimpleNamespace

from abso.core.apply_feedback import (
    append_unique_message,
    collect_apply_notices,
    collect_apply_warnings,
    describe_restore_summary,
    determine_apply_summary_level,
    is_soft_apply_warning,
)


def test_append_unique_message_strips_and_dedupes():
    messages = ["Existing"]

    append_unique_message(messages, "  New warning  ")
    append_unique_message(messages, "New warning")
    append_unique_message(messages, "")
    append_unique_message(messages, None)

    assert messages == ["Existing", "New warning"]


def test_collect_apply_warnings_dedupes_result_transaction_and_compliance():
    result = SimpleNamespace(warnings=["Mixed refresh rates detected", "Repeated"])
    tx = SimpleNamespace(
        checkpoints=[
            SimpleNamespace(status="warn", message="Repeated"),
            SimpleNamespace(status="ok", message="Ignored"),
        ],
        compliance_report=SimpleNamespace(
            warnings=[
                SimpleNamespace(
                    message="Verification mismatch in NvidiaSettingsHandler",
                    details="driver profile not active",
                )
            ]
        ),
    )

    assert collect_apply_warnings(tx, result) == [
        "Mixed refresh rates detected",
        "Repeated",
        "Verification mismatch in NvidiaSettingsHandler: driver profile not active",
    ]


def test_collect_apply_notices_ignores_empty_result_and_dedupes():
    assert collect_apply_notices(None) == []
    result = SimpleNamespace(notices=["  Reusing existing profile  ", "Reusing existing profile"])

    assert collect_apply_notices(result) == ["Reusing existing profile"]


def test_soft_warning_classification_drives_summary_level():
    assert is_soft_apply_warning("2 monitors detected")
    assert is_soft_apply_warning("MPO glitch risk: VRR/G-Sync active")
    assert not is_soft_apply_warning("Game executable is running during apply")

    assert (
        determine_apply_summary_level(
            ["Mixed refresh rates detected", "2 monitors detected"],
            ["Profile already current"],
        )
        == "caution"
    )
    assert determine_apply_summary_level(["Game executable is running"], []) == "warning"
    assert determine_apply_summary_level([], ["Profile already current"]) == "notice"
    assert determine_apply_summary_level([], []) == "success"


def test_describe_restore_summary_can_ignore_nonblocking_components():
    summary = {
        "failed_components": [
            {"handler": "WindowsSettingsHandler", "blocking": True},
            {"handler": "TimerSettingsHandler", "blocking": False},
        ],
        "skipped_components": [
            {"handler": "NvidiaSettingsHandler"},
        ],
    }

    assert (
        describe_restore_summary(summary)
        == "Restore incomplete for: WindowsSettingsHandler, TimerSettingsHandler, NvidiaSettingsHandler"
    )
    assert (
        describe_restore_summary(summary, blocking_only=True)
        == "Restore incomplete for: WindowsSettingsHandler, NvidiaSettingsHandler"
    )
    assert describe_restore_summary({"failed_components": [], "skipped_components": []}) is None
