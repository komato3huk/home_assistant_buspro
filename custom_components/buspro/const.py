"""Constants for the HDL Buspro integration."""

import logging
from datetime import timedelta
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorStateClass,
)
from homeassistant.const import (
    UnitOfTemperature,
    PERCENTAGE,
    UnitOfIlluminance,
    UnitOfTime,
)

DOMAIN = "buspro"
DEFAULT_NAME = "HDL Buspro"

LOGGER = logging.getLogger(__package__)

# Конфигурационные параметры
CONF_DEVICE_SUBNET_ID = "device_subnet_id"
CONF_DEVICE_ID = "device_id"
CONF_POLL_INTERVAL = "poll_interval"
CONF_GATEWAY_HOST = "gateway_host"
CONF_GATEWAY_PORT = "gateway_port"
CONF_TIMEOUT = "timeout"
CONF_GATEWAY_NAME = "gateway_name"

# IP-адрес и порт по умолчанию для шлюза HDL Buspro
DEFAULT_HOST = "192.168.1.1"
DEFAULT_PORT = 6000
DEFAULT_TIMEOUT = 3  # Тайм-аут запросов в секундах
DEFAULT_POLL_INTERVAL = 30  # Интервал опроса устройств в секундах

# Базовые коды операций для протокола HDL Buspro
OPERATION_READ_STATUS = 0x0031  # Чтение состояния устройства
OPERATION_WRITE = 0x0032  # Запись значения в устройство

# Типы устройств
DEVICE_TYPES = {
    "binary_sensor": "binary_sensor",
    "climate": "climate",
    "cover": "cover",
    "light": "light",
    "sensor": "sensor",
    "switch": "switch",
}

# Типы датчиков, поддерживаемые интеграцией
SENSOR_TYPES = {
    # Температура
    0x01: {
        "name": "Temperature",
        "device_class": SensorDeviceClass.TEMPERATURE,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": UnitOfTemperature.CELSIUS,
        "multiplier": 0.1,  # Множитель для преобразования сырого значения
        "icon": "mdi:thermometer",
    },
    # Влажность
    0x02: {
        "name": "Humidity",
        "device_class": SensorDeviceClass.HUMIDITY,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": PERCENTAGE,
        "multiplier": 1.0,
        "icon": "mdi:water-percent",
    },
    # Освещенность
    0x03: {
        "name": "Illuminance",
        "device_class": SensorDeviceClass.ILLUMINANCE,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": UnitOfIlluminance.LUX,
        "multiplier": 1.0,
        "icon": "mdi:brightness-5",
    },
    # Скорость ветра (для метеостанции)
    0x04: {
        "name": "Wind Speed",
        "device_class": None,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": "m/s",
        "multiplier": 0.1,
        "icon": "mdi:weather-windy",
    },
    # CO2 (для датчика качества воздуха)
    0x05: {
        "name": "CO2",
        "device_class": SensorDeviceClass.CO2,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": "ppm",
        "multiplier": 1.0,
        "icon": "mdi:molecule-co2",
    },
}

# Конфигурация для Home Assistant
CONF_SUBNET_ID = "subnet_id"
CONF_DEVICE_ID = "device_id"
CONF_HOST = "host"
CONF_PORT = "port"
CONF_TIMEOUT = "timeout"
CONF_POLL_INTERVAL = "poll_interval"
CONF_DEVICE_SUBNET_ID = "device_subnet_id"
CONF_PRESET_MODES = "preset_modes"

# Названия типов компонентов для конфигурационного файла
BINARY_SENSOR = "binary_sensor"
CLIMATE = "climate"
COVER = "cover"
LIGHT = "light"
SENSOR = "sensor"
SWITCH = "switch"

# Операционные коды HDL
OPERATION_DISCOVERY = 0x000E
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

# Preset modes
CONF_PRESET_MODES = "preset_modes"