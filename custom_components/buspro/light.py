"""
This component provides light support for Buspro.

For more details about this platform, please refer to the documentation at
https://home-assistant.io/components/...
"""

import logging
from typing import Any, Dict, List, Optional, Tuple

import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from homeassistant.components.light import (
    LightEntity, 
    ColorMode, 
    PLATFORM_SCHEMA, 
    ATTR_BRIGHTNESS,
)
from homeassistant.const import (CONF_NAME, CONF_DEVICES)
from homeassistant.core import callback
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType

from .const import DOMAIN, OPERATION_SINGLE_CHANNEL, OPERATION_READ_STATUS, LIGHT

_LOGGER = logging.getLogger(__name__)

DEFAULT_DEVICE_RUNNING_TIME = 0
DEFAULT_PLATFORM_RUNNING_TIME = 0
DEFAULT_DIMMABLE = True

DEVICE_SCHEMA = vol.Schema({
    vol.Optional("running_time", default=DEFAULT_DEVICE_RUNNING_TIME): cv.positive_int,
    vol.Optional("dimmable", default=DEFAULT_DIMMABLE): cv.boolean,
    vol.Required(CONF_NAME): cv.string,
})

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Optional("running_time", default=DEFAULT_PLATFORM_RUNNING_TIME): cv.positive_int,
    vol.Required(CONF_DEVICES): {cv.string: DEVICE_SCHEMA},
})


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the HDL Buspro light platform."""
    gateway = hass.data[DOMAIN][config_entry.entry_id]["gateway"]
    discovery = gateway.discovery
    
    entities = []
    
    # Обработка найденных устройств освещения
    for device in discovery.get_devices_by_type(LIGHT):
        subnet_id = device["subnet_id"]
        # Работаем только с устройствами из подсети 1
        if subnet_id != 1:
            continue
            
        device_id = device["device_id"]
        channel = device["channel"]
        device_name = device.get("name", f"Light {subnet_id}.{device_id}.{channel}")
        
        entity = BusproLight(gateway, subnet_id, device_id, channel, device_name)
        entities.append(entity)
    
    if entities:
        async_add_entities(entities)
        _LOGGER.info(f"Добавлено {len(entities)} устройств освещения HDL Buspro")


# noinspection PyAbstractClass
class BusproLight(LightEntity):
    """Representation of a HDL Buspro Light."""

    def __init__(self, gateway, subnet_id, device_id, channel, name):
        """Initialize the light."""
        self._gateway = gateway
        self._subnet_id = subnet_id
        self._device_id = device_id
        self._channel = channel
        self._attr_name = name
        self._attr_unique_id = f"light_{subnet_id}_{device_id}_{channel}"
        self._state = False
        self._brightness = 255
        self._attr_color_mode = ColorMode.BRIGHTNESS
        self._attr_supported_color_modes = {ColorMode.BRIGHTNESS}
        self._attr_has_entity_name = True
        
    async def async_added_to_hass(self):
        """Register callbacks."""
        await self.async_register_callbacks()
        
    async def async_register_callbacks(self):
        """Register callbacks for device updates."""
        def state_updated(subnet_id, device_id, channel, value):
            """Handle state updates."""
            if subnet_id == self._subnet_id and device_id == self._device_id and channel == self._channel:
                self._state = value > 0
                self._brightness = min(255, value * 255 // 100) if value > 0 else 0
                _LOGGER.debug(f"Обновление состояния света {self._attr_unique_id}: включено={self._state}, яркость={self._brightness}")
                self.async_write_ha_state()
                
        # Регистрируем колбэк
        self._gateway.register_callback(self._subnet_id, self._device_id, self._channel, state_updated)
        
        # Запрашиваем текущее состояние
        self._gateway.send_hdl_command(self._subnet_id, self._device_id, OPERATION_SINGLE_CHANNEL, [self._channel, 0])
        
    async def async_will_remove_from_hass(self):
        """Unregister callbacks."""
        # Удаляем колбэк при удалении устройства
        if hasattr(self._gateway, "unregister_callback"):
            self._gateway.unregister_callback(self._subnet_id, self._device_id, self._channel, None)
    
    @property
    def should_poll(self):
        """No polling needed within Buspro."""
        return False

    @property
    def name(self) -> str:
        """Return the display name of this light."""
        return self._attr_name

    @property
    def available(self):
        """Return True if entity is available."""
        return self._gateway.connected

    @property
    def brightness(self) -> Optional[int]:
        """Return the brightness of this light."""
        return self._brightness

    @property
    def is_on(self) -> bool:
        """Return true if light is on."""
        return self._state

    @property
    def supported_features(self) -> int:
        """Flag supported features."""
        # По умолчанию возвращаем 0, так как функциональность яркости 
        # уже поддерживается через color_mode
        return 0

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the light on."""
        brightness = kwargs.get(ATTR_BRIGHTNESS, 255)
        brightness_pct = min(100, brightness * 100 // 255)
        
        # Отправляем команду включения с заданной яркостью
        self._gateway.send_hdl_command(
            self._subnet_id, 
            self._device_id, 
            OPERATION_SINGLE_CHANNEL, 
            [self._channel, brightness_pct]
        )
        
        _LOGGER.debug(f"Включение света {self._attr_unique_id} с яркостью {brightness_pct}%")
        
        # Обновляем состояние
        self._state = True
        self._brightness = brightness
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the light off."""
        # Отправляем команду выключения
        self._gateway.send_hdl_command(
            self._subnet_id, 
            self._device_id, 
            OPERATION_SINGLE_CHANNEL, 
            [self._channel, 0]
        )
        
        _LOGGER.debug(f"Выключение света {self._attr_unique_id}")
        
        # Обновляем состояние
        self._state = False
        self.async_write_ha_state()

    @property
    def unique_id(self):
        """Return the unique id."""
        return self._attr_unique_id

    async def async_update(self) -> None:
        """Fetch updated state."""
        # Запрашиваем текущее состояние
        self._gateway.send_hdl_command(
            self._subnet_id, 
            self._device_id, 
            OPERATION_SINGLE_CHANNEL, 
            [self._channel, 0]
        )
        _LOGGER.debug(f"Запрос обновления состояния света {self._attr_unique_id}")
