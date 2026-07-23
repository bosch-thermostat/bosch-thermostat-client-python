"""Circuits module of Bosch thermostat."""
import logging
from bosch_thermostat_client.circuits.circuit import BasicCircuit
from bosch_thermostat_client.circuits.easycontrol import (
    EasyDhwCircuit,
    EasyControlDVCircuit,
)
from bosch_thermostat_client.const import (
    ID,
    HC,
    DHW,
    ZN,
    SC,
    AC,
    REFERENCES,
    OAUTH2,
)
from bosch_thermostat_client.helper import BoschEntities
from .nefit import NefitCircuit, NefitHeatingCircuit
from .ivt import IVTCircuit
from .easycontrol import EasycontrolCircuit, EasyZoneCircuit
from .ivtair import ACCircuit
from bosch_thermostat_client.const.ivt import IVT, CIRCUIT_TYPES, IVT_MBLAN, IVTAIR, BRUDERUS
from bosch_thermostat_client.const.nefit import NEFIT
from bosch_thermostat_client.const.easycontrol import (
    EASYCONTROL,
    PROGRAM_LIST,
    DV,
    CIRCUIT_TYPES as EASYCONTROL_CIRCUIT_TYPES,
)
from bosch_thermostat_client.const.oauth2 import (
    CIRCUIT_TYPES as POINTTAPI_CIRCUIT_TYPES,
)
from bosch_thermostat_client.schedule import ZonePrograms

_LOGGER = logging.getLogger(__name__)


def choose_circuit_type(device_type, circuit_type):
    def suffix():
        if circuit_type == ZN:
            return ZN
        elif circuit_type == HC and device_type == NEFIT:
            return HC
        elif circuit_type == DHW and device_type == EASYCONTROL:
            return DHW
        elif circuit_type == AC:
            return AC
        else:
            return ""

    _LOGGER.debug("searching for circuit type: %s", device_type + suffix())
    return {
        IVT: IVTCircuit,
        IVT_MBLAN: IVTCircuit,
        NEFIT: NefitCircuit,
        NEFIT + HC: NefitHeatingCircuit,
        EASYCONTROL: EasycontrolCircuit,
        EASYCONTROL + DHW: EasyDhwCircuit,
        EASYCONTROL + ZN: EasyZoneCircuit,
        IVTAIR + AC: ACCircuit,
        BRUDERUS: IVTCircuit,
    }[device_type + suffix()]


class Circuits(BoschEntities):
    """Circuits main object containing multiple Circuit objects."""

    def __init__(self, connector, circuit_type, bus_type, device_type):
        """
        Initialize circuits.

        :param obj get -> get function
        :param obj put -> put http function
        :param str circuit_type: is it HC or DHW
        """
        self._circuit_type = circuit_type
        self._connector = connector
        self._bus_type = bus_type
        self._device_type = device_type
        self._zone_programs = None
        super().__init__(connector.get)

    @property
    def circuits(self):
        """Get circuits."""
        return self.get_items()

    async def initialize(self, database, current_date, db_prefix):
        """Initialize HeatingCircuits asynchronously."""
        if not self._circuit_type:
            return None
        if db_prefix not in database:
            _LOGGER.debug("Circuit not exist in database %s", db_prefix)
            return None
        circuits = await self.retrieve_from_module(1, f"/{db_prefix}")
        if self._device_type == EASYCONTROL and PROGRAM_LIST in database:
            self._zone_programs = ZonePrograms(
                program_uri=database[PROGRAM_LIST], connector=self._connector
            )

        for circuit in circuits:
            if REFERENCES in circuit:
                circuit_object = self.create_circuit(circuit, database, current_date)
                if circuit_object:
                    await circuit_object.initialize()
                    if circuit_object.state:
                        self._items.append(circuit_object)

    def create_circuit(self, circuit, database, current_date):
        """Create single circuit of given type."""
        if self._circuit_type == SC or (
            self._circuit_type == HC and self._device_type == EASYCONTROL
        ):
            return BasicCircuit(
                connector=self._connector,
                attr_id=circuit[ID],
                db=database,
                _type=CIRCUIT_TYPES[self._circuit_type],
                bus_type=self._bus_type,
            )
        elif self._circuit_type in (HC, DHW, ZN):
            Circuit = choose_circuit_type(self._device_type, self._circuit_type)
            return Circuit(
                connector=self._connector,
                attr_id=circuit[ID],
                db=database,
                _type=self._circuit_type,
                bus_type=self._bus_type,
                current_date=current_date,
                zone_program=self._zone_programs,
            )
        elif self._circuit_type == DV:
            return EasyControlDVCircuit(
                connector=self._connector,
                attr_id=circuit[ID],
                db=database,
                _type=EASYCONTROL_CIRCUIT_TYPES[self._circuit_type],
                bus_type=self._bus_type,
            )
        elif self._circuit_type == AC:
            Circuit = choose_circuit_type(self._device_type, self._circuit_type)
            return Circuit(
                connector=self._connector,
                attr_id=circuit[ID],
                db=database,
                _type=POINTTAPI_CIRCUIT_TYPES[self._circuit_type],
                bus_type=self._bus_type,
            )
        return None
