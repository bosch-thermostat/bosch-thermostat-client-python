#!/usr/bin/env python3
"""Unit tests for PoinTT API token refresh functionality."""

import unittest
import asyncio
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from aiohttp import ClientSession

from bosch_thermostat_client.connectors.pointtapi import PoinTTAPIConnector
from bosch_thermostat_client.exceptions import DeviceException


class TestTokenRefresh(unittest.TestCase):
    """Test token refresh functionality."""

    def setUp(self):
        """Set up test fixtures."""
        self.test_token_file = Path("test_tokens.json")
        self.device_id = "test_device_123"
        self.access_token = "test_access_token"
        self.refresh_token = "test_refresh_token"

        # Clean up any existing test token file
        if self.test_token_file.exists():
            self.test_token_file.unlink()

    def tearDown(self):
        """Clean up after tests."""
        if self.test_token_file.exists():
            self.test_token_file.unlink()

    def test_is_token_expired_no_expiry_with_refresh_token(self):
        """Test that token is considered expired when no expiry is set but refresh token exists."""
        with patch('aiohttp.ClientSession') as mock_session:
            connector = PoinTTAPIConnector(
                host=self.device_id,
                access_token=self.access_token,
                loop=mock_session(),
                token_file=str(self.test_token_file)
            )

            # Set refresh token but no expiry
            connector._refresh_token = self.refresh_token
            connector._token_expires_at = None

            # Should return True (expired) because we have refresh token but no expiry
            result = connector._is_token_expired()
            print(f"Test 1: no expiry + refresh token -> expired={result}")
            self.assertTrue(result, "Token should be expired when no expiry is set but refresh token exists")

    def test_is_token_expired_past_expiry(self):
        """Test that token is expired when expiry is in the past."""
        with patch('aiohttp.ClientSession') as mock_session:
            connector = PoinTTAPIConnector(
                host=self.device_id,
                access_token=self.access_token,
                loop=mock_session(),
                token_file=str(self.test_token_file)
            )

            # Set expiry to 10 minutes ago
            connector._refresh_token = self.refresh_token
            connector._token_expires_at = datetime.now(timezone.utc) - timedelta(minutes=10)

            result = connector._is_token_expired()
            print(f"Test 2: past expiry -> expired={result}")
            self.assertTrue(result, "Token should be expired when expiry is in the past")

    def test_is_token_expired_near_expiry(self):
        """Test that token is expired when expiry is within 5 minutes."""
        with patch('aiohttp.ClientSession') as mock_session:
            connector = PoinTTAPIConnector(
                host=self.device_id,
                access_token=self.access_token,
                loop=mock_session(),
                token_file=str(self.test_token_file)
            )

            # Set expiry to 3 minutes from now (within 5 minute buffer)
            connector._refresh_token = self.refresh_token
            connector._token_expires_at = datetime.now(timezone.utc) + timedelta(minutes=3)

            result = connector._is_token_expired()
            print(f"Test 3: expires in 3 minutes -> expired={result}")
            self.assertTrue(result, "Token should be expired when expiry is within 5 minutes")

    def test_is_token_expired_valid_token(self):
        """Test that token is not expired when expiry is well in the future."""
        with patch('aiohttp.ClientSession') as mock_session:
            connector = PoinTTAPIConnector(
                host=self.device_id,
                access_token=self.access_token,
                loop=mock_session(),
                token_file=str(self.test_token_file)
            )

            # Set expiry to 30 minutes from now
            connector._refresh_token = self.refresh_token
            connector._token_expires_at = datetime.now(timezone.utc) + timedelta(minutes=30)

            result = connector._is_token_expired()
            print(f"Test 4: expires in 30 minutes -> expired={result}")
            self.assertFalse(result, "Token should not be expired when expiry is 30 minutes away")

    def test_refresh_access_token(self):
        """Test that refresh_access_token actually calls the API and updates tokens."""
        async def run_test():
            # Mock the aiohttp session with proper async context manager
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_response.json = AsyncMock(return_value={
                'access_token': 'new_access_token',
                'refresh_token': 'new_refresh_token',
                'expires_in': 3600
            })

            # Create context manager mock
            mock_cm = AsyncMock()
            mock_cm.__aenter__ = AsyncMock(return_value=mock_response)
            mock_cm.__aexit__ = AsyncMock(return_value=None)

            mock_session = MagicMock()
            mock_session.post = MagicMock(return_value=mock_cm)

            connector = PoinTTAPIConnector(
                host=self.device_id,
                access_token=self.access_token,
                loop=mock_session,
                token_file=str(self.test_token_file)
            )

            # Set refresh token
            connector._refresh_token = self.refresh_token

            print("\nTest 5: Calling _refresh_access_token()...")
            result = await connector._refresh_access_token()

            print(f"Result: {result}")
            print(f"New access token: {connector._access_token}")
            print(f"Token expires at: {connector._token_expires_at}")

            self.assertTrue(result)
            self.assertEqual(connector._access_token, 'new_access_token')
            self.assertEqual(connector._refresh_token, 'new_refresh_token')
            self.assertIsNotNone(connector._token_expires_at)

            # Check that token file was saved
            self.assertTrue(self.test_token_file.exists())
            with open(self.test_token_file, 'r') as f:
                saved_tokens = json.load(f)
                print(f"Saved tokens: {json.dumps(saved_tokens, indent=2)}")
                self.assertEqual(saved_tokens['access_token'], 'new_access_token')
                self.assertEqual(saved_tokens['refresh_token'], 'new_refresh_token')
                self.assertIsNotNone(saved_tokens['expires_at'])

        asyncio.run(run_test())

    def test_ensure_valid_token_with_expired_token(self):
        """Test that ensure_valid_token triggers refresh when token is expired."""
        async def run_test():
            # Mock the aiohttp session with proper async context manager
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_response.json = AsyncMock(return_value={
                'access_token': 'refreshed_token',
                'refresh_token': 'refreshed_refresh_token',
                'expires_in': 3600
            })

            # Create context manager mock
            mock_cm = AsyncMock()
            mock_cm.__aenter__ = AsyncMock(return_value=mock_response)
            mock_cm.__aexit__ = AsyncMock(return_value=None)

            mock_session = MagicMock()
            mock_session.post = MagicMock(return_value=mock_cm)

            connector = PoinTTAPIConnector(
                host=self.device_id,
                access_token=self.access_token,
                loop=mock_session,
                token_file=str(self.test_token_file)
            )

            # Set expired token
            connector._refresh_token = self.refresh_token
            connector._token_expires_at = datetime.now(timezone.utc) - timedelta(minutes=10)

            old_token = connector._access_token
            print(f"\nTest 6: Token expired, calling _ensure_valid_token()...")
            print(f"Old token: {old_token}")

            await connector._ensure_valid_token()

            print(f"New token: {connector._access_token}")
            print(f"Refresh was called: {connector._access_token != old_token}")

            self.assertNotEqual(connector._access_token, old_token)
            self.assertEqual(connector._access_token, 'refreshed_token')

        asyncio.run(run_test())

    def test_get_triggers_token_refresh(self):
        """Test that calling get() triggers token refresh when token is expired."""
        async def run_test():
            # Mock token refresh response
            mock_token_response = AsyncMock()
            mock_token_response.status = 200
            mock_token_response.json = AsyncMock(return_value={
                'access_token': 'refreshed_via_get',
                'refresh_token': 'refreshed_refresh_token',
                'expires_in': 3600
            })

            # Create token refresh context manager mock
            mock_token_cm = AsyncMock()
            mock_token_cm.__aenter__ = AsyncMock(return_value=mock_token_response)
            mock_token_cm.__aexit__ = AsyncMock(return_value=None)

            # Mock API call response
            mock_api_response = AsyncMock()
            mock_api_response.status = 200
            mock_api_response.json = AsyncMock(return_value={
                'id': '/test',
                'value': 'test_value'
            })
            mock_api_response.content_type = 'application/json'

            # Create API call context manager mock
            mock_api_cm = AsyncMock()
            mock_api_cm.__aenter__ = AsyncMock(return_value=mock_api_response)
            mock_api_cm.__aexit__ = AsyncMock(return_value=None)

            mock_session = MagicMock()
            mock_session.post = MagicMock(return_value=mock_token_cm)

            # Mock get method with __name__ attribute for logging
            mock_get = MagicMock(return_value=mock_api_cm)
            mock_get.__name__ = 'get'
            mock_session.get = mock_get

            connector = PoinTTAPIConnector(
                host=self.device_id,
                access_token=self.access_token,
                loop=mock_session,
                token_file=str(self.test_token_file)
            )

            # Set expired token
            connector._refresh_token = self.refresh_token
            connector._token_expires_at = datetime.now(timezone.utc) - timedelta(minutes=10)

            old_token = connector._access_token
            print(f"\nTest 7: Calling get() with expired token...")
            print(f"Old token: {old_token}")
            print(f"Token expired: {connector._is_token_expired()}")

            result = await connector.get('/test')

            print(f"New token: {connector._access_token}")
            print(f"Token was refreshed: {connector._access_token != old_token}")
            print(f"API call result: {result}")

            # Token should have been refreshed
            self.assertNotEqual(connector._access_token, old_token)
            self.assertEqual(connector._access_token, 'refreshed_via_get')

            # API call should have succeeded
            self.assertEqual(result['value'], 'test_value')

        asyncio.run(run_test())


if __name__ == '__main__':
    print("=" * 70)
    print("Testing PoinTT API Token Refresh")
    print("=" * 70)
    unittest.main(verbosity=2)
