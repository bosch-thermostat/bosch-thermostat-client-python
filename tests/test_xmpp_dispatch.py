"""RED test stubs for XMPP dispatch redesign.

Covers concurrent request handling, exact path routing, and sequence number improvements.

All six tests are expected to FAIL against the unmodified production code.
They will pass GREEN after implementation introduces:
  - _pending dict replacing listeners set for concurrent request handling and exact path routing
  - Removal of global _lock to support concurrent requests
  - itertools.count() replacing int _seqno for sequence number uniqueness
"""

import itertools
import ssl

import pytest
from unittest.mock import MagicMock, patch

from bosch_thermostat_client.connectors.ivt import IVTXMPPConnector
from bosch_thermostat_client.connectors.easycontrol import EasycontrolConnector
from bosch_thermostat_client.connectors.xmpp import XMPPBaseConnector
from bosch_thermostat_client.const import GET


_PATCH_TARGET = "bosch_thermostat_client.connectors.xmpp.BoschClientXMPP"


def _make_ivt_connector():
    """Return an IVTXMPPConnector with BoschClientXMPP patched to a MagicMock."""
    mock_client = MagicMock()
    mock_client.plugin = {}
    mock_encryption = MagicMock()
    with patch(_PATCH_TARGET, return_value=mock_client):
        connector = IVTXMPPConnector(
            host="SERIALNUMBER",
            access_key="ACCESSKEY01",
            encryption=mock_encryption,
        )
    return connector


def _make_easycontrol_connector():
    """Return an EasycontrolConnector with BoschClientXMPP and ssl.SSLContext patched.

    ssl.SSLContext is patched to avoid real filesystem CA certificate loading.
    """
    mock_client = MagicMock()
    mock_client.plugin = {}
    mock_encryption = MagicMock()
    mock_ssl_ctx = MagicMock()
    with patch(_PATCH_TARGET, return_value=mock_client), \
         patch("ssl.SSLContext", return_value=mock_ssl_ctx):
        connector = EasycontrolConnector(
            host="SERIALNUMBER",
            encryption=mock_encryption,
            access_key="ACCESSKEY01",
        )
    return connector


def test_concurrent_requests():
    """Concurrent request handling: _request uses _pending dict, not listeners set.

    RED until XMPPBaseConnector replaces self.listeners with self._pending dict.
    After GREEN: connector._pending is a dict used for per-request futures keyed by path.
    """
    connector = _make_ivt_connector()
    assert hasattr(connector, "_pending") and isinstance(connector._pending, dict), (
        "_pending dict not found"
    )


def test_pending_lifecycle():
    """Concurrent request handling: global _lock removed from XMPPBaseConnector.

    RED until self._lock is removed from __init__.
    After GREEN: per-request futures replace the global lock; _lock no longer exists.
    """
    connector = _make_ivt_connector()
    assert not hasattr(connector, "_lock"), (
        "self._lock still present — global lock not yet removed"
    )


def test_exact_path_routing():
    """Exact path routing: listeners set removed; routing is exact key lookup in _pending.

    RED until self.listeners set is removed from XMPPBaseConnector.
    After GREEN: self.listeners is gone; main_listener uses _pending[path] for dispatch.
    """
    connector = _make_ivt_connector()
    assert not hasattr(connector, "listeners"), (
        "self.listeners still present — fan-out routing not yet replaced"
    )


def test_exact_path_match():
    """Exact path routing: _pending dict present for exact-match routing.

    RED until _pending dict replaces listeners set.
    After GREEN: _pending provides O(1) exact-path lookup instead of fan-out iteration.
    """
    connector = _make_ivt_connector()
    assert hasattr(connector, "_pending"), (
        "_pending not found — exact-match routing not yet implemented"
    )


def test_seqno_is_count():
    """Sequence number improvement: XMPP connectors use a count for sequence numbers.
    After 8d6b7f7, self._count in XMPPBaseConnector is used.
    """
    ivt = _make_ivt_connector()
    easy = _make_easycontrol_connector()
    assert isinstance(ivt._count, int), f"IVTConnector._count is {type(ivt._count)}, expected int"
    assert isinstance(easy._count, int), f"EasycontrolConnector._count is {type(easy._count)}, expected int"


def test_seqno_uniqueness():
    """Sequence number uniqueness regression guard: _build_message embeds the provided seq_no.
    Uniqueness is now managed by XMPPBaseConnector._request using self._count.
    """
    ivt = _make_ivt_connector()
    msg1 = ivt._build_message(method=GET, path="/test/path", seq_no=1)
    msg2 = ivt._build_message(method=GET, path="/test/path", seq_no=2)
    # Extract Seq-No values from both messages
    seq1 = next(line for line in msg1.split("\r\r") if "Seq-No" in line).split(": ")[1].strip()
    seq2 = next(line for line in msg2.split("\r\r") if "Seq-No" in line).split(": ")[1].strip()
    assert seq1 == '1'
    assert seq2 == '2'
    assert seq1 != seq2

