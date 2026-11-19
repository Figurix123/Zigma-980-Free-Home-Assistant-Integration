"""Constants for Zigma Free."""

from homeassistant.const import Platform

DOMAIN = "zigma_free"
DEFAULT_PORT = 8765
DEFAULT_SCAN_INTERVAL = 10
CONF_HOST = "host"
CONF_PORT = "port"
CONF_ACCESS_KEY = "access_key"
CONF_FAN_POWER = "fan_power"
FAN_POWER_OPTIONS = {"Leise": 1, "Normal": 2, "Maximal": 3}
DEFAULT_FAN_POWER = 3
PLATFORMS = [
    Platform.VACUUM,
    Platform.SENSOR,
    Platform.BUTTON,
    Platform.CAMERA,
    Platform.SWITCH,
    Platform.SELECT,
]
