"""Reliability hardening verification for Phase 7.

Tests the sequence-aware fallback for XMPP responses and exception hierarchy.
"""

import asyncio
from unittest.mock import MagicMock, patch
import pytest

from bosch_thermostat_client.connectors.ivt import IVTXMPPConnector
from bosch_thermostat_client.exceptions import DeviceException, MsgException, EncryptionException


@pytest.mark.asyncio
async def test_rel01_seq_no_matching_ignores_late_responses():
    """Verify that Seq-No: 0 responses are ignored if they match a timed-out sequence."""
    mock_encryption = MagicMock()
    # Mock json_decrypt to return a fixed value
    mock_encryption.json_decrypt.return_value = {"value": "ok"}
    
    with patch("bosch_thermostat_client.connectors.xmpp.BoschClientXMPP"):
        connector = IVTXMPPConnector(
            host="SERIAL",
            encryption=mock_encryption,
            access_key="ACCESSKEY",
        )

    # Case 1: Response matches a sequence that is <= _last_timeout_seq
    connector._last_timeout_seq = 10
    future_late = asyncio.get_running_loop().create_future()
    connector._pending = {10: future_late}
    
    # Simulate receiving a message with Seq-No: 0
    # The message body must look like a valid HTTP response for the listener to process it
    late_msg = {
        "type": "chat",
        "body": "HTTP/1.1 200 OK\nSeq-No: 0\n\n{\"value\": \"ignored\"}"
    }
    
    connector.main_listener(late_msg)
    
    assert not future_late.done(), "Future should NOT be completed for late response"
    assert 10 in connector._pending, "Sequence 10 should still be in pending"

    # Case 2: Response matches a sequence that is > _last_timeout_seq
    connector._last_timeout_seq = 9
    future_valid = asyncio.get_running_loop().create_future()
    connector._pending = {10: future_valid}
    
    valid_msg = {
        "type": "chat",
        "body": "HTTP/1.1 200 OK\nSeq-No: 0\n\n{\"value\": \"ok\"}"
    }
    
    connector.main_listener(valid_msg)
    
    assert future_valid.done(), "Future SHOULD be completed for valid response"
    assert await future_valid == {"value": "ok"}


def test_rel02_msg_exception_inheritance():
    """Verify MsgException is a subclass of DeviceException and caught by its handlers."""
    # 1. Structural check
    assert issubclass(MsgException, DeviceException)
    
    # 2. Behavioral check: caught by DeviceException handler
    try:
        raise MsgException("test timeout")
    except DeviceException as e:
        assert str(e) == "test timeout"
        caught = True
    except Exception:
        caught = False
        
    assert caught, "MsgException should have been caught by DeviceException handler"

@pytest.mark.asyncio
async def test_rel03_session_end_sets_last_timeout_seq():
    """Verify that session_end sets _last_timeout_seq to the highest pending sequence."""
    mock_encryption = MagicMock()
    with patch("bosch_thermostat_client.connectors.xmpp.BoschClientXMPP"):
        connector = IVTXMPPConnector(
            host="SERIAL",
            encryption=mock_encryption,
            access_key="ACCESSKEY",
        )
    
    # Setup pending futures
    fut1 = asyncio.get_running_loop().create_future()
    fut2 = asyncio.get_running_loop().create_future()
    connector._pending = {5: fut1, 12: fut2}
    connector._last_timeout_seq = 0
    
    # Trigger session_end
    await connector.session_end()
    
    assert connector._last_timeout_seq == 12
    assert fut1.done()
    assert fut2.done()
    
    # Retrieve all exceptions to keep test output clean
    with pytest.raises(MsgException, match="XMPP session ended"):
        await fut1
    with pytest.raises(MsgException, match="XMPP session ended"):
        await fut2
        
    assert not connector._pending, "Pending dict should be cleared"
