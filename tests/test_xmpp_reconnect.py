"""RED test stubs for Phase 3 reconnect hardening. All tests are
expected to FAIL before Plan 03-01 implementation.

Covers requirements reconnect logic.

connected_event and _auth_success are not cleared on session_end, causing
         stale state when the XMPP session restarts after a disconnect.
main_listener is registered unconditionally in __init__ with no dedup guard,
         so a reconnect cycle that re-instantiates the connector would accumulate
         duplicate "message" handlers.
"""

import asyncio

import pytest
from unittest.mock import MagicMock, patch

from bosch_thermostat_client.connectors.ivt import IVTXMPPConnector
from bosch_thermostat_client.connectors.xmpp import XMPPBaseConnector


_PATCH_TARGET = "bosch_thermostat_client.connectors.xmpp.BoschClientXMPP"


def _make_ivt_connector():
    """Return an IVTXMPPConnector with BoschClientXMPP patched to a MagicMock."""
    mock_client = MagicMock()
    mock_client.plugin = {}
    mock_encryption = MagicMock()
    with patch(_PATCH_TARGET, return_value=mock_client):
        connector = IVTXMPPConnector(
            host="SERIALNUMBER",
            access_key="ACCESSKEY01",
            encryption=mock_encryption,
        )
    return connector, mock_client


def test_reset_events_method_exists():
    """Structural: XMPPBaseConnector must expose a _reset_events() method.

    RED until _reset_events is added to XMPPBaseConnector.
    After GREEN: _reset_events() clears connected_event and resets _auth_success.
    """
    assert hasattr(XMPPBaseConnector, "_reset_events") and callable(
        getattr(XMPPBaseConnector, "_reset_events")
    ), "XMPPBaseConnector has no _reset_events method"


@pytest.mark.asyncio
async def test_connected_event_cleared_after_session_end():
    """Unit: connected_event must be cleared when the session ends.

    RED until session_end calls _reset_events() (or equivalent).
    After GREEN: waiting on connected_event will block until the next session_start.
    """
    connector, _mock_client = _make_ivt_connector()
    # Simulate a previously connected session
    connector.connected_event.set()
    connector._auth_success = True

    await connector.session_end(event=None)

    assert not connector.connected_event.is_set(), (
        "connected_event still set after session_end"
    )


@pytest.mark.asyncio
async def test_auth_success_reset_after_session_end():
    """Unit: _auth_success must be reset to False when the session ends.

    RED until session_end resets _auth_success.
    After GREEN: a reconnect attempt will re-authenticate rather than skip the auth gate.
    """
    connector, _mock_client = _make_ivt_connector()
    connector._auth_success = True

    await connector.session_end(event=None)

    assert not connector._auth_success, (
        "_auth_success still True after session_end"
    )


def test_main_listener_registered_once():
    """Regression guard: main_listener is NOT registered in __init__;
    _register_message_handler() registers it exactly once via del+add.

    After fix, registration happens in session_start (not __init__).
    This test documents the session_start-based invariant.
    """
    connector, mock_client = _make_ivt_connector()

    # After __init__, message handler must NOT be pre-registered
    message_registrations_at_init = [
        c for c in mock_client.add_event_handler.call_args_list
        if c.args and c.args[0] == "message"
    ]
    assert len(message_registrations_at_init) == 0, (
        f"main_listener registered {len(message_registrations_at_init)} times in __init__; "
        "expected 0"
    )

    # Calling _register_message_handler() must result in exactly one add
    mock_client.reset_mock()
    connector._register_message_handler()
    message_registrations_after_call = [
        c for c in mock_client.add_event_handler.call_args_list
        if c.args and c.args[0] == "message"
    ]
    assert len(message_registrations_after_call) == 1, (
        f"_register_message_handler() produced {len(message_registrations_after_call)} "
        "add_event_handler('message') calls, expected 1"
    )


def test_no_duplicate_main_listener_after_reconnect():
    """Unit: XMPPBaseConnector must expose _register_message_handler for dedup.

    RED until _register_message_handler is added to XMPPBaseConnector.
    After GREEN: calling _register_message_handler twice must not produce a second
    "message" event handler — the method removes any existing handler before re-adding.
    """
    connector, mock_client = _make_ivt_connector()
    assert hasattr(connector, "_register_message_handler"), (
        "XMPPBaseConnector has no _register_message_handler method"
    )
