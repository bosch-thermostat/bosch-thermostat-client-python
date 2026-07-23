
import pytest
from unittest.mock import patch, MagicMock, AsyncMock as CoroutineMock
from aiohttp import ClientSession
from bosch_thermostat_client.gateway.ivt import IVTGateway as Gateway
from bosch_thermostat_client.errors import Response404Error, ResponseError
from bosch_thermostat_client.const import HTTP, GATEWAY


@pytest.mark.asyncio
async def test_get_success():
    async with ClientSession() as session:
        gateway = Gateway(session=session, session_type=HTTP, host='bla', access_token='aaa', password='xxx')
        with patch.object(gateway._connector, 'get', new=CoroutineMock(return_value={'id': '/gateway/uuid'})) as mocked_get:
            gtw_resp = await gateway.get('/gateway/uuid')
            mocked_get.assert_called_once_with('/gateway/uuid')
            assert gtw_resp == {'id': '/gateway/uuid'}


@pytest.mark.asyncio
async def test_get_notfound():
    async with ClientSession() as session:
        from bosch_thermostat_client.exceptions import DeviceException
        gateway = Gateway(session=session, session_type=HTTP, host='bla', access_token='aaa', password='xxx')
        with patch.object(gateway._connector, 'get', new=CoroutineMock(side_effect=DeviceException("Path does not exist: /gateway/uuid"))) as mocked_get:
            gtw_resp = await gateway.get('/gateway/uuid')
            mocked_get.assert_called_once_with('/gateway/uuid')
            assert gtw_resp is None


@pytest.mark.asyncio
async def test_get_invalidjson():
    async with ClientSession() as session:
        gateway = Gateway(session=session, session_type=HTTP, host='bla', access_token='aaa', password='xxx')
        with patch.object(gateway._connector, 'get', new=CoroutineMock(return_value={'id': 'invalid'})) as mocked_get:
            gtw_resp = await gateway.get('/gateway/uuid')
            assert gtw_resp == {'id': 'invalid'}


@pytest.mark.asyncio
async def test_update_info():
    async with ClientSession() as session:
        gateway = Gateway(session=session, session_type=HTTP, host='bla', access_token='aaa', password='xxx')
        # Patch gateway._connector.get because _update_info calls it
        with patch.object(gateway._connector, 'get', new=CoroutineMock(return_value={'id': '/gateway/uuid', 'value':'test_gtw_update'})) as mocked_get:
            await gateway._update_info({'uuid': '/gateway/uuid'})
            assert gateway._data[GATEWAY]['uuid'] == 'test_gtw_update'
