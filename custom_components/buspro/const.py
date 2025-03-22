"""Constants for HDL Buspro."""

DOMAIN = "buspro"

# Операционные коды для HDL Buspro
OPERATION_READ_STATUS = 0x0032      # Read status
OPERATION_SINGLE_CHANNEL = 0x0031   # Single channel control
OPERATION_SCENE_CONTROL = 0x0002    # Scene control
OPERATION_UNIVERSAL_SWITCH = 0x0003 # Universal switch
OPERATION_DISCOVERY = 0x000D        # Device discovery

# Максимальное количество каналов для разных типов устройств
MAX_CHANNELS = {
    "light": 12,     # Стандартные DLP и реле HDL имеют до 12 каналов
    "cover": 2,      # Модули управления шторами обычно имеют 1-2 канала
    "climate": 1,    # Термостаты обычно 1 канал
    "sensor": 4,     # Сенсоры обычно до 4 каналов
    "binary_sensor": 8, # Бинарные сенсоры до 8 каналов
    "switch": 12     # Выключатели до 12 каналов
}

# Таймаут операций в секундах
OPERATION_TIMEOUT = 3.0

# Интервал опроса устройств в секундах (по умолчанию)
DEFAULT_POLL_INTERVAL = 30

# Device Types
DEVICE_TYPE_LIGHT = "light"
DEVICE_TYPE_COVER = "cover"
DEVICE_TYPE_CLIMATE = "climate"
DEVICE_TYPE_SENSOR = "sensor"

# Platform constants
LIGHT = "light"
COVER = "cover"
CLIMATE = "climate"
SENSOR = "sensor"
BINARY_SENSOR = "binary_sensor"
SWITCH = "switch"

# Configuration constants
CONF_DEVICE_SUBNET_ID = "device_subnet_id"
CONF_DEVICE_ID = "device_id"
CONF_POLL_INTERVAL = "poll_interval"
CONF_GATEWAY_HOST = "gateway_host"
CONF_GATEWAY_PORT = "gateway_port"

# Default Values
DEFAULT_PORT = 6000
DEFAULT_TIMEOUT = 5  # seconds
DEFAULT_DEVICE_SUBNET_ID = 200  # Default subnet ID for the gateway
DEFAULT_DEVICE_ID = 200  # Default device ID for the gateway
DEFAULT_GATEWAY_HOST = ""  # По умолчанию используем тот же хост, что и для подключения
DEFAULT_GATEWAY_PORT = 6000  # Стандартный порт для HDL Buspro

# Translations
ATTR_BRIGHTNESS = "brightness"
ATTR_POSITION = "position"
ATTR_TEMPERATURE = "temperature"