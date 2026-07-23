from typing import Any
import os
import click
import logging
from colorlog import ColoredFormatter
import aiohttp
import bosch_thermostat_client as bosch
from bosch_thermostat_client.const import XMPP, HTTP, OAUTH2
from bosch_thermostat_client.const.ivt import IVT, IVTAIR, BRUDERUS
from bosch_thermostat_client.const.nefit import NEFIT
from bosch_thermostat_client.const.easycontrol import EASYCONTROL
from bosch_thermostat_client.version import __version__
from bosch_thermostat_client.exceptions import FailedAuthException
from bosch_thermostat_client.gateway import Oauth2Gateway
import json
import asyncio
from functools import wraps
from pathlib import Path
from yaml import load

try:
    from yaml import CLoader as Loader
except ImportError:
    from yaml import Loader


_LOGGER = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)
fmt = "%(asctime)s %(levelname)s (%(threadName)s) [%(name)s] %(message)s"
datefmt = "%Y-%m-%d %H:%M:%S"
colorfmt = f"%(log_color)s{fmt}%(reset)s"
logging.getLogger().handlers[0].setFormatter(
    ColoredFormatter(
        colorfmt,
        datefmt=datefmt,
        reset=True,
        log_colors={
            "DEBUG": "cyan",
            "INFO": "green",
            "WARNING": "yellow",
            "ERROR": "red",
            "CRITICAL": "red",
        },
    )
)

def set_debug(debug: int) -> None:
    if debug == 0:
        logging.basicConfig(level=logging.INFO)
    if debug > 0:
        _LOGGER.info("Debug mode active")
        _LOGGER.debug(f"Lib version is {bosch.version}")
    if debug > 1:
        logging.getLogger("slixmpp").setLevel(logging.DEBUG)
        logging.getLogger("asyncio").setLevel(logging.DEBUG)
    else:
        logging.getLogger("slixmpp").setLevel(logging.WARN)
        logging.getLogger("asyncio").setLevel(logging.WARN)
    logging.getLogger("slixmpp.stringprep").setLevel(logging.ERROR)


def set_default(ctx, param, value):
    if os.path.exists(value):
        with open(value, "r") as f:
            config = load(f.read(), Loader=Loader)
        ctx.default_map = config
    return value


def add_options(options):
    def _add_options(func):
        for option in reversed(options):
            func = option(func)
        return func

    return _add_options


async def _scan(gateway, smallscan, output, stdout):
    _LOGGER.info(
        "Successfully connected to gateway. Found UUID: %s", gateway.uuid
    )
    if smallscan:
        result = await gateway.smallscan(_type=smallscan.lower())
        out_file = output if output else f"smallscan_{gateway.uuid}.json"
    else:
        result = await gateway.rawscan()
        out_file = output if output else f"rawscan_{gateway.uuid}.json"
    if stdout:
        click.secho(json.dumps(result, indent=4), fg="green")
    else:
        with open(out_file, "w") as logfile:
            json.dump(result, logfile, indent=4)
            _LOGGER.info("Successfully saved result to file: %s", out_file)
            _LOGGER.debug("Job done.")


async def _runquery(gateway, path):
    _LOGGER.debug("Trying to connect to gateway.")
    results = []
    for p in path:
        result = await gateway.raw_query(p)
        if result:
            results.append(result)
        await asyncio.sleep(0.3)
    if results:
        _LOGGER.info("Query succeed: %s", path)
        click.secho(json.dumps(results, indent=4, sort_keys=True), fg="green")
    else:
        _LOGGER.warning("No results from queries: %s", path)


async def _runpush(gateway, path, value):
    try:
        if value.isnumeric():
            _value = int(value)
        _value = float(value)
    except ValueError:
        _value = value
    _LOGGER.debug("Trying to connect to gateway.")
    result = await gateway.raw_put(path, _value)
    _LOGGER.info("Put succeed: %s", path)
    click.secho(json.dumps(result, indent=4, sort_keys=True), fg="green")


def coro(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        return asyncio.run(f(*args, **kwargs))

    return wrapper

async def load_tokens(token_file):
    if token_file.is_file():
        with open(token_file) as f:
            tokens = json.load(f)
        return tokens
    return None

async def authenticate_and_save_tokens(device_id=None, token_file="tokens.json"):
    """
    Perform OAuth authentication flow and save tokens.

    Args:
        device_id (str, optional): Your Bosch device ID (gateway UUID)
        token_file (str): Path to save tokens (default: tokens.json)

    Returns:
        dict: Token information if successful, None otherwise
    """
    async with aiohttp.ClientSession() as session:
        # Create connector to handle OAuth flow
        # We use a placeholder for access_token initially
        gateway = Oauth2Gateway(
            session=session,
            session_type="HTTP",
            host=device_id,
            access_key=None,
            access_token="PLACEHOLDER",  # Will be replaced after OAuth
            refresh_token=None,
            token_file=None  # Don't auto-save yet
        )

        connector = gateway._connector

        # Step 1: Generate and open OAuth URL
        print("\n[Step 1] Opening browser for Bosch login...")
        auth_url = connector.start_oauth_flow(open_browser=True)
        print(f"\nIf browser didn't open, visit this URL manually:")
        print(f"{auth_url}\n")

        # Step 2: Get callback URL from user
        print("[Step 2] After logging in, you'll be redirected to a URL starting with:")
        print("         com.bosch.tt.dashtt.pointt://app/login?code=...")
        print("\nNote: The page may show 'Cannot open page' - that's normal!")
        print("      Just copy the entire URL from your browser's address bar.\n")

        callback_url = input("Paste the callback URL here: ").strip()

        if not callback_url:
            print("❌ No URL provided. Exiting.")
            return None

        # Step 3: Extract authorization code
        print("\n[Step 3] Extracting authorization code...")
        code = connector.extract_code_from_url(callback_url)

        if not code:
            print("❌ Could not extract authorization code from URL.")
            print("   Make sure you copied the complete callback URL.")
            return None

        print(f"✓ Authorization code extracted: {code[:20]}...")

        # Step 4: Exchange code for tokens
        print("\n[Step 4] Exchanging code for access tokens...")
        success = await connector.exchange_code_for_tokens(code)

        if not success:
            print("❌ Token exchange failed. Check logs for details.")
            return None

        print("✓ Successfully obtained OAuth tokens!")

        # Step 5: Save tokens to file
        print(f"\n[Step 5] Saving tokens to {token_file}...")
        token_data = {
            "device_id": device_id,
            "access_token": connector._access_token,
            "refresh_token": connector._refresh_token,
            "expires_at": connector._token_expires_at.isoformat() if connector._token_expires_at else None,
        }

        token_path = Path(token_file)
        with open(token_path, 'w') as f:
            json.dump(token_data, f, indent=2)

        print(f"✓ Tokens saved to {token_path.absolute()}")

async def init_gateway(host, session, session_type, device_type, token, password):
    BoschGateway = bosch.gateway_chooser(device_type=device_type)
    if (session_type == OAUTH2):
        # cloud API (OAUTH2 authentication)
        token_file = Path(token)
        tokens = await load_tokens(token_file)
        if not tokens:
            _LOGGER.warning("Failed to open token file: %s", token)
            await authenticate_and_save_tokens(host, token)
            # retry loading token file
            tokens = await load_tokens(token_file)
            if tokens is None:
                _LOGGER.error("Failed to load tokens after authentication. Exiting.")
                raise FailedAuthException("Failed to load tokens after authentication.")

        gateway = BoschGateway(
            session=session,
            session_type=session_type,
            device_type=device_type,
            host=host,
            access_key=None,
            access_token=tokens['access_token'],
            refresh_token=tokens['refresh_token'],
            token_file=token_file
        )
    else:
        gateway = BoschGateway(
            session=session,
            session_type=session_type,
            host=host,
            access_token=token,
            password=password,
        )
    return gateway

@click.group(no_args_is_help=True)
@click.pass_context
@click.version_option(__version__)
@coro
async def cli(ctx):
    """A tool to run commands against Bosch thermostat."""

    pass


_cmd1_options = [
    click.option(
        "--config",
        default="config.yml",
        type=click.Path(),
        callback=set_default,
        is_eager=True,
        expose_value=False,
        show_default=True,
        help="Read configuration from PATH.",
    ),
    click.option(
        "--host",
        envvar="BOSCH_HOST",
        type=str,
        required=True,
        help="IP address of gateway or SERIAL for XMPP and OAUTH2 ('Login' on a sticker on your device)",
    ),
    click.option(
        "--token",
        envvar="BOSCH_ACCESS_TOKEN",
        type=str,
        required=True,
        help="Token from sticker without dashes.",
    ),
    click.option(
        "--password",
        envvar="BOSCH_PASSWORD",
        type=str,
        required=False,
        help="Password you set in mobile app.",
    ),
    click.option(
        "--protocol",
        envvar="BOSCH_PROTOCOL",
        type=click.Choice([XMPP, HTTP, OAUTH2], case_sensitive=True),
        required=True,
        help="Bosch protocol. Either XMPP, HTTP or OAUTH2.",
    ),
    click.option(
        "--device",
        envvar="BOSCH_DEVICE",
        type=click.Choice([NEFIT, IVT, EASYCONTROL, BRUDERUS, IVTAIR], case_sensitive=False),
        required=True,
        help="Bosch device type (brand)",
    ),
    click.option(
        "-d",
        "--debug",
        default=False,
        count=True,
        help="Set Debug mode. Single debug is debug of this lib. Second d is debug of aioxmpp as well.",
    ),
]

_scan_options = [
    click.option(
        "-o",
        "--output",
        type=str,
        required=False,
        help="Path to output file of scan. Default to [raw/small]scan_uuid.json",
    ),
    click.option(
        "--stdout", default=False, count=True, help="Print scan to stdout"
    ),
    click.option(
        "-i",
        "--ignore-unknown",
        count=True,
        default=False,
        help="Ignore unknown device type. Try to scan anyway. Useful for discovering new devices.",
    ),
    click.option(
        "-s",
        "--smallscan",
        type=click.Choice(
            ["HC", "DHW", "SENSORS", "RECORDINGS"], case_sensitive=False
        ),
        help="Scan only single circuit of thermostat.",
    ),
]


@cli.command()
@add_options(_cmd1_options)
@add_options(_scan_options)
@click.pass_context
@coro
async def scan(
    ctx,
    host: str,
    token: str,
    password: str,
    protocol: str,
    device: str,
    output: str,
    stdout: int,
    debug: int,
    ignore_unknown: int,
    smallscan: str,
):
    """Create rawscan of Bosch thermostat."""
    if debug > 0:
        logging.basicConfig(
            # colorfmt,
            datefmt=datefmt,
            level=logging.DEBUG,
            filename="out.log",
            filemode="a",
        )
    set_debug(debug)
    device_type = device.upper()
    session_type = protocol.upper()
    gateway = None
    if session_type == XMPP:
        session = asyncio.get_event_loop()
    elif session_type == HTTP:
        session = aiohttp.ClientSession()
        if device_type != IVT:
            _LOGGER.warning(
                "You're using HTTP protocol, but your device probably doesn't support it. Check for mistakes!"
            )
    elif session_type == OAUTH2:
        session = aiohttp.ClientSession()
    else:
        _LOGGER.error("Wrong protocol for this device")
        return
    try:
        gateway = await init_gateway(host, session, session_type, device_type,token, password)

        _LOGGER.debug("Trying to connect to gateway.")
        connected = True if ignore_unknown else await gateway.check_connection()
        if connected:
            _LOGGER.info("Running scan")
            await _scan(gateway, smallscan, output, stdout)
        else:
            _LOGGER.error("Couldn't connect to gateway!")
    finally:
        await session.close()
        if gateway is not None:
            await gateway.close(force=True)


_path_options = [
    click.option(
        "-p",
        "--path",
        type=str,
        required=True,
        multiple=True,
        help="Path to run against. Look at rawscan at possible paths. e.g. /gateway/uuid - Can be specified multiple times!",
    )
]


@cli.command()
@add_options(_cmd1_options)
@add_options(_path_options)
@click.pass_context
@coro
async def query(
    ctx,
    host: str,
    token: str,
    password: str,
    protocol: str,
    device: str,
    path: list[str],
    debug: int,
):
    """Query values of Bosch thermostat."""
    set_debug(debug=debug)

    device_type = device.upper()
    session_type = protocol.upper()
    _LOGGER.info("Connecting to %s with '%s'", host, session_type)
    gateway = None
    if session_type == XMPP:
        session = asyncio.get_event_loop()
    elif session_type == HTTP:
        session = aiohttp.ClientSession()
        if device_type != IVT:
            _LOGGER.warning(
                "You're using HTTP protocol, but your device probably doesn't support it. Check for mistakes!"
            )
    elif session_type == OAUTH2:
        session = aiohttp.ClientSession()
    else:
        _LOGGER.error("Wrong protocol for this device")
    try:
        gateway = await init_gateway(host, session, session_type, device_type, token, password)
        await _runquery(gateway, path)
    except FailedAuthException as e:
        _LOGGER.error(e)
    finally:
        await session.close()
        if gateway is not None:
            await gateway.close(force=True)


_path_put_options = [
    click.option(
        "-p",
        "--path",
        type=str,
        required=True,
        multiple=False,
        help="Path to run against. Look at rawscan at possible paths. e.g. /gateway/uuid - Can be specified multiple times!",
    )
]


@cli.command()
@add_options(_cmd1_options)
@add_options(_path_put_options)
@click.argument("value", nargs=1)
@click.pass_context
@coro
async def put(
    ctx,
    host: str,
    token: str,
    password: str,
    protocol: str,
    device: str,
    path: str,
    debug: int,
    value: str,
):
    """Send value to Bosch thermostat.

    VALUE is the raw value to send to thermostat. It will be parsed to json.
    """
    set_debug(debug=debug)

    if not value:
        _LOGGER.error("Value to put not provided. Exiting")
        return
    if value.isnumeric():
        value = float(value)
    device_type = device.upper()
    session_type = protocol.upper()
    _LOGGER.info("Connecting to %s with '%s'", host, session_type)
    gateway = None
    if session_type == XMPP:
        session = asyncio.get_event_loop()
    elif session_type == HTTP:
        session = aiohttp.ClientSession()
        if device_type != IVT:
            _LOGGER.warning(
                "You're using HTTP protocol, but your device probably doesn't support it. Check for mistakes!"
            )
    else:
        _LOGGER.error("Wrong protocol for this device")
        return
    try:
        gateway = await init_gateway(host, session, session_type, device_type, token, password)
        await _runpush(gateway, path, value)
    finally:
        if gateway is not None:
            await gateway.close(force=True)


if __name__ == "__main__":
    asyncio.get_event_loop().run_until_complete(cli())
