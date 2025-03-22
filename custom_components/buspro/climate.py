"""
This component provides climate support for Buspro.

For more details about this platform, please refer to the documentation at
https://home-assistant.io/components/...
"""

import logging
from typing import Any, Dict, List, Optional, Set

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

from .const import DOMAIN, OPERATION_READ_STATUS, CLIMATE

_LOGGER = logging.getLogger(__name__)

CONF_PRESET_MODES = "preset_modes"

# Маппинг между режимами Home Assistant и режимами HDL Buspro
HVAC_MODES_MAP = {
    HVACMode.OFF: 0x00,
    HVACMode.HEAT: 0x01,
    HVACMode.COOL: 0x02,
    HVACMode.AUTO: 0x03,
    HVACMode.FAN_ONLY: 0x04,
    HVACMode.DRY: 0x05,
}

# Маппинг между режимами предустановок Home Assistant и режимами HDL Buspro
PRESET_MODES_MAP = {
    PRESET_NONE: 0x00,
    PRESET_AWAY: 0x01,
    PRESET_HOME: 0x02,
    PRESET_SLEEP: 0x03,
}

DEFAULT_MIN_TEMP = 5.0
DEFAULT_MAX_TEMP = 35.0

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
        
    async def async_set_hvac_mode(self, hvac_mode: str) -> None:
        """Set new target hvac mode."""
        if hvac_mode not in self._attr_hvac_modes:
            _LOGGER.warning(f"Устройство не поддерживает режим {hvac_mode}")
            return
            
        hdl_mode = HVAC_MODES_MAP.get(hvac_mode, 0)
        
        # Отправляем команду на устройство
        self._gateway.send_hdl_command(
            self._subnet_id,
            self._device_id,
            OPERATION_READ_STATUS,  # Здесь нужно использовать правильный код операции
            [0x01, hdl_mode]  # Операция установки режима
        )
        
        # Обновляем состояние
        if hvac_mode == HVACMode.OFF:
            self._hvac_action = HVACAction.IDLE
        elif hvac_mode == HVACMode.HEAT:
            self._hvac_action = HVACAction.HEATING
        elif hvac_mode == HVACMode.COOL:
            self._hvac_action = HVACAction.COOLING
        else:
            self._hvac_action = HVACAction.IDLE
            
        self._hvac_mode = hvac_mode
        self.async_write_ha_state()
        
    async def async_set_preset_mode(self, preset_mode: str) -> None:
        """Set new preset mode."""
        if not self._supported_preset_modes or preset_mode not in self._supported_preset_modes:
            _LOGGER.warning(f"Устройство не поддерживает режим предустановки {preset_mode}")
            return
            
        hdl_preset = PRESET_MODES_MAP.get(preset_mode, 0)
        
        # Отправляем команду на устройство
        self._gateway.send_hdl_command(
            self._subnet_id,
            self._device_id,
            OPERATION_READ_STATUS,  # Здесь нужно использовать правильный код операции
            [0x02, hdl_preset]  # Операция установки режима предустановки
        )
        
        # Обновляем состояние
        self._preset_mode = preset_mode
        self.async_write_ha_state()
        
    async def async_set_temperature(self, **kwargs) -> None:
        """Set new target temperature."""
        temperature = kwargs.get(ATTR_TEMPERATURE)
        if temperature is None:
            return
            
        if temperature < self._attr_min_temp or temperature > self._attr_max_temp:
            _LOGGER.warning(f"Температура {temperature} вне допустимого диапазона ({self._attr_min_temp}-{self._attr_max_temp})")
            return
            
        # Преобразуем температуру в формат HDL Buspro (обычно умножается на 10)
        hdl_temp = int(temperature * 10)
        
        # Отправляем команду на устройство
        self._gateway.send_hdl_command(
            self._subnet_id,
            self._device_id,
            OPERATION_READ_STATUS,  # Здесь нужно использовать правильный код операции
            [0x03, hdl_temp >> 8, hdl_temp & 0xFF]  # Операция установки температуры
        )
        
        # Обновляем состояние
        self._target_temperature = temperature
        self.async_write_ha_state()
        
    async def async_update(self) -> None:
        """Fetch new state data for this climate device."""
        try:
            # Запрашиваем текущую температуру
            temp_response = await self._gateway.send_message(
                [self._subnet_id, self._device_id],
                [OPERATION_READ_STATUS],
                [0x01]  # Канал для текущей температуры
            )
            
            if temp_response and len(temp_response) > 0:
                # HDL обычно отправляет температуру * 10
                self._current_temperature = temp_response[0] / 10.0
                
            # Запрашиваем целевую температуру
            target_temp_response = await self._gateway.send_message(
                [self._subnet_id, self._device_id],
                [OPERATION_READ_STATUS],
                [0x02]  # Канал для целевой температуры
            )
            
            if target_temp_response and len(target_temp_response) > 0:
                self._target_temperature = target_temp_response[0] / 10.0
                
            # Запрашиваем режим работы
            mode_response = await self._gateway.send_message(
                [self._subnet_id, self._device_id],
                [OPERATION_READ_STATUS],
                [0x03]  # Канал для режима работы
            )
            
            if mode_response and len(mode_response) > 0:
                hdl_mode = mode_response[0]
                # Преобразуем режим HDL в режим Home Assistant
                for ha_mode, hdl_value in HVAC_MODES_MAP.items():
                    if hdl_value == hdl_mode:
                        self._hvac_mode = ha_mode
                        break
                        
            # Обновляем доступность
            self._available = True
            
        except Exception as err:
            _LOGGER.error(f"Ошибка при обновлении состояния устройства климат-контроля: {err}")
            self._available = False
