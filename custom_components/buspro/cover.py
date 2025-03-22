"""
This component provides cover support for HDL Buspro.

For more details about this platform, please refer to the documentation at
https://home-assistant.io/components/...
"""

import logging
from typing import Any, Dict, Optional

import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from homeassistant.components.cover import (
    ATTR_POSITION,
    CoverDeviceClass,
    CoverEntity,
    CoverEntityFeature,
    PLATFORM_SCHEMA,
)
from homeassistant.const import CONF_NAME, CONF_DEVICES
from homeassistant.core import HomeAssistant, callback
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType

from .const import DOMAIN, OPERATION_CURTAIN_SWITCH, OPERATION_READ_STATUS, COVER

_LOGGER = logging.getLogger(__name__)

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Required(CONF_DEVICES): {cv.string: cv.string},
})

# Константы для команд управления шторами
CURTAIN_CMD_STOP = 0  # Остановка движения
CURTAIN_CMD_UP = 1    # Движение вверх
CURTAIN_CMD_DOWN = 2  # Движение вниз
CURTAIN_CMD_POS = 7   # Установка позиции

async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the HDL Buspro cover platform."""
    gateway = hass.data[DOMAIN][config_entry.entry_id]["gateway"]
    discovery = hass.data[DOMAIN][config_entry.entry_id]["discovery"]
    
    entities = []
    
    # Получение обнаруженных устройств штор
    if COVER in discovery.devices:
        for device in discovery.devices[COVER]:
            subnet_id = device.get("subnet_id")
            device_id = device.get("device_id")
            channel = device.get("channel")
            name = device.get("name")
            
            _LOGGER.info(f"Добавление штор: {name} ({subnet_id}.{device_id}.{channel})")
            entities.append(
                BusproCover(gateway, subnet_id, device_id, channel, name)
            )
    
    if entities:
        async_add_entities(entities)
        _LOGGER.info(f"Добавлено {len(entities)} устройств штор HDL Buspro")

async def async_setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    async_add_entities: AddEntitiesCallback,
    discovery_info: Optional[DiscoveryInfoType] = None,
) -> None:
    """Set up the HDL Buspro cover platform."""
    # Проверяем, что компонент Buspro настроен
    if DOMAIN not in hass.data:
        _LOGGER.error("Cannot set up cover - HDL Buspro integration not found")
        return
    
    hdl = hass.data[DOMAIN].get("gateway")
    if not hdl:
        _LOGGER.error("Cannot set up cover - HDL Buspro gateway not found")
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
        
        _LOGGER.debug(f"Добавление шторы '{name}' с адресом {subnet_id}.{device_id}.{channel}")
        
        entity = BusproCover(hdl, subnet_id, device_id, channel, name)
        entities.append(entity)
    
    if entities:
        async_add_entities(entities)
        _LOGGER.info(f"Добавлено {len(entities)} устройств штор HDL Buspro из configuration.yaml")


class BusproCover(CoverEntity):
    """Представление шторы HDL Buspro."""

    def __init__(
        self,
        gateway,
        subnet_id: int,
        device_id: int,
        channel: int,
        name: str,
    ):
        """Инициализация шторы."""
        self._gateway = gateway
        self._subnet_id = subnet_id
        self._device_id = device_id
        self._channel = channel
        self._name = name
        
        # Состояние шторы
        self._position = 0  # 0 - закрыто полностью, 100 - открыто полностью
        self._is_opening = False
        self._is_closing = False
        self._available = True
        
        # Создаем уникальный ID, включающий все параметры устройства
        self._unique_id = f"cover_{subnet_id}_{device_id}_{channel}"
        
        # Добавляем поддержку операций: открытие, закрытие, стоп, установка позиции
        self._attr_supported_features = (
            CoverEntityFeature.OPEN | 
            CoverEntityFeature.CLOSE | 
            CoverEntityFeature.STOP | 
            CoverEntityFeature.SET_POSITION
        )
        
        # Установка типа устройства
        self._attr_device_class = CoverDeviceClass.CURTAIN
        
    @property
    def name(self) -> str:
        """Возвращает имя шторы."""
        return self._name
        
    @property
    def current_cover_position(self) -> int:
        """Возвращает текущее положение шторы."""
        return self._position
        
    @property
    def is_opening(self) -> bool:
        """Возвращает True, если шторы в процессе открытия."""
        return self._is_opening
        
    @property
    def is_closing(self) -> bool:
        """Возвращает True, если шторы в процессе закрытия."""
        return self._is_closing
        
    @property
    def is_closed(self) -> bool:
        """Возвращает True, если шторы полностью закрыты."""
        return self._position == 0
        
    @property
    def available(self) -> bool:
        """Возвращает True, если устройство доступно."""
        return self._available
        
    @property
    def unique_id(self) -> str:
        """Возвращает уникальный ID."""
        return self._unique_id
        
    async def async_open_cover(self, **kwargs: Any) -> None:
        """Открытие шторы."""
        _LOGGER.info(f"Открытие шторы {self._name} ({self._subnet_id}.{self._device_id}.{self._channel})")
        
        # Используем код OPERATION_CURTAIN_SWITCH для управления шторами
        operation_code = OPERATION_CURTAIN_SWITCH
        
        # Формируем команду: [channel, command]
        data = [self._channel, CURTAIN_CMD_UP]
        
        try:
            # Отправляем команду через шлюз
            response = await self._gateway.send_message(
                [self._subnet_id, self._device_id, 0, 0],  # target_address
                [operation_code >> 8, operation_code & 0xFF],  # operation_code
                data,  # data
            )
            
            # Обновляем состояние
            self._is_opening = True
            self._is_closing = False
            self.async_write_ha_state()
            
        except Exception as e:
            _LOGGER.error(f"Ошибка при открытии шторы {self._name}: {e}")
        
    async def async_close_cover(self, **kwargs: Any) -> None:
        """Закрытие шторы."""
        _LOGGER.info(f"Закрытие шторы {self._name} ({self._subnet_id}.{self._device_id}.{self._channel})")
        
        # Используем код OPERATION_CURTAIN_SWITCH для управления шторами
        operation_code = OPERATION_CURTAIN_SWITCH
        
        # Формируем команду: [channel, command]
        data = [self._channel, CURTAIN_CMD_DOWN]
        
        try:
            # Отправляем команду через шлюз
            response = await self._gateway.send_message(
                [self._subnet_id, self._device_id, 0, 0],  # target_address
                [operation_code >> 8, operation_code & 0xFF],  # operation_code
                data,  # data
            )
            
            # Обновляем состояние
            self._is_opening = False
            self._is_closing = True
            self.async_write_ha_state()
            
        except Exception as e:
            _LOGGER.error(f"Ошибка при закрытии шторы {self._name}: {e}")
        
    async def async_stop_cover(self, **kwargs: Any) -> None:
        """Остановка шторы."""
        _LOGGER.info(f"Остановка шторы {self._name} ({self._subnet_id}.{self._device_id}.{self._channel})")
        
        # Используем код OPERATION_CURTAIN_SWITCH для управления шторами
        operation_code = OPERATION_CURTAIN_SWITCH
        
        # Формируем команду: [channel, command]
        data = [self._channel, CURTAIN_CMD_STOP]
        
        try:
            # Отправляем команду через шлюз
            response = await self._gateway.send_message(
                [self._subnet_id, self._device_id, 0, 0],  # target_address
                [operation_code >> 8, operation_code & 0xFF],  # operation_code
                data,  # data
            )
            
            # Обновляем состояние
            self._is_opening = False
            self._is_closing = False
            self.async_write_ha_state()
            
        except Exception as e:
            _LOGGER.error(f"Ошибка при остановке шторы {self._name}: {e}")
        
    async def async_set_cover_position(self, **kwargs: Any) -> None:
        """Установка позиции шторы."""
        if ATTR_POSITION not in kwargs:
            return
            
        position = kwargs[ATTR_POSITION]
        _LOGGER.info(f"Установка позиции шторы {self._name} ({self._subnet_id}.{self._device_id}.{self._channel}) на {position}%")
        
        # Используем код OPERATION_CURTAIN_SWITCH для управления шторами
        operation_code = OPERATION_CURTAIN_SWITCH
        
        # Формируем команду: [channel, command, position]
        data = [self._channel, CURTAIN_CMD_POS, position]
        
        try:
            # Отправляем команду через шлюз
            response = await self._gateway.send_message(
                [self._subnet_id, self._device_id, 0, 0],  # target_address
                [operation_code >> 8, operation_code & 0xFF],  # operation_code
                data,  # data
            )
            
            # Обновляем состояние
            self._position = position
            self._is_opening = False
            self._is_closing = False
            self.async_write_ha_state()
            
        except Exception as e:
            _LOGGER.error(f"Ошибка при установке позиции шторы {self._name}: {e}")
        
    async def async_update(self) -> None:
        """Получение нового состояния шторы."""
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
            _LOGGER.error(f"Ошибка при обновлении состояния шторы {self._name}: {e}")
            self._available = False 