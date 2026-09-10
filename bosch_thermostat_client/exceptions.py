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


class MsgException(BoschException):
    """
    Invalid request.

    Unable to fulfill request.
    Raised when host or API cannot be reached.
    """

    pass


class FirmwareException(BoschException):
    """
    Wrong firmware version.

    Unable to fulfill request.
    Raised when host or API cannot be reached.
    """

    pass


class FailedAuthException(BoschException):
    """Failed auth."""
    pass


class UnknownDevice(BoschException):
    """
    Unknown device.

    Unable to fulfill request.
    Raised when host or API cannot be reached.
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
