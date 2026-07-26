"""Unit tests for AuditLogger — before/after logging, tail, clear."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from cloudshellgpt.audit import AuditLogger
from cloudshellgpt.executor import ExecutionResult

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def audit_logger(tmp_path: Path) -> AuditLogger:
    """Provide an AuditLogger backed by a temporary log file."""
    return AuditLogger(log_path=tmp_path / "test_audit.log")


# ---------------------------------------------------------------------------
# Tests: Initialization
# ---------------------------------------------------------------------------


class TestAuditLoggerInit:
    """Verify AuditLogger initialization."""

    @pytest.mark.unit
    def test_creates_parent_directory(self, tmp_path: Path) -> None:
        """AuditLogger creates parent directories on init."""
        log_path = tmp_path / "subdir" / "nested" / "audit.log"
        logger = AuditLogger(log_path=log_path)
        assert logger.log_path == log_path
        assert log_path.parent.exists()

    @pytest.mark.unit
    def test_default_path_is_set(self) -> None:
        """AuditLogger has a default path at ~/.csgpt/audit.log."""
        assert AuditLogger.DEFAULT_PATH == Path.home() / ".csgpt" / "audit.log"


# ---------------------------------------------------------------------------
# Tests: log_before
# ---------------------------------------------------------------------------


class TestLogBefore:
    """Verify log_before writes pre-execution entries."""

    @pytest.mark.unit
    def test_log_before_returns_entry_id(self, audit_logger: AuditLogger) -> None:
        """log_before returns a hex entry_id string."""
        entry_id = audit_logger.log_before(
            intent="list buckets",
            command="aws s3 ls",
            risk="low",
            dry_run=False,
        )
        assert entry_id is not None
        assert len(entry_id) == 32  # uuid4 hex

    @pytest.mark.unit
    def test_log_before_writes_json_line(self, audit_logger: AuditLogger) -> None:
        """log_before writes a valid JSON entry to the log file."""
        audit_logger.log_before(
            intent="list buckets",
            command="aws s3 ls",
            risk="low",
            dry_run=False,
        )
        content = audit_logger.log_path.read_text(encoding="utf-8")
        entry = json.loads(content.strip())
        assert entry["phase"] == "before"
        assert entry["intent"] == "list buckets"
        assert entry["command"] == "aws s3 ls"
        assert entry["risk_level"] == "low"
        assert entry["dry_run"] is False
        assert "timestamp" in entry
        assert "user" in entry

    @pytest.mark.unit
    def test_log_before_dry_run_true(self, audit_logger: AuditLogger) -> None:
        """log_before correctly records dry_run=True."""
        audit_logger.log_before(
            intent="delete bucket",
            command="aws s3api delete-bucket --bucket prod",
            risk="high",
            dry_run=True,
        )
        content = audit_logger.log_path.read_text(encoding="utf-8")
        entry = json.loads(content.strip())
        assert entry["dry_run"] is True
        assert entry["risk_level"] == "high"

    @pytest.mark.unit
    def test_log_before_handles_io_error_gracefully(self, tmp_path: Path) -> None:
        """log_before returns None when the log file cannot be written."""
        # Point to a path that can't be written (use a directory name as file)
        log_path = tmp_path / "blocked_dir"
        log_path.mkdir()
        # On Windows, writing to a directory path fails
        logger = AuditLogger(log_path=log_path)
        result = logger.log_before("test", "aws s3 ls", "low", False)
        assert result is None


# ---------------------------------------------------------------------------
# Tests: log_after
# ---------------------------------------------------------------------------


class TestLogAfter:
    """Verify log_after writes post-execution entries."""

    @pytest.mark.unit
    def test_log_after_writes_result(self, audit_logger: AuditLogger) -> None:
        """log_after writes execution result details."""
        entry_id = audit_logger.log_before(
            intent="list buckets",
            command="aws s3 ls",
            risk="low",
            dry_run=False,
        )
        result = ExecutionResult(
            command="aws s3 ls",
            stdout='{"Buckets": []}',
            stderr="",
            exit_code=0,
            duration_ms=150,
            dry_run=False,
        )
        audit_logger.log_after(entry_id, result)

        lines = audit_logger.log_path.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == 2
        after_entry = json.loads(lines[1])
        assert after_entry["phase"] == "after"
        assert after_entry["entry_id"] == entry_id
        assert after_entry["exit_code"] == 0
        assert after_entry["duration_ms"] == 150
        assert after_entry["stdout_size"] == len('{"Buckets": []}')
        assert after_entry["stderr"] is None  # no stderr for success

    @pytest.mark.unit
    def test_log_after_records_error(self, audit_logger: AuditLogger) -> None:
        """log_after records stderr and error for failed commands."""
        entry_id = audit_logger.log_before("delete", "aws s3 rm s3://prod", "high", False)
        result = ExecutionResult(
            command="aws s3 rm s3://prod",
            stdout="",
            stderr="AccessDenied",
            exit_code=1,
            duration_ms=200,
            dry_run=False,
            error="AccessDenied",
        )
        audit_logger.log_after(entry_id, result)

        lines = audit_logger.log_path.read_text(encoding="utf-8").strip().split("\n")
        after_entry = json.loads(lines[1])
        assert after_entry["stderr"] == "AccessDenied"
        assert after_entry["error"] == "AccessDenied"

    @pytest.mark.unit
    def test_log_after_with_none_entry_id(self, audit_logger: AuditLogger) -> None:
        """log_after handles None entry_id (pre-log failed)."""
        result = ExecutionResult(
            command="aws s3 ls",
            stdout="",
            stderr="",
            exit_code=0,
            duration_ms=50,
            dry_run=False,
        )
        audit_logger.log_after(None, result)
        content = audit_logger.log_path.read_text(encoding="utf-8")
        entry = json.loads(content.strip())
        assert entry["entry_id"] is None
        assert entry["phase"] == "after"


# ---------------------------------------------------------------------------
# Tests: log (convenience method)
# ---------------------------------------------------------------------------


class TestLogConvenience:
    """Verify the convenience log() method."""

    @pytest.mark.unit
    def test_log_without_result_writes_only_before(self, audit_logger: AuditLogger) -> None:
        """log() without result writes only the before entry."""
        audit_logger.log(
            intent="list",
            command="aws s3 ls",
            risk="low",
            dry_run=False,
        )
        content = audit_logger.log_path.read_text(encoding="utf-8").strip()
        lines = content.split("\n")
        assert len(lines) == 1
        entry = json.loads(lines[0])
        assert entry["phase"] == "before"

    @pytest.mark.unit
    def test_log_with_result_writes_both(self, audit_logger: AuditLogger) -> None:
        """log() with result writes both before and after entries."""
        result = ExecutionResult(
            command="aws s3 ls",
            stdout="output",
            stderr="",
            exit_code=0,
            duration_ms=100,
            dry_run=False,
        )
        audit_logger.log(
            intent="list",
            command="aws s3 ls",
            risk="low",
            dry_run=False,
            result=result,
        )
        lines = audit_logger.log_path.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == 2
        assert json.loads(lines[0])["phase"] == "before"
        assert json.loads(lines[1])["phase"] == "after"


# ---------------------------------------------------------------------------
# Tests: tail
# ---------------------------------------------------------------------------


class TestTail:
    """Verify tail() reads the last N entries."""

    @pytest.mark.unit
    def test_tail_empty_log(self, audit_logger: AuditLogger) -> None:
        """tail() returns empty list when log doesn't exist."""
        entries = audit_logger.tail()
        assert entries == []

    @pytest.mark.unit
    def test_tail_returns_last_n(self, audit_logger: AuditLogger) -> None:
        """tail(n) returns the last n entries."""
        for i in range(5):
            audit_logger.log_before(f"intent-{i}", f"aws s3 ls --page {i}", "low", False)

        entries = audit_logger.tail(3)
        assert len(entries) == 3
        assert entries[-1]["intent"] == "intent-4"
        assert entries[0]["intent"] == "intent-2"

    @pytest.mark.unit
    def test_tail_all_entries(self, audit_logger: AuditLogger) -> None:
        """tail() with n larger than entries returns all."""
        audit_logger.log_before("only one", "aws s3 ls", "low", False)
        entries = audit_logger.tail(100)
        assert len(entries) == 1

    @pytest.mark.unit
    def test_tail_handles_corrupt_json(self, audit_logger: AuditLogger) -> None:
        """tail() skips corrupt JSON lines without crashing."""
        audit_logger.log_before("valid", "aws s3 ls", "low", False)
        # Write corrupt line
        with audit_logger.log_path.open("a", encoding="utf-8") as f:
            f.write("this is not json\n")
        audit_logger.log_before("valid2", "aws ec2 describe-instances", "low", False)

        entries = audit_logger.tail(10)
        assert len(entries) == 2  # skipped corrupt line


# ---------------------------------------------------------------------------
# Tests: clear
# ---------------------------------------------------------------------------


class TestClear:
    """Verify clear() deletes the audit log."""

    @pytest.mark.unit
    def test_clear_removes_log_file(self, audit_logger: AuditLogger) -> None:
        """clear() removes the log file."""
        audit_logger.log_before("test", "aws s3 ls", "low", False)
        assert audit_logger.log_path.exists()
        audit_logger.clear()
        assert not audit_logger.log_path.exists()

    @pytest.mark.unit
    def test_clear_when_no_log_exists(self, audit_logger: AuditLogger) -> None:
        """clear() succeeds silently when log doesn't exist."""
        audit_logger.clear()  # Should not raise
        assert not audit_logger.log_path.exists()
