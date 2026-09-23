"""The EasyControl CA helper is public API for the integration.

Without it the Home Assistant integration imports the private
`connectors.easycontrol._CA_CERT_PATH`, and the connector builds a context -
blocking I/O - on every setup attempt.
"""

import ssl
from pathlib import Path
from unittest.mock import MagicMock, patch

import bosch_thermostat_client
from bosch_thermostat_client.connectors.easycontrol import (
    EasycontrolConnector,
    easycontrol_ca_path,
    easycontrol_ssl_context,
)

_PATCH_TARGET = "bosch_thermostat_client.connectors.xmpp.BoschClientXMPP"


def test_helper_is_exported_from_the_package_root():
    assert hasattr(bosch_thermostat_client, "easycontrol_ssl_context")
    assert "easycontrol_ssl_context" in bosch_thermostat_client.__all__


def test_ca_path_exists():
    path = easycontrol_ca_path()
    assert isinstance(path, Path)
    assert path.is_file(), f"CA bundle missing at {path}"


def test_context_trusts_the_bundled_ca():
    ctx = easycontrol_ssl_context()
    assert isinstance(ctx, ssl.SSLContext)
    assert ctx.get_ca_certs(), "no CA loaded into the context"


def test_context_is_cached():
    assert easycontrol_ssl_context() is easycontrol_ssl_context()


def test_supplied_context_is_used_unchanged():
    """A consumer that builds its own context in an executor must win."""
    supplied = MagicMock()
    with patch(_PATCH_TARGET) as client:
        EasycontrolConnector(
            host="SERIAL",
            encryption=MagicMock(),
            access_key="ACCESSKEY",
            ssl_context=supplied,
        )
    assert client.call_args.kwargs["ssl_context"] is supplied
