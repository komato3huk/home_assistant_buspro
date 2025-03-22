"""Platform for HDL Buspro cover integration."""
import logging
from typing import Any, Optional

from homeassistant.components.cover import (
    CoverEntity,
    CoverEntityFeature,
    ATTR_POSITION,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, OPERATION_SINGLE_CHANNEL, OPERATION_READ_STATUS

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the HDL Buspro cover platform."""
    gateway = hass.data[DOMAIN][config_entry.entry_id]["gateway"]
    devices = hass.data[DOMAIN][config_entry.entry_id]["devices"]
    
    entities = []
    
    # Add all discovered cover devices
    for device in devices.get("cover", []):
        entities.append(
            BusproCover(
                gateway,
                device["subnet_id"],
                device["device_id"],
                device["name"],
            )
        )
    
    async_add_entities(entities)

class BusproCover(CoverEntity):
    """Representation of a HDL Buspro Cover."""

    def __init__(self, gateway, subnet_id: int, device_id: int, name: str):
        """Initialize the cover."""
        self._gateway = gateway
        self._subnet_id = subnet_id
        self._device_id = device_id
        self._name = name
        self._position = None
        self._is_closing = None
        self._is_opening = None
        self._available = True
        self._attr_supported_features = (
            CoverEntityFeature.OPEN 
            | CoverEntityFeature.CLOSE 
            | CoverEntityFeature.STOP 
            | CoverEntityFeature.SET_POSITION
        )

    @property
    def name(self) -> str:
        """Return the display name of this cover."""
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
    def is_closed(self) -> Optional[bool]:
        """Return if the cover is closed or not."""
        if self._position is not None:
            return self._position == 0
        return None

    @property
    def is_closing(self) -> Optional[bool]:
        """Return if the cover is closing or not."""
        return self._is_closing

    @property
    def is_opening(self) -> Optional[bool]:
        """Return if the cover is opening or not."""
        return self._is_opening

    async def async_open_cover(self, **kwargs: Any) -> None:
        """Open the cover."""
        await self._gateway.send_message(
            [self._subnet_id, self._device_id],
            [OPERATION_SINGLE_CHANNEL],
            [1, 100]  # Channel 1, 100% open
        )
        self._is_opening = True
        self._is_closing = False

    async def async_close_cover(self, **kwargs: Any) -> None:
        """Close the cover."""
        await self._gateway.send_message(
            [self._subnet_id, self._device_id],
            [OPERATION_SINGLE_CHANNEL],
            [1, 0]  # Channel 1, 0% open (closed)
        )
        self._is_closing = True
        self._is_opening = False

    async def async_stop_cover(self, **kwargs: Any) -> None:
        """Stop the cover."""
        await self._gateway.send_message(
            [self._subnet_id, self._device_id],
            [OPERATION_SINGLE_CHANNEL],
            [1, self._position or 50]  # Keep current position or default to 50%
        )
        self._is_closing = False
        self._is_opening = False

    async def async_set_cover_position(self, **kwargs: Any) -> None:
        """Move the cover to a specific position."""
        position = kwargs.get(ATTR_POSITION)
        if position is None:
            return
        
        await self._gateway.send_message(
            [self._subnet_id, self._device_id],
            [OPERATION_SINGLE_CHANNEL],
            [1, position]
        )

    async def async_update(self) -> None:
        """Fetch new state data for this cover."""
        try:
            response = await self._gateway.send_message(
                [self._subnet_id, self._device_id],
                [OPERATION_READ_STATUS],
                [1]  # Channel 1
            )
            
            if response:
                self._position = response[0]
                self._is_closing = False
                self._is_opening = False
                self._available = True
        except Exception as err:
            _LOGGER.error("Error updating cover state: %s", err)
            self._available = False

    @property
    def unique_id(self) -> str:
        """Return a unique ID."""
        return f"cover_{self._subnet_id}_{self._device_id}"

    @property
    def entity_id(self) -> str:
        """Return the entity ID for this cover."""
        return f"cover.cover_{self._subnet_id}_{self._device_id}" 