"""
This component provides cover support for Buspro.

For more details about this platform, please refer to the documentation at
https://home-assistant.io/components/...
"""

import logging
from typing import Any, Dict, List, Optional

import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from homeassistant.components.cover import (
    CoverEntity,
    PLATFORM_SCHEMA,
    CoverEntityFeature,
)
from homeassistant.const import (CONF_NAME, CONF_DEVICES)
from homeassistant.core import HomeAssistant, callback
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType

from .const import DOMAIN, OPERATION_WRITE

_LOGGER = logging.getLogger(__name__)

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Required(CONF_DEVICES): {cv.string: cv.string},
})

DEFAULT_FEATURES = (
    CoverEntityFeature.OPEN |
    CoverEntityFeature.CLOSE |
    CoverEntityFeature.STOP |
    CoverEntityFeature.SET_POSITION
)

# HDL Buspro commands for controlling covers
COMMAND_STOP = 0
COMMAND_UP = 1
COMMAND_DOWN = 2
COMMAND_POSITION = 3

async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the HDL Buspro cover platform."""
    gateway = hass.data[DOMAIN][config_entry.entry_id]["gateway"]
    discovery = hass.data[DOMAIN][config_entry.entry_id]["discovery"]
    
    entities = []
    
    # Get covers from discovered devices
    for device in discovery.get_devices_by_type("cover"):
        subnet_id = device["subnet_id"]
        device_id = device["device_id"]
        channel = device.get("channel", 1)
        device_name = device.get("name", f"Cover {subnet_id}.{device_id}.{channel}")
        
        _LOGGER.info(f"Found cover device: {device_name} ({subnet_id}.{device_id}.{channel})")
        
        entity = BusproCover(
            gateway,
            subnet_id,
            device_id,
            channel,
            device_name,
        )
        entities.append(entity)
        
        _LOGGER.debug(f"Added cover: {device_name} ({subnet_id}.{device_id}.{channel})")
    
    if entities:
        async_add_entities(entities)
        _LOGGER.info(f"Added {len(entities)} HDL Buspro covers")


async def async_setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    async_add_entities: AddEntitiesCallback,
    discovery_info: Optional[DiscoveryInfoType] = None,
) -> None:
    """Set up the HDL Buspro cover platform with configuration.yaml."""
    # Проверяем, что компонент Buspro настроен
    if DOMAIN not in hass.data:
        _LOGGER.error("Cannot set up covers - HDL Buspro integration not found")
        return
    
    hdl = hass.data[DOMAIN].get("gateway")
    if not hdl:
        _LOGGER.error("Cannot set up covers - HDL Buspro gateway not found")
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
        
        _LOGGER.debug(f"Добавление устройства управления шторами '{name}' с адресом {subnet_id}.{device_id}.{channel}")
        
        entity = BusproCover(hdl, subnet_id, device_id, channel, name)
        entities.append(entity)
    
    if entities:
        async_add_entities(entities)
        _LOGGER.info(f"Добавлено {len(entities)} устройств управления шторами HDL Buspro из configuration.yaml")


class BusproCover(CoverEntity):
    """Representation of a HDL Buspro Cover device."""

    def __init__(
        self,
        gateway,
        subnet_id: int,
        device_id: int,
        channel: int,
        name: str,
    ):
        """Initialize the cover device."""
        self._gateway = gateway
        self._subnet_id = subnet_id
        self._device_id = device_id
        self._channel = channel
        self._name = name
        
        # State properties
        self._position = None
        self._is_opening = False
        self._is_closing = False
        self._available = True
        
        # Generate unique ID
        self._attr_unique_id = f"cover_{subnet_id}_{device_id}_{channel}"
        
        # Set supported features
        self._attr_supported_features = (
            CoverEntityFeature.OPEN | 
            CoverEntityFeature.CLOSE | 
            CoverEntityFeature.STOP | 
            CoverEntityFeature.SET_POSITION
        )
        
    @property
    def name(self) -> str:
        """Return the name of the cover."""
        return self._name
        
    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return self._available
        
    @property
    def current_cover_position(self) -> Optional[int]:
        """Return current position of cover.
        
        None is unknown, 0 is closed, 100 is fully open.
        """
        return self._position
        
    @property
    def is_opening(self) -> bool:
        """Return if the cover is opening or not."""
        return self._is_opening
        
    @property
    def is_closing(self) -> bool:
        """Return if the cover is closing or not."""
        return self._is_closing
        
    @property
    def is_closed(self) -> Optional[bool]:
        """Return if the cover is closed or not."""
        if self._position is None:
            return None
        return self._position == 0
        
    async def async_open_cover(self, **kwargs: Any) -> None:
        """Open the cover."""
        _LOGGER.debug(f"Opening cover {self._subnet_id}.{self._device_id}.{self._channel}")
        
        # Create telegram for opening
        telegram = {
            "subnet_id": self._subnet_id,
            "device_id": self._device_id,
            "operate_code": OPERATION_WRITE,
            "data": [COMMAND_UP, self._channel],
        }
        
        # Send telegram via gateway
        try:
            await self._gateway.send_telegram(telegram)
            self._is_opening = True
            self._is_closing = False
            _LOGGER.info(f"Cover {self._subnet_id}.{self._device_id}.{self._channel} opening")
        except Exception as err:
            _LOGGER.error(f"Error opening cover {self._subnet_id}.{self._device_id}.{self._channel}: {err}")
        
    async def async_close_cover(self, **kwargs: Any) -> None:
        """Close the cover."""
        _LOGGER.debug(f"Closing cover {self._subnet_id}.{self._device_id}.{self._channel}")
        
        # Create telegram for closing
        telegram = {
            "subnet_id": self._subnet_id,
            "device_id": self._device_id,
            "operate_code": OPERATION_WRITE,
            "data": [COMMAND_DOWN, self._channel],
        }
        
        # Send telegram via gateway
        try:
            await self._gateway.send_telegram(telegram)
            self._is_opening = False
            self._is_closing = True
            _LOGGER.info(f"Cover {self._subnet_id}.{self._device_id}.{self._channel} closing")
        except Exception as err:
            _LOGGER.error(f"Error closing cover {self._subnet_id}.{self._device_id}.{self._channel}: {err}")
        
    async def async_stop_cover(self, **kwargs: Any) -> None:
        """Stop the cover."""
        _LOGGER.debug(f"Stopping cover {self._subnet_id}.{self._device_id}.{self._channel}")
        
        # Create telegram for stopping
        telegram = {
            "subnet_id": self._subnet_id,
            "device_id": self._device_id,
            "operate_code": OPERATION_WRITE,
            "data": [COMMAND_STOP, self._channel],
        }
        
        # Send telegram via gateway
        try:
            await self._gateway.send_telegram(telegram)
            self._is_opening = False
            self._is_closing = False
            _LOGGER.info(f"Cover {self._subnet_id}.{self._device_id}.{self._channel} stopped")
        except Exception as err:
            _LOGGER.error(f"Error stopping cover {self._subnet_id}.{self._device_id}.{self._channel}: {err}")
        
    async def async_set_cover_position(self, **kwargs: Any) -> None:
        """Set the cover position."""
        position = kwargs.get("position")
        if position is None:
            return
            
        _LOGGER.debug(f"Setting cover {self._subnet_id}.{self._device_id}.{self._channel} position to {position}%")
        
        # Convert position from 0-100 to device format (0-255)
        hdl_position = int(position * 255 / 100)
        
        # Create telegram for setting position
        telegram = {
            "subnet_id": self._subnet_id,
            "device_id": self._device_id,
            "operate_code": OPERATION_WRITE,
            "data": [COMMAND_POSITION, self._channel, hdl_position],
        }
        
        # Send telegram via gateway
        try:
            await self._gateway.send_telegram(telegram)
            self._position = position
            self._is_opening = False
            self._is_closing = False
            _LOGGER.info(f"Cover {self._subnet_id}.{self._device_id}.{self._channel} position set to {position}%")
        except Exception as err:
            _LOGGER.error(f"Error setting cover position for {self._subnet_id}.{self._device_id}.{self._channel}: {err}")
        
    async def async_update(self) -> None:
        """Fetch new state data for this cover."""
        try:
            _LOGGER.debug(f"Updating cover state for {self._subnet_id}.{self._device_id}.{self._channel}")
            
            # For now, we have limited feedback from the device
            # In a real scenario, you would send a status request telegram and process the response
            # For demonstration, we'll just mark the device as available
            self._available = True
            
            # If in motion, update position based on direction
            if self._is_opening and self._position is not None:
                self._position = min(100, self._position + 10)
                if self._position >= 100:
                    self._is_opening = False
                    
            elif self._is_closing and self._position is not None:
                self._position = max(0, self._position - 10)
                if self._position <= 0:
                    self._is_closing = False
                    
            # If position is still None, set a default
            if self._position is None:
                self._position = 50
                
        except Exception as err:
            _LOGGER.error(f"Error updating cover state for {self._subnet_id}.{self._device_id}.{self._channel}: {err}")
            # Don't change availability for temporary errors
            if self._position is None:
                self._available = False 