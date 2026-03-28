"""Shared pytest fixtures for bosch-thermostat-client tests."""
import pytest
from unittest.mock import MagicMock


@pytest.fixture()
def mock_logger():
    """Return a MagicMock to stand in for a module-level _LOGGER."""
    return MagicMock()


@pytest.fixture()
def mock_slixmpp_client():
    """Return a MagicMock that mimics a BoschClientXMPP instance.

    Attributes
    ----------
    plugin : dict
        Empty dict mirroring slixmpp's plugin registry.
    register_plugin : MagicMock callable
        Records all register_plugin(...) invocations.
    """
    client = MagicMock()
    client.plugin = {}
    return client
