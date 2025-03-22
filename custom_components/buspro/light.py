"""
This component provides light support for Buspro.

For more details about this platform, please refer to the documentation at
https://home-assistant.io/components/...
"""

import logging
from typing import Any, Dict, List, Optional, Tuple, Callable

import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_RGB_COLOR,
    PLATFORM_SCHEMA,
    ColorMode,
    LightEntity,
    LightEntityFeature,
)
from homeassistant.const import (CONF_NAME, CONF_DEVICES)
from homeassistant.core import HomeAssistant, callback
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType
from homeassistant.util.color import (
    color_rgb_to_rgbw,
    color_rgbw_to_rgb,
)

from .const import DOMAIN, OPERATION_SINGLE_CHANNEL, OPERATION_READ_STATUS, LIGHT, OPERATION_WRITE

_LOGGER = logging.getLogger(__name__)

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Required(CONF_DEVICES): {cv.string: cv.string},
})

# Команды для управления светом
CMD_SINGLE_CHANNEL = 0x0031  # Одноканальное управление
CMD_SCENE_CONTROL = 0x0002   # Вызов сцены

async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the HDL Buspro light platform."""
    gateway = hass.data[DOMAIN][config_entry.entry_id]["gateway"]
    discovery = hass.data[DOMAIN][config_entry.entry_id]["discovery"]
    
    entities = []
    
    # Получение обнаруженных устройств освещения
    if LIGHT in discovery.devices:
        for device in discovery.devices[LIGHT]:
            subnet_id = device.get("subnet_id")
            device_id = device.get("device_id")
            channel = device.get("channel")
            name = device.get("name")
            model = device.get("model", "")
            
            # Определение типа устройства по модели
            if model and ("RGB" in model or "rgb" in model):
                _LOGGER.info(f"Добавление RGB светильника: {name} ({subnet_id}.{device_id}.{channel})")
                entities.append(
                    BusproRGBLight(gateway, subnet_id, device_id, channel, name)
                )
            elif model and ("Dimmer" in model or "dimmer" in model or "MDT" in model):
                _LOGGER.info(f"Добавление диммера: {name} ({subnet_id}.{device_id}.{channel})")
                entities.append(
                    BusproDimmerLight(gateway, subnet_id, device_id, channel, name)
                )
            else:
                _LOGGER.info(f"Добавление релейного светильника: {name} ({subnet_id}.{device_id}.{channel})")
                entities.append(
                    BusproRelayLight(gateway, subnet_id, device_id, channel, name)
                )
    
    if entities:
        async_add_entities(entities)
        _LOGGER.info(f"Добавлено {len(entities)} устройств освещения HDL Buspro")


async def async_setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    async_add_entities: AddEntitiesCallback,
    discovery_info: Optional[DiscoveryInfoType] = None,
) -> None:
    """Set up the HDL Buspro light platform with configuration.yaml."""
    # Проверяем, что компонент Buspro настроен
    if DOMAIN not in hass.data:
        _LOGGER.error("Cannot set up lights - HDL Buspro integration not found")
        return
    
    hdl = hass.data[DOMAIN].get("gateway")
    if not hdl:
        _LOGGER.error("Cannot set up lights - HDL Buspro gateway not found")
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
        
        _LOGGER.debug(f"Добавление света '{name}' с адресом {subnet_id}.{device_id}.{channel}")
        
        entity = BusproLight(hdl, subnet_id, device_id, channel, name)
        entities.append(entity)
    
    if entities:
        async_add_entities(entities)
        _LOGGER.info(f"Добавлено {len(entities)} устройств освещения HDL Buspro из configuration.yaml")


class BusproBaseLight(LightEntity):
    """Базовый класс для светильников HDL Buspro."""

    def __init__(
        self,
        gateway,
        subnet_id: int,
        device_id: int,
        channel: int,
        name: str,
    ):
        """Initialize the light."""
        self._gateway = gateway
        self._subnet_id = subnet_id
        self._device_id = device_id
        self._channel = channel
        self._name = name
        self._state = False
        self._available = True
        # Создаем уникальный ID, включающий все параметры устройства
        self._unique_id = f"light_{subnet_id}_{device_id}_{channel}"
        
    @property
    def name(self) -> str:
        """Return the name of the light."""
        return self._name
        
    @property
    def is_on(self) -> bool:
        """Return true if light is on."""
        return self._state
        
    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return self._available
        
    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the light on."""
        raise NotImplementedError()
        
    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the light off."""
        raise NotImplementedError()
        
    async def async_update(self) -> None:
        """Fetch new state data for this light."""
        raise NotImplementedError()

    @property
    def unique_id(self) -> str:
        """Return a unique ID."""
        return self._unique_id


class BusproRelayLight(BusproBaseLight):
    """Representation of a HDL Buspro Relay Light."""

    @property
    def color_mode(self) -> str:
        """Return the color mode of the light."""
        return ColorMode.ONOFF

    @property
    def supported_color_modes(self) -> set[str]:
        """Return supported color modes."""
        return {ColorMode.ONOFF}

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the light on."""
        _LOGGER.info(f"Включение реле {self._name} ({self._subnet_id}.{self._device_id}.{self._channel})")
        
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
            _LOGGER.error(f"Ошибка при включении реле {self._name}: {e}")

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the light off."""
        _LOGGER.info(f"Выключение реле {self._name} ({self._subnet_id}.{self._device_id}.{self._channel})")
        
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
            _LOGGER.error(f"Ошибка при выключении реле {self._name}: {e}")

    async def async_update(self) -> None:
        """Fetch new state data for this light."""
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
            _LOGGER.error(f"Ошибка при обновлении состояния реле {self._name}: {e}")
            self._available = False


class BusproDimmerLight(BusproBaseLight):
    """Representation of a HDL Buspro Dimmer Light."""

    def __init__(
        self,
        gateway,
        subnet_id: int,
        device_id: int,
        channel: int,
        name: str,
    ):
        """Initialize the dimmer light."""
        super().__init__(gateway, subnet_id, device_id, channel, name)
        self._brightness = 255  # Полная яркость по умолчанию

    @property
    def color_mode(self) -> str:
        """Return the color mode of the light."""
        return ColorMode.BRIGHTNESS

    @property
    def supported_color_modes(self) -> set[str]:
        """Return supported color modes."""
        return {ColorMode.BRIGHTNESS}

    @property
    def brightness(self) -> int:
        """Return the brightness of this light between 0..255."""
        return self._brightness

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the light on."""
        brightness = kwargs.get(ATTR_BRIGHTNESS, self._brightness if self._state else 255)
        
        # Преобразуем яркость из диапазона 0-255 в диапазон 0-100
        brightness_percent = int(brightness / 255 * 100)
        
        _LOGGER.info(f"Включение диммера {self._name} ({self._subnet_id}.{self._device_id}.{self._channel}) с яркостью {brightness_percent}%")
        
        # Используем код OPERATION_SINGLE_CHANNEL (0x0031) для управления диммером
        operation_code = OPERATION_SINGLE_CHANNEL
        
        # Формируем команду: [channel, value, unused]
        # value = яркость в процентах (0-100)
        data = [self._channel, brightness_percent, 0]
        
        try:
            # Отправляем команду через шлюз
            response = await self._gateway.send_message(
                [self._subnet_id, self._device_id, 0, 0],  # target_address
                [operation_code >> 8, operation_code & 0xFF],  # operation_code
                data,  # data
            )
            
            # Обновляем состояние
            self._state = True
            self._brightness = brightness
            self.async_write_ha_state()
            
        except Exception as e:
            _LOGGER.error(f"Ошибка при включении диммера {self._name}: {e}")

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the light off."""
        _LOGGER.info(f"Выключение диммера {self._name} ({self._subnet_id}.{self._device_id}.{self._channel})")
        
        # Используем код OPERATION_SINGLE_CHANNEL (0x0031) для выключения диммера
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
            _LOGGER.error(f"Ошибка при выключении диммера {self._name}: {e}")

    async def async_update(self) -> None:
        """Fetch new state data for this light."""
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
            _LOGGER.error(f"Ошибка при обновлении состояния диммера {self._name}: {e}")
            self._available = False


class BusproRGBLight(BusproBaseLight):
    """Representation of a HDL Buspro RGB Light."""

    def __init__(
        self,
        gateway,
        subnet_id: int,
        device_id: int,
        channel: int,
        name: str,
    ):
        """Initialize the RGB light."""
        super().__init__(gateway, subnet_id, device_id, channel, name)
        
        # Настройка цветового режима
        self._attr_color_mode = ColorMode.RGB
        self._attr_supported_color_modes = {ColorMode.RGB}
        
        # RGB цвет и яркость
        self._rgb_color = (255, 255, 255)
        self._brightness = 0
        
    @property
    def brightness(self) -> Optional[int]:
        """Return the brightness of this light between 0..255."""
        return self._brightness
        
    @property
    def rgb_color(self) -> Optional[Tuple[int, int, int]]:
        """Return the rgb color value [int, int, int]."""
        return self._rgb_color
        
    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the light on."""
        if ATTR_RGB_COLOR in kwargs:
            self._rgb_color = kwargs[ATTR_RGB_COLOR]
            
        brightness = kwargs.get(ATTR_BRIGHTNESS, 255 if self._brightness == 0 else self._brightness)
        
        # Преобразуем яркость в диапазон 0-100%
        level = int(brightness * 100 / 255)
        
        _LOGGER.debug(f"Включение RGB света {self._subnet_id}.{self._device_id}.{self._channel} " + 
                     f"с цветом {self._rgb_color} и яркостью {level}%")
        
        # Создаем телеграмму для установки RGB цвета
        # В HDL Buspro обычно используются отдельные каналы для R, G, B
        # Канал R = базовый канал, G = канал+1, B = канал+2
        r, g, b = self._rgb_color
        
        # Масштабируем RGB значения с учетом яркости
        r_level = int(r * level / 255)
        g_level = int(g * level / 255)
        b_level = int(b * level / 255)
        
        # Отправляем команды для каждого канала
        for color_offset, color_value in enumerate([r_level, g_level, b_level]):
            try:
                # Создаем телеграмму для каждого цветового канала
                telegram = {
                    "subnet_id": self._subnet_id,
                    "device_id": self._device_id,
                    "operate_code": OPERATION_WRITE,
                    "data": [CMD_SINGLE_CHANNEL, self._channel + color_offset, color_value],
                }
                
                # Отправляем телеграмму через шлюз
                await self._gateway.send_telegram(telegram)
                _LOGGER.debug(f"Установлен канал {self._channel + color_offset} на значение {color_value}")
            except Exception as err:
                _LOGGER.error(f"Ошибка при установке RGB канала {self._channel + color_offset}: {err}")
                return
        
        self._state = True
        self._brightness = brightness
        _LOGGER.info(f"RGB свет {self._subnet_id}.{self._device_id}.{self._channel} включен с цветом {self._rgb_color} и яркостью {level}%")
        
    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the light off."""
        _LOGGER.debug(f"Выключение RGB света {self._subnet_id}.{self._device_id}.{self._channel}")
        
        # Отправляем команды для выключения каждого канала
        for color_offset in range(3):  # R, G, B
            try:
                # Создаем телеграмму для каждого цветового канала
                telegram = {
                    "subnet_id": self._subnet_id,
                    "device_id": self._device_id,
                    "operate_code": OPERATION_WRITE,
                    "data": [CMD_SINGLE_CHANNEL, self._channel + color_offset, 0],  # 0% - выключено
                }
                
                # Отправляем телеграмму через шлюз
                await self._gateway.send_telegram(telegram)
                _LOGGER.debug(f"Выключен канал {self._channel + color_offset}")
            except Exception as err:
                _LOGGER.error(f"Ошибка при выключении RGB канала {self._channel + color_offset}: {err}")
                return
        
        self._state = False
        _LOGGER.info(f"RGB свет {self._subnet_id}.{self._device_id}.{self._channel} выключен")
        
    async def async_update(self) -> None:
        """Fetch new state data for this light."""
        try:
            _LOGGER.debug(f"Обновление состояния RGB света {self._subnet_id}.{self._device_id}.{self._channel}")
            
            rgb_values = []
            
            # Запрашиваем состояние каждого цветового канала
            for color_offset in range(3):  # R, G, B
                # Создаем телеграмму для запроса статуса
                telegram = {
                    "subnet_id": self._subnet_id,
                    "device_id": self._device_id,
                    "operate_code": CMD_SINGLE_CHANNEL,
                    "data": [self._channel + color_offset],
                }
                
                # Отправляем запрос через шлюз
                response = await self._gateway.send_telegram(telegram)
                
                if response and isinstance(response, dict) and "data" in response and response["data"]:
                    # Получаем значение канала (0-100%)
                    if len(response["data"]) > 0:
                        level = response["data"][0]
                        # Преобразуем из 0-100% в 0-255
                        rgb_value = int(level * 255 / 100)
                        rgb_values.append(rgb_value)
                    else:
                        rgb_values.append(0)
                else:
                    rgb_values.append(0)
            
            # Обновляем состояние RGB света
            if len(rgb_values) == 3:
                r, g, b = rgb_values
                self._rgb_color = (r, g, b)
                self._state = any(val > 0 for val in rgb_values)
                
                # Определяем яркость как максимальное значение из RGB
                if self._state:
                    self._brightness = max(rgb_values)
                    
                _LOGGER.debug(f"Получено состояние RGB света {self._subnet_id}.{self._device_id}.{self._channel}: " + 
                             f"{'включен' if self._state else 'выключен'}, цвет: {self._rgb_color}, яркость: {self._brightness}")
                
                self._available = True
            else:
                _LOGGER.warning(f"Не удалось получить полные данные от RGB света {self._subnet_id}.{self._device_id}.{self._channel}")
                # Не меняем доступность при временной ошибке
            
        except Exception as err:
            _LOGGER.error(f"Ошибка при обновлении состояния RGB света {self._subnet_id}.{self._device_id}.{self._channel}: {err}")
            # Не меняем доступность при временной ошибке
