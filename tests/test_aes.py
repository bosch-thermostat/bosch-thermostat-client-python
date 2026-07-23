import unittest
from bosch_thermostat_client.encryption import IVTEncryption as Encryption


class AesTest(unittest.TestCase):

    def setUp(self):
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
