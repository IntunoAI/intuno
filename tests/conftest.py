"""Pytest configuration: mark live integration tests so CI can skip them."""

import pytest


def pytest_collection_modifyitems(config, items):
    """Auto-mark tests in files that require a running backend as 'integration'."""
    integration_files = {
        "test_sdk_integration.py",
        "test_user_session.py",
        "test_economy.py",
        "test_workflow.py",
        "test_new_orchestrator.py",
    }
    for item in items:
        if item.path and item.path.name in integration_files:
            item.add_marker(pytest.mark.integration)


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "integration: marks tests that need a running backend (deselect with '-m \"not integration\"')",
    )
