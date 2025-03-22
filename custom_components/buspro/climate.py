"""Platform for HDL Buspro climate integration."""
import logging
from typing import Any, List, Optional

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACMode,
    HVACAction,
)
from homeassistant.components.climate.const import (
    ATTR_HVAC_MODE,
    ATTR_TARGET_TEMP_HIGH,
    ATTR_TARGET_TEMP_LOW,
)
from homeassistant.const import (
    ATTR_TEMPERATURE,
    UnitOfTemperature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, OPERATION_SINGLE_CHANNEL, OPERATION_READ_STATUS

_LOGGER = logging.getLogger(__name__)

# HDL Buspro specific HVAC modes
HVAC_MODES = {
    0: HVACMode.OFF,
    1: HVACMode.HEAT,
    2: HVACMode.COOL,
    3: HVACMode.AUTO,
    4: HVACMode.FAN_ONLY,
    5: HVACMode.DRY,
}

HVAC_ACTIONS = {
    0: HVACAction.OFF,
    1: HVACAction.HEATING,
    2: HVACAction.COOLING,
    3: HVACAction.IDLE,
    4: HVACAction.FAN,
    5: HVACAction.DRYING,
}

async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the HDL Buspro climate platform."""
    gateway = hass.data[DOMAIN][config_entry.entry_id]["gateway"]
    devices = hass.data[DOMAIN][config_entry.entry_id]["devices"]
    
    entities = []
    
    # Add all discovered climate devices
    for device in devices.get("climate", []):
        entities.append(
            BusproClimate(
                gateway,
                device["subnet_id"],
                device["device_id"],
                device["name"],
            )
        )
    
    async_add_entities(entities)

class BusproClimate(ClimateEntity):
    """Representation of a HDL Buspro Climate device."""

    def __init__(self, gateway, subnet_id: int, device_id: int, name: str):
        """Initialize the climate device."""
        self._gateway = gateway
        self._subnet_id = subnet_id
        self._device_id = device_id
        self._name = name
        self._available = True
        
        # State
        self._hvac_mode = None
        self._hvac_action = None
        self._target_temperature = None
        self._current_temperature = None
        self._fan_mode = None
        self._attr_target_temperature_high = None
        self._attr_target_temperature_low = None
        
        # Default values
        self._min_temp = 16
        self._max_temp = 30
        self._target_temperature_step = 0.5

    @property
    def should_poll(self) -> bool:
        """No polling needed within Buspro."""
        return False

    @property
    def name(self) -> str:
        """Return the display name of this climate device."""
        return self._name

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return self._available

    @property
    def temperature_unit(self) -> str:
        """Return the unit of measurement."""
        return UnitOfTemperature.CELSIUS

    @property
    def current_temperature(self) -> Optional[float]:
        """Return the current temperature."""
        return self._current_temperature

    @property
    def target_temperature(self) -> Optional[float]:
        """Return the temperature we try to reach."""
        return self._target_temperature

    @property
    def target_temperature_high(self) -> Optional[float]:
        """Return the upper bound target temperature we try to reach."""
        return self._attr_target_temperature_high

    @property
    def target_temperature_low(self) -> Optional[float]:
        """Return the lower bound target temperature we try to reach."""
        return self._attr_target_temperature_low

    @property
    def target_temperature_step(self) -> float:
        """Return the supported step of target temperature."""
        return self._target_temperature_step

    @property
    def min_temp(self) -> float:
        """Return the minimum temperature."""
        return self._min_temp

    @property
    def max_temp(self) -> float:
        """Return the maximum temperature."""
        return self._max_temp

    @property
    def hvac_mode(self) -> Optional[str]:
        """Return hvac operation ie. heat, cool mode."""
        return self._hvac_mode

    @property
    def hvac_modes(self) -> List[str]:
        """Return the list of available hvac operation modes."""
        return list(set(HVAC_MODES.values()))

    @property
    def hvac_action(self) -> Optional[str]:
        """Return the current running hvac operation."""
        return self._hvac_action

    @property
    def supported_features(self) -> int:
        """Return the list of supported features."""
        return (
            ClimateEntityFeature.TARGET_TEMPERATURE |
            ClimateEntityFeature.TARGET_TEMPERATURE_RANGE
        )

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set new target temperature."""
        if ATTR_TEMPERATURE in kwargs:
            temperature = kwargs[ATTR_TEMPERATURE]
            await self._gateway.send_message(
                [self._subnet_id, self._device_id],
                [OPERATION_SINGLE_CHANNEL],
                [1, int(temperature * 10)]  # Temperature is sent as integer (multiplied by 10)
            )
            self._target_temperature = temperature
            self.async_write_ha_state()
        elif ATTR_TARGET_TEMP_HIGH in kwargs or ATTR_TARGET_TEMP_LOW in kwargs:
            high = kwargs.get(ATTR_TARGET_TEMP_HIGH)
            low = kwargs.get(ATTR_TARGET_TEMP_LOW)
            
            # Update the target temperature range
            if high is not None:
                self._attr_target_temperature_high = high
            if low is not None:
                self._attr_target_temperature_low = low
                
            # Send the average as the target temperature to the device
            if high is not None and low is not None:
                avg_temp = (high + low) / 2
                await self._gateway.send_message(
                    [self._subnet_id, self._device_id],
                    [OPERATION_SINGLE_CHANNEL],
                    [1, int(avg_temp * 10)]
                )
            
            self.async_write_ha_state()

    async def async_set_hvac_mode(self, hvac_mode: str) -> None:
        """Set new target hvac mode."""
        # Find HDL mode number from HA hvac_mode
        hdl_mode = next(
            (k for k, v in HVAC_MODES.items() if v == hvac_mode),
            None
        )
        if hdl_mode is not None:
            await self._gateway.send_message(
                [self._subnet_id, self._device_id],
                [OPERATION_SINGLE_CHANNEL],
                [2, hdl_mode]  # Channel 2 for mode
            )
            self._hvac_mode = hvac_mode
            self.async_write_ha_state()

    async def async_turn_off(self) -> None:
        """Turn off the climate device."""
        await self.async_set_hvac_mode(HVACMode.OFF)

    async def async_turn_on(self) -> None:
        """Turn on the climate device."""
        await self.async_set_hvac_mode(HVACMode.HEAT)

    async def async_update(self) -> None:
        """Fetch new state data for this climate device."""
        try:
            # Get temperature
            temp_response = await self._gateway.send_message(
                [self._subnet_id, self._device_id],
                [OPERATION_READ_STATUS],
                [1]  # Channel 1 for temperature
            )
            
            # Get mode
            mode_response = await self._gateway.send_message(
                [self._subnet_id, self._device_id],
                [OPERATION_READ_STATUS],
                [2]  # Channel 2 for mode
            )
            
            if temp_response and mode_response:
                # Temperature comes as integer (multiplied by 10)
                self._current_temperature = temp_response[0] / 10
                self._target_temperature = temp_response[1] / 10 if len(temp_response) > 1 else None
                
                # Set temperature range if target temperature is available
                if self._target_temperature is not None:
                    self._attr_target_temperature_high = self._target_temperature + 1
                    self._attr_target_temperature_low = self._target_temperature - 1
                
                # Update mode and action
                hdl_mode = mode_response[0]
                self._hvac_mode = HVAC_MODES.get(hdl_mode)
                self._hvac_action = HVAC_ACTIONS.get(hdl_mode)
                
                self._available = True
        except Exception as err:
            _LOGGER.error("Error updating climate state: %s", err)
            self._available = False
        finally:
            self.async_write_ha_state()

    @property
    def unique_id(self) -> str:
        """Return a unique ID."""
        return f"climate_{self._subnet_id}_{self._device_id}"
        
    @property
    def entity_id(self) -> str:
        """Return the entity ID for this climate device."""
        return f"climate.climate_{self._subnet_id}_{self._device_id}"
