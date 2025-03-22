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
    LightEntityFeature
)
from homeassistant.const import (CONF_NAME, CONF_DEVICES)
from homeassistant.core import callback
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN

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
                device["name"],
            )
        )
    
    async_add_entities(entities)


# noinspection PyAbstractClass
class BusproLight(LightEntity):
    """Representation of a HDL Buspro Light."""

    def __init__(self, gateway, subnet_id: int, device_id: int, name: str):
        """Initialize the light."""
        self._gateway = gateway
        self._subnet_id = subnet_id
        self._device_id = device_id
        self._name = name
        self._state = None
        self._brightness = None
        self._attr_color_mode = ColorMode.BRIGHTNESS
        self._attr_supported_color_modes = {ColorMode.BRIGHTNESS}
        self.async_register_callbacks()

    @callback
    def async_register_callbacks(self):
        """Register callbacks to update hass after device was changed."""

        # noinspection PyUnusedLocal
        async def after_update_callback(device):
            """Call after device was updated."""
            self.async_write_ha_state()

        self._gateway.register_device_updated_cb(after_update_callback)

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
        return self._state

    @property
    def supported_features(self) -> int:
        """Flag supported features."""
        return LightEntityFeature.BRIGHTNESS

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the light on."""
        brightness = kwargs.get(ATTR_BRIGHTNESS, 255)
        
        # Convert Home Assistant brightness (0-255) to HDL brightness (0-100)
        hdl_brightness = int(brightness * 100 / 255)
        
        await self._gateway.send_message(
            [self._subnet_id, self._device_id],
            [0x0031],  # Single channel control
            [1, hdl_brightness]  # Channel 1, brightness value
        )
        
        self._state = True
        self._brightness = brightness

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the light off."""
        await self._gateway.send_message(
            [self._subnet_id, self._device_id],
            [0x0031],  # Single channel control
            [1, 0]  # Channel 1, brightness 0
        )
        
        self._state = False
        self._brightness = 0

    @property
    def unique_id(self):
        """Return the unique id."""
        return f"{self._subnet_id}_{self._device_id}"

    async def async_update(self) -> None:
        """Fetch new state data for this light."""
        try:
            response = await self._gateway.send_message(
                [self._subnet_id, self._device_id],
                [0x0032],  # Read status
                [1]  # Channel 1
            )
            
            if response:
                self._state = response[0] > 0
                # Convert HDL brightness (0-100) to Home Assistant brightness (0-255)
                self._brightness = int(response[0] * 255 / 100)
        except Exception as err:
            _LOGGER.error("Error updating light state: %s", err)
