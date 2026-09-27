"""XMPP Connector to talk to bosch."""

from bosch_thermostat_client.const import PUT, GET, USER_AGENT, CONTENT_TYPE, APP_JSON
from bosch_thermostat_client.const.nefit import NEFIT, NEFITEASY
from .xmpp import XMPPBaseConnector


class NefitConnector(XMPPBaseConnector):
    _accesskey_prefix = "Ct7ZR03b_"
    _rrc_contact_prefix = "rrccontact_"
    _rrc_gateway_prefix = "rrcgateway_"
    xmpp_host = "wa2-mz36-qrmzh6.bosch.de"
    device_type = NEFIT
    disable_starttls = True
    force_starttls = False
    use_ssl = False

    def _build_message(self, method, path, data=None, seq_no=0) -> str:
        if not path:
            return
        if method == GET:
            body = "\r\r".join(
                [f"GET {path} HTTP/1.1", f"{USER_AGENT}: {NEFITEASY}", "\r\r"]
            )
        elif method == PUT and data:
            body = "\r\r".join(
                [
                    f"PUT {path} HTTP/1.1",
                    f"{USER_AGENT}: {NEFITEASY}",
                    f"{CONTENT_TYPE}: {APP_JSON}",
                    f"Content-Length: {len(data)}",
                    "",
                    data.decode("utf-8"),
                    "\r\r",
                ]
            )
        else:
            return
        return body
