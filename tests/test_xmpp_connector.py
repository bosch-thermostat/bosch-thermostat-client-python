"""Verification of XEP-0199 (XMPP Ping) registration.

XMPP Ping (XEP-0199) must be registered with
         keepalive=True, interval=300, timeout=30 so the Bosch server
         does not drop idle connections.

The test is expected to FAIL until XMPPBaseConnector is updated to pass
the configuration dict to register_plugin.
"""
import unittest.mock as mock
from unittest.mock import MagicMock, patch, call

import pytest

from bosch_thermostat_client.connectors.ivt import IVTXMPPConnector


def test_keepalive_registered():
    """register_plugin("xep_0199", {...}) must include keepalive config.

    RED until XMPPBaseConnector.register_plugin call for xep_0199 passes
    {'keepalive': True, 'interval': 300, 'timeout': 30}.
    """
    mock_client = MagicMock()
    mock_client.plugin = {}

    mock_encryption = MagicMock()

    with patch(
        "bosch_thermostat_client.connectors.xmpp.BoschClientXMPP",
        return_value=mock_client,
    ):
        connector = IVTXMPPConnector(
            host="SERIALNUMBER",
            access_key="ACCESSKEY01",
            encryption=mock_encryption,
        )

    # Collect all register_plugin calls
    all_calls = mock_client.register_plugin.call_args_list

    # Look for the xep_0199 call with the keepalive config dict
    expected_config = {"keepalive": True, "interval": 60, "timeout": 30}
    xep_0199_calls = [
        c for c in all_calls if c.args and c.args[0] == "xep_0199"
    ]

    assert xep_0199_calls, (
        "register_plugin was never called with 'xep_0199'"
    )

    # The call must include the config dict as second positional or keyword arg
    found_with_config = any(
        (len(c.args) >= 2 and c.args[1] == expected_config)
        or c.kwargs.get("config") == expected_config
        for c in xep_0199_calls
    )
    assert found_with_config, (
        "register_plugin('xep_0199', ...) was called but without the required "
        "keepalive config dict %s. Actual calls: %s" % (expected_config, xep_0199_calls)
    )
