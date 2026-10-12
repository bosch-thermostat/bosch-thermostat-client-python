"""Verification of SSL context support and legacy code removal.

BoschClientXMPP accepts an ssl_context kwarg in its constructor.
The legacy connectors/client/slixmpp.py file is removed and
        xmpp.py no longer contains the version-dispatch import branch.

All tests in this module are expected to FAIL until those requirements
are implemented.
"""
import inspect
import ssl
from pathlib import Path

import pytest

from bosch_thermostat_client.connectors.client.slixmpp010 import BoschClientXMPP


def test_ssl_context_kwarg():
    """BoschClientXMPP.__init__ must declare an ssl_context parameter.

    RED until the constructor signature is updated to accept ssl_context=.
    """
    sig = inspect.signature(BoschClientXMPP.__init__)
    assert "ssl_context" in sig.parameters, (
        "BoschClientXMPP.__init__ does not accept ssl_context kwarg"
    )


def test_legacy_file_removed():
    """The legacy slixmpp.py connector file must not exist.

    RED until connectors/client/slixmpp.py is deleted.
    """
    assert not Path(
        "bosch_thermostat_client/connectors/client/slixmpp.py"
    ).exists(), "Legacy file bosch_thermostat_client/connectors/client/slixmpp.py still exists"


def test_version_dispatch_removed():
    """xmpp.py must not contain the legacy slixmpp version-dispatch import.

    RED until the 'from .client.slixmpp import' branch is removed from xmpp.py.
    """
    source = Path(
        "bosch_thermostat_client/connectors/xmpp.py"
    ).read_text(encoding="utf-8")
    assert "from .client.slixmpp import" not in source, (
        "bosch_thermostat_client/connectors/xmpp.py still contains "
        "'from .client.slixmpp import'"
    )
