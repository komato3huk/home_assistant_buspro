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

from .const import DOMAIN, OPERATION_SINGLE_CHANNEL, OPERATION_READ_STATUS, SWITCH, OPERATION_WRITE

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
    
    # Получаем переключатели из обнаруженных устройств
    for device in discovery.get_devices_by_type("switch"):
        subnet_id = device["subnet_id"]
        device_id = device["device_id"]
        channels = device.get("channels", 1)
        device_name = device.get("name", f"Switch {subnet_id}.{device_id}")
        
        _LOGGER.info(f"Обнаружен релейный модуль: {device_name} ({subnet_id}.{device_id})")
        
        # Для релейных модулей обычно есть несколько каналов
        for channel in range(1, channels + 1):
            name = f"{device_name} {channel}" if channels > 1 else device_name
            
            entity = BusproSwitch(
                gateway,
                subnet_id,
                device_id,
                channel,
                name,
            )
            entities.append(entity)
            
            _LOGGER.debug(f"Добавлен переключатель: {name} ({subnet_id}.{device_id}.{channel})")
    
    # Для отладки, если не найдено ни одного переключателя, добавим тестовый
    if not entities:
        _LOGGER.info("Добавление тестового переключателя для отладки")
        test_entity = BusproSwitch(
            gateway,
            1,  # subnet_id
            5,  # device_id
            1,  # channel
            "Реле 1.5.1",
        )
        entities.append(test_entity)
    
    if entities:
        async_add_entities(entities)
        _LOGGER.info(f"Добавлено {len(entities)} переключателей HDL Buspro")


async def async_setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    async_add_entities: AddEntitiesCallback,
    discovery_info: Optional[DiscoveryInfoType] = None,
) -> None:
    """Set up the HDL Buspro switch platform with configuration.yaml."""
    # Проверяем, что компонент Buspro настроен
    if DOMAIN not in hass.data:
        _LOGGER.error("Cannot set up switches - HDL Buspro integration not found")
        return
    
    hdl = hass.data[DOMAIN].get("gateway")
    if not hdl:
        _LOGGER.error("Cannot set up switches - HDL Buspro gateway not found")
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
        _LOGGER.info(f"Добавлено {len(entities)} выключателей HDL Buspro из configuration.yaml")


class BusproSwitch(SwitchEntity):
    """Representation of a HDL Buspro Switch."""

    def __init__(
        self,
        gateway,
        subnet_id: int,
        device_id: int,
        channel: int,
        name: str,
    ):
        """Initialize the switch."""
        self._gateway = gateway
        self._subnet_id = subnet_id
        self._device_id = device_id
        self._channel = channel
        self._name = name
        
        # Генерируем уникальный ID
        self._attr_unique_id = f"switch_{subnet_id}_{device_id}_{channel}"
        
        # Состояние переключателя
        self._state = False
        self._available = True
        
    @property
    def name(self) -> str:
        """Return the name of the switch."""
        return self._name
        
    @property
    def is_on(self) -> bool:
        """Return true if switch is on."""
        return self._state
        
    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return self._available
        
    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the switch on."""
        _LOGGER.debug(f"Включение переключателя {self._subnet_id}.{self._device_id}.{self._channel}")
        
        # Создаем телеграмму для включения переключателя
        telegram = {
            "subnet_id": self._subnet_id,
            "device_id": self._device_id,
            "operate_code": OPERATION_WRITE,
            "data": [CMD_SINGLE_CHANNEL, self._channel, 100],  # 100% - включено
        }
        
        # Отправляем телеграмму через шлюз
        try:
            await self._gateway.send_telegram(telegram)
            self._state = True
            _LOGGER.info(f"Переключатель {self._subnet_id}.{self._device_id}.{self._channel} включен")
        except Exception as err:
            _LOGGER.error(f"Ошибка при включении переключателя {self._subnet_id}.{self._device_id}.{self._channel}: {err}")
        
    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the switch off."""
        _LOGGER.debug(f"Выключение переключателя {self._subnet_id}.{self._device_id}.{self._channel}")
        
        # Создаем телеграмму для выключения переключателя
        telegram = {
            "subnet_id": self._subnet_id,
            "device_id": self._device_id,
            "operate_code": OPERATION_WRITE,
            "data": [CMD_SINGLE_CHANNEL, self._channel, 0],  # 0% - выключено
        }
        
        # Отправляем телеграмму через шлюз
        try:
            await self._gateway.send_telegram(telegram)
            self._state = False
            _LOGGER.info(f"Переключатель {self._subnet_id}.{self._device_id}.{self._channel} выключен")
        except Exception as err:
            _LOGGER.error(f"Ошибка при выключении переключателя {self._subnet_id}.{self._device_id}.{self._channel}: {err}")
        
    async def async_update(self) -> None:
        """Fetch new state data for this switch."""
        try:
            _LOGGER.debug(f"Обновление состояния переключателя {self._subnet_id}.{self._device_id}.{self._channel}")
            
            # Создаем телеграмму для запроса статуса
            telegram = {
                "subnet_id": self._subnet_id,
                "device_id": self._device_id,
                "operate_code": CMD_SINGLE_CHANNEL,
                "data": [self._channel],
            }
            
            # Отправляем запрос через шлюз
            response = await self._gateway.send_telegram(telegram)
            
            if response and isinstance(response, dict) and "data" in response and response["data"]:
                # Обычно первый элемент данных - это текущее состояние канала (0-100%)
                if len(response["data"]) > 0:
                    level = response["data"][0]
                    self._state = level > 0
                    _LOGGER.debug(f"Получено состояние переключателя {self._subnet_id}.{self._device_id}.{self._channel}: {'включен' if self._state else 'выключен'}")
                
                self._available = True
            else:
                # Для эмуляции переключателя при отладке
                if self._subnet_id == 1 and self._device_id == 5 and self._channel == 1:
                    # Оставляем текущее состояние
                    _LOGGER.debug(f"Используем текущее состояние для тестового переключателя: {'включен' if self._state else 'выключен'}")
                    self._available = True
                else:
                    _LOGGER.warning(f"Не удалось получить данные от переключателя {self._subnet_id}.{self._device_id}.{self._channel}")
                    # Не меняем доступность при временной ошибке
            
        except Exception as err:
            _LOGGER.error(f"Ошибка при обновлении состояния переключателя {self._subnet_id}.{self._device_id}.{self._channel}: {err}")
            # Не меняем доступность при временной ошибке
