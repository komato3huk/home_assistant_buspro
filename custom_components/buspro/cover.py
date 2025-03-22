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

from .const import DOMAIN, OPERATION_SINGLE_CHANNEL, OPERATION_READ_STATUS, COVER

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

async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the HDL Buspro cover platform."""
    gateway = hass.data[DOMAIN][config_entry.entry_id]["gateway"]
    discovery = hass.data[DOMAIN][config_entry.entry_id]["discovery"]
    
    entities = []
    
    # Обрабатываем найденные устройства управления шторами
    for device in discovery.get_devices_by_type(COVER):
        subnet_id = device["subnet_id"]
        # Работаем только с устройствами из подсети 1
        if subnet_id != 1:
            continue
            
        device_id = device["device_id"]
        channel = device.get("channel", 1)
        device_name = device.get("name", f"Cover {subnet_id}.{device_id}.{channel}")
        
        entity = BusproCover(gateway, subnet_id, device_id, channel, device_name)
        entities.append(entity)
    
    if entities:
        async_add_entities(entities)
        _LOGGER.info(f"Добавлено {len(entities)} устройств управления шторами HDL Buspro")


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
    """Representation of a HDL Buspro Cover."""

    def __init__(
        self,
        gateway,
        subnet_id: int,
        device_id: int,
        channel: int,
        name: str,
    ):
        """Initialize the cover."""
        self._gateway = gateway
        self._subnet_id = subnet_id
        self._device_id = device_id
        self._channel = channel
        self._attr_name = name
        self._attr_unique_id = f"cover_{subnet_id}_{device_id}_{channel}"
        self._position = None
        self._is_opening = False
        self._is_closing = False
        self._available = True
        
        # Поддерживаемые функции
        self._attr_supported_features = DEFAULT_FEATURES
        
    @property
    def name(self) -> str:
        """Return the name of the cover."""
        return self._attr_name
        
    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return self._available
        
    @property
    def current_cover_position(self) -> Optional[int]:
        """Return current position of cover."""
        return self._position
        
    @property
    def is_opening(self) -> bool:
        """Return true if the cover is opening."""
        return self._is_opening
        
    @property
    def is_closing(self) -> bool:
        """Return true if the cover is closing."""
        return self._is_closing
        
    @property
    def is_closed(self) -> bool:
        """Return true if the cover is closed."""
        if self._position is None:
            return None
        return self._position == 0
        
    async def async_open_cover(self, **kwargs: Any) -> None:
        """Open the cover."""
        # Отправляем команду на устройство
        self._gateway.send_hdl_command(
            self._subnet_id,
            self._device_id,
            OPERATION_SINGLE_CHANNEL,
            [self._channel, 100]  # Полностью открыть (100%)
        )
        
        # Обновляем состояние
        self._is_opening = True
        self._is_closing = False
        self.async_write_ha_state()
        
    async def async_close_cover(self, **kwargs: Any) -> None:
        """Close the cover."""
        # Отправляем команду на устройство
        self._gateway.send_hdl_command(
            self._subnet_id,
            self._device_id,
            OPERATION_SINGLE_CHANNEL,
            [self._channel, 0]  # Полностью закрыть (0%)
        )
        
        # Обновляем состояние
        self._is_opening = False
        self._is_closing = True
        self.async_write_ha_state()
        
    async def async_stop_cover(self, **kwargs: Any) -> None:
        """Stop the cover."""
        # Отправляем команду на устройство
        self._gateway.send_hdl_command(
            self._subnet_id,
            self._device_id,
            OPERATION_SINGLE_CHANNEL,
            [self._channel, 0xFF]  # Специальный код для остановки
        )
        
        # Обновляем состояние
        self._is_opening = False
        self._is_closing = False
        self.async_write_ha_state()
        
    async def async_set_cover_position(self, **kwargs: Any) -> None:
        """Move the cover to a specific position."""
        position = kwargs.get("position")
        if position is None:
            return
            
        # Отправляем команду на устройство
        self._gateway.send_hdl_command(
            self._subnet_id,
            self._device_id,
            OPERATION_SINGLE_CHANNEL,
            [self._channel, position]
        )
        
        # Обновляем состояние
        self._position = position
        self._is_opening = position > 0 and (self._position is None or position > self._position)
        self._is_closing = position < 100 and (self._position is None or position < self._position)
        self.async_write_ha_state()
        
    async def async_update(self) -> None:
        """Fetch new state data for this cover."""
        try:
            # Запрашиваем текущую позицию
            response = await self._gateway.send_message(
                [self._subnet_id, self._device_id],
                [OPERATION_READ_STATUS],
                [self._channel]
            )
            
            if response and len(response) > 0:
                self._position = response[0]
                self._is_opening = False
                self._is_closing = False
                
            self._available = True
            
        except Exception as err:
            _LOGGER.error(f"Ошибка при обновлении состояния устройства управления шторами: {err}")
            self._available = False 