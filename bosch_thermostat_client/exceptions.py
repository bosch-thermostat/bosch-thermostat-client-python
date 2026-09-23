"""Bosch Themrostat errors."""

from bosch_thermostat_client.const import APP_JSON


class BoschException(Exception):
    """Base error for bosch_Thermostat."""


class DeviceException(BoschException):
    """
    Invalid request.

    Unable to fulfill request.
    Raised when host or API cannot be reached.
    """

    pass


class DeviceConnectionError(DeviceException):
    """HTTP request failed before a complete response was received."""


class MsgException(DeviceException):
    """
    Invalid request.

    Unable to fulfill request.
    Raised when host or API cannot be reached.
    """

    pass


class FirmwareException(BoschException):
    """Unsupported firmware version.

    Deliberately NOT a DeviceException: it describes the device, not a failed
    request, and consumers handle it separately from transport errors.
    """

    pass


class FailedAuthException(BoschException):
    """Failed auth.

    Deliberately NOT a DeviceException: consumers catch DeviceException around
    updates and discovery, and a wrong access key has to reach them so they can
    ask for credentials again instead of retrying forever.
    """
    pass


class UnknownDevice(BoschException):
    """Device model is not in the database.

    Deliberately NOT a DeviceException, for the same reason as
    FirmwareException.
    """

    pass


class ResponseException(BoschException):
    """
    When trying to connect to something what is not surely Bosch."""

    def __init__(self, response_info):
        self._status = False
        self._content_type = False
        if response_info:
            self._status = response_info.status if response_info.status else False
            self._content_type = (
                response_info._content_type if response_info._content_type else False
            )

    def __str__(self):
        if self._status == 200 and self._content_type != APP_JSON:
            return "Wrong content_type %s" % (self._content_type)
        return "Wrong status %s with content_type %s" % (
            self._status,
            self._content_type,
        )


class EncryptionException(BoschException):
    """Unable to decrypt."""
