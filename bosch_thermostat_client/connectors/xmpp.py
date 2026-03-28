"""XMPP Connector to talk to bosch."""

import asyncio
import json
import logging
import re

from slixmpp import Iq
from slixmpp.exceptions import IqError, IqTimeout
from slixmpp.xmlstream.handler import Callback
from slixmpp.xmlstream.matcher import StanzaPath

from .client.slixmpp010 import BoschClientXMPP

from bosch_thermostat_client.const import (
    ACCESS_KEY,
    GET,
    PUT,
    REQUEST_TIMEOUT,
)
from bosch_thermostat_client.exceptions import (
    DeviceException,
    EncryptionException,
    FailedAuthException,
    MsgException,
)

_LOGGER = logging.getLogger(__name__)


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
        self._pending: dict = {}
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
        self.client.disconnect()
        try:
            async with asyncio.timeout(10):
                await self.disconnect_event.wait()
        except asyncio.TimeoutError:
            _LOGGER.debug("Timeout waiting for XMPP disconnect")

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
            for key, fut in list(self._pending.items()):
                if not fut.done():
                    fut.set_exception(MsgException("XMPP session ended"))
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
            except Exception as err:
                _LOGGER.warning("Unexpected XMPP error for %s: %s", path, err)
                raise DeviceException(f"Unexpected error for {path}: {err}")
        
        raise DeviceException(f"Error requesting data from {path}: empty response")

    async def put(self, path, value):
        _LOGGER.debug("Sending PUT request to %s with value %s", path, value)
        json_data = json.dumps({"value": value})
        data = await self._request(
            method=PUT,
            encrypted_msg=self._encryption.encrypt(json_data),
            path=path,
            payload=json_data,
        )
        if data:
            return True
    async def _request(self, method, path, encrypted_msg=None, timeout=REQUEST_TIMEOUT, payload=None):
        async with self._request_lock:
            data = None
            _LOGGER.debug("XMPP unencrypted request: %s %s%s", method, path, f" payload: {payload}" if payload else "")
            try:
                if not self._auth_success:
                    _LOGGER.info("XMPP not authorized, connecting...")
                    self.client.connect()
                    async with asyncio.timeout(30):
                        await self.connected_event.wait()
                    if not self._auth_success:
                        raise FailedAuthException("Can't authorize to XMPP server.")
            except asyncio.TimeoutError:
                _LOGGER.error(
                    "Can't connect to XMPP server!. Check your network connection or credentials!"
                )
                raise DeviceException("XMPP connection timeout")

            # Use sequence number as the unique key for this request
            seq_no = self._count
            self._count += 1
            future = asyncio.get_running_loop().create_future()
            self._pending[seq_no] = future

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
                _LOGGER.warn(err)
                raise EncryptionException(err)
            finally:
                self._pending.pop(seq_no, None)
                if not future.done():
                    future.cancel()
                if put_lock is not None and put_lock.locked():
                    put_lock.release()

    def main_listener(self, msg):
        if msg["type"] not in ("normal", "chat"):
            return
        body = msg["body"]
        if not body:
            return

        try:
            body_arr = body.split("\n")
        except AttributeError:
            return

        # Extract Seq-No from headers
        seq_no = None
        for line in body_arr:
            if line.startswith("Seq-No:"):
                try:
                    seq_no = int(line.split(":")[1].strip())
                except (ValueError, IndexError):
                    pass
                break

        if seq_no is not None:
            fut = self._pending.get(seq_no)
            if not fut and seq_no == 0 and len(self._pending) == 1:
                # Some gateways ignore Seq-No and always return 0.
                # Since we serialize requests via _request_lock, we can safely
                # match the single pending request.
                
                # Match the single pending request's sequence number
                actual_seq = next(iter(self._pending))
                
                # HARDENING: Only match if this request was started AFTER the last timeout.
                # If actual_seq <= _last_timeout_seq, this response is likely a ghost
                # from a request that already timed out.
                if actual_seq <= self._last_timeout_seq:
                    _LOGGER.warning(
                        "Ignoring late Seq-No: 0 response (matches timed-out Seq: %d). Current Seq: %d",
                        actual_seq,
                        actual_seq,
                    )
                    return

                seq_no = actual_seq
                fut = self._pending.get(seq_no)
                _LOGGER.debug("Matching Seq-No: 0 response to pending Seq-No: %d", seq_no)

            if not fut or fut.done():
                _LOGGER.debug("Received XMPP response for unknown or already completed Seq-No: %d", seq_no)
                return
        else:
            _LOGGER.warning("Received XMPP message without Seq-No header")
            return

        http_response = body_arr[0]
        if re.match(r"HTTP/1.[0-1] 20*", http_response):
            payload = ""
            for line in reversed(body_arr):
                if line.strip():
                    payload = line
                    break
            try:
                decrypted_body = self._encryption.json_decrypt(payload)
                _LOGGER.debug("XMPP unencrypted response (Seq: %d): %s", seq_no, decrypted_body)
                fut.set_result(decrypted_body if decrypted_body else True)
            except EncryptionException:
                fut.set_exception(EncryptionException("Can't decrypt"))
            return

        if re.match(r"HTTP/1.[0-1] 40*", http_response):
            fut.set_exception(MsgException(f"400 HTTP Error: {body}"))

    @staticmethod
    def discard_ssl_invalid_chain(*_, **__):
        """Do nothing if ssl certificate is invalid."""
        _LOGGER.debug("Ignoring invalid SSL certificate as requested")
