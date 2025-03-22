"""Constants for the HDL Buspro integration."""

DOMAIN = "buspro"
DEFAULT_NAME = "HDL Buspro"

# Конфигурационные параметры
CONF_DEVICE_SUBNET_ID = "device_subnet_id"
CONF_DEVICE_ID = "device_id"
CONF_POLL_INTERVAL = "poll_interval"
CONF_GATEWAY_HOST = "gateway_host"
CONF_GATEWAY_PORT = "gateway_port"

# Значения по умолчанию
DEFAULT_PORT = 10000
DEFAULT_TIMEOUT = 5
DEFAULT_DEVICE_SUBNET_ID = 0
DEFAULT_DEVICE_ID = 1
DEFAULT_POLL_INTERVAL = 30
DEFAULT_GATEWAY_HOST = "255.255.255.255"  # Broadcast
DEFAULT_GATEWAY_PORT = 6000

# Типы устройств
LIGHT = "light"
SWITCH = "switch"
COVER = "cover"
CLIMATE = "climate"
SENSOR = "sensor"
BINARY_SENSOR = "binary_sensor"

# Операционные коды HDL
OPERATION_DISCOVERY = 0x000E
OPERATION_READ_STATUS = 0x000C
OPERATION_SINGLE_CHANNEL = 0x0031
OPERATION_SCENE_CONTROL = 0x0002
OPERATION_UNIVERSAL_SWITCH = 0x0003
OPERATION_CURTAIN_SWITCH = 0xE01C

# Типы сенсоров
SENSOR_TYPE_TEMPERATURE = 1
SENSOR_TYPE_HUMIDITY = 2
SENSOR_TYPE_ILLUMINANCE = 3

# Словарь для преобразования строковых типов из configuration.yaml в внутренние типы
SENSOR_TYPE_STRINGS = {
    "temperature": SENSOR_TYPE_TEMPERATURE,
    "humidity": SENSOR_TYPE_HUMIDITY,
    "illuminance": SENSOR_TYPE_ILLUMINANCE
}

# Таблица соответствия типов сенсоров и их единиц измерения
SENSOR_TYPES = {
    SENSOR_TYPE_TEMPERATURE: {"name": "Temperature", "unit": "°C"},
    SENSOR_TYPE_HUMIDITY: {"name": "Humidity", "unit": "%"},
    SENSOR_TYPE_ILLUMINANCE: {"name": "Illuminance", "unit": "lx"}
}

# Аттрибуты устройств
ATTR_BRIGHTNESS = "brightness"
ATTR_POSITION = "position"
ATTR_TEMPERATURE = "temperature"
ATTR_TARGET_TEMPERATURE = "target_temperature"
ATTR_CURRENT_TEMPERATURE = "current_temperature"
ATTR_FAN_MODE = "fan_mode"
ATTR_HVAC_MODE = "hvac_mode"
ATTR_PRESET_MODE = "preset_mode"

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

# Mapping string types from configuration.yaml to internal types
SENSOR_TYPE_STRINGS = {
    "temperature": 0x01,
    "humidity": 0x02,
    "illuminance": 0x03,
}

# Translations
ATTR_BRIGHTNESS = "brightness"
ATTR_POSITION = "position"
ATTR_TEMPERATURE = "temperature"