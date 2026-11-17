#!/usr/bin/env python3
"""
PoinTT API OAuth Setup Example

This script demonstrates how to authenticate with the Bosch PoinTT API using OAuth 2.0.
After authentication, tokens are saved to a JSON file for use with Home Assistant or
other applications.

Usage:
    python3 pointtapi_oauth_setup.py

The script will:
1. Open your browser to the Bosch login page
2. Ask you to paste the callback URL after login
3. Exchange the authorization code for access/refresh tokens
4. Save tokens to tokens.json
5. Test the connection by fetching device information
"""

import asyncio
import json
import logging
import sys
from pathlib import Path

import aiohttp

from bosch_thermostat_client.const import POINTTAPI
from bosch_thermostat_client.gateway import gateway_chooser

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
_LOGGER = logging.getLogger(__name__)


async def authenticate_and_save_tokens(device_id=None, token_file="tokens.json"):
    """
    Perform OAuth authentication flow and save tokens.

    Args:
        device_id (str, optional): Your Bosch device ID (gateway UUID)
        token_file (str): Path to save tokens (default: tokens.json)

    Returns:
        dict: Token information if successful, None otherwise
    """
    print("\n" + "="*70)
    print("Bosch PoinTT API - OAuth Authentication Setup")
    print("="*70)

    # Get device ID if not provided
    if not device_id:
        print("\nYou'll need your device ID (gateway UUID) to proceed.")
        print("You can find this in the Bosch mobile app or after successful login.")
        device_id = input("Enter your device ID (or press Enter to skip for now): ").strip()
        if not device_id:
            device_id = "TEMPORARY_ID"  # Will need to update later
            print("⚠️  Using temporary ID - you'll need to update tokens.json with your real device ID")

    async with aiohttp.ClientSession() as session:
        # Create connector to handle OAuth flow
        # We use a placeholder for access_token initially
        GatewayClass = gateway_chooser(POINTTAPI)
        gateway = GatewayClass(
            session=session,
            session_type="HTTP",
            host=device_id,
            access_key=None,
            access_token="PLACEHOLDER",  # Will be replaced after OAuth
            refresh_token=None,
            token_file=None  # Don't auto-save yet
        )

        connector = gateway._connector

        # Step 1: Generate and open OAuth URL
        print("\n[Step 1] Opening browser for Bosch login...")
        auth_url = connector.start_oauth_flow(open_browser=True)
        print(f"\nIf browser didn't open, visit this URL manually:")
        print(f"{auth_url}\n")

        # Step 2: Get callback URL from user
        print("[Step 2] After logging in, you'll be redirected to a URL starting with:")
        print("         com.bosch.tt.dashtt.pointt://app/login?code=...")
        print("\nNote: The page may show 'Cannot open page' - that's normal!")
        print("      Just copy the entire URL from your browser's address bar.\n")

        callback_url = input("Paste the callback URL here: ").strip()

        if not callback_url:
            print("❌ No URL provided. Exiting.")
            return None

        # Step 3: Extract authorization code
        print("\n[Step 3] Extracting authorization code...")
        code = connector.extract_code_from_url(callback_url)

        if not code:
            print("❌ Could not extract authorization code from URL.")
            print("   Make sure you copied the complete callback URL.")
            return None

        print(f"✓ Authorization code extracted: {code[:20]}...")

        # Step 4: Exchange code for tokens
        print("\n[Step 4] Exchanging code for access tokens...")
        success = await connector.exchange_code_for_tokens(code)

        if not success:
            print("❌ Token exchange failed. Check logs for details.")
            return None

        print("✓ Successfully obtained OAuth tokens!")

        # Step 5: Save tokens to file
        print(f"\n[Step 5] Saving tokens to {token_file}...")
        token_data = {
            "device_id": device_id,
            "access_token": connector._access_token,
            "refresh_token": connector._refresh_token,
            "expires_at": connector._token_expires_at.isoformat() if connector._token_expires_at else None,
        }

        token_path = Path(token_file)
        with open(token_path, 'w') as f:
            json.dump(token_data, f, indent=2)

        print(f"✓ Tokens saved to {token_path.absolute()}")

        # Step 6: Test connection (if real device ID provided)
        if device_id != "TEMPORARY_ID":
            print("\n[Step 6] Testing connection...")
            try:
                # Create a new gateway with the real tokens
                test_gateway = GatewayClass(
                    session=session,
                    session_type="HTTP",
                    host=device_id,
                    access_key=None,
                    access_token=connector._access_token,
                    refresh_token=connector._refresh_token,
                    token_file=token_file
                )

                await test_gateway.initialize()

                print("✓ Successfully connected to device!")
                print(f"  - Device UUID: {test_gateway.uuid}")
                print(f"  - Firmware: {test_gateway.get_info('firmware_version')}")

            except Exception as e:
                print(f"⚠️  Connection test failed: {e}")
                print("   Tokens are saved, but verify your device ID is correct.")

        return token_data


async def main():
    """Main entry point."""
    try:
        # Check if tokens already exist
        token_file = "tokens.json"
        if Path(token_file).exists():
            print(f"\n⚠️  Warning: {token_file} already exists!")
            response = input("Do you want to overwrite it? (y/N): ").strip().lower()
            if response != 'y':
                print("Aborting. Delete or rename the existing file to continue.")
                return

        # Run authentication flow
        tokens = await authenticate_and_save_tokens(token_file=token_file)

        if tokens:
            print("\n" + "="*70)
            print("✓✓✓ Authentication Complete! ✓✓✓")
            print("="*70)
            print(f"\nYour tokens have been saved to: {Path(token_file).absolute()}")
            print("\nNext steps:")
            print("1. Keep tokens.json secure (contains sensitive credentials)")
            print("2. For Home Assistant:")
            print("   - Use the device_id, access_token, and refresh_token")
            print("   - HA will automatically refresh tokens as needed")
            print("3. For standalone scripts:")
            print("   - Load tokens.json and create PoinTTAPIGateway")
            print("   - Tokens will auto-refresh when expired")
            print("\nExample usage in Python:")
            print("""
    import json
    import aiohttp
    from bosch_thermostat_client.gateway.pointtapi import PoinTTAPIGateway

    # Load tokens
    with open('tokens.json') as f:
        tokens = json.load(f)

    # Create gateway
    async with aiohttp.ClientSession() as session:
        gateway = PoinTTAPIGateway(
            session=session,
            session_type="HTTP",
            host=tokens['device_id'],
            access_key=None,
            access_token=tokens['access_token'],
            refresh_token=tokens['refresh_token'],
            token_file='tokens.json'
        )
        await gateway.initialize()

        # Use gateway...
        print(f"Temperature: {gateway.ac_circuits[0].current_temp}°C")
            """)
        else:
            print("\n❌ Authentication failed. Please try again.")
            sys.exit(1)

    except KeyboardInterrupt:
        print("\n\nAuthentication cancelled by user.")
        sys.exit(1)
    except Exception as e:
        _LOGGER.exception("Unexpected error during authentication")
        print(f"\n❌ Unexpected error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
