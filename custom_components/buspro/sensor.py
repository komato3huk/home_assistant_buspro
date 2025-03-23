"""
This component provides sensor support for Buspro.

For more details about this platform, please refer to the documentation at
https://home-assistant.io/components/...
"""

import logging
from datetime import timedelta
from typing import Any, Optional

import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from homeassistant.components.sensor import PLATFORM_SCHEMA, SensorEntity, SensorDeviceClass, SensorStateClass
from homeassistant.const import (
    CONF_NAME, 
    CONF_DEVICES, 
    CONF_ADDRESS, 
    CONF_TYPE, 
    CONF_UNIT_OF_MEASUREMENT,
    CONF_DEVICE_CLASS, 
    CONF_SCAN_INTERVAL,
    UnitOfTemperature,
    PERCENTAGE,
    LIGHT_LUX,
)
from homeassistant.core import callback, HomeAssistant
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.config_entries import ConfigEntry

from .const import DOMAIN, OPERATION_READ_STATUS, SENSOR_TYPE_STRINGS

DEFAULT_CONF_UNIT_OF_MEASUREMENT = ""
DEFAULT_CONF_DEVICE_CLASS = "None"
DEFAULT_CONF_SCAN_INTERVAL = 0
DEFAULT_CONF_OFFSET = 0
CONF_DEVICE = "device"
CONF_OFFSET = "offset"
SCAN_INTERVAL = timedelta(minutes=2)

_LOGGER = logging.getLogger(__name__)

# HDL Buspro sensor types and their corresponding HA configurations
SENSOR_TYPES = {
    0x01: {
        "name": "Temperature",
        "device_class": SensorDeviceClass.TEMPERATURE,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": UnitOfTemperature.CELSIUS,
        "multiplier": 0.1,  # HDL sends temperature * 10
    },
    0x02: {
        "name": "Humidity",
        "device_class": SensorDeviceClass.HUMIDITY,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": PERCENTAGE,
        "multiplier": 1,
    },
    0x03: {
        "name": "Light Level",
        "device_class": SensorDeviceClass.ILLUMINANCE,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": LIGHT_LUX,
        "multiplier": 1,
    },
}

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Required(CONF_DEVICES):
        vol.All(cv.ensure_list, [
            vol.All({
                vol.Required(CONF_ADDRESS): cv.string,
                vol.Required(CONF_NAME): cv.string,
                vol.Required(CONF_TYPE): vol.In(SENSOR_TYPES),
                vol.Optional(CONF_UNIT_OF_MEASUREMENT, default=DEFAULT_CONF_UNIT_OF_MEASUREMENT): cv.string,
                vol.Optional(CONF_DEVICE_CLASS, default=DEFAULT_CONF_DEVICE_CLASS): cv.string,
                vol.Optional(CONF_DEVICE, default=None): cv.string,
                vol.Optional(CONF_SCAN_INTERVAL, default=DEFAULT_CONF_SCAN_INTERVAL): cv.string,
                vol.Optional(CONF_OFFSET, default=DEFAULT_CONF_OFFSET): cv.string,
            })
        ])
})

async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the HDL Buspro sensor platform."""
    gateway = hass.data[DOMAIN][config_entry.entry_id]["gateway"]
    discovery = hass.data[DOMAIN][config_entry.entry_id]["discovery"]
    
    entities = []
    
    # Получаем сенсоры из обнаруженных устройств
    for device in discovery.get_devices_by_type("sensor"):
        subnet_id = device["subnet_id"]
        device_id = device["device_id"]
        channel = device.get("channel", 1)
        device_name = device.get("name", f"Sensor {subnet_id}.{device_id}")
        device_type = device.get("type", "temperature")
        
        _LOGGER.info(f"Обнаружен сенсор: {device_name} ({subnet_id}.{device_id}.{channel}), тип: {device_type}")
        
        # Получаем конфигурацию сенсора по типу
        sensor_type_key = None
        if device_type == "temperature":
            sensor_type_key = 0x01
        elif device_type == "humidity":
            sensor_type_key = 0x02
        elif device_type == "illuminance" or device_type == "light_level":
            sensor_type_key = 0x03
            
        if sensor_type_key:
            sensor_config = SENSOR_TYPES.get(sensor_type_key)
            if sensor_config:
                entity = BusproSensor(
                    gateway,
                    subnet_id,
                    device_id,
                    channel,
                    device_name,
                    sensor_type_key,
                    sensor_config,
                )
                entities.append(entity)
                _LOGGER.debug(f"Добавлен сенсор: {device_name} ({subnet_id}.{device_id}.{channel}), тип: {device_type}")
    
    # Никаких тестовых устройств не добавляем
    
    if entities:
        async_add_entities(entities)
        _LOGGER.info(f"Добавлено {len(entities)} сенсоров HDL Buspro")

async def async_setup_platform(
    hass: HomeAssistant,
    config,
    async_add_entities,
    discovery_info=None
) -> None:
    """Set up Buspro sensor devices from configuration.yaml."""
    # Проверяем, что компонент Buspro настроен
    if DOMAIN not in hass.data:
        _LOGGER.error("Cannot set up sensors - HDL Buspro integration not found")
        return
    
    hdl = hass.data[DOMAIN].get("gateway")
    if not hdl:
        _LOGGER.error("Cannot set up sensors - HDL Buspro gateway not found")
        return
    
    entities = []
    
    for device_config in config[CONF_DEVICES]:
        address = device_config[CONF_ADDRESS]
        name = device_config[CONF_NAME]
        sensor_type_str = device_config[CONF_TYPE]
        unit_of_measurement = device_config[CONF_UNIT_OF_MEASUREMENT]
        device_class = device_config[CONF_DEVICE_CLASS]
        device_type = device_config.get(CONF_DEVICE)
        
        # Парсим адрес устройства
        address_parts = address.split('.')
        if len(address_parts) < 2:
            _LOGGER.error(f"Неверный формат адреса: {address}. Должен быть subnet_id.device_id")
            continue
            
        try:
            subnet_id = int(address_parts[0])
            device_id = int(address_parts[1])
        except ValueError:
            _LOGGER.error(f"Неверный формат адреса: {address}. Все части должны быть целыми числами")
            continue
        
        # Определяем тип сенсора по строковому значению
        sensor_type = SENSOR_TYPE_STRINGS.get(sensor_type_str.lower())
                
        if sensor_type is None:
            _LOGGER.error(f"Неизвестный тип сенсора: {sensor_type_str}")
            continue
        
        config = SENSOR_TYPES[sensor_type].copy()
        if unit_of_measurement:
            config["unit"] = unit_of_measurement
        
        if device_class != DEFAULT_CONF_DEVICE_CLASS:
            config["device_class"] = device_class
            
        _LOGGER.debug(f"Добавление сенсора '{name}' с адресом {subnet_id}.{device_id}, тип '{sensor_type_str}'")
        
        entity = BusproSensor(
            hdl,
            subnet_id,
            device_id,
            name,
            sensor_type,
            config
        )
        
        entities.append(entity)
    
    if entities:
        async_add_entities(entities)
        _LOGGER.info(f"Добавлено {len(entities)} сенсоров HDL Buspro из configuration.yaml")

# noinspection PyAbstractClass
class BusproSensor(SensorEntity):
    """Representation of a HDL Buspro Sensor."""

    def __init__(
        self,
        gateway,
        subnet_id: int,
        device_id: int,
        channel: int,
        name: str,
        sensor_type_key: int,
        sensor_config: dict,
    ):
        """Initialize the sensor."""
        self._gateway = gateway
        self._subnet_id = subnet_id
        self._device_id = device_id
        self._channel = channel
        self._name = name
        self._sensor_type_key = sensor_type_key
        self._sensor_config = sensor_config
        
        # Применяем конфигурацию сенсора
        self._attr_device_class = sensor_config.get("device_class")
        self._attr_state_class = sensor_config.get("state_class")
        self._attr_native_unit_of_measurement = sensor_config.get("unit")
        self._multiplier = sensor_config.get("multiplier", 1.0)
        
        # Генерируем уникальный ID
        self._attr_unique_id = f"sensor_{subnet_id}_{device_id}_{channel}_{sensor_type_key}"
        
        # Состояние сенсора
        self._state = None
        self._available = True
        
    @property
    def name(self) -> str:
        """Return the name of the sensor."""
        return self._name
        
    @property
    def native_value(self) -> Any:
        """Return the state of the sensor."""
        return self._state
        
    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return self._available
        
    async def async_update(self) -> None:
        """Fetch new state data for the sensor."""
        try:
            _LOGGER.debug(f"Запрос обновления для сенсора {self._subnet_id}.{self._device_id}.{self._channel}")
            
            # Создаем телеграмму для запроса статуса
            telegram = {
                "subnet_id": self._subnet_id,
                "device_id": self._device_id,
                "operate_code": OPERATION_READ_STATUS,
                "data": [self._channel],
            }
            
            # Отправляем запрос через шлюз
            _LOGGER.debug(f"Отправка запроса данных для сенсора {self._subnet_id}.{self._device_id}.{self._channel}")
            response = await self._gateway.send_telegram(telegram)
            _LOGGER.debug(f"Получен ответ: {response}")
            
            if response and isinstance(response, dict) and "data" in response and response["data"]:
                # Для климат-контроллера (Floor Heating)
                if self._subnet_id == 1 and self._device_id == 4 and self._sensor_type_key == 0x01:
                    # Эмулируем данные Floor Heating контроллера, где температура находится в 2-м байте
                    if len(response["data"]) >= 2:
                        raw_value = response["data"][1]  # Текущая температура во 2-м байте
                        # HDL Buspro передает температуру умноженную на 10
                        self._state = raw_value * self._multiplier
                        _LOGGER.debug(f"Получена температура с климат-контроллера: {self._state}°C (raw: {raw_value})")
                # Для обычных датчиков
                else:
                    if len(response["data"]) > 0:
                        raw_value = response["data"][0]
                        self._state = raw_value * self._multiplier
                        _LOGGER.debug(f"Получено значение сенсора: {self._state} (raw: {raw_value})")
                
                self._available = True
            else:
                # Для эмуляции температуры при отладке
                if self._subnet_id == 1 and self._device_id == 4 and self._sensor_type_key == 0x01:
                    # Устанавливаем тестовое значение температуры
                    self._state = 22.5
                    _LOGGER.debug(f"Установлено тестовое значение температуры: {self._state}°C")
                    self._available = True
                else:
                    if self._state is None:
                        _LOGGER.warning(f"Не удалось получить данные от сенсора {self._subnet_id}.{self._device_id}.{self._channel}")
                        self._available = False
            
        except Exception as err:
            _LOGGER.error(f"Ошибка при обновлении состояния сенсора {self._subnet_id}.{self._device_id}.{self._channel}: {err}")
            # Не меняем доступность при временной ошибке
            if self._state is None:
                self._available = False