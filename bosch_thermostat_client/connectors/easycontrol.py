"""XMPP Connector to talk to bosch."""

import itertools
import ssl
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


class EasycontrolConnector(XMPPBaseConnector):
    xmpp_host = "xmpp.rrcng.ticx.boschtt.net"
    _accesskey_prefix = "C42i9NNp_"
    _rrc_contact_prefix = "rrc2contact_"
    _rrc_gateway_prefix = "rrc2gateway_"
    device_type = EASYCONTROL

    def __init__(self, host, encryption, **kwargs):
        self._seqno = itertools.count(0)
        ssl_ctx = kwargs.get("ssl_context")
        if not ssl_ctx:
            ssl_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            ssl_ctx.load_verify_locations(cafile=str(_CA_CERT_PATH))
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
