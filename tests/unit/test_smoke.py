"""Smoke test to verify pytest setup with moto, pytest-cov, and pytest-asyncio."""

from __future__ import annotations

from typing import Any

import pytest


@pytest.mark.unit
def test_moto_s3_mock(s3_client: Any) -> None:
    """Verify moto correctly mocks S3 operations."""
    s3_client.create_bucket(Bucket="test-bucket")
    response = s3_client.list_buckets()
    bucket_names = [b["Name"] for b in response["Buckets"]]
    assert "test-bucket" in bucket_names


@pytest.mark.unit
async def test_async_support() -> None:
    """Verify pytest-asyncio is configured and async tests run."""
    result = await _async_helper()
    assert result == 42


async def _async_helper() -> int:
    return 42
