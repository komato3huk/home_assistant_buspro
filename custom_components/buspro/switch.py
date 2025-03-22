"""
This component provides switch support for Buspro.

For more details about this platform, please refer to the documentation at
https://home-assistant.io/components/...
"""

import logging
from typing import Any, Dict, List, Optional, Tuple, Callable

import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from homeassistant.components.switch import (
    SwitchEntity,
    PLATFORM_SCHEMA,
)
from homeassistant.const import (CONF_NAME, CONF_DEVICES, STATE_ON, STATE_OFF)
from homeassistant.core import HomeAssistant, callback
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType

from .const import DOMAIN, OPERATION_SINGLE_CHANNEL, OPERATION_READ_STATUS, SWITCH

_LOGGER = logging.getLogger(__name__)

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Required(CONF_DEVICES): {cv.string: cv.string},
})

# HDL Buspro commands for controlling switches
CMD_SINGLE_CHANNEL = 0x0031  # Одноканальное управление

async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the HDL Buspro switch platform."""
    gateway = hass.data[DOMAIN][config_entry.entry_id]["gateway"]
    discovery = hass.data[DOMAIN][config_entry.entry_id]["discovery"]
    
    entities = []
    
    # Получение обнаруженных устройств выключателей
    if SWITCH in discovery.devices:
        for device in discovery.devices[SWITCH]:
            subnet_id = device.get("subnet_id")
            device_id = device.get("device_id")
            channel = device.get("channel")
            name = device.get("name")
            
            _LOGGER.info(f"Добавление релейного выключателя: {name} ({subnet_id}.{device_id}.{channel})")
            entities.append(
                BusproSwitch(gateway, subnet_id, device_id, channel, name)
            )
    
    if entities:
        async_add_entities(entities)
        _LOGGER.info(f"Добавлено {len(entities)} устройств выключателей HDL Buspro")


async def async_setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    async_add_entities: AddEntitiesCallback,
    discovery_info: Optional[DiscoveryInfoType] = None,
) -> None:
    """Set up the HDL Buspro switch platform."""
    # Проверяем, что компонент Buspro настроен
    if DOMAIN not in hass.data:
        _LOGGER.error("Cannot set up switch - HDL Buspro integration not found")
        return
    
    hdl = hass.data[DOMAIN].get("gateway")
    if not hdl:
        _LOGGER.error("Cannot set up switch - HDL Buspro gateway not found")
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
        
        _LOGGER.debug(f"Добавление выключателя '{name}' с адресом {subnet_id}.{device_id}.{channel}")
        
        entity = BusproSwitch(hdl, subnet_id, device_id, channel, name)
        entities.append(entity)
    
    if entities:
        async_add_entities(entities)
        _LOGGER.info(f"Добавлено {len(entities)} устройств выключателей HDL Buspro из configuration.yaml")


class BusproSwitch(SwitchEntity):
    """Репрезентация выключателя HDL Buspro."""

    def __init__(
        self,
        gateway,
        subnet_id: int,
        device_id: int,
        channel: int,
        name: str,
    ):
        """Инициализация выключателя."""
        self._gateway = gateway
        self._subnet_id = subnet_id
        self._device_id = device_id
        self._channel = channel
        self._name = name
        self._state = False
        self._available = True
        # Создаем уникальный ID, включающий все параметры устройства
        self._unique_id = f"switch_{subnet_id}_{device_id}_{channel}"
        
    @property
    def name(self) -> str:
        """Возвращает имя выключателя."""
        return self._name
        
    @property
    def is_on(self) -> bool:
        """Возвращает true если выключатель включен."""
        return self._state
        
    @property
    def available(self) -> bool:
        """Возвращает True если сущность доступна."""
        return self._available
        
    @property
    def unique_id(self) -> str:
        """Возвращает уникальный ID."""
        return self._unique_id
        
    async def async_turn_on(self, **kwargs: Any) -> None:
        """Включение выключателя."""
        _LOGGER.info(f"Включение выключателя {self._name} ({self._subnet_id}.{self._device_id}.{self._channel})")
        
        # Используем код OPERATION_SINGLE_CHANNEL (0x0031) для включения реле
        operation_code = OPERATION_SINGLE_CHANNEL
        
        # Формируем команду: [channel, value, unused]
        # value = 100 (полная яркость для релейного выхода, в процентах)
        data = [self._channel, 100, 0]
        
        try:
            # Отправляем команду через шлюз
            response = await self._gateway.send_message(
                [self._subnet_id, self._device_id, 0, 0],  # target_address
                [operation_code >> 8, operation_code & 0xFF],  # operation_code
                data,  # data
            )
            
            # Обновляем состояние
            self._state = True
            self.async_write_ha_state()
            
        except Exception as e:
            _LOGGER.error(f"Ошибка при включении выключателя {self._name}: {e}")
        
    async def async_turn_off(self, **kwargs: Any) -> None:
        """Выключение выключателя."""
        _LOGGER.info(f"Выключение выключателя {self._name} ({self._subnet_id}.{self._device_id}.{self._channel})")
        
        # Используем код OPERATION_SINGLE_CHANNEL (0x0031) для выключения реле
        operation_code = OPERATION_SINGLE_CHANNEL
        
        # Формируем команду: [channel, value, unused]
        # value = 0 (выключено, 0 процентов)
        data = [self._channel, 0, 0]
        
        try:
            # Отправляем команду через шлюз
            response = await self._gateway.send_message(
                [self._subnet_id, self._device_id, 0, 0],  # target_address
                [operation_code >> 8, operation_code & 0xFF],  # operation_code
                data,  # data
            )
            
            # Обновляем состояние
            self._state = False
            self.async_write_ha_state()
            
        except Exception as e:
            _LOGGER.error(f"Ошибка при выключении выключателя {self._name}: {e}")
        
    async def async_update(self) -> None:
        """Получение нового состояния выключателя."""
        try:
            # Запрашиваем состояние устройства
            operation_code = OPERATION_READ_STATUS
            
            # Формируем команду: [channel]
            data = [self._channel]
            
            # Отправляем запрос статуса через шлюз
            response = await self._gateway.send_message(
                [self._subnet_id, self._device_id, 0, 0],  # target_address
                [operation_code >> 8, operation_code & 0xFF],  # operation_code
                data,  # data
            )
            
            # Обработка ответа
            # Это заглушка, так как реальный ответ обрабатывается асинхронно через колбэки
            # В реальной реализации устанавливаем значение, только если получен ответ
            self._available = True
            
        except Exception as e:
            _LOGGER.error(f"Ошибка при обновлении состояния выключателя {self._name}: {e}")
            self._available = False
