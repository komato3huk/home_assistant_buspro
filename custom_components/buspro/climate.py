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

# Константы для режимов вентилятора
FAN_MODE_AUTO = "auto"
FAN_MODE_LOW = "low"
FAN_MODE_MEDIUM = "medium"
FAN_MODE_HIGH = "high"

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
    """Set up the HDL Buspro climate platform."""
    gateway = hass.data[DOMAIN][config_entry.entry_id]["gateway"]
    discovery = hass.data[DOMAIN][config_entry.entry_id]["discovery"]

    entities = []

    # Получаем устройства климат-контроля из обнаруженных устройств
    for device in discovery.get_devices_by_type(CLIMATE):
        subnet_id = device["subnet_id"]
        device_id = device["device_id"]
        name = device.get("name", f"Climate {subnet_id}.{device_id}")
        model = device.get("model", "HDL-MAC01.431")  # По умолчанию считаем модель кондиционера
        
        _LOGGER.info(f"Обнаружено климатическое устройство: {name} ({subnet_id}.{device_id}), модель: {model}")
        
        # Создаем сущность climate
        entity = BusproClimate(
            gateway,
            subnet_id,
            device_id,
            name,
            model,
            device.get("features", ["temperature", "fan_speed", "mode"])
        )
        entities.append(entity)
        
        _LOGGER.debug(f"Добавлено климатическое устройство: {name} ({subnet_id}.{device_id})")

    if entities:
        async_add_entities(entities)
        _LOGGER.info(f"Добавлено {len(entities)} климатических устройств HDL Buspro")
    else:
        _LOGGER.warning("Не найдено ни одного климатического устройства HDL Buspro")


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
        model: str = "Unknown",
        features: List[str] = ["temperature"],
    ):
        """Initialize the climate device."""
        self.gateway = gateway
        self.subnet_id = subnet_id
        self.device_id = device_id
        self._name = name
        self._model = model
        self._features = features
        
        # Состояния
        self._hvac_mode = HVACMode.OFF
        self._fan_mode = FAN_MODE_MEDIUM
        self._temperature = 20
        self._target_temp = 20
        self._current_operation = HVACAction.IDLE
        self._available = True
        self._attr_temperature_unit = UnitOfTemperature.CELSIUS
        
        _LOGGER.info(f"Инициализирован климатический контроллер: {name} ({subnet_id}.{device_id}), модель: {model}")
        
    async def async_added_to_hass(self):
        """Register callbacks when entity is added to Home Assistant."""
        try:
            # Получаем текущее состояние устройства
            await self.async_update()
            _LOGGER.debug(f"Успешно получено состояние для {self._name}")
        except Exception as e:
            _LOGGER.error(f"Ошибка при добавлении {self._name} в Home Assistant: {e}")
            
    @property
    def supported_features(self) -> int:
        """Return the list of supported features."""
        features = 0
        
        if "temperature" in self._features:
            features |= ClimateEntityFeature.TARGET_TEMPERATURE
            
        if "fan_speed" in self._features:
            features |= ClimateEntityFeature.FAN_MODE
            
        if "preset" in self._features:
            features |= ClimateEntityFeature.PRESET_MODE
            
        if "swing" in self._features:
            features |= ClimateEntityFeature.SWING_MODE
            
        return features
        
    @property
    def name(self) -> str:
        """Return the name of the climate device."""
        return self._name

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
        return self._current_operation

    @property
    def fan_mode(self) -> HVACMode:
        """Return the fan setting."""
        return self._fan_mode

    @property
    def current_temperature(self) -> Optional[float]:
        """Return the current temperature."""
        return self._temperature

    @property
    def target_temperature(self) -> Optional[float]:
        """Return the temperature we try to reach."""
        return self._target_temp
        
    async def async_set_temperature(self, **kwargs) -> None:
        """Set new target temperature."""
        temperature = kwargs.get(ATTR_TEMPERATURE)
        if temperature is None:
            return
            
        self._target_temp = temperature
        
        # Отправляем команду на устройство
        try:
            # Преобразуем температуру в формат устройства (умножаем на 10 для работы с десятыми долями)
            temp_value = int(temperature * 10)
            
            # Создаем телеграмму для установки температуры
            telegram = {
                "subnet_id": self.subnet_id,
                "device_id": self.device_id,
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
            await self.gateway.send_telegram(telegram)
            _LOGGER.debug(f"Установлена целевая температура {temperature}°C для устройства {self.subnet_id}.{self.device_id}")
            
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
                "subnet_id": self.subnet_id,
                "device_id": self.device_id,
                "operate_code": OPERATE_CODES["control_floor_heating"],
                "data": [
                    1,  # temperature_type (Celsius)
                    0,  # current_temperature (не меняется при установке)
                    status,  # status (on/off)
                    1,  # mode (Normal)
                    int(self._target_temp * 10),  # normal_temperature
                    240,  # day_temperature (24.0°C, не меняется)
                    180,  # night_temperature (18.0°C, не меняется)
                    150,  # away_temperature (15.0°C, не меняется)
                ],
            }
            
            # Отправляем команду через шлюз
            await self.gateway.send_telegram(telegram)
            _LOGGER.debug(f"Установлен режим HVAC {hvac_mode} для устройства {self.subnet_id}.{self.device_id}")
            
            # Обновляем состояние после отправки команды
            await self.async_update()
            
        except Exception as err:
            _LOGGER.error(f"Ошибка при установке режима HVAC: {err}")
            
    async def async_set_fan_mode(self, fan_mode: str) -> None:
        """Set fan mode."""
        if fan_mode not in [FAN_MODE_AUTO, FAN_MODE_LOW, FAN_MODE_MEDIUM, FAN_MODE_HIGH]:
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
            
            response = await self.gateway.send_message(
                [self.subnet_id, self.device_id, 0, 0],  # target_address
                [operation_code >> 8, operation_code & 0xFF],  # operation_code
                data,  # data
            )
            
            self.async_write_ha_state()
        except Exception as e:
            _LOGGER.error(f"Ошибка при установке режима вентилятора для MAC01.431: {e}")
    
    async def async_update(self) -> None:
        """Update the climate device."""
        try:
            # Получаем текущее состояние климатического устройства
            _LOGGER.debug(f"Обновление состояния климатического устройства: {self.name}")
            
            # Отправляем запрос на получение состояния устройства
            # Код операции 0x0032 - запрос состояния
            response = await self.gateway.send_telegram(
                self.subnet_id, 
                self.device_id,
                0x0032,  # Код операции для запроса состояния
                [0x01]   # Запрос данных о текущем состоянии
            )
            
            if not response:
                _LOGGER.warning(f"Не получен ответ при запросе состояния климатического устройства: {self.name}")
                return
                
            # В реальном устройстве здесь должна быть обработка ответа от устройства
            # Для примера устанавливаем фиксированные значения
            self._temperature = 22.5
            self._target_temp = 23.0
            self._hvac_mode = HVACMode.HEAT
            self._current_operation = HVACAction.HEATING
            
        except Exception as exc:
            _LOGGER.error(f"Ошибка при обновлении климатического устройства {self.name}: {exc}")
            import traceback
            _LOGGER.error(traceback.format_exc())

    def _get_fan_mode_code(self, fan_mode: str) -> int:
        """Получить код режима вентилятора для отправки на устройство."""
        if fan_mode == FAN_MODE_AUTO:
            return 0
        elif fan_mode == FAN_MODE_LOW:
            return 1
        elif fan_mode == FAN_MODE_MEDIUM:
            return 2
        elif fan_mode == FAN_MODE_HIGH:
            return 3
        return 0  # Auto by default


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
