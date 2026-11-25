"""A GET that gets no answer is tried again; a PUT, and any other failure, is not.

Measured on an iCom_low_CAN_v1 gateway on firmware 01.03.00, polled every 20 s: the
first request after the pause went unanswered 30 times in 120, the one after it 5 times
in 30.
"""

import asyncio
from unittest.mock import MagicMock

import pytest
from aiohttp.client_exceptions import ClientConnectionError

from bosch_thermostat_client.connectors import HttpConnector
from bosch_thermostat_client.connectors.http import GET_TRIES
from bosch_thermostat_client.exceptions import DeviceConnectionError, DeviceException


class Answer:
    def __init__(self, outcome):
        self.outcome = outcome
        self.status = 200
        self.content_type = "application/json"

    async def __aenter__(self):
        if isinstance(self.outcome, BaseException):
            raise self.outcome
        return self

    async def __aexit__(self, *exc):
        return False

    async def json(self, loads):
        return loads(self.outcome)

    async def text(self):
        return ""


class Session:
    """Gives each request the next outcome: an exception raised, or a body answered."""

    def __init__(self, *outcomes):
        self.outcomes = list(outcomes)
        self.gets = 0
        self.puts = 0

    def get(self, url, **kwargs):
        self.gets += 1
        return Answer(self.outcomes.pop(0))

    def put(self, url, **kwargs):
        self.puts += 1
        return Answer(self.outcomes.pop(0))


def connector(session):
    encryption = MagicMock()
    encryption.json_decrypt = lambda raw: raw
    encryption.encrypt = lambda raw: raw
    return HttpConnector("192.0.2.1", encryption, loop=session)


@pytest.mark.asyncio
async def test_a_get_unanswered_is_tried_again():
    session = Session(asyncio.TimeoutError(), asyncio.TimeoutError(), '{"value": 1}')
    assert await connector(session).get("/gateway/uuid") == '{"value": 1}'
    assert session.gets == 3


@pytest.mark.asyncio
async def test_a_get_never_answered_says_so_after_its_tries():
    session = Session(*[asyncio.TimeoutError() for _ in range(GET_TRIES)])
    with pytest.raises(DeviceConnectionError):
        await connector(session).get("/gateway/uuid")
    assert session.gets == GET_TRIES


@pytest.mark.asyncio
async def test_a_get_refused_is_not_tried_again():
    session = Session(ClientConnectionError("refused"), '{"value": 1}')
    with pytest.raises(DeviceConnectionError):
        await connector(session).get("/gateway/uuid")
    assert session.gets == 1


@pytest.mark.asyncio
async def test_a_put_unanswered_is_never_sent_again():
    session = Session(asyncio.TimeoutError(), "")
    with pytest.raises(DeviceException):
        await connector(session).put(
            "/heatingCircuits/hc1/temperatureLevels/normal", 21
        )
    assert session.puts == 1
