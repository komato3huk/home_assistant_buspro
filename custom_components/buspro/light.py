"""
This component provides light support for Buspro.

For more details about this platform, please refer to the documentation at
https://home-assistant.io/components/...
"""

import logging
from typing import Any, Dict, Optional

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

from .const import DOMAIN, OPERATION_SINGLE_CHANNEL, OPERATION_READ_STATUS

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
    devices = hass.data[DOMAIN][config_entry.entry_id]["devices"]
    
    entities = []
    
    # Add all discovered light devices
    for device in devices.get("light", []):
        entities.append(
            BusproLight(
                gateway,
                device["subnet_id"],
                device["device_id"],
                device["channel"],
                device["name"],
            )
        )
    
    _LOGGER.info(f"Добавлено {len(entities)} устройств освещения HDL Buspro")
    async_add_entities(entities)


# noinspection PyAbstractClass
class BusproLight(LightEntity):
    """Representation of a HDL Buspro Light."""

    def __init__(self, gateway, subnet_id: int, device_id: int, channel: int, name: str):
        """Initialize the light."""
        self._gateway = gateway
        self._subnet_id = subnet_id
        self._device_id = device_id
        self._channel = channel
        self._name = name
        self._state = None
        self._brightness = None
        self._attr_color_mode = ColorMode.BRIGHTNESS
        self._attr_supported_color_modes = {ColorMode.BRIGHTNESS}
        self._attr_has_entity_name = True
        self._attr_name = f"{self._subnet_id}.{self._device_id}.{self._channel}"
        self.async_register_callbacks()

    @callback
    def async_register_callbacks(self):
        """Register callbacks to update hass after device was changed."""

        async def after_update_callback(devices):
            """Call after device was updated."""
            # Проверяем, есть ли обновления для этого устройства
            device_key = f"{self._subnet_id}.{self._device_id}.{self._channel}"
            if device_key in devices:
                device_data = devices[device_key]
                if device_data["type"] == "light":
                    self._state = device_data["state"]
                    self._brightness = int(device_data["brightness"] * 255 / 100)  # Convert 0-100 to 0-255
                    self.async_write_ha_state()

        self._gateway.register_callback(after_update_callback)

    @property
    def should_poll(self):
        """No polling needed within Buspro."""
        return False

    @property
    def name(self) -> str:
        """Return the display name of this light."""
        return self._name

    @property
    def available(self):
        """Return True if entity is available."""
        return self._gateway.connected

    @property
    def brightness(self) -> Optional[int]:
        """Return the brightness of the light."""
        return self._brightness

    @property
    def is_on(self) -> bool:
        """Return true if light is on."""
        return self._state if self._state is not None else False

    @property
    def supported_features(self) -> int:
        """Flag supported features."""
        # По умолчанию возвращаем 0, так как функциональность яркости 
        # уже поддерживается через color_mode
        return 0

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the light on."""
        brightness = kwargs.get(ATTR_BRIGHTNESS, 255)
        
        # Convert Home Assistant brightness (0-255) to HDL brightness (0-100)
        hdl_brightness = int(brightness * 100 / 255)
        
        await self._gateway.send_message(
            [self._subnet_id, self._device_id],
            [OPERATION_SINGLE_CHANNEL],
            [self._channel, hdl_brightness]  # Specific channel, brightness value
        )
        
        self._state = True
        self._brightness = brightness
        _LOGGER.debug(f"Включено устройство {self._name} с яркостью {hdl_brightness}%")
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the light off."""
        await self._gateway.send_message(
            [self._subnet_id, self._device_id],
            [OPERATION_SINGLE_CHANNEL],
            [self._channel, 0]  # Specific channel, brightness 0
        )
        
        self._state = False
        self._brightness = 0
        _LOGGER.debug(f"Выключено устройство {self._name}")
        self.async_write_ha_state()

    @property
    def unique_id(self):
        """Return the unique id."""
        return f"light_{self._subnet_id}_{self._device_id}_{self._channel}"

    async def async_update(self) -> None:
        """Fetch new state data for this light."""
        try:
            response = await self._gateway.send_message(
                [self._subnet_id, self._device_id],
                [OPERATION_READ_STATUS],
                [self._channel]  # Specific channel
            )
            
            if response:
                self._state = response[0] > 0
                # Convert HDL brightness (0-100) to Home Assistant brightness (0-255)
                self._brightness = int(response[0] * 255 / 100)
                _LOGGER.debug(f"Обновлено состояние устройства {self._name}: {self._state}, яркость: {response[0]}%")
        except Exception as err:
            _LOGGER.error(f"Ошибка при обновлении состояния света {self._name}: {err}")
