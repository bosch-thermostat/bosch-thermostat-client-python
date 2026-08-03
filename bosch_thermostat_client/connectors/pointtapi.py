"""PoinTT API connector for Bosch thermostats."""

import json
import logging
import asyncio
import base64
import hashlib
import urllib.parse
import webbrowser
from collections import namedtuple
from urllib.parse import urljoin, unquote, urlencode, urlunparse
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
import os
import stat
from pathlib import Path

from aiohttp.client_exceptions import (
    ClientResponseError,
    ClientConnectorError,
    ClientError,
)

from bosch_thermostat_client.const import POINTTAPI, APP_JSON, GET, PUT
from bosch_thermostat_client.exceptions import DeviceException, ResponseException

_LOGGER = logging.getLogger(__name__)


class BulkEndpoint:
    """Stores a list of URIs for bulk requests.
    Keeps track of requesting the bulk data, and storing the result
    for each URI. When a URI is requested and there is data available,
    no new bulk request is made unless it is the second time that URI
    is requested since the last bulk request.
    """

    def __init__(self, websession, headers_callback, endpoint, uris):
        """Initialize BulkEndpoint.

        Args:
            websession: The aiohttp session for making requests
            headers_callback: Callable that returns current headers (for token refresh)
            endpoint: The bulk endpoint URL
            uris: List of URIs this bulk endpoint covers
        """
        self._websession = websession
        self._headers_callback = headers_callback
        self._endpoint = endpoint
        self._uris = uris
        self._data = {}
        self._requested_uris = set()

    async def get(self, uri):
        if uri in self._uris:
            if uri not in self._data or uri in self._requested_uris:
                await self._request()
                self._requested_uris.clear()
            self._requested_uris.add(uri)
            result = self._data.get(uri)
            if result is None:
                _LOGGER.warning(
                    "URI %s is in bulk endpoint but not in response data. "
                    "Available URIs: %s",
                    uri,
                    list(self._data.keys())
                )
            return result
        else:
            return {}

    async def _request(self):
        # Get fresh headers on each request to handle token refresh
        headers = self._headers_callback()
        try:
            async with self._websession.get(self._endpoint, headers=headers) as response:
                if response.status != 200:
                    _LOGGER.error(
                        "Bulk endpoint %s returned status %s",
                        self._endpoint,
                        response.status
                    )
                    return
                data = await response.json()
            for uri_data in data.get("references", []):
                self._data[uri_data["id"]] = uri_data
            _LOGGER.debug(
                "Bulk endpoint %s fetched %d URIs",
                self._endpoint,
                len(self._data)
            )
        except Exception as e:
            _LOGGER.error(
                "Error fetching bulk endpoint %s: %s",
                self._endpoint,
                e
            )


class PoinTTAPIConnector:
    """Connector for Bosch PoinTT API with OAuth authentication."""

    POINTTAPI_BASE_URL = "https://pointt-api.bosch-thermotechnology.com/pointt-api/api/v1/gateways/"
    TOKEN_URL = "https://singlekey-id.com/auth/connect/token"
    AUTH_BASE_URL = "https://singlekey-id.com"

    # OAuth constants
    CLIENT_ID = "762162C0-FA2D-4540-AE66-6489F189FADC"
    REDIRECT_URI = "com.bosch.tt.dashtt.pointt://app/login"
    # Note: CODE_VERIFIER is static (not randomized per flow)
    # This matches the official Bosch mobile app implementation.
    # The Bosch PoinTT API appears to expect this specific verifier value.
    CODE_VERIFIER = "abcdefghijklmnopqrstuvwxyz0123456789abcdefghijklm"

    SCOPES = [
        "openid",
        "email",
        "profile",
        "offline_access",
        "pointt.gateway.claiming",
        "pointt.gateway.removal",
        "pointt.gateway.list",
        "pointt.gateway.users",
        "pointt.gateway.resource.dashapp",
        "pointt.castt.flow.token-exchange",
        "bacon",
    ]

    def __init__(self, host, access_token, refresh_token=None, token_expires_at=None, device_type=POINTTAPI, token_file=None, **kwargs):
        """Init PoinTT API connector.

        Args:
            host: Device ID for the PoinTT API (not a hostname)
            access_token: OAuth access token
            refresh_token: OAuth refresh token (optional, for token renewal)
            token_expires_at: Token expiration timestamp (ISO string or datetime, optional)
            device_type: Device type constant
            token_file: Path to token storage file (optional, for standalone use)
            **kwargs: Additional arguments including 'loop' for websession
        """
        self._lock = asyncio.Lock()
        self._device_id = host  # In PoinTT API, 'host' is actually the device ID
        self._base_url = f"{self.POINTTAPI_BASE_URL}{self._device_id}/"
        self._websession = kwargs.get("loop")
        self._request_timeout = 30
        self.device_type = device_type
        self._token_file = Path(token_file) if token_file else None

        # OAuth token management
        self._access_token = access_token
        self._refresh_token = refresh_token

        # Parse token_expires_at if provided
        if token_expires_at:
            if isinstance(token_expires_at, str):
                self._token_expires_at = datetime.fromisoformat(token_expires_at)
            else:
                self._token_expires_at = token_expires_at
        else:
            self._token_expires_at = None

        # Bulk request management
        self._bulk_endpoints = {}
        self._uri_bulk_endpoints = {}

        # Load existing tokens if available (only if token_file provided)
        if self._token_file:
            self._load_tokens()

    def _load_tokens(self):
        """Load tokens from JSON file if it exists."""
        try:
            if self._token_file.exists():
                # Check file permissions for security
                file_stat = self._token_file.stat()
                if file_stat.st_mode & 0o077:
                    _LOGGER.warning(
                        "Token file %s has insecure permissions %s, should be 0600",
                        self._token_file,
                        oct(file_stat.st_mode)[-3:]
                    )

                with open(self._token_file, 'r', encoding='utf-8') as f:
                    tokens = json.load(f)
                    self._access_token = tokens.get('access_token', self._access_token)
                    self._refresh_token = tokens.get('refresh_token')
                    expires_at = tokens.get('expires_at')
                    if expires_at:
                        self._token_expires_at = datetime.fromisoformat(expires_at)

                _LOGGER.debug("Successfully loaded tokens from %s", self._token_file)
        except json.JSONDecodeError as e:
            _LOGGER.error("Invalid JSON in token file %s: %s", self._token_file, e)
        except Exception as e:
            _LOGGER.warning("Could not load tokens from %s: %s", self._token_file, e)

    def _save_tokens(self):
        """Save tokens to JSON file with secure permissions.

        Only saves if token_file was provided during initialization.
        For Home Assistant integration, tokens are managed by HA via entry.data.
        """
        if not self._token_file:
            _LOGGER.debug("Token file not configured, skipping save (using HA entry.data)")
            return

        try:
            tokens = {
                'access_token': self._access_token,
                'refresh_token': self._refresh_token,
                'expires_at': self._token_expires_at.isoformat() if self._token_expires_at else None,
                'saved_at': datetime.now(timezone.utc).isoformat(),
                'device_id': self._device_id,
            }

            # Create file with secure permissions (0600 - owner read/write only)
            with open(self._token_file, 'w', encoding='utf-8') as f:
                json.dump(tokens, f, indent=2)

            # Set file permissions to 0600 (owner read/write only)
            try:
                os.chmod(self._token_file, stat.S_IRUSR | stat.S_IWUSR)
                _LOGGER.debug("Set secure permissions (0600) on token file %s", self._token_file)
            except OSError as e:
                _LOGGER.warning("Could not set secure permissions on %s: %s", self._token_file, e)

            _LOGGER.debug("Successfully saved tokens to %s", self._token_file)

        except Exception as e:
            _LOGGER.error("Could not save tokens to %s: %s", self._token_file, e)

    def _is_token_expired(self):
        """Check if the current token is expired or expires soon.

        Returns True if:
        - Token expires within 5 minutes, OR
        - No expiry timestamp is set (initial state with refresh token available)
        """
        if not self._token_expires_at:
            # If we have a refresh token but no expiry, refresh proactively
            return bool(self._refresh_token)
        # Consider token expired if it expires within 5 minutes
        return datetime.now(timezone.utc) >= (self._token_expires_at - timedelta(minutes=5))

    async def _refresh_access_token(self):
        """Refresh the access token using the refresh token."""
        if not self._refresh_token:
            raise DeviceException("No refresh token available")

        data = {
            'grant_type': 'refresh_token',
            'refresh_token': self._refresh_token,
            'scope': ' '.join(self.SCOPES),
            'client_id': self.CLIENT_ID,
            'code_verifier': self.CODE_VERIFIER,
        }

        try:
            async with self._websession.post(self.TOKEN_URL, data=data) as response:
                if response.status == 200:
                    token_data = await response.json()
                    self._access_token = token_data.get('access_token')
                    if 'refresh_token' in token_data:
                        self._refresh_token = token_data['refresh_token']

                    expires_in = token_data.get('expires_in', 3600)
                    self._token_expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)

                    self._save_tokens()
                    _LOGGER.info("Successfully refreshed access token (expires in %s seconds)", expires_in)
                    return True
                else:
                    raise DeviceException(f"Token refresh failed: {response.status}")
        except Exception as e:
            raise DeviceException(f"Error refreshing token: {e}")

    async def _ensure_valid_token(self):
        """Ensure we have a valid access token, refreshing if necessary."""
        if self._is_token_expired():
            await self._refresh_access_token()

    @property
    def _headers(self):
        return {"Authorization": f"Bearer {self._access_token}"}

    def _make_url(self, uri):
        """Make full URL from URI."""
        return urljoin(self._base_url + "resource/", uri.lstrip("/"))

    def add_bulk_endpoint(self, endpoint, uris):
        """Add a bulk endpoint for efficient batch requests."""
        bulk_endpoint = BulkEndpoint(
            self._websession, lambda: self._headers, self._make_url(endpoint), uris
        )
        self._bulk_endpoints[endpoint] = bulk_endpoint
        self._uri_bulk_endpoints.update({uri: bulk_endpoint for uri in uris})

    async def _request(self, method, uri, **kwargs):
        """Make authenticated request to PoinTT API with exponential backoff retry.

        Retries on:
        - HTTP 429 (Too Many Requests)
        - HTTP 503 (Service Unavailable)

        Retry configuration:
        - Initial backoff: 1 second
        - Max backoff: 60 seconds
        - Max retries: 5 attempts
        - Backoff multiplier: 2x
        """
        await self._ensure_valid_token()

        url = self._make_url(uri)
        headers = kwargs.get('headers', {})
        headers.update(self._headers)
        kwargs['headers'] = headers
        kwargs.setdefault('timeout', self._request_timeout)

        # Retry configuration
        max_retries = 5
        initial_backoff = 1.0  # seconds
        max_backoff = 60.0  # seconds
        backoff_multiplier = 2.0

        last_exception = None
        backoff = initial_backoff

        for attempt in range(max_retries):
            try:
                _LOGGER.debug("Sending %s request to %s (attempt %d/%d)",
                             method.__name__.upper(), url, attempt + 1, max_retries)

                method_func = getattr(self._websession, method.__name__)
                async with method_func(url, **kwargs) as response:
                    # Check for rate limiting or service unavailable
                    if response.status in (429, 503):
                        if attempt < max_retries - 1:
                            # Calculate backoff with exponential increase
                            wait_time = min(backoff, max_backoff)
                            _LOGGER.warning(
                                "Received HTTP %d for %s, retrying in %.1f seconds (attempt %d/%d)",
                                response.status, uri, wait_time, attempt + 1, max_retries
                            )
                            await asyncio.sleep(wait_time)
                            backoff *= backoff_multiplier
                            continue
                        else:
                            # Last attempt failed
                            raise DeviceException(
                                f"Max retries exceeded for {uri}: HTTP {response.status}"
                            )

                    if response.status == 200:
                        if response.content_type == APP_JSON:
                            return await response.json()
                        else:
                            return await response.text()
                    elif method.__name__ == 'put' and response.status == 204:
                        return True
                    else:
                        raise ResponseException(response)

            except ClientResponseError as err:
                raise DeviceException(f"URI {uri} does not exist: {err}")
            except ClientConnectorError as err:
                raise DeviceException(f"Connection error: {err}")
            except ClientError as err:
                raise DeviceException(f"Client error for {uri}: {err}")
            except DeviceException:
                # Re-raise DeviceException (including rate limit errors)
                raise
            except Exception as err:
                last_exception = err
                if attempt < max_retries - 1:
                    wait_time = min(backoff, max_backoff)
                    _LOGGER.warning(
                        "Request failed with %s, retrying in %.1f seconds (attempt %d/%d)",
                        type(err).__name__, wait_time, attempt + 1, max_retries
                    )
                    await asyncio.sleep(wait_time)
                    backoff *= backoff_multiplier
                    continue
                else:
                    raise DeviceException(f"Unexpected error for {uri}: {err}")

        # Should not reach here, but just in case
        if last_exception:
            raise DeviceException(f"Max retries exceeded for {uri}: {last_exception}")

    async def get(self, uri):
        """Get data from API endpoint."""
        # IMPORTANT: Ensure token is valid before ANY API call (including bulk endpoints)
        await self._ensure_valid_token()

        # Check if this URI has a bulk endpoint
        if uri in self._uri_bulk_endpoints:
            return await self._uri_bulk_endpoints[uri].get(uri)

        async with self._lock:
            return await self._request(self._websession.get, uri)

    async def put(self, uri, value):
        """Send data to API endpoint."""
        async with self._lock:
            data = json.dumps({"value": value})
            return await self._request(
                self._websession.put,
                uri,
                data=data,
                headers={"Content-Type": APP_JSON}
            )

    def set_timeout(self, timeout=30):
        """Set timeout for API calls."""
        self._request_timeout = timeout

    async def close(self, force=False):
        """Close the connector."""
        # PoinTT API connector doesn't maintain persistent connections
        # so there's nothing specific to close here
        pass

    # OAuth authentication methods

    def _generate_code_challenge(self):
        """Generate OAuth2 PKCE code challenge."""
        code_challenge = hashlib.sha256(self.CODE_VERIFIER.encode("utf-8")).digest()
        code_challenge = base64.urlsafe_b64encode(code_challenge).decode("utf-8")
        return code_challenge.replace("=", "")

    def build_auth_url(self):
        """
        Build the OAuth authorization URL.

        Returns:
            str: The complete OAuth authorization URL
        """
        Components = namedtuple(
            "Components", ["scheme", "netloc", "url", "path", "query", "fragment"]
        )

        code_challenge = self._generate_code_challenge()

        query_params = {
            "redirect_uri": urllib.parse.quote_plus(self.REDIRECT_URI),
            "client_id": self.CLIENT_ID,
            "response_type": "code",
            "prompt": "login",
            "state": "_yUmSV3AjUTXfn6DSZQZ-g",
            "nonce": "5iiIvx5_9goDrYwxxUEorQ",
            "scope": urllib.parse.quote(" ".join(self.SCOPES)),
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
            "style_id": "tt_bsch",
            "suppressed_prompt": "login",
        }

        query_params_encoded = unquote(urlencode(query_params))
        query = urllib.parse.quote(query_params_encoded)

        query_params_new = urllib.parse.quote_plus("/auth/connect/authorize/callback?")
        query_full = "ReturnUrl=" + query_params_new + query + "&f=g4nN"

        return urlunparse(
            Components(
                scheme="https",
                netloc="singlekey-id.com",
                query=query_full,
                path="",
                url="/auth/en-us/login",
                fragment="",
            )
        )

    def extract_code_from_url(self, url):
        """
        Extract authorization code from callback URL.

        Args:
            url (str): The callback URL containing the code

        Returns:
            str: The authorization code, or None if not found
        """
        try:
            if "code=" in url:
                parsed_url = urllib.parse.urlparse(url)
                query_params = urllib.parse.parse_qs(parsed_url.query)
                return query_params.get("code", [None])[0]
        except Exception as e:
            _LOGGER.error("Error extracting code from URL: %s", e)
        return None

    async def exchange_code_for_tokens(self, code):
        """
        Exchange authorization code for access and refresh tokens.

        Args:
            code (str): Authorization code from OAuth callback

        Returns:
            bool: True if successful, False otherwise
        """
        data = {
            "grant_type": "authorization_code",
            "scope": " ".join(self.SCOPES),
            "code": code,
            "redirect_uri": self.REDIRECT_URI,
            "client_id": self.CLIENT_ID,
            "code_verifier": self.CODE_VERIFIER,
        }

        try:
            async with self._websession.post(self.TOKEN_URL, data=data) as response:
                if response.status == 200:
                    response_json = await response.json()

                    if "access_token" in response_json and "refresh_token" in response_json:
                        # Update token information
                        self._access_token = response_json["access_token"]
                        self._refresh_token = response_json.get("refresh_token")

                        expires_in = response_json.get("expires_in", 3600)
                        self._token_expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)

                        self._save_tokens()

                        _LOGGER.info("Successfully obtained OAuth tokens")
                        return True
                    else:
                        _LOGGER.error("Missing tokens in OAuth response")
                        return False
                else:
                    error_text = await response.text()
                    _LOGGER.error("Token exchange failed: %s - %s", response.status, error_text)
                    return False

        except Exception as e:
            _LOGGER.error("Error during token exchange: %s", e)
            return False

    def start_oauth_flow(self, open_browser=True):
        """
        Start the OAuth authentication flow.

        Args:
            open_browser (bool): Whether to automatically open the browser

        Returns:
            str: The authorization URL
        """
        auth_url = self.build_auth_url()

        if open_browser:
            try:
                webbrowser.open(auth_url)
                _LOGGER.info("OAuth URL opened in browser")
            except Exception as e:
                _LOGGER.warning("Could not open browser: %s", e)
                _LOGGER.info("Please manually open: %s", auth_url)
        else:
            _LOGGER.info("OAuth URL: %s", auth_url)

        return auth_url