"""
This component provides cover support for Buspro.

For more details about this platform, please refer to the documentation at
https://home-assistant.io/components/...
"""

import logging
from typing import Any, Dict, List, Optional
import asyncio

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

from .const import DOMAIN, OPERATION_WRITE, COVER

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

# Коды операций для управления рольставнями
OPERATION_CURTAIN_CONTROL = 0xE01C

async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the HDL Buspro cover platform."""
    gateway = hass.data[DOMAIN][config_entry.entry_id]["gateway"]
    discovery = hass.data[DOMAIN][config_entry.entry_id]["discovery"]
    
    entities = []
    
    # Получение обнаруженных устройств управления рольставнями
    if COVER in discovery.devices:
        for device in discovery.devices[COVER]:
            subnet_id = device.get("subnet_id")
            device_id = device.get("device_id")
            channel = device.get("channel")
            name = device.get("name")
            
            _LOGGER.info(f"Добавление устройства управления рольставнями: {name} ({subnet_id}.{device_id}.{channel})")
            entities.append(
                BusproCover(gateway, subnet_id, device_id, channel, name)
            )
    
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
        self._name = name
        self._position = None
        self._is_opening = False
        self._is_closing = False
        self._available = True
        # Создаем уникальный ID, включающий все параметры устройства
        self._unique_id = f"cover_{subnet_id}_{device_id}_{channel}"
        
        # Поддерживаемые функции
        self._attr_supported_features = DEFAULT_FEATURES
        
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
        
    @property
    def unique_id(self) -> str:
        """Return a unique ID."""
        return self._unique_id
        
    async def async_open_cover(self, **kwargs: Any) -> None:
        """Open the cover."""
        _LOGGER.info(f"Открываем рольставни: {self._name} ({self._subnet_id}.{self._device_id}.{self._channel})")
        
        # Операция управления шторами, команда UP (1)
        operation_code = OPERATION_CURTAIN_CONTROL
        data = [self._channel, COMMAND_UP, 0, 0]  # channel, command, unused1, unused2
        
        try:
            await self._gateway.send_message(
                [self._subnet_id, self._device_id, 0, 0],  # target address
                [operation_code >> 8, operation_code & 0xFF],  # operation code
                data,
            )
            
            # Обновляем внутреннее состояние
            self._is_opening = True
            self._is_closing = False
            self.async_write_ha_state()
            
            # Через небольшую задержку обновим состояние, чтобы получить обновленное положение
            await asyncio.sleep(1)
            await self.async_update()
        except Exception as e:
            _LOGGER.error(f"Не удалось открыть рольставни {self._name}: {e}")

    async def async_close_cover(self, **kwargs: Any) -> None:
        """Close the cover."""
        _LOGGER.info(f"Закрываем рольставни: {self._name} ({self._subnet_id}.{self._device_id}.{self._channel})")
        
        # Операция управления шторами, команда DOWN (2)
        operation_code = OPERATION_CURTAIN_CONTROL
        data = [self._channel, COMMAND_DOWN, 0, 0]  # channel, command, unused1, unused2
        
        try:
            await self._gateway.send_message(
                [self._subnet_id, self._device_id, 0, 0],  # target address
                [operation_code >> 8, operation_code & 0xFF],  # operation code
                data,
            )
            
            # Обновляем внутреннее состояние
            self._is_opening = False
            self._is_closing = True
            self.async_write_ha_state()
            
            # Через небольшую задержку обновим состояние, чтобы получить обновленное положение
            await asyncio.sleep(1)
            await self.async_update()
        except Exception as e:
            _LOGGER.error(f"Не удалось закрыть рольставни {self._name}: {e}")

    async def async_stop_cover(self, **kwargs: Any) -> None:
        """Stop the cover movement."""
        _LOGGER.info(f"Останавливаем рольставни: {self._name} ({self._subnet_id}.{self._device_id}.{self._channel})")
        
        # Операция управления шторами, команда STOP (0)
        operation_code = OPERATION_CURTAIN_CONTROL
        data = [self._channel, COMMAND_STOP, 0, 0]  # channel, command, unused1, unused2
        
        try:
            await self._gateway.send_message(
                [self._subnet_id, self._device_id, 0, 0],  # target address
                [operation_code >> 8, operation_code & 0xFF],  # operation code
                data,
            )
            
            # Обновляем внутреннее состояние
            self._is_opening = False
            self._is_closing = False
            self.async_write_ha_state()
            
            # Через небольшую задержку обновим состояние, чтобы получить обновленное положение
            await asyncio.sleep(1)
            await self.async_update()
        except Exception as e:
            _LOGGER.error(f"Не удалось остановить рольставни {self._name}: {e}")

    async def async_set_cover_position(self, **kwargs: Any) -> None:
        """Set the cover position."""
        position = kwargs.get("position")
        if position is None:
            _LOGGER.error(f"Не указано положение для рольставни {self._name}")
            return
        
        _LOGGER.info(f"Устанавливаем положение рольставни {self._name} на {position}%")
        
        # HDL Buspro использует обратный процент (0% = полностью открыто, 100% = полностью закрыто)
        # Home Assistant использует: 0% = полностью закрыто, 100% = полностью открыто
        # Поэтому инвертируем значение
        hdl_position = 100 - position
        
        # Операция управления шторами, команда POSITION (3)
        operation_code = OPERATION_CURTAIN_CONTROL
        data = [self._channel, COMMAND_POSITION, hdl_position, 0]  # channel, command, position, unused
        
        try:
            await self._gateway.send_message(
                [self._subnet_id, self._device_id, 0, 0],  # target address
                [operation_code >> 8, operation_code & 0xFF],  # operation code
                data,
            )
            
            # Обновляем внутреннее состояние
            self._position = position
            self._is_opening = False
            self._is_closing = False
            self.async_write_ha_state()
            
            # Через небольшую задержку обновим состояние, чтобы получить обновленное положение
            await asyncio.sleep(1)
            await self.async_update()
        except Exception as e:
            _LOGGER.error(f"Не удалось установить положение рольставни {self._name}: {e}")

    async def async_update(self) -> None:
        """Update the cover state."""
        try:
            # Запрос состояния устройства
            operation_code = OPERATION_CURTAIN_CONTROL
            data = [self._channel, 0, 0, 0]  # channel, запрос состояния
            
            # Отправляем запрос на получение состояния
            response = await self._gateway.send_message(
                [self._subnet_id, self._device_id, 0, 0],  # target address
                [operation_code >> 8, operation_code & 0xFF],  # operation code
                data,
            )
            
            if response and len(response) >= 4:
                # HDL Buspro использует обратный процент (0% = полностью открыто, 100% = полностью закрыто)
                # Home Assistant использует: 0% = полностью закрыто, 100% = полностью открыто
                hdl_position = response[2]  # Третий байт содержит положение
                self._position = 100 - hdl_position
                self._is_opening = False
                self._is_closing = False
                self._available = True
            else:
                _LOGGER.warning(f"Неверный ответ от рольставни {self._name}: {response}")
        except Exception as e:
            _LOGGER.error(f"Ошибка при обновлении состояния рольставни {self._name}: {e}")
            self._available = False 