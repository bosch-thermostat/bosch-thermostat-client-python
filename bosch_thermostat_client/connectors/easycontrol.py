"""XMPP Connector to talk to bosch."""

import ssl
from functools import lru_cache
from pathlib import Path

from bosch_thermostat_client.const import (
    PUT,
    GET,
    USER_AGENT,
    CONTENT_TYPE,
    APP_JSON,
    ACCESS_KEY,
)
from bosch_thermostat_client.const.easycontrol import EASYCONTROL
from .xmpp import XMPPBaseConnector

USERAGENT = "rrc2"
_CA_CERT_PATH = Path(__file__).resolve().parent.parent / "easycontrol_ca.pem"


def easycontrol_ca_path() -> Path:
    """Return the path of the CA bundle EasyControl's XMPP host is signed by."""
    return _CA_CERT_PATH


@lru_cache(maxsize=1)
def easycontrol_ssl_context() -> ssl.SSLContext:
    """Build an SSL context trusting the EasyControl CA.

    Loading a CA file is blocking. The result is cached, so a consumer running
    an event loop (Home Assistant) pays it once per process instead of on
    every setup attempt; better still, call this in an executor and pass the
    result as ``ssl_context=``.
    """
    ssl_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ssl_ctx.load_verify_locations(cafile=str(_CA_CERT_PATH))
    return ssl_ctx


class EasycontrolConnector(XMPPBaseConnector):
    xmpp_host = "xmpp.rrcng.ticx.boschtt.net"
    _accesskey_prefix = "C42i9NNp_"
    _rrc_contact_prefix = "rrc2contact_"
    _rrc_gateway_prefix = "rrc2gateway_"
    device_type = EASYCONTROL

    def __init__(self, host, encryption, **kwargs):
        ssl_ctx = kwargs.get("ssl_context")
        if not ssl_ctx:
            ssl_ctx = easycontrol_ssl_context()
        super().__init__(
            host=host,
            encryption=encryption,
            access_key=kwargs.get(ACCESS_KEY),
            ssl_context=ssl_ctx,
        )

    def _build_message(self, method, path, data=None, seq_no=0):
        if not path:
            return
        if method == GET:
            lines = [
                f"GET {path} HTTP/1.1",
                f"{USER_AGENT}: {USERAGENT}",
                f"Seq-No: {seq_no}",
            ]
            return "\n".join(lines) + "\n\n"
        elif method == PUT and data:
            lines = [
                f"PUT {path} HTTP/1.1",
                f"{USER_AGENT}: {USERAGENT}",
                f"{CONTENT_TYPE}: {APP_JSON}",
                f"Seq-No: {seq_no}",
                f"Content-Length: {len(data)}",
                "",
                data.decode("utf-8"),
            ]
            return "\n".join(lines) + "\n\n"
        return None
