BS = 16
XMPP = "XMPP"
HTTP = "HTTP"
OAUTH2 = "OAUTH2"
UUID = "uuid"

""" METHODS """
GET = "get"
PUT = "put"

GATEWAY = "gateway"
MODELS = "models"

TIMEOUT = 10
REQUEST_TIMEOUT = 6
BODY_400 = "400Error"
WRONG_ENCRYPTION = "WrongEncryption"

USER_AGENT = "User-Agent"
CONTENT_TYPE = "Content-Type"
APP_JSON = "application/json"

EMS = "EMS"
DEFAULT = "default"
ID = "id"
DATE = "dateTime"

HEATING_CIRCUITS = "heatingCircuits"
DHW_CIRCUITS = "dhwCircuits"
SOLAR_CIRCUITS = "solarCircuits"
AC_CIRCUITS = "acCircuits"
HC = "hc"
NAME = "name"
DHW = "dhw"
AC = "ac"
ZONES = "zones"
ZN = "zn"
SC = "sc"
PATH = "path"
RESULT = "result"  # to not mismarch with value
TYPE = "type"
URI = "uri"
TIMESTAMP = "timestamp"
REGULAR = "regular"
BINARY = "binary"
NUMBER = "number"
AUTO = "auto"
MANUAL = "manual"
SWITCH_PROGRAMS = "switchPrograms"

OPERATION_MODE = "operation_mode"
VALUE = "value"
MAX_VALUE = "maxValue"
MIN_VALUE = "minValue"
UNITS = "unitOfMeasure"
CURRENT_TEMP = "current_temp"
MODE_TO_SETPOINT = "mode_to_setpoint"
REFS = "refs"
HA_STATES = "hastates"
REFERENCES = "references"
RECORDINGS = "recordings"
STATUS = "status"
OFF = "off"
ACTIVE_PROGRAM = "activeProgram"

DEFAULT_MIN_TEMP = 0
DEFAULT_MAX_TEMP = 100
DEFAULT_MAX_HC_TEMP = 30
DEFAULT_MIN_HC_TEMP = 5
SETPOINT = "setpoint"

DAYS = {
    "Mo": "monday",
    "Tu": "tuesday",
    "We": "wednesday",
    "Th": "thursday",
    "Fr": "friday",
    "Sa": "saturday",
    "Su": "sunday",
}

DAYS_INT = [k for k in DAYS.keys()]
DAYS_INDEXES = [k for k in DAYS.values()]
DAYS_INV = [{v: k for k, v in DAYS.items()}]

MAX_REF = "max_ref"
MIN_REF = "min_ref"

HA_NAME = "haname"
BOSCH_NAME = "boschname"

MODE = "mode"
SWITCHPROGRAM = "switchprogram"
SWITCHPROGRAM_MODE = "switchProgramMode"
LEVELS = "levels"
ABSOLUTE = "absolute"
MAX = "max"
MIN = "min"
ON = "on"

FIRMWARE_VERSION = "versionFirmware"
BASE_FIRMWARE_VERSION = "versionFirmwarePath"
CRAWL_SENSORS = "crawlSensors"
SELECT = "select"
ENERGY_HISTORY_ENTRIES = "/energy/historyEntries"
ENERGY_HISTORY = "/energy/history"

ROOT_PATHS = [
    "/systemStates",
    "/dhwCircuits",
    "/gateway",
    "/heatingCircuits",
    "/heatSources",
    "/notifications",
    "/system",
    "/solarCircuits",
    "/recordings",
    "/devices",
    "/energy",
    "/events",
    "/programs",
    "/zones",
    "/ecus",
    "/application",
    "/gservice_tariff",
]
SENSORS = "sensors"
SWITCHES = "switches"
SWITCH = "switch"
SENSOR = "sensor"
VALUES = "values"
SENSOR_TYPE = "sensorType"
SYSTEM_BUS = "systemBus"
WRITEABLE = "writeable"
WRITE = "write"

RECORDERDRES = "recordedResource"
RECORDING = "recording"
ECUS_RECORDING = "ecus_recording"
INTERVAL = "interval"
SWITCH = "switch"
DEEP = "deep"
HVAC_ACTION = "hvacAction"
HVAC_HEAT = "heat"
HVAC_COOL = "cool"
HVAC_FAN = "fan"
HVAC_OFF = "off"
USED = "used"
ACCESS_KEY = "access_key"
TEMP_CELSIUS = "°C"
ENERGY_KILO_WATT_HOUR = "kWh"
ENERGY_WATT_HOUR = "Wh"
DB_RECORD = "db_record"
STATE_CLASS = "state_class"
DEVICE_CLASS = "device_class"
TURN_ON = "turn_on"
TURN_OFF = "turn_off"

SCHEDULE = "schedule"
PROGRAM = "program"
K_DAY = "key_day"
K_SETPOINT = "key_setpoint"
K_TIME = "key_time"

DEFAULT_STEP = "defaultStep"
