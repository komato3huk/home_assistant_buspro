"""
This component provides climate support for Buspro.

For more details about this platform, please refer to the documentation at
https://home-assistant.io/components/...
"""

import logging
from typing import Any, Dict, List, Optional, Set
from datetime import timedelta

import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from homeassistant.components.climate import (
    ClimateEntity,
    PLATFORM_SCHEMA,
    HVACMode,
    HVACAction,
    ClimateEntityFeature,
    PRESET_NONE,
    PRESET_AWAY,
    PRESET_HOME,
    PRESET_SLEEP,
)
from homeassistant.components.climate.const import ATTR_PRESET_MODE
from homeassistant.const import (
    CONF_NAME,
    CONF_DEVICES,
    CONF_ADDRESS,
    UnitOfTemperature,
    ATTR_TEMPERATURE,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType

from .const import DOMAIN, OPERATION_READ_STATUS, CLIMATE, CONF_PRESET_MODES

_LOGGER = logging.getLogger(__name__)

# Константы для работы с климат-контроллером
DEFAULT_MIN_TEMP = 5
DEFAULT_MAX_TEMP = 40

# Карты режимов
PRESET_MODES_MAP = {
    "normal": 1,
    "day": 2,
    "night": 3,
    "away": 4,
    "timer": 5,
}

# Коды операций
OPERATE_CODES = {
    "read_floor_heating": 0x1944,  # ReadFloorHeatingStatus
    "control_floor_heating": 0x1946,  # ControlFloorHeatingStatus
}

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Required(CONF_DEVICES):
        vol.All(cv.ensure_list, [
            vol.Schema({
                vol.Required(CONF_ADDRESS): cv.string,
                vol.Required(CONF_NAME): cv.string,
                vol.Optional(CONF_PRESET_MODES, default=[]): vol.All(cv.ensure_list, [cv.string]),
            })
        ])
})

async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the HDL Buspro climate devices from config entry."""
    gateway = hass.data[DOMAIN][config_entry.entry_id]["gateway"]
    discovery = hass.data[DOMAIN][config_entry.entry_id]["discovery"]
    
    entities = []
    
    # Обрабатываем обнаруженные устройства климат-контроля
    for device in discovery.get_devices_by_type(CLIMATE):
        subnet_id = device["subnet_id"]
        # Работаем только с устройствами из подсети 1
        if subnet_id != 1:
            continue
            
        device_id = device["device_id"]
        channel = device.get("channel", 1)
        device_name = device.get("name", f"Climate {subnet_id}.{device_id}")
        
        # Создаем сущность климат-контроля
        entity = BusproClimate(gateway, subnet_id, device_id, device_name)
        entities.append(entity)
    
    if entities:
        async_add_entities(entities)
        _LOGGER.info(f"Добавлено {len(entities)} устройств климат-контроля HDL Buspro")


async def async_setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    async_add_entities: AddEntitiesCallback,
    discovery_info: Optional[DiscoveryInfoType] = None,
) -> None:
    """Set up the HDL Buspro climate platform with configuration.yaml."""
    # Проверяем, что компонент Buspro настроен
    if DOMAIN not in hass.data:
        _LOGGER.error("Cannot set up climate devices - HDL Buspro integration not found")
        return
    
    hdl = hass.data[DOMAIN].get("gateway")
    if not hdl:
        _LOGGER.error("Cannot set up climate devices - HDL Buspro gateway not found")
        return
    
    entities = []
    
    for device_config in config[CONF_DEVICES]:
        address = device_config[CONF_ADDRESS]
        name = device_config[CONF_NAME]
        preset_modes = device_config.get(CONF_PRESET_MODES, [])
        
        # Парсим адрес устройства
        address_parts = address.split('.')
        if len(address_parts) < 2:
            _LOGGER.error(f"Неверный формат адреса: {address}. Должен быть subnet_id.device_id")
            continue
            
        try:
            subnet_id = int(address_parts[0])
            device_id = int(address_parts[1])
        except ValueError:
            _LOGGER.error(f"Неверный формат адреса: {address}. Все части должны быть целыми числами")
            continue
        
        _LOGGER.debug(f"Добавление устройства климат-контроля '{name}' с адресом {subnet_id}.{device_id}")
        
        # Создаем сущность климат-контроля
        entity = BusproClimate(hdl, subnet_id, device_id, name, preset_modes)
        entities.append(entity)
    
    if entities:
        async_add_entities(entities)
        _LOGGER.info(f"Добавлено {len(entities)} устройств климат-контроля HDL Buspro из configuration.yaml")


class BusproClimate(ClimateEntity):
    """Representation of a HDL Buspro Climate device."""

    def __init__(
        self,
        gateway,
        subnet_id: int,
        device_id: int,
        name: str,
        preset_modes: List[str] = None,
    ):
        """Initialize the climate device."""
        self._gateway = gateway
        self._subnet_id = subnet_id
        self._device_id = device_id
        self._attr_name = name
        self._attr_unique_id = f"climate_{subnet_id}_{device_id}"
        
        # Состояние устройства
        self._hvac_mode = HVACMode.OFF
        self._hvac_action = HVACAction.IDLE
        self._target_temperature = 24.0
        self._current_temperature = None
        self._preset_mode = PRESET_NONE
        
        # Поддерживаемые режимы
        self._attr_hvac_modes = [HVACMode.OFF, HVACMode.HEAT, HVACMode.COOL, HVACMode.AUTO]
        
        # Настройка поддерживаемых режимов предустановок
        self._supported_preset_modes = []
        if preset_modes:
            valid_presets = [mode for mode in preset_modes if mode in PRESET_MODES_MAP]
            self._supported_preset_modes = valid_presets
        
        # Настройка поддерживаемых функций
        features = ClimateEntityFeature.TARGET_TEMPERATURE
        if self._supported_preset_modes:
            features |= ClimateEntityFeature.PRESET_MODE
        
        self._attr_supported_features = features
        
        # Настройки температуры
        self._attr_temperature_unit = UnitOfTemperature.CELSIUS
        self._attr_min_temp = DEFAULT_MIN_TEMP
        self._attr_max_temp = DEFAULT_MAX_TEMP
        self._attr_target_temperature_step = 0.5
        
        # Доступность устройства
        self._available = True
        
    async def async_added_to_hass(self):
        """Register callbacks when entity is added to Home Assistant."""
        await self.async_update()
        
    @property
    def name(self) -> str:
        """Return the name of the climate device."""
        return self._attr_name
        
    @property
    def unique_id(self) -> str:
        """Return the unique ID of the climate device."""
        return self._attr_unique_id
        
    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return self._available
        
    @property
    def hvac_mode(self) -> HVACMode:
        """Return hvac operation mode."""
        return self._hvac_mode
        
    @property
    def hvac_action(self) -> HVACAction:
        """Return the current running hvac operation."""
        return self._hvac_action
        
    @property
    def preset_mode(self) -> Optional[str]:
        """Return the current preset mode."""
        if not self._supported_preset_modes:
            return None
        return self._preset_mode
        
    @property
    def preset_modes(self) -> Optional[List[str]]:
        """Return a list of available preset modes."""
        if not self._supported_preset_modes:
            return None
        return self._supported_preset_modes
        
    @property
    def current_temperature(self) -> Optional[float]:
        """Return the current temperature."""
        return self._current_temperature
        
    @property
    def target_temperature(self) -> Optional[float]:
        """Return the temperature we try to reach."""
        return self._target_temperature
        
    async def async_set_temperature(self, **kwargs) -> None:
        """Set new target temperature."""
        temperature = kwargs.get(ATTR_TEMPERATURE)
        if temperature is None:
            return
            
        self._target_temperature = temperature
        
        # Отправляем команду на устройство
        try:
            # Преобразуем температуру в формат устройства (умножаем на 10 для работы с десятыми долями)
            temp_value = int(temperature * 10)
            
            # Создаем телеграмму для установки температуры
            telegram = {
                "subnet_id": self._subnet_id,
                "device_id": self._device_id,
                "operate_code": OPERATE_CODES["control_floor_heating"],
                "data": [
                    1,  # temperature_type (Celsius)
                    0,  # current_temperature (не меняется при установке)
                    1 if self._hvac_mode != HVACMode.OFF else 0,  # status (on/off)
                    1,  # mode (Normal)
                    temp_value,  # normal_temperature
                    240,  # day_temperature (24.0°C, не меняется)
                    180,  # night_temperature (18.0°C, не меняется)
                    150,  # away_temperature (15.0°C, не меняется)
                ],
            }
            
            # Отправляем команду через шлюз
            await self._gateway.send_telegram(telegram)
            _LOGGER.debug(f"Установлена целевая температура {temperature}°C для устройства {self._subnet_id}.{self._device_id}")
            
            # Обновляем состояние после отправки команды
            await self.async_update()
            
        except Exception as err:
            _LOGGER.error(f"Ошибка при установке температуры: {err}")
            
    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set new hvac mode."""
        # Преобразуем режим HVAC в состояние устройства
        status = 0  # По умолчанию - выключено
        
        if hvac_mode != HVACMode.OFF:
            status = 1  # Включено
            
        self._hvac_mode = hvac_mode
        
        # Отправляем команду на устройство
        try:
            # Создаем телеграмму для установки режима
            telegram = {
                "subnet_id": self._subnet_id,
                "device_id": self._device_id,
                "operate_code": OPERATE_CODES["control_floor_heating"],
                "data": [
                    1,  # temperature_type (Celsius)
                    0,  # current_temperature (не меняется при установке)
                    status,  # status (on/off)
                    1,  # mode (Normal)
                    int(self._target_temperature * 10),  # normal_temperature
                    240,  # day_temperature (24.0°C, не меняется)
                    180,  # night_temperature (18.0°C, не меняется)
                    150,  # away_temperature (15.0°C, не меняется)
                ],
            }
            
            # Отправляем команду через шлюз
            await self._gateway.send_telegram(telegram)
            _LOGGER.debug(f"Установлен режим HVAC {hvac_mode} для устройства {self._subnet_id}.{self._device_id}")
            
            # Обновляем состояние после отправки команды
            await self.async_update()
            
        except Exception as err:
            _LOGGER.error(f"Ошибка при установке режима HVAC: {err}")
            
    async def async_set_preset_mode(self, preset_mode: str) -> None:
        """Set new preset mode."""
        if preset_mode not in self._supported_preset_modes:
            _LOGGER.error(f"Неподдерживаемый режим предустановки: {preset_mode}")
            return
            
        # Получаем режим температуры из карты предустановок
        temp_mode = PRESET_MODES_MAP.get(preset_mode, 1)  # По умолчанию - Normal (1)
        self._preset_mode = preset_mode
        
        # Отправляем команду на устройство
        try:
            # Создаем телеграмму для установки режима предустановки
            telegram = {
                "subnet_id": self._subnet_id,
                "device_id": self._device_id,
                "operate_code": OPERATE_CODES["control_floor_heating"],
                "data": [
                    1,  # temperature_type (Celsius)
                    0,  # current_temperature (не меняется при установке)
                    1 if self._hvac_mode != HVACMode.OFF else 0,  # status (on/off)
                    temp_mode,  # mode (из карты предустановок)
                    int(self._target_temperature * 10),  # normal_temperature
                    240,  # day_temperature (24.0°C, не меняется)
                    180,  # night_temperature (18.0°C, не меняется)
                    150,  # away_temperature (15.0°C, не меняется)
                ],
            }
            
            # Отправляем команду через шлюз
            await self._gateway.send_telegram(telegram)
            _LOGGER.debug(f"Установлен режим предустановки {preset_mode} для устройства {self._subnet_id}.{self._device_id}")
            
            # Обновляем состояние после отправки команды
            await self.async_update()
            
        except Exception as err:
            _LOGGER.error(f"Ошибка при установке режима предустановки: {err}")
            
    async def async_update(self) -> None:
        """Fetch new state data for this climate device."""
        try:
            # Создаем телеграмму для запроса статуса
            telegram = {
                "subnet_id": self._subnet_id,
                "device_id": self._device_id,
                "operate_code": OPERATE_CODES["read_floor_heating"],
                "data": [],
            }
            
            # Отправляем запрос через шлюз
            response = await self._gateway.send_telegram(telegram)
            
            if response and "data" in response:
                data = response["data"]
                
                if len(data) >= 8:
                    # Интерпретируем полученные данные
                    temperature_type = data[0]  # 1 - Celsius, 2 - Fahrenheit
                    current_temp = data[1] / 10.0  # Делим на 10 для получения градусов
                    status = data[2]  # 0 - выключено, 1 - включено
                    mode = data[3]  # 1 - Normal, 2 - Day, 3 - Night, 4 - Away, 5 - Timer
                    normal_temp = data[4] / 10.0
                    day_temp = data[5] / 10.0
                    night_temp = data[6] / 10.0
                    away_temp = data[7] / 10.0
                    
                    # Обновляем состояние устройства
                    self._current_temperature = current_temp
                    
                    # Определяем HVAC режим на основе статуса
                    if status == 0:
                        self._hvac_mode = HVACMode.OFF
                        self._hvac_action = HVACAction.IDLE
                    else:
                        # По умолчанию устанавливаем режим HEAT
                        self._hvac_mode = HVACMode.HEAT
                        self._hvac_action = HVACAction.HEATING
                    
                    # Определяем целевую температуру на основе режима
                    if mode == 1:  # Normal
                        self._target_temperature = normal_temp
                        self._preset_mode = PRESET_NONE
                    elif mode == 2:  # Day
                        self._target_temperature = day_temp
                        for preset, preset_mode in PRESET_MODES_MAP.items():
                            if preset_mode == mode and preset in self._supported_preset_modes:
                                self._preset_mode = preset
                                break
                    elif mode == 3:  # Night
                        self._target_temperature = night_temp
                        for preset, preset_mode in PRESET_MODES_MAP.items():
                            if preset_mode == mode and preset in self._supported_preset_modes:
                                self._preset_mode = preset
                                break
                    elif mode == 4:  # Away
                        self._target_temperature = away_temp
                        for preset, preset_mode in PRESET_MODES_MAP.items():
                            if preset_mode == mode and preset in self._supported_preset_modes:
                                self._preset_mode = preset
                                break
                                
                    self._available = True
                    _LOGGER.debug(f"Обновлено состояние устройства климат-контроля {self._subnet_id}.{self._device_id}")
                else:
                    _LOGGER.warning(f"Получен неполный ответ от устройства климат-контроля {self._subnet_id}.{self._device_id}: {data}")
            else:
                _LOGGER.warning(f"Не удалось получить данные от устройства климат-контроля {self._subnet_id}.{self._device_id}")
                self._available = False
            
        except Exception as err:
            _LOGGER.error(f"Ошибка при обновлении состояния устройства климат-контроля: {err}")
            self._available = False
