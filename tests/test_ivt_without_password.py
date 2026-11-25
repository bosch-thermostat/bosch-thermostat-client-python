import hashlib

import pytest
from aiohttp import ClientSession

from bosch_thermostat_client.const import HTTP
from bosch_thermostat_client.const.ivt import MAGIC_IVT
from bosch_thermostat_client.encryption import IVTEncryption
from bosch_thermostat_client.gateway.ivt import IVTGateway

TOKEN = "AbCd-EfGh-IjKl-MnOp"


@pytest.mark.asyncio
async def test_key_without_password_is_the_tokens_alone():
    async with ClientSession() as session:
        gateway = IVTGateway(
            session=session,
            session_type=HTTP,
            host="gateway.invalid",
            access_token=TOKEN,
        )
        token = TOKEN.replace("-", "")
        expected = (
            hashlib.md5(bytearray(token, "utf8") + MAGIC_IVT).hexdigest()
            + hashlib.md5(MAGIC_IVT).hexdigest()
        )
        assert gateway.access_key == expected


@pytest.mark.asyncio
async def test_key_without_password_encrypts_and_decrypts():
    async with ClientSession() as session:
        gateway = IVTGateway(
            session=session,
            session_type=HTTP,
            host="gateway.invalid",
            access_token=TOKEN,
        )
        encryption = IVTEncryption(gateway.access_key)
        assert encryption.json_decrypt(encryption.encrypt('{"value": 21.5}')) == {
            "value": 21.5
        }


@pytest.mark.asyncio
async def test_a_stored_key_is_used_as_given():
    stored = "00" * 32
    async with ClientSession() as session:
        gateway = IVTGateway(
            session=session,
            session_type=HTTP,
            host="gateway.invalid",
            access_token=TOKEN,
            access_key=stored,
        )
        assert gateway.access_key == stored


@pytest.mark.asyncio
async def test_a_password_still_makes_the_key():
    async with ClientSession() as session:
        gateway = IVTGateway(
            session=session,
            session_type=HTTP,
            host="gateway.invalid",
            access_token=TOKEN,
            password="secret",
        )
        assert gateway.access_key == IVTEncryption(TOKEN.replace("-", ""), "secret").key
