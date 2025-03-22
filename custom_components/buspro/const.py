"""Constants for the HDL Buspro integration."""

DOMAIN = "buspro"

# Device Types
DEVICE_TYPE_LIGHT = "light"
DEVICE_TYPE_COVER = "cover"
DEVICE_TYPE_CLIMATE = "climate"
DEVICE_TYPE_SENSOR = "sensor"

# Operation Codes
OPERATION_SINGLE_CHANNEL = 0x0031
OPERATION_READ_STATUS = 0x0032
OPERATION_DISCOVERY = 0x000D

# Configuration constants
CONF_DEVICE_SUBNET_ID = "device_subnet_id"
CONF_DEVICE_ID = "device_id"
CONF_POLL_INTERVAL = "poll_interval"

# Default Values
DEFAULT_PORT = 6000
DEFAULT_TIMEOUT = 5  # seconds
DEFAULT_POLL_INTERVAL = 30  # seconds
DEFAULT_DEVICE_SUBNET_ID = 200  # Default subnet ID for the gateway
DEFAULT_DEVICE_ID = 200  # Default device ID for the gateway

# Translations
ATTR_BRIGHTNESS = "brightness"
ATTR_POSITION = "position"
ATTR_TEMPERATURE = "temperature"