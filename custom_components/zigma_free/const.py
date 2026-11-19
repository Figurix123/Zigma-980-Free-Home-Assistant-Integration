"""Constants for Zigma Free."""

from homeassistant.const import Platform

DOMAIN = "zigma_free"
DEFAULT_PORT = 8765
DEFAULT_SCAN_INTERVAL = 10
CONF_HOST = "host"
CONF_PORT = "port"
CONF_ACCESS_KEY = "access_key"
PLATFORMS = [Platform.VACUUM, Platform.SENSOR, Platform.BUTTON]
