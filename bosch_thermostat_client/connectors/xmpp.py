"""XMPP Connector to talk to bosch."""

from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import dataclass

from slixmpp import Iq
from slixmpp.exceptions import IqError, IqTimeout
from slixmpp.xmlstream.handler import Callback
from slixmpp.xmlstream.matcher import StanzaPath

from .client.slixmpp010 import BoschClientXMPP

from bosch_thermostat_client.const import (
    ACCESS_KEY,
    GET,
    ID,
    PUT,
    REQUEST_TIMEOUT,
    TIMEOUT,
)
from bosch_thermostat_client.exceptions import (
    BoschException,
    DeviceException,
    EncryptionException,
    FailedAuthException,
    MsgException,
)

_LOGGER = logging.getLogger(__name__)

#: Bosch gateways separate the lines of a message with "\r\r", "\r\n", "\n"
#: or "\r" depending on model and firmware.
_LINE_SPLIT = re.compile(r"\r\r|\r\n|\n|\r")
#: "Seq-No: 3", "Content-Type: application/json", ... - a header, not a payload.
_HEADER_LINE = re.compile(r"^[A-Za-z][A-Za-z0-9-]*:")
_STATUS_2XX = re.compile(r"HTTP/1\.[0-1] 2\d\d")
_STATUS_ERROR = re.compile(r"HTTP/1\.[0-1] [45]\d\d")


@dataclass
class _PendingRequest:
    """One in-flight request, awaiting its reply."""

    future: asyncio.Future
    method: str
    path: str


class XMPPBaseConnector:
    ca_certs = None

    def __init__(self, host, encryption, ssl_context=None, **kwargs):
        """
        :param host: aka serial number
        :param password:
        """
        self.serial_number = host
        self._encryption = encryption

        identifier = self.serial_number + "@" + self.xmpp_host
        self._from = self._rrc_contact_prefix + identifier

        self._to = self._rrc_gateway_prefix + identifier
        self._password = self._accesskey_prefix + kwargs.get(ACCESS_KEY)
        self.client = BoschClientXMPP(
            jid=self._from, password=self._password, ssl_context=ssl_context
        )
        self.client.register_plugin("xep_0030")  # Service Discovery
        self.client.register_plugin(
            "xep_0199", {"keepalive": True, "interval": 60, "timeout": 30}
        )  # XMPP Ping with keep-alive
        self.client.add_event_handler("session_start", self.session_start)
        self.client.add_event_handler("session_end", self.session_end)
        self.client.add_event_handler("auth_success", lambda _: self._auth(True))
        self.client.add_event_handler("failed_auth", lambda _: self._auth(False))

        self.client.register_handler(
            Callback(
                "Query Request",
                StanzaPath("iq@type=get"),
                self.handle_query_request,
            )
        )
        self.client.add_event_handler(
            "ssl_invalid_chain", self.discard_ssl_invalid_chain
        )
        self.connected_event = asyncio.Event()
        self.disconnect_event = asyncio.Event()
        self._last_timeout_seq = -1
        self._auth_success = False
        self.received_message = None
        self._pending: dict[int, _PendingRequest] = {}
        self._put_locks: dict = {}
        self._request_lock = asyncio.Lock()
        self._count = 0

    def _auth(self, success: bool) -> None:
        """Called after authentication.

        Args:
            success: Whether or not the authentication was successful.
        """
        # store and fire
        self._auth_success = success
        if not success:
            self.connected_event.set()

    def handle_query_request(self, iq: Iq):
        query = iq.get_query()
        reply = iq.reply()
        if query == "jabber:iq:version":
            reply["xmlns"] = "jabber:iq:version"
            reply["version"] = "-1364755535"
            reply.send()
        if query == "com.bosch.tt.buderus.controlng":
            reply["xmlns"] = "com.bosch.tt.buderus.controlng"
            reply["name"] = "3.6.0"
            reply["version"] = "3.6.0"
            reply["os"] = ""
            reply.send()

    async def close(self, force=False):
        """Disconnect and stop any reconnect attempt still running.

        slixmpp only fires ``session_end`` for a session that actually
        started. A client that never connected - or is still retrying in the
        background - would make close() wait for an event that never comes and
        leave the reconnect loop running, so cancel the attempt and return.
        """
        self._cancel_connection_attempt()
        if not self.client.is_connected():
            _LOGGER.debug("XMPP client is not connected, nothing to disconnect")
            self._abort_client()
            self.disconnect_event.set()
            return
        self.client.disconnect()
        try:
            async with asyncio.timeout(10):
                await self.disconnect_event.wait()
        except asyncio.TimeoutError:
            _LOGGER.debug("Timeout waiting for XMPP disconnect, aborting connection")
            self._abort_client()

    def _cancel_connection_attempt(self) -> None:
        """Cancel an in-flight slixmpp connection attempt, if any.

        Without this a connect() that timed out on our side keeps retrying with
        an exponential back-off for the lifetime of the process.
        """
        cancel = getattr(self.client, "cancel_connection_attempt", None)
        if not callable(cancel):
            return
        try:
            cancel()
        except Exception as err:  # pragma: no cover - defensive
            _LOGGER.debug("Suppressed %s cancelling connection: %s", type(err).__name__, err)

    def _abort_client(self) -> None:
        """Drop the transport without waiting for the server."""
        abort = getattr(self.client, "abort", None)
        if not callable(abort):
            return
        try:
            abort()
        except Exception as err:  # pragma: no cover - defensive
            _LOGGER.debug("Suppressed %s aborting connection: %s", type(err).__name__, err)

    async def session_start(self, *_, **__):
        self.client.send_presence()
        self.client.get_roster()
        self._register_message_handler()
        self.connected_event.set()

    async def session_end(self, *_, **__):
        self.disconnect_event.set()   # signal close() waiters first
        self._reset_events()          # then clear for next connection attempt

    def _reset_events(self) -> None:
        """Clear per-connection state so the next connect() waits for real auth.

        Called from session_end. Clears connected_event and resets _auth_success.
        Does NOT clear disconnect_event (close() awaits it via disconnect_event.wait()).
        """
        self.connected_event.clear()
        self._auth_success = False
        # Fail in-flight futures immediately rather than waiting for REQUEST_TIMEOUT
        if self._pending:
            # Mark the highest pending seq as timed out so we ignore late responses
            self._last_timeout_seq = max(self._pending.keys())
            for entry in list(self._pending.values()):
                if not entry.future.done():
                    entry.future.set_exception(MsgException("XMPP session ended"))
        self._pending.clear()

    def _register_message_handler(self) -> None:
        """Register main_listener exactly once; idempotent via del+add.

        Uses slixmpp's del_event_handler (no-op if not registered) before add_event_handler
        to prevent duplicate registration on reconnect. Per slixmpp xmlstream.py:1036,
        add_event_handler appends unconditionally with no deduplication.
        """
        self.client.del_event_handler("message", self.main_listener)
        self.client.add_event_handler("message", self.main_listener)

    @property
    def encryption_key(self):
        return self._encryption.key

    def _build_message(self, method, path, data=None, seq_no=0):
        pass

    async def get(self, path):
        _LOGGER.debug("Sending GET request to %s by %s", path, id(self))
        for attempt in range(2):
            try:
                data = await self._request(method=GET, path=path)
                if data:
                    _LOGGER.debug("Response to GET request %s: %s", path, json.dumps(data))
                    return data
            except (asyncio.TimeoutError, MsgException) as err:
                _LOGGER.debug("XMPP request error for %s (attempt %d): %s", path, attempt + 1, err)
                if attempt == 1:
                    if "/devices" in path or "productLookup" in path:
                        _LOGGER.debug("XMPP request for %s failed after 2 attempts (expected for some models)", path)
                    else:
                        _LOGGER.warning("XMPP request for %s failed after 2 attempts", path)
                    raise DeviceException(f"XMPP request error for {path} after 2 attempts: {err}")
            except EncryptionException as err:
                # Never leaves the connector: callers guard against DeviceException.
                raise DeviceException(f"Can't decrypt response for {path}: {err}") from err
            except BoschException:
                # FailedAuthException and friends must reach the consumer intact.
                raise
            except Exception as err:
                _LOGGER.warning("Unexpected XMPP error for %s: %s", path, err)
                raise DeviceException(f"Unexpected error for {path}: {err}")

        raise DeviceException(f"Error requesting data from {path}: empty response")

    async def put(self, path, value):
        _LOGGER.debug("Sending PUT request to %s with value %s", path, value)
        json_data = json.dumps({"value": value})
        try:
            data = await self._request(
                method=PUT,
                encrypted_msg=self._encryption.encrypt(json_data),
                path=path,
                payload=json_data,
            )
        except EncryptionException as err:
            raise DeviceException(f"Can't decrypt response for {path}: {err}") from err
        if data:
            return True

    async def _request(self, method, path, encrypted_msg=None, timeout=None, payload=None):
        if timeout is None:
            timeout = REQUEST_TIMEOUT
        async with self._request_lock:
            data = None
            _LOGGER.debug("XMPP unencrypted request: %s %s%s", method, path, f" payload: {payload}" if payload else "")
            try:
                if not self._auth_success:
                    _LOGGER.info("XMPP not authorized, connecting...")
                    self.client.connect()
                    async with asyncio.timeout(TIMEOUT):
                        await self.connected_event.wait()
                    if not self._auth_success:
                        raise FailedAuthException("Can't authorize to XMPP server.")
            except asyncio.TimeoutError:
                # slixmpp keeps retrying in the background unless told otherwise.
                self._cancel_connection_attempt()
                _LOGGER.error(
                    "Can't connect to XMPP server!. Check your network connection or credentials!"
                )
                raise DeviceException("XMPP connection timeout")

            # Use sequence number as the unique key for this request
            seq_no = self._count
            self._count += 1
            future = asyncio.get_running_loop().create_future()
            self._pending[seq_no] = _PendingRequest(future=future, method=method, path=path)

            put_lock = None
            if method == PUT:
                put_lock = self._put_locks.setdefault(path, asyncio.Lock())
                await put_lock.acquire()

            msg_to_send = self._build_message(method=method, path=path, data=encrypted_msg, seq_no=seq_no)
            _LOGGER.debug("Sending XMPP message (Seq: %d) to %s: %s", seq_no, self._to, msg_to_send)
            try:
                self.client.send_message(mto=self._to, mbody=msg_to_send, mtype="chat")
                async with asyncio.timeout(timeout):
                    data = await asyncio.shield(future)
                _LOGGER.debug("XMPP request for %s (Seq: %d) returned success", path, seq_no)

                return data
            except IqError as e:
                _LOGGER.error("Error sending message: %s", e)
                raise DeviceException(f"IqError: {e}")
            except IqTimeout:
                _LOGGER.error("IqTimeout sending message")
                raise DeviceException("IqTimeout")
            except asyncio.TimeoutError:
                self._last_timeout_seq = seq_no
                _LOGGER.debug("Timeout waiting for response from %s (Seq: %d)", path, seq_no)
                raise MsgException("Request timed out")

            except MsgException as err:
                _LOGGER.debug("Msg exception for %s: %s", path, err)
                raise err

            except EncryptionException as err:
                _LOGGER.warning(err)
                raise EncryptionException(err)
            finally:
                self._pending.pop(seq_no, None)
                if not future.done():
                    future.cancel()
                if put_lock is not None and put_lock.locked():
                    put_lock.release()

    @staticmethod
    def _parse_seq_no(lines: list) -> int | None:
        """Return the Seq-No header of a reply, or None when it carries none."""
        for line in lines:
            if line.startswith("Seq-No:"):
                try:
                    return int(line.split(":")[1].strip())
                except (ValueError, IndexError):
                    return None
        return None

    @staticmethod
    def _extract_payload(lines: list) -> str | None:
        """Return the encrypted body of a reply, or None when it has none.

        A 204 (successful PUT) is headers only. Taking the last non-empty line
        unconditionally would hand a header to the decrypter and turn a
        successful write into an error.
        """
        for line in reversed(lines):
            candidate = line.strip()
            if not candidate:
                continue
            if candidate.startswith("HTTP/") or _HEADER_LINE.match(candidate):
                return None
            return candidate
        return None

    @staticmethod
    def _payload_matches_path(decrypted, path: str) -> bool:
        """True when a decrypted body belongs to the request for `path`."""
        if not isinstance(decrypted, dict):
            return True
        identifier = decrypted.get(ID)
        if not identifier or not isinstance(identifier, str):
            return True
        return identifier in path

    def _match_response(self, seq_no: int | None, decrypted) -> _PendingRequest | None:
        """Find the request a reply belongs to.

        Matching is by Seq-No when the gateway echoes one. NEFIT gateways do
        not, so fall back to the payload id against the pending path, the way
        the pre-dispatch code did - requests are serialised by _request_lock,
        so there is at most one candidate.
        """
        if seq_no is not None and seq_no in self._pending:
            entry = self._pending[seq_no]
            if not entry.future.done():
                return entry
            _LOGGER.debug(
                "Received XMPP response for unknown or already completed Seq-No: %d",
                seq_no,
            )
            return None

        pending = [
            (seq, entry)
            for seq, entry in self._pending.items()
            if not entry.future.done()
        ]
        if not pending:
            _LOGGER.debug("Received XMPP response with no request waiting for it")
            return None

        if seq_no is not None:
            if seq_no != 0:
                _LOGGER.debug(
                    "Received XMPP response for unknown or already completed Seq-No: %d",
                    seq_no,
                )
                return None
            # Some gateways ignore Seq-No and always answer with 0.
            if len(pending) != 1:
                _LOGGER.debug("Ambiguous Seq-No: 0 response, %d requests pending", len(pending))
                return None
            actual_seq, entry = pending[0]
            # Only match a request started AFTER the last timeout: an earlier
            # one is a ghost reply to a request that already gave up.
            if actual_seq <= self._last_timeout_seq:
                _LOGGER.warning(
                    "Ignoring late Seq-No: 0 response (matches timed-out Seq: %d)",
                    actual_seq,
                )
                return None
            if not self._payload_matches_path(decrypted, entry.path):
                _LOGGER.warning(
                    "Ignoring Seq-No: 0 response for %s, it does not answer pending %s",
                    decrypted.get(ID) if isinstance(decrypted, dict) else decrypted,
                    entry.path,
                )
                return None
            _LOGGER.debug("Matching Seq-No: 0 response to pending Seq-No: %d", actual_seq)
            return entry

        # No Seq-No header at all (NEFIT).
        for _seq, entry in pending:
            if self._payload_matches_path(decrypted, entry.path):
                return entry
        _LOGGER.debug("No pending request matches the received XMPP response")
        return None

    def main_listener(self, msg):
        if msg["type"] not in ("normal", "chat"):
            return
        body = msg["body"]
        if not body:
            return

        try:
            body_arr = _LINE_SPLIT.split(body)
        except (AttributeError, TypeError):
            return
        if not body_arr:
            return

        http_response = body_arr[0].strip()
        seq_no = self._parse_seq_no(body_arr)

        if _STATUS_2XX.match(http_response):
            payload = self._extract_payload(body_arr)
            decrypted_body = None
            if payload is not None:
                try:
                    decrypted_body = self._encryption.json_decrypt(payload)
                except EncryptionException:
                    entry = self._match_response(seq_no, None)
                    if entry is not None:
                        entry.future.set_exception(
                            EncryptionException(f"Can't decrypt for {entry.path}")
                        )
                    return
            entry = self._match_response(seq_no, decrypted_body)
            if entry is None:
                return
            _LOGGER.debug("XMPP unencrypted response for %s: %s", entry.path, decrypted_body)
            if entry.method == PUT:
                # A successful write answers 204 with no body.
                entry.future.set_result(decrypted_body if decrypted_body else True)
            else:
                # An empty body is not a result; never hand back True for a GET,
                # the caller would call .get() on a bool.
                entry.future.set_result(decrypted_body if decrypted_body else None)
            return

        if _STATUS_ERROR.match(http_response):
            entry = self._match_response(seq_no, None)
            if entry is None:
                return
            if http_response.split()[1] == "401":
                # A rejected credential is not a transport error: it has to
                # reach the consumer so it can ask for a new access key.
                entry.future.set_exception(
                    FailedAuthException(f"401 for {entry.path}: {body}")
                )
            else:
                entry.future.set_exception(
                    MsgException(f"{http_response} for {entry.path}: {body}")
                )

    @staticmethod
    def discard_ssl_invalid_chain(*_, **__):
        """Do nothing if ssl certificate is invalid."""
        _LOGGER.debug("Ignoring invalid SSL certificate as requested")
