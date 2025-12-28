"""Tests for configuration audit module."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from abso.core.auditor import ConfigurationAuditor
from abso.core.models import Issue


class TestConfigurationAuditorInit:
    """Tests for ConfigurationAuditor initialization."""

    def test_init_creates_instance(self):
        """Test ConfigurationAuditor can be instantiated."""
        with patch("abso.core.auditor._get_handlers", return_value=[]):
            auditor = ConfigurationAuditor()
            assert auditor is not None

    def test_init_loads_handlers(self):
        """Test ConfigurationAuditor loads handlers on init."""
        mock_handler = MagicMock()

        with patch("abso.core.auditor._get_handlers", return_value=[mock_handler]):
            auditor = ConfigurationAuditor()
            assert len(auditor._handlers) == 1


class TestAuditAll:
    """Tests for audit_all method."""

    def test_audit_all_returns_issues(self):
        """Test audit_all returns list of issues."""
        mock_handler = MagicMock()
        mock_handler.audit.return_value = [
            Issue(
                title="Test Issue",
                severity="warning",
                current_value="current",
                optimal_value="optimal",
                explanation="Test explanation",
                category="test",
            )
        ]

        with patch("abso.core.auditor._get_handlers", return_value=[mock_handler]):
            auditor = ConfigurationAuditor()
            issues = auditor.audit_all()

        assert len(issues) == 1
        assert issues[0].title == "Test Issue"

    def test_audit_all_aggregates_multiple_handlers(self):
        """Test audit_all aggregates issues from multiple handlers."""
        handler1 = MagicMock()
        handler1.audit.return_value = [
            Issue(
                title="Issue 1",
                severity="warning",
                current_value="a",
                optimal_value="b",
                category="cat1",
            )
        ]

        handler2 = MagicMock()
        handler2.audit.return_value = [
            Issue(
                title="Issue 2",
                severity="info",
                current_value="c",
                optimal_value="d",
                category="cat2",
            )
        ]

        with patch("abso.core.auditor._get_handlers", return_value=[handler1, handler2]):
            auditor = ConfigurationAuditor()
            issues = auditor.audit_all()

        assert len(issues) == 2

    def test_audit_all_sorts_by_severity(self):
        """Test audit_all sorts issues by severity (critical first)."""
        handler = MagicMock()
        handler.audit.return_value = [
            Issue(
                title="Info Issue",
                severity="info",
                current_value="a",
                optimal_value="b",
                category="test",
            ),
            Issue(
                title="Critical Issue",
                severity="critical",
                current_value="a",
                optimal_value="b",
                category="test",
            ),
            Issue(
                title="Warning Issue",
                severity="warning",
                current_value="a",
                optimal_value="b",
                category="test",
            ),
        ]

        with patch("abso.core.auditor._get_handlers", return_value=[handler]):
            auditor = ConfigurationAuditor()
            issues = auditor.audit_all()

        assert issues[0].severity == "critical"
        assert issues[1].severity == "warning"
        assert issues[2].severity == "info"

    def test_audit_all_handles_handler_exception(self):
        """Test audit_all handles handler exceptions gracefully."""
        handler = MagicMock()
        handler.__class__.__name__ = "TestHandler"
        handler.audit.side_effect = PermissionError("Access denied")

        with patch("abso.core.auditor._get_handlers", return_value=[handler]):
            auditor = ConfigurationAuditor()
            issues = auditor.audit_all()

        assert len(issues) == 1
        assert "permission denied" in issues[0].title.lower()

    def test_audit_all_handles_os_error(self):
        """Test audit_all handles OSError gracefully."""
        handler = MagicMock()
        handler.__class__.__name__ = "TestHandler"
        handler.audit.side_effect = OSError("Registry error")

        with patch("abso.core.auditor._get_handlers", return_value=[handler]):
            auditor = ConfigurationAuditor()
            issues = auditor.audit_all()

        assert len(issues) == 1
        assert "os error" in issues[0].title.lower()

    def test_audit_all_handles_value_error(self):
        """Test audit_all handles ValueError gracefully."""
        handler = MagicMock()
        handler.__class__.__name__ = "TestHandler"
        handler.audit.side_effect = ValueError("Invalid value")

        with patch("abso.core.auditor._get_handlers", return_value=[handler]):
            auditor = ConfigurationAuditor()
            issues = auditor.audit_all()

        assert len(issues) == 1
        assert "data error" in issues[0].title.lower()

    def test_audit_all_empty_handlers(self):
        """Test audit_all with no handlers returns empty list."""
        with patch("abso.core.auditor._get_handlers", return_value=[]):
            auditor = ConfigurationAuditor()
            issues = auditor.audit_all()

        assert issues == []


class TestAuditCategory:
    """Tests for audit_category method."""

    def test_audit_category_unknown_raises(self):
        """Test audit_category raises ValueError for unknown category."""
        with patch("abso.core.auditor._get_handlers", return_value=[]):
            auditor = ConfigurationAuditor()

            with pytest.raises(ValueError) as exc_info:
                auditor.audit_category("unknown_category")

            assert "Unknown category" in str(exc_info.value)

    def test_audit_category_windows(self):
        """Test audit_category for windows category."""
        mock_handler = MagicMock()
        mock_handler.audit.return_value = [
            Issue(
                title="Windows Issue",
                severity="info",
                current_value="a",
                optimal_value="b",
                category="windows",
            )
        ]

        with (patch("abso.core.auditor._get_handlers", return_value=[]),
              patch("abso.settings.windows.WindowsSettingsHandler", return_value=mock_handler)):
            auditor = ConfigurationAuditor()
            issues = auditor.audit_category("windows")

        assert len(issues) == 1
        assert issues[0].category == "windows"

    def test_audit_category_case_insensitive(self):
        """Test audit_category is case-insensitive."""
        mock_handler = MagicMock()
        mock_handler.audit.return_value = []

        with patch("abso.core.auditor._get_handlers", return_value=[]):
            auditor = ConfigurationAuditor()

            # These should all work (not raise)
            for category in ["WINDOWS", "Windows", "windows"]:
                with patch("abso.settings.windows.WindowsSettingsHandler", return_value=mock_handler):
                    try:
                        auditor.audit_category(category)
                    except ValueError:
                        pytest.fail(f"audit_category should accept '{category}'")


class TestIssueModel:
    """Tests for Issue dataclass."""

    def test_issue_creation(self):
        """Test Issue can be created with all fields."""
        issue = Issue(
            title="Test Title",
            severity="critical",
            current_value="current",
            optimal_value="optimal",
            explanation="explanation",
            category="category",
        )

        assert issue.title == "Test Title"
        assert issue.severity == "critical"
        assert issue.current_value == "current"
        assert issue.optimal_value == "optimal"
        assert issue.explanation == "explanation"
        assert issue.category == "category"

    def test_issue_default_values(self):
        """Test Issue default values."""
        issue = Issue(
            title="Test",
            severity="info",
            current_value="a",
            optimal_value="b",
        )

        assert issue.explanation is None
        assert issue.category == "general"

    def test_issue_severity_values(self):
        """Test Issue accepts valid severity values."""
        for severity in ["critical", "warning", "info"]:
            issue = Issue(
                title="Test",
                severity=severity,
                current_value="a",
                optimal_value="b",
            )
            assert issue.severity == severity
