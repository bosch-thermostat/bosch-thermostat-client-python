"""Encryption logic of Bosch thermostat."""
import logging
import base64
import hashlib
import binascii
import json
from pyaes import PADDING_NONE, AESModeOfOperationECB, Decrypter, Encrypter

from bosch_thermostat_client.const import BS
from bosch_thermostat_client.exceptions import EncryptionException, DeviceException

_LOGGER = logging.getLogger(__name__)


class BaseEncryption:
    """Encryption class."""

    jsondecoder = json.JSONDecoder

    def __init__(self, access_key, password=None):
        """
        Initialize encryption.

        :param str access_key: Access key to Bosch thermostat.
            If no password specified assumed as ready key to encrypt.
        :param str password: Password created with Bosch app.
        """
        self._bs = BS
        if password and access_key:
            key_hash = hashlib.md5(bytearray(access_key, "utf8") + self.magic)
            password_hash = hashlib.md5(self.magic + bytearray(password, "utf8"))
            self._saved_key = key_hash.hexdigest() + password_hash.hexdigest()
            self._key = binascii.unhexlify(self._saved_key)
        elif access_key:
            self._saved_key = access_key
            self._key = binascii.unhexlify(self._saved_key)

    @classmethod
    def key_without_password(cls, access_key):
        """Key of a gateway whose app password was never set: its access key's alone."""
        key_hash = hashlib.md5(bytearray(access_key, "utf8") + cls.magic)
        return key_hash.hexdigest() + hashlib.md5(cls.magic).hexdigest()

    @property
    def key(self):
        """Return key to store in config entry."""
        return self._saved_key

    def json_decrypt(self, raw):
        try:
            if raw:
                return json.loads(self.decrypt(raw), cls=self.jsondecoder)
            return None
        except json.JSONDecodeError:
            raise DeviceException("Unable to decode Json response.")

    def encrypt(self, raw) -> bytes:
        """Encrypt raw message."""
        if len(raw) % self._bs != 0:
            raw = self._pad(raw)
        cipher = Encrypter(AESModeOfOperationECB(self._key), padding=PADDING_NONE)
        ciphertext = cipher.feed(raw) + cipher.feed()
        return base64.b64encode(ciphertext)

    def decrypt(self, enc):
        """
        Decryption algorithm.

        Decrypt raw message only if length > 2.
        Padding is not working for lenght less than 2.
        """
        decrypted = "{}"
        try:
            if enc and len(enc) > 2:
                enc = base64.b64decode(enc)
                if len(enc) % self._bs != 0:
                    enc = self._pad(enc)
                cipher = Decrypter(
                    AESModeOfOperationECB(self._key), padding=PADDING_NONE
                )
                decrypted = cipher.feed(enc) + cipher.feed()
                return decrypted.decode("utf8").rstrip(chr(0))
            return decrypted
        except UnicodeDecodeError as err:
            _LOGGER.debug(f"Unable to decrypt: {decrypted} with error: {err}")
            raise EncryptionException(f"Unable to decrypt: {err}")
        except Exception as err:
            raise EncryptionException(f"Unable to decrypt: {err}")

    def _pad(self, _s):
        """Pad of encryption."""
        return _s + ((self._bs - len(_s) % self._bs) * chr(0))
