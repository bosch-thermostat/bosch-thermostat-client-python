"""Verification of Gateway async context manager support.

All tests except test_close_still_callable_directly are expected to FAIL
before Plan 04-01 adds __aenter__ / __aexit__ to BaseGateway.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

_PATCH_TARGET = "bosch_thermostat_client.connectors.xmpp.BoschClientXMPP"


def _make_gateway():
    with patch(_PATCH_TARGET, return_value=MagicMock(plugin={})):
        from bosch_thermostat_client.gateway.ivt import IVTGateway
        gw = IVTGateway(
            session_type="XMPP",
            host="SERIALNUMBER",
            access_token="ACCESSTOKEN01",
        )
    gw.close = AsyncMock()
    return gw


@pytest.mark.asyncio
async def test_aenter_returns_self():
    """__aenter__ must return the gateway instance itself.

    RED until __aenter__ is added to BaseGateway — AttributeError on 'async with'.
    After GREEN: 'async with gw as entered_gw' binds entered_gw to the same object as gw.
    """
    gw = _make_gateway()
    async with gw as entered_gw:
        assert entered_gw is gw, "__aenter__ must return self"


@pytest.mark.asyncio
async def test_context_manager_calls_close_on_exit():
    """__aexit__ must call close() when the async with block exits normally.

    RED until __aexit__ is added to BaseGateway — AttributeError on 'async with'.
    After GREEN: gw.close is awaited exactly once on normal block exit.
    """
    gw = _make_gateway()
    async with gw:
        pass
    gw.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_context_manager_calls_close_on_exception():
    """__aexit__ must call close() even when the block raises.

    RED until __aexit__ is added to BaseGateway — AttributeError on 'async with'.
    After GREEN: gw.close is awaited exactly once even if the block raises RuntimeError.
    """
    gw = _make_gateway()
    with pytest.raises(RuntimeError):
        async with gw:
            raise RuntimeError("simulated error")
    gw.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_close_still_callable_directly():
    """close() must remain callable without async with.

    GREEN immediately — close() already exists on BaseGateway.
    This test guards against accidental regression in Plan 04-01.
    """
    gw = _make_gateway()
    await gw.close()
    gw.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_exception_not_suppressed():
    """__aexit__ must not suppress exceptions raised inside the async with block.

    RED until __aexit__ is added to BaseGateway — AttributeError on 'async with'.
    After GREEN: RuntimeError raised inside the block propagates to the caller.
    """
    gw = _make_gateway()
    with pytest.raises(RuntimeError):
        async with gw:
            raise RuntimeError("exception must propagate")
