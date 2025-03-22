"""
This component provides light support for Buspro.

For more details about this platform, please refer to the documentation at
https://home-assistant.io/components/...
"""

import logging
from typing import Any, Dict, List, Optional, Tuple, Callable

import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    PLATFORM_SCHEMA,
    ColorMode,
    LightEntity,
)
from homeassistant.const import (CONF_NAME, CONF_DEVICES)
from homeassistant.core import HomeAssistant, callback
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType

from .const import DOMAIN, OPERATION_SINGLE_CHANNEL, OPERATION_READ_STATUS, LIGHT

_LOGGER = logging.getLogger(__name__)

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Required(CONF_DEVICES): {cv.string: cv.string},
})

async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the HDL Buspro light platform."""
    gateway = hass.data[DOMAIN][config_entry.entry_id]["gateway"]
    discovery = hass.data[DOMAIN][config_entry.entry_id]["discovery"]
    
    entities = []
    
    # Обрабатываем найденные устройства освещения
    for device in discovery.get_devices_by_type(LIGHT):
        subnet_id = device["subnet_id"]
        # Работаем только с устройствами из подсети 1
        if subnet_id != 1:
            continue
            
        device_id = device["device_id"]
        channel = device.get("channel", 1)
        device_name = device.get("name", f"Light {subnet_id}.{device_id}.{channel}")
        
        entity = BusproLight(gateway, subnet_id, device_id, channel, device_name)
        entities.append(entity)
    
    if entities:
        async_add_entities(entities)
        _LOGGER.info(f"Добавлено {len(entities)} устройств освещения HDL Buspro")


async def async_setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    async_add_entities: AddEntitiesCallback,
    discovery_info: Optional[DiscoveryInfoType] = None,
) -> None:
    """Set up the HDL Buspro light platform with configuration.yaml."""
    # Проверяем, что компонент Buspro настроен
    if DOMAIN not in hass.data:
        _LOGGER.error("Cannot set up lights - HDL Buspro integration not found")
        return
    
    hdl = hass.data[DOMAIN].get("gateway")
    if not hdl:
        _LOGGER.error("Cannot set up lights - HDL Buspro gateway not found")
        return
    
    entities = []
    
    for address, name in config[CONF_DEVICES].items():
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
        
        _LOGGER.debug(f"Добавление света '{name}' с адресом {subnet_id}.{device_id}.{channel}")
        
        entity = BusproLight(hdl, subnet_id, device_id, channel, name)
        entities.append(entity)
    
    if entities:
        async_add_entities(entities)
        _LOGGER.info(f"Добавлено {len(entities)} устройств освещения HDL Buspro из configuration.yaml")


class BusproLight(LightEntity):
    """Representation of a HDL Buspro Light."""

    def __init__(
        self,
        gateway,
        subnet_id: int,
        device_id: int,
        channel: int,
        name: str,
    ):
        """Initialize the light."""
        self._gateway = gateway
        self._subnet_id = subnet_id
        self._device_id = device_id
        self._channel = channel
        self._attr_name = name
        self._attr_unique_id = f"light_{subnet_id}_{device_id}_{channel}"
        self._state = None
        self._brightness = None
        self._available = True
        self._attr_color_mode = ColorMode.BRIGHTNESS
        self._attr_supported_color_modes = {ColorMode.BRIGHTNESS}
        
    @property
    def name(self) -> str:
        """Return the name of the light."""
        return self._attr_name
        
    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return self._available
        
    @property
    def is_on(self) -> bool:
        """Return true if light is on."""
        return self._state
        
    @property
    def brightness(self) -> Optional[int]:
        """Return the brightness of this light between 0..255."""
        return self._brightness
        
    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the light on."""
        brightness = kwargs.get(ATTR_BRIGHTNESS, 255)
        
        # Отправляем команду на устройство
        self._gateway.send_hdl_command(
            self._subnet_id,
            self._device_id,
            OPERATION_SINGLE_CHANNEL,
            [self._channel, brightness]
        )
        
        # Обновляем состояние
        self._state = True
        self._brightness = brightness
        self.async_write_ha_state()
        
    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the light off."""
        # Отправляем команду на устройство
        self._gateway.send_hdl_command(
            self._subnet_id,
            self._device_id,
            OPERATION_SINGLE_CHANNEL,
            [self._channel, 0]
        )
        
        # Обновляем состояние
        self._state = False
        self._brightness = 0
        self.async_write_ha_state()
        
    async def async_update(self) -> None:
        """Fetch new state data for this light."""
        try:
            # Запрашиваем текущее состояние
            response = await self._gateway.send_message(
                [self._subnet_id, self._device_id],
                [OPERATION_READ_STATUS],
                [self._channel]
            )
            
            if response and len(response) > 0:
                brightness = response[0]
                self._brightness = brightness
                self._state = brightness > 0
                
            self._available = True
            
        except Exception as err:
            _LOGGER.error(f"Ошибка при обновлении состояния света: {err}")
            self._available = False
