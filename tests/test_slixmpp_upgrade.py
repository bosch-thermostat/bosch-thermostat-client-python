"""Verification of the slixmpp 1.14.1 upgrade.

Ensures that the core XMPP dependency is correctly versioned, configured
with secure TLS defaults, and that asynchronous event handlers and 
keep-alive plugins are correctly registered and compatible with 
Python 3.14.
"""

import asyncio
import inspect
import slixmpp
from unittest.mock import MagicMock, patch
import pytest

from bosch_thermostat_client.connectors.client.slixmpp010 import BoschClientXMPP
from bosch_thermostat_client.connectors.xmpp import XMPPBaseConnector
from bosch_thermostat_client.connectors.ivt import IVTXMPPConnector


def test_slixmpp_version():
    """Verify that slixmpp 1.14.1 is installed in the environment."""
    assert slixmpp.__version__ == "1.14.1"


def test_force_starttls_enabled():
    """Verify that BoschClientXMPP explicitly enables force_starttls for security."""
    client = BoschClientXMPP(jid="test@test.com", password="password")
    # force_starttls is set in connect()
    with patch("slixmpp.ClientXMPP.connect"):
        client.connect()
    assert client.force_starttls is True


def test_async_event_handlers():
    """Verify that session lifecycle handlers are asynchronous coroutines."""
    assert inspect.iscoroutinefunction(XMPPBaseConnector.session_start)
    assert inspect.iscoroutinefunction(XMPPBaseConnector.session_end)


def test_xep0199_ping_registration():
    """Verify that XEP-0199 keep-alive plugin is registered with the correct parameters."""
    mock_client = MagicMock()
    mock_client.plugin = {}
    mock_encryption = MagicMock()

    with patch(
        "bosch_thermostat_client.connectors.xmpp.BoschClientXMPP",
        return_value=mock_client,
    ):
        connector = IVTXMPPConnector(
            host="SERIAL",
            encryption=mock_encryption,
            access_key="ACCESSKEY",
        )

    # Check for xep_0199 registration call
    expected_config = {"keepalive": True, "interval": 60, "timeout": 30}
    
    # Extract calls to register_plugin
    calls = [
        c for c in mock_client.register_plugin.call_args_list
        if c.args and c.args[0] == "xep_0199"
    ]
    
    assert len(calls) == 1, "XEP-0199 (Ping) plugin was not registered"
    
    # Verify the provided configuration matches the expected defaults
    actual_config = calls[0].args[1]
    assert actual_config == expected_config
