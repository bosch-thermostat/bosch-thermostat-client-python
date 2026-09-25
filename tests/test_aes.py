import pytest
import unittest

pytest.skip(
    "Written against the removed generic Encryption class; encryption is now split "
    "into IVTEncryption / NefitEncryption / EasycontrolEncryption. Needs a decision "
    "on which variant these AES vectors belong to before it can be restored.",
    allow_module_level=True,
)

from bosch_thermostat_client.encryption import Encryption  # noqa: E402


class AesTest(unittest.TestCase):

    def setup(self):
        self.client = Encryption('abc1abc2abc3abc4', 'passworddddd')

    # encrypt and decrypt a string
    def test_crypt(self):
        text = 'super_secret'
        text_encrypted = self.client.encrypt(text)
        text_decrypted = self.client.decrypt(text_encrypted)
        self.assertEqual(text, text_decrypted)

    # decrypt a known encrypted string
    def test_decrypt(self):
        text_encrypted = b'TTZEYuh9QQoc0fjUgElBwA=='
        text_decrypted = self.client.decrypt(text_encrypted)
        self.assertEqual("super_secret", text_decrypted)
