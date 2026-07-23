"""XMPP Connector to talk to bosch."""
import itertools

from bosch_thermostat_client.const import PUT, GET, USER_AGENT, CONTENT_TYPE, APP_JSON
from bosch_thermostat_client.const.ivt import TELEHEATER, IVT
from .xmpp import XMPPBaseConnector


class IVTXMPPConnector(XMPPBaseConnector):
    _accesskey_prefix = "C6u9jPue_"
    _rrc_contact_prefix = "contact_"
    _rrc_gateway_prefix = "gateway_"
    xmpp_host = "wa2-mz36-qrmzh6.bosch.de"
    device_type = IVT
    disable_starttls = True
    force_starttls = False
    use_ssl = False


    def __init__(self, host, access_key, encryption, **kwargs):
        """IVTConnector constructor

        Args:
            host (str): serialnumber of target
            access_key (str): access key to bosch
            encryption (obj): Encryption object
        """
        self._seqno = itertools.count(1)
        super().__init__(host=host, access_key=access_key, encryption=encryption, **kwargs)

    def _build_message(self, method, path, data=None, seq_no=0) -> str:
        if not path:
            return
        if method == GET:
            body = "\r\r".join(
                [
                    f"GET {path} HTTP/1.1",
                    f"{USER_AGENT}: {TELEHEATER}",
                    f"Seq-No: {seq_no}",
                    "\r\r",
                ]
            )
        elif method == PUT and data:
            body = "\r\r".join(
                [
                    f"PUT {path} HTTP/1.1",
                    f"{USER_AGENT}: {TELEHEATER}",
                    f"{CONTENT_TYPE}: {APP_JSON}",
                    f"Content-Length: {len(data)}",
                    f"Seq-No: {seq_no}",
                    "",
                    data.decode("utf-8"),
                ]
            )
        else:
            return
        return body
