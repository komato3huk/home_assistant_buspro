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
    devices_found = False
    
    # Обрабатываем обнаруженные устройства климат-контроля
    for device in discovery.get_devices_by_type(CLIMATE):
        devices_found = True
        subnet_id = device["subnet_id"]
        device_id = device["device_id"]
        channel = device.get("channel", 1)
        device_name = device.get("name", f"Climate {subnet_id}.{device_id}")
        
        _LOGGER.info(f"Обнаружено устройство климат-контроля: {device_name} ({subnet_id}.{device_id})")
        
        # Специальная обработка для определенных устройств
        # HDL Buspro Floor Heating Actuator обычно имеет тип 0x0073
        device_type = device.get("device_type", 0)
        _LOGGER.debug(f"Тип устройства климат-контроля: 0x{device_type:04X}")
        
        # Специальная обработка для модуля кондиционера MAC01.431 (0x0270)
        if device_type == 0x0270:
            _LOGGER.info(f"Модуль управления кондиционером MAC01.431: {subnet_id}.{device_id}")
            entity = BusproAirConditioner(gateway, subnet_id, device_id, device_name)
            entities.append(entity)
            continue
        
        # Создаем сущность климат-контроля
        entity = BusproClimate(gateway, subnet_id, device_id, device_name)
        entities.append(entity)
    
    # Если устройства не обнаружены, добавляем их вручную для отладки
    if not devices_found:
        _LOGGER.info(f"Устройства климат-контроля не обнаружены. Добавляем устройство вручную для отладки.")
        entity = BusproClimate(gateway, 1, 4, "Floor Heating 1.4")
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
            _LOGGER.debug(f"Запрос обновления для устройства климат-контроля {self._subnet_id}.{self._device_id}")
            
            # Создаем телеграмму для запроса статуса
            telegram = {
                "subnet_id": self._subnet_id,
                "device_id": self._device_id,
                "operate_code": OPERATE_CODES["read_floor_heating"],
                "data": [],
            }
            
            # Отправляем запрос через шлюз
            _LOGGER.debug(f"Отправка запроса данных для {self._subnet_id}.{self._device_id}: {telegram}")
            response = await self._gateway.send_telegram(telegram)
            _LOGGER.debug(f"Получен ответ от {self._subnet_id}.{self._device_id}: {response}")
            
            if response and isinstance(response, dict) and "data" in response and response["data"]:
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
                    
                    _LOGGER.debug(f"Климат-контроль {self._subnet_id}.{self._device_id}: " +
                                  f"тип={temperature_type}, текущая={current_temp}°C, статус={status}, " +
                                  f"режим={mode}, уставка_обычная={normal_temp}°C, уставка_день={day_temp}°C, " +
                                  f"уставка_ночь={night_temp}°C, уставка_отсутствие={away_temp}°C")
                    
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
                    # При недостаточном количестве данных не меняем статус доступности
                    _LOGGER.warning(f"Получен неполный ответ от устройства климат-контроля {self._subnet_id}.{self._device_id}: {data}")
            else:
                # Если устройство доступно, но ответ пустой, сохраняем текущее состояние устройства
                # и не меняем доступность
                if self._available:
                    _LOGGER.debug(f"Устройство климат-контроля {self._subnet_id}.{self._device_id} не вернуло данных, используем предыдущее состояние")
                else:
                    _LOGGER.warning(f"Не удалось получить данные от устройства климат-контроля {self._subnet_id}.{self._device_id}")
                    # Устанавливаем по умолчанию статус доступности только при первом запуске
                    # при отсутствии данных
                    if self._current_temperature is None:
                        self._available = False
            
        except Exception as err:
            _LOGGER.error(f"Ошибка при обновлении состояния устройства климат-контроля {self._subnet_id}.{self._device_id}: {err}")
            # Не меняем доступность, если произошла временная ошибка
            # Это позволит избежать мигания устройства в интерфейсе
            if self._current_temperature is None:
                self._available = False


class BusproAirConditioner(ClimateEntity):
    """Представление модуля управления кондиционером HDL Buspro MAC01.431."""

    def __init__(
        self,
        gateway,
        subnet_id: int,
        device_id: int,
        name: str,
    ):
        """Инициализация модуля управления кондиционером."""
        self._gateway = gateway
        self._subnet_id = subnet_id
        self._device_id = device_id
        self._attr_name = f"{name} (AC)"
        self._attr_unique_id = f"ac_{subnet_id}_{device_id}"
        
        # Состояние устройства
        self._hvac_mode = HVACMode.OFF
        self._hvac_action = HVACAction.IDLE
        self._target_temperature = 24.0
        self._current_temperature = None
        self._fan_mode = None
        
        # Поддерживаемые режимы HVAC
        self._attr_hvac_modes = [
            HVACMode.OFF, 
            HVACMode.HEAT, 
            HVACMode.COOL, 
            HVACMode.AUTO,
            HVACMode.FAN_ONLY,
            HVACMode.DRY
        ]
        
        # Поддерживаемые режимы вентилятора
        self._attr_fan_modes = [
            "auto", "low", "medium", "high"
        ]
        
        # Настройка поддерживаемых функций
        self._attr_supported_features = (
            ClimateEntityFeature.TARGET_TEMPERATURE |
            ClimateEntityFeature.FAN_MODE
        )
        
        # Настройки температуры
        self._attr_temperature_unit = UnitOfTemperature.CELSIUS
        self._attr_min_temp = 16
        self._attr_max_temp = 30
        self._attr_target_temperature_step = 1.0
        
        # Доступность устройства
        self._available = True
        
        _LOGGER.info(f"Инициализирован модуль управления кондиционером: {name} ({subnet_id}.{device_id})")
        
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
    def fan_mode(self) -> Optional[str]:
        """Return the fan setting."""
        return self._fan_mode
        
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

        # Проверяем ограничения температуры
        if temperature < self._attr_min_temp:
            temperature = self._attr_min_temp
        elif temperature > self._attr_max_temp:
            temperature = self._attr_max_temp

        self._target_temperature = temperature
        
        # Отправляем команду на устройство
        # Для MAC01.431 используем специальную команду управления кондиционером
        try:
            # Код операции для управления кондиционером
            operation_code = 0x1947  # Примерный код, нужно проверить документацию
            
            # Данные команды включают температуру и текущий режим
            # [целевая_температура, режим]
            data = [int(self._target_temperature), self._get_hvac_mode_code()]
            
            _LOGGER.debug(f"Отправка команды установки температуры для MAC01.431: {data}")
            
            response = await self._gateway.send_message(
                [self._subnet_id, self._device_id, 0, 0],  # target_address
                [operation_code >> 8, operation_code & 0xFF],  # operation_code
                data,  # data
            )
            
            self.async_write_ha_state()
            
        except Exception as e:
            _LOGGER.error(f"Ошибка при установке температуры для MAC01.431: {e}")
    
    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set HVAC mode."""
        if hvac_mode not in self._attr_hvac_modes:
            _LOGGER.warning(f"Неподдерживаемый режим HVAC: {hvac_mode}")
            return
            
        self._hvac_mode = hvac_mode
        
        # Обновляем текущее действие
        if hvac_mode == HVACMode.OFF:
            self._hvac_action = HVACAction.OFF
        elif hvac_mode == HVACMode.HEAT:
            self._hvac_action = HVACAction.HEATING
        elif hvac_mode == HVACMode.COOL:
            self._hvac_action = HVACAction.COOLING
        elif hvac_mode == HVACMode.FAN_ONLY:
            self._hvac_action = HVACAction.FAN
        elif hvac_mode == HVACMode.DRY:
            self._hvac_action = HVACAction.DRYING
        elif hvac_mode == HVACMode.AUTO:
            # В автоматическом режиме действие зависит от текущей и целевой температуры
            if self._current_temperature and self._target_temperature:
                if self._current_temperature < self._target_temperature:
                    self._hvac_action = HVACAction.HEATING
                elif self._current_temperature > self._target_temperature:
                    self._hvac_action = HVACAction.COOLING
                else:
                    self._hvac_action = HVACAction.IDLE
            else:
                self._hvac_action = HVACAction.IDLE
        
        # Отправляем команду на устройство
        try:
            # Код операции для управления режимом
            operation_code = 0x1946  # Примерный код, нужно проверить документацию
            
            # Данные команды: [режим, вкл/выкл]
            mode_code = self._get_hvac_mode_code()
            power = 1 if hvac_mode != HVACMode.OFF else 0
            data = [mode_code, power]
            
            _LOGGER.debug(f"Отправка команды установки режима для MAC01.431: {data}")
            
            response = await self._gateway.send_message(
                [self._subnet_id, self._device_id, 0, 0],  # target_address
                [operation_code >> 8, operation_code & 0xFF],  # operation_code
                data,  # data
            )
            
            self.async_write_ha_state()
            
        except Exception as e:
            _LOGGER.error(f"Ошибка при установке режима HVAC для MAC01.431: {e}")
    
    async def async_set_fan_mode(self, fan_mode: str) -> None:
        """Set fan mode."""
        if fan_mode not in self._attr_fan_modes:
            _LOGGER.warning(f"Неподдерживаемый режим вентилятора: {fan_mode}")
            return
            
        self._fan_mode = fan_mode
        
        # Отправляем команду на устройство
        try:
            # Код операции для управления вентилятором
            operation_code = 0x1948  # Примерный код, нужно проверить документацию
            
            # Данные команды: [режим_вентилятора]
            fan_mode_code = self._get_fan_mode_code(fan_mode)
            data = [fan_mode_code]
            
            _LOGGER.debug(f"Отправка команды установки режима вентилятора для MAC01.431: {data}")
            
            response = await self._gateway.send_message(
                [self._subnet_id, self._device_id, 0, 0],  # target_address
                [operation_code >> 8, operation_code & 0xFF],  # operation_code
                data,  # data
            )
            
            self.async_write_ha_state()
            
        except Exception as e:
            _LOGGER.error(f"Ошибка при установке режима вентилятора для MAC01.431: {e}")
    
    async def async_update(self) -> None:
        """Retrieve latest state from the device."""
        try:
            # Код операции для запроса статуса кондиционера
            operation_code = 0x1945  # Примерный код, нужно проверить документацию
            
            _LOGGER.debug(f"Запрос статуса кондиционера MAC01.431: {self._subnet_id}.{self._device_id}")
            
            response = await self._gateway.send_message(
                [self._subnet_id, self._device_id, 0, 0],  # target_address
                [operation_code >> 8, operation_code & 0xFF],  # operation_code
                [],  # data
            )
            
            # Обрабатываем ответ, если получили данные
            if response and isinstance(response, dict) and "data" in response:
                # Пример: data = [power, mode, fan_speed, current_temp, target_temp]
                data = response["data"]
                
                if len(data) >= 5:
                    power = data[0]
                    mode_code = data[1]
                    fan_speed_code = data[2]
                    current_temp = data[3]
                    target_temp = data[4]
                    
                    # Обновляем состояние
                    if power == 0:
                        self._hvac_mode = HVACMode.OFF
                        self._hvac_action = HVACAction.OFF
                    else:
                        # Устанавливаем режим на основе кода
                        self._hvac_mode = self._get_hvac_mode_from_code(mode_code)
                        
                        # Устанавливаем действие на основе режима
                        if self._hvac_mode == HVACMode.HEAT:
                            self._hvac_action = HVACAction.HEATING
                        elif self._hvac_mode == HVACMode.COOL:
                            self._hvac_action = HVACAction.COOLING
                        elif self._hvac_mode == HVACMode.FAN_ONLY:
                            self._hvac_action = HVACAction.FAN
                        elif self._hvac_mode == HVACMode.DRY:
                            self._hvac_action = HVACAction.DRYING
                        else:
                            self._hvac_action = HVACAction.IDLE
                    
                    # Обновляем режим вентилятора
                    self._fan_mode = self._get_fan_mode_from_code(fan_speed_code)
                    
                    # Обновляем температуры
                    self._current_temperature = float(current_temp)
                    self._target_temperature = float(target_temp)
                    
                    self._available = True
                else:
                    _LOGGER.warning(f"Недостаточно данных в ответе от MAC01.431: {data}")
            else:
                _LOGGER.warning(f"Не удалось получить данные от MAC01.431: {response}")
                self._available = False
            
        except Exception as e:
            _LOGGER.error(f"Ошибка при обновлении состояния MAC01.431: {e}")
            self._available = False
        
        self.async_write_ha_state()
    
    def _get_hvac_mode_code(self) -> int:
        """Получить код режима HVAC для отправки на устройство."""
        if self._hvac_mode == HVACMode.HEAT:
            return 1
        elif self._hvac_mode == HVACMode.COOL:
            return 2
        elif self._hvac_mode == HVACMode.AUTO:
            return 3
        elif self._hvac_mode == HVACMode.DRY:
            return 4
        elif self._hvac_mode == HVACMode.FAN_ONLY:
            return 5
        return 0  # Выключено
    
    def _get_hvac_mode_from_code(self, code: int) -> HVACMode:
        """Получить режим HVAC из кода устройства."""
        if code == 1:
            return HVACMode.HEAT
        elif code == 2:
            return HVACMode.COOL
        elif code == 3:
            return HVACMode.AUTO
        elif code == 4:
            return HVACMode.DRY
        elif code == 5:
            return HVACMode.FAN_ONLY
        return HVACMode.OFF
    
    def _get_fan_mode_code(self, fan_mode: str) -> int:
        """Получить код режима вентилятора для отправки на устройство."""
        if fan_mode == "auto":
            return 0
        elif fan_mode == "low":
            return 1
        elif fan_mode == "medium":
            return 2
        elif fan_mode == "high":
            return 3
        return 0  # Auto by default
    
    def _get_fan_mode_from_code(self, code: int) -> str:
        """Получить режим вентилятора из кода устройства."""
        if code == 1:
            return "low"
        elif code == 2:
            return "medium"
        elif code == 3:
            return "high"
        return "auto"
