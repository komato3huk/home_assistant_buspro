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
    ILLUMINANCE, 
    TEMPERATURE, 
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
    devices = hass.data[DOMAIN][config_entry.entry_id]["devices"]
    
    entities = []
    
    # Add all discovered sensor devices
    for device in devices.get("sensor", []):
        # Each sensor device might have multiple sensor types
        for sensor_type, config in SENSOR_TYPES.items():
            entities.append(
                BusproSensor(
                    gateway,
                    device["subnet_id"],
                    device["device_id"],
                    f"{device['name']} {config['name']}",
                    sensor_type,
                    config,
                )
            )
    
    async_add_entities(entities)

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
        name: str,
        sensor_type: int,
        config: dict,
    ):
        """Initialize the sensor."""
        self._gateway = gateway
        self._subnet_id = subnet_id
        self._device_id = device_id
        self._name = name
        self._sensor_type = sensor_type
        self._config = config
        self._available = True
        self._state = None

        # Set entity properties from config
        self._attr_device_class = config["device_class"]
        self._attr_state_class = config["state_class"]
        self._attr_native_unit_of_measurement = config["unit"]

    @property
    def should_poll(self) -> bool:
        """No polling needed within Buspro."""
        return False

    @property
    def name(self) -> str:
        """Return the display name of this sensor."""
        return self._name

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return self._available

    @property
    def native_value(self) -> Optional[float]:
        """Return the state of the sensor."""
        return self._state

    async def async_update(self) -> None:
        """Fetch new state data for this sensor."""
        try:
            response = await self._gateway.send_message(
                [self._subnet_id, self._device_id],
                [OPERATION_READ_STATUS],
                [self._sensor_type]
            )
            
            if response:
                # Apply multiplier to convert raw value to actual value
                self._state = response[0] * self._config["multiplier"]
                self._available = True
        except Exception as err:
            _LOGGER.error("Error updating sensor state: %s", err)
            self._available = False

    @property
    def unique_id(self) -> str:
        """Return a unique ID."""
        return f"sensor_{self._subnet_id}_{self._device_id}_{self._sensor_type}"