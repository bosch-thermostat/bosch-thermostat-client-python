"""Behaviour tests for the XMPP dispatch engine.

These exercise the paths a real gateway drives and that the structural tests
(hasattr / source-text checks) cannot reach: a 204 reply to a PUT, a reply
carrying no Seq-No header at all (NEFIT), an empty payload, and a late reply
belonging to a different path.
"""

import asyncio
from unittest.mock import MagicMock, patch

import pytest

from bosch_thermostat_client.connectors.ivt import IVTXMPPConnector
from bosch_thermostat_client.connectors.nefit import NefitConnector
from bosch_thermostat_client.connectors.xmpp import _PendingRequest
from bosch_thermostat_client.exceptions import (
    DeviceException,
    EncryptionException,
    FailedAuthException,
    MsgException,
)

_PATCH_TARGET = "bosch_thermostat_client.connectors.xmpp.BoschClientXMPP"


def _make(cls=IVTXMPPConnector, decrypt=None):
    client = MagicMock()
    client.plugin = {}
    encryption = MagicMock()
    if decrypt is not None:
        encryption.json_decrypt.side_effect = decrypt
    with patch(_PATCH_TARGET, return_value=client):
        connector = cls(
            host="SERIAL",
            encryption=encryption,
            access_key="ACCESSKEY",
        )
    return connector, client


def _pending(connector, seq, method, path):
    future = asyncio.get_running_loop().create_future()
    connector._pending = {seq: _PendingRequest(future=future, method=method, path=path)}
    return future


# ---------------------------------------------------------------------------
# Blocker 1: a successful PUT answers 204 with headers only
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_put_204_resolves_true_without_decrypting():
    """A 204 carries no body; the last line is a header, not a payload."""
    connector, _ = _make()
    future = _pending(connector, 0, "put", "/heatingCircuits/hc1/temperatureRoomManual")

    connector.main_listener(
        {
            "type": "chat",
            "body": (
                "HTTP/1.0 204 No Content\r\r"
                "Seq-No: 0\r\r"
                "Content-Type: application/json\r\r"
                "Content-Length: 0\r\r"
            ),
        }
    )

    assert future.done(), "204 reply did not resolve the pending PUT"
    assert await future is True
    connector._encryption.json_decrypt.assert_not_called()


@pytest.mark.asyncio
async def test_put_204_without_seq_no_resolves_true():
    """Same, on a gateway that echoes no Seq-No (NEFIT)."""
    connector, _ = _make(cls=NefitConnector)
    future = _pending(connector, 3, "put", "/ecus/rrc/uiStatus")

    connector.main_listener(
        {"type": "chat", "body": "HTTP/1.0 204 No Content\r\rContent-Length: 0\r\r"}
    )

    assert future.done()
    assert await future is True


# ---------------------------------------------------------------------------
# Blocker 3: NEFIT replies carry no Seq-No header
# ---------------------------------------------------------------------------


def test_nefit_build_message_sends_no_seq_no():
    """Documents why the no-Seq-No fallback has to exist."""
    connector, _ = _make(cls=NefitConnector)
    body = connector._build_message(method="get", path="/ecus/rrc/uiStatus")
    assert "Seq-No" not in body


@pytest.mark.asyncio
async def test_reply_without_seq_no_resolves_by_path():
    """A reply with no Seq-No matches the pending request by payload id."""
    payload = {"id": "/ecus/rrc/uiStatus", "value": "ok"}
    connector, _ = _make(cls=NefitConnector, decrypt=lambda _: payload)
    future = _pending(connector, 7, "get", "/ecus/rrc/uiStatus")

    connector.main_listener(
        {
            "type": "chat",
            "body": "HTTP/1.0 200 OK\r\rContent-Type: application/json\r\r\r\rENCRYPTED",
        }
    )

    assert future.done(), "reply without Seq-No was dropped"
    assert await future == payload


@pytest.mark.asyncio
async def test_reply_without_seq_no_for_other_path_is_ignored():
    """A late answer for /a must not resolve a pending GET for /b."""
    payload = {"id": "/gateway/uuid", "value": "1"}
    connector, _ = _make(cls=NefitConnector, decrypt=lambda _: payload)
    future = _pending(connector, 7, "get", "/gateway/versionFirmware")

    connector.main_listener(
        {"type": "chat", "body": "HTTP/1.0 200 OK\r\r\r\rENCRYPTED"}
    )

    assert not future.done(), "reply for a different path resolved the request"


@pytest.mark.asyncio
async def test_seq_no_zero_fallback_checks_path():
    """The Seq-No 0 fallback must not hand /a's answer to a GET for /b."""
    payload = {"id": "/gateway/uuid", "value": "1"}
    connector, _ = _make(decrypt=lambda _: payload)
    connector._last_timeout_seq = -1
    future = _pending(connector, 4, "get", "/gateway/versionFirmware")

    connector.main_listener(
        {"type": "chat", "body": "HTTP/1.0 200 OK\r\rSeq-No: 0\r\r\r\rENCRYPTED"}
    )

    assert not future.done(), "Seq-No 0 fallback resolved the wrong request"


# ---------------------------------------------------------------------------
# An empty payload must not become a True result for a GET
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_empty_get_payload_does_not_resolve_true():
    """`{}` used to resolve a GET with True, so the caller's .get() blew up."""
    connector, _ = _make(decrypt=lambda _: {})
    future = _pending(connector, 1, "get", "/gateway/uuid")

    connector.main_listener(
        {"type": "chat", "body": "HTTP/1.0 200 OK\r\rSeq-No: 1\r\r\r\rENCRYPTED"}
    )

    assert future.done()
    assert await future is None


@pytest.mark.asyncio
async def test_get_with_empty_response_raises_device_exception():
    connector, _ = _make()
    with patch.object(connector, "_request", return_value=None) as request:
        request.return_value = None

        async def _none(*_, **__):
            return None

        connector._request = _none
        with pytest.raises(DeviceException):
            await connector.get("/gateway/uuid")


# ---------------------------------------------------------------------------
# Exceptions that must reach the consumer
# ---------------------------------------------------------------------------


def test_failed_auth_is_not_a_device_exception():
    """A wrong access key must survive the `except DeviceException` handlers."""
    from bosch_thermostat_client.exceptions import (
        BoschException,
        FirmwareException,
        UnknownDevice,
    )

    for exc in (FailedAuthException, FirmwareException, UnknownDevice):
        assert issubclass(exc, BoschException)
        assert not issubclass(exc, DeviceException), f"{exc.__name__} is swallowed"


@pytest.mark.asyncio
async def test_failed_auth_propagates_through_get():
    """get() retries transport errors but must not swallow an auth failure."""
    connector, _ = _make()

    async def _raise(*_, **__):
        raise FailedAuthException("Can't authorize to XMPP server.")

    connector._request = _raise
    with pytest.raises(FailedAuthException):
        await connector.get("/gateway/uuid")


@pytest.mark.asyncio
async def test_failed_auth_reaches_check_connection():
    """gateway.check_connection catches DeviceException; auth must get past it."""
    with patch(_PATCH_TARGET, return_value=MagicMock(plugin={})):
        from bosch_thermostat_client.gateway.ivt import IVTGateway

        gateway = IVTGateway(
            session_type="XMPP", host="SERIAL", access_token="ACCESSTOKEN01"
        )

    async def _raise(*_, **__):
        raise FailedAuthException("Can't authorize to XMPP server.")

    gateway._connector.get = _raise
    gateway._initialized = True
    gateway._db = {"gateway": {"uuid": "/gateway/uuid"}}
    with pytest.raises(FailedAuthException):
        await gateway.check_connection()


@pytest.mark.asyncio
async def test_encryption_failure_is_a_device_exception():
    """EncryptionException must not escape get()/put() unguarded."""
    connector, _ = _make()

    async def _raise(*_, **__):
        raise EncryptionException("Can't decrypt")

    connector._request = _raise
    with pytest.raises(DeviceException):
        await connector.get("/gateway/uuid")
    with pytest.raises(DeviceException):
        await connector.put("/gateway/uuid", 1)


@pytest.mark.asyncio
async def test_http_error_status_raises_msg_exception():
    connector, _ = _make()
    future = _pending(connector, 2, "get", "/gateway/uuid")

    connector.main_listener(
        {"type": "chat", "body": "HTTP/1.0 403 Forbidden\r\rSeq-No: 2\r\r"}
    )

    assert future.done()
    with pytest.raises(MsgException):
        await future


@pytest.mark.asyncio
async def test_http_401_raises_failed_auth():
    """A rejected access key must reach the consumer as a reauth signal."""
    connector, _ = _make()
    future = _pending(connector, 5, "get", "/gateway/uuid")

    connector.main_listener(
        {"type": "chat", "body": "HTTP/1.0 401 Unauthorized\r\rSeq-No: 5\r\r"}
    )

    assert future.done()
    with pytest.raises(FailedAuthException):
        await future


@pytest.mark.asyncio
async def test_failing_get_releases_the_lock_between_attempts():
    """A PUT must not queue behind the whole retry budget of a failing GET.

    Two GET attempts, each with its own timeout, so the request lock is taken
    and released twice - a PUT waiting on it gets in after one timeout, not
    after both.
    """
    connector, client = _make()
    connector._auth_success = True
    client.send_message = MagicMock()
    acquired_during_retry = asyncio.Event()

    async def waiter():
        await connector._request_lock.acquire()
        acquired_during_retry.set()
        connector._request_lock.release()

    with patch("bosch_thermostat_client.connectors.xmpp.REQUEST_TIMEOUT", 0.01):
        task = asyncio.create_task(waiter())
        with pytest.raises(DeviceException):
            await connector.get("/slow")
        await asyncio.wait_for(task, timeout=1)

    assert acquired_during_retry.is_set()
    # Both attempts were sent, so the retry really did run.
    assert client.send_message.call_count == 2


# ---------------------------------------------------------------------------
# close() must not wait for a session that never started
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_close_without_connection_returns_immediately():
    connector, client = _make()
    client.is_connected.return_value = False

    await asyncio.wait_for(connector.close(), timeout=1)

    client.cancel_connection_attempt.assert_called_once()
    client.disconnect.assert_not_called()


@pytest.mark.asyncio
async def test_connect_timeout_cancels_the_attempt():
    """Otherwise slixmpp keeps retrying in the background for ever."""
    connector, client = _make()
    client.is_connected.return_value = False
    connector._auth_success = False

    with patch("bosch_thermostat_client.connectors.xmpp.TIMEOUT", 0.01):
        with pytest.raises(DeviceException):
            await connector._request(method="get", path="/gateway/uuid")

    client.cancel_connection_attempt.assert_called()
