"""
This component provides binary sensor support for Buspro.

For more details about this platform, please refer to the documentation at
https://home-assistant.io/components/...
"""

import logging
from typing import Any, Dict, List, Optional, Tuple, Callable

import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from homeassistant.components.binary_sensor import (
    BinarySensorEntity,
    PLATFORM_SCHEMA,
    BinarySensorDeviceClass,
)
from homeassistant.const import (CONF_NAME, CONF_DEVICES, CONF_DEVICE_CLASS)
from homeassistant.core import HomeAssistant, callback
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType

from .const import DOMAIN, OPERATION_READ_STATUS, BINARY_SENSOR

_LOGGER = logging.getLogger(__name__)

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Required(CONF_DEVICES): {
        cv.string: vol.Schema({
            vol.Required(CONF_NAME): cv.string,
            vol.Optional(CONF_DEVICE_CLASS): cv.string,
        }),
    },
})

async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the HDL Buspro binary sensor platform."""
    gateway = hass.data[DOMAIN][config_entry.entry_id]["gateway"]
    discovery = hass.data[DOMAIN][config_entry.entry_id]["discovery"]
    
    entities = []
    
    # Обрабатываем найденные бинарные сенсоры
    for device in discovery.get_devices_by_type(BINARY_SENSOR):
        subnet_id = device["subnet_id"]
        # Работаем только с устройствами из подсети 1
        if subnet_id != 1:
            continue
            
        device_id = device["device_id"]
        channel = device.get("channel", 1)
        device_name = device.get("name", f"Binary Sensor {subnet_id}.{device_id}.{channel}")
        device_class = device.get("type")
        
        # Преобразуем тип датчика в класс устройства HA
        ha_device_class = _get_device_class(device_class)
        
        entity = BusproBinarySensor(gateway, subnet_id, device_id, channel, device_name, ha_device_class)
        entities.append(entity)
    
    if entities:
        async_add_entities(entities)
        _LOGGER.info(f"Добавлено {len(entities)} бинарных сенсоров HDL Buspro")


async def async_setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    async_add_entities: AddEntitiesCallback,
    discovery_info: Optional[DiscoveryInfoType] = None,
) -> None:
    """Set up the HDL Buspro binary sensor platform with configuration.yaml."""
    # Проверяем, что компонент Buspro настроен
    if DOMAIN not in hass.data:
        _LOGGER.error("Cannot set up binary sensors - HDL Buspro integration not found")
        return
    
    hdl = hass.data[DOMAIN].get("gateway")
    if not hdl:
        _LOGGER.error("Cannot set up binary sensors - HDL Buspro gateway not found")
        return
    
    entities = []
    
    for address, device_config in config[CONF_DEVICES].items():
        # Парсим адрес устройства
        address_parts = address.split('.')
        if len(address_parts) != 3:
            _LOGGER.error(f"Неверный формат адреса: {address}. Должен быть subnet_id.device_id.channel")
            continue
            
        try:
            subnet_id = int(address_parts[0])
            device_id = int(address_parts[1])
            channel = int(address_parts[2])
        except ValueError:
            _LOGGER.error(f"Неверный формат адреса: {address}. Все части должны быть целыми числами")
            continue
        
        name = device_config[CONF_NAME]
        device_class = device_config.get(CONF_DEVICE_CLASS)
        
        # Преобразуем тип датчика в класс устройства HA
        ha_device_class = _get_device_class(device_class)
        
        _LOGGER.debug(f"Добавление бинарного сенсора '{name}' с адресом {subnet_id}.{device_id}.{channel}")
        
        entity = BusproBinarySensor(hdl, subnet_id, device_id, channel, name, ha_device_class)
        entities.append(entity)
    
    if entities:
        async_add_entities(entities)
        _LOGGER.info(f"Добавлено {len(entities)} бинарных сенсоров HDL Buspro из configuration.yaml")


def _get_device_class(device_type: Optional[str]) -> Optional[str]:
    """Map HDL Buspro sensor type to Home Assistant device class."""
    if not device_type:
        return None
        
    device_type = device_type.lower()
    
    if device_type == "motion":
        return BinarySensorDeviceClass.MOTION
    elif device_type == "door":
        return BinarySensorDeviceClass.DOOR
    elif device_type == "window":
        return BinarySensorDeviceClass.WINDOW
    elif device_type == "presence":
        return BinarySensorDeviceClass.PRESENCE
    elif device_type == "smoke":
        return BinarySensorDeviceClass.SMOKE
    elif device_type == "gas":
        return BinarySensorDeviceClass.GAS
    elif device_type == "moisture":
        return BinarySensorDeviceClass.MOISTURE
    
    # По умолчанию возвращаем None, чтобы HA сам выбрал подходящий класс
    return None


class BusproBinarySensor(BinarySensorEntity):
    """Representation of a HDL Buspro Binary Sensor."""

    def __init__(
        self,
        gateway,
        subnet_id: int,
        device_id: int,
        channel: int,
        name: str,
        device_class: Optional[str] = None,
    ):
        """Initialize the binary sensor."""
        self._gateway = gateway
        self._subnet_id = subnet_id
        self._device_id = device_id
        self._channel = channel
        self._attr_name = name
        self._attr_unique_id = f"binary_sensor_{subnet_id}_{device_id}_{channel}"
        self._attr_device_class = device_class
        self._is_on = None
        self._available = True
        
    @property
    def name(self) -> str:
        """Return the name of the binary sensor."""
        return self._attr_name
        
    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return self._available
        
    @property
    def is_on(self) -> Optional[bool]:
        """Return true if the binary sensor is on."""
        return self._is_on
        
    @property
    def device_class(self) -> Optional[str]:
        """Return the device class of the binary sensor."""
        return self._attr_device_class
        
    async def async_update(self) -> None:
        """Fetch new state data for this binary sensor."""
        try:
            # Запрашиваем текущее состояние
            response = await self._gateway.send_message(
                [self._subnet_id, self._device_id],
                [OPERATION_READ_STATUS],
                [self._channel]
            )
            
            if response and len(response) > 0:
                self._is_on = response[0] > 0
                
            self._available = True
            
        except Exception as err:
            _LOGGER.error(f"Ошибка при обновлении состояния бинарного сенсора: {err}")
            self._available = False
