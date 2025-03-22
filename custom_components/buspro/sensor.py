"""
This component provides sensor support for Buspro.

For more details about this platform, please refer to the documentation at
https://home-assistant.io/components/...
"""

import logging
from datetime import timedelta
from typing import Any, Optional

import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from homeassistant.components.sensor import PLATFORM_SCHEMA, SensorEntity, SensorDeviceClass, SensorStateClass
from homeassistant.const import (
    CONF_NAME, 
    CONF_DEVICES, 
    CONF_ADDRESS, 
    CONF_TYPE, 
    CONF_UNIT_OF_MEASUREMENT,
    ILLUMINANCE, 
    TEMPERATURE, 
    CONF_DEVICE_CLASS, 
    CONF_SCAN_INTERVAL,
    UnitOfTemperature,
    PERCENTAGE,
    LIGHT_LUX,
)
from homeassistant.core import callback, HomeAssistant
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.config_entries import ConfigEntry

from ..buspro import DATA_BUSPRO
from .const import DOMAIN, OPERATION_READ_STATUS

DEFAULT_CONF_UNIT_OF_MEASUREMENT = ""
DEFAULT_CONF_DEVICE_CLASS = "None"
DEFAULT_CONF_SCAN_INTERVAL = 0
DEFAULT_CONF_OFFSET = 0
CONF_DEVICE = "device"
CONF_OFFSET = "offset"
SCAN_INTERVAL = timedelta(minutes=2)

_LOGGER = logging.getLogger(__name__)

# HDL Buspro sensor types and their corresponding HA configurations
SENSOR_TYPES = {
    0x01: {
        "name": "Temperature",
        "device_class": SensorDeviceClass.TEMPERATURE,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": UnitOfTemperature.CELSIUS,
        "multiplier": 0.1,  # HDL sends temperature * 10
    },
    0x02: {
        "name": "Humidity",
        "device_class": SensorDeviceClass.HUMIDITY,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": PERCENTAGE,
        "multiplier": 1,
    },
    0x03: {
        "name": "Light Level",
        "device_class": SensorDeviceClass.ILLUMINANCE,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": LIGHT_LUX,
        "multiplier": 1,
    },
}

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Required(CONF_DEVICES):
        vol.All(cv.ensure_list, [
            vol.All({
                vol.Required(CONF_ADDRESS): cv.string,
                vol.Required(CONF_NAME): cv.string,
                vol.Required(CONF_TYPE): vol.In(SENSOR_TYPES),
                vol.Optional(CONF_UNIT_OF_MEASUREMENT, default=DEFAULT_CONF_UNIT_OF_MEASUREMENT): cv.string,
                vol.Optional(CONF_DEVICE_CLASS, default=DEFAULT_CONF_DEVICE_CLASS): cv.string,
                vol.Optional(CONF_DEVICE, default=None): cv.string,
                vol.Optional(CONF_SCAN_INTERVAL, default=DEFAULT_CONF_SCAN_INTERVAL): cv.string,
                vol.Optional(CONF_OFFSET, default=DEFAULT_CONF_OFFSET): cv.string,
            })
        ])
})


# noinspection PyUnusedLocal
async def async_setup_platform(hass, config, async_add_entites, discovery_info=None):
    """Set up Buspro switch devices."""
    # noinspection PyUnresolvedReferences
    from .pybuspro.devices import Sensor

    hdl = hass.data[DATA_BUSPRO].hdl
    devices = []

    for device_config in config[CONF_DEVICES]:
        address = device_config[CONF_ADDRESS]
        name = device_config[CONF_NAME]
        sensor_type = device_config[CONF_TYPE]
        device = device_config[CONF_DEVICE]
        offset = device_config[CONF_OFFSET]
        
        scan_interval = device_config[CONF_SCAN_INTERVAL]
        interval = 0
        if scan_interval is not None:
            interval = int(scan_interval)
            
        address2 = address.split('.')
        device_address = (int(address2[0]), int(address2[1]))

        _LOGGER.debug("Adding sensor '{}' with address {}, sensor type '{}'".format(
            name, device_address, sensor_type))

        sensor = Sensor(hdl, device_address, device=device, name=name)

        devices.append(BusproSensor(hass, sensor, sensor_type, interval, offset))

    async_add_entites(devices)


# noinspection PyAbstractClass
class BusproSensor(SensorEntity):
    """Representation of a HDL Buspro Sensor."""

    def __init__(
        self,
        hass: HomeAssistant,
        device,
        sensor_type: int,
        scan_interval: int,
        offset: int,
    ):
        """Initialize the sensor."""
        self._hass = hass
        self._device = device
        self._sensor_type = sensor_type
        self._offset = offset
        self._available = True
        self._state = None

        # Set entity properties from config
        self._attr_device_class = SENSOR_TYPES[sensor_type]["device_class"]
        self._attr_state_class = SENSOR_TYPES[sensor_type]["state_class"]
        self._attr_native_unit_of_measurement = SENSOR_TYPES[sensor_type]["unit"]

        self._should_poll = False
        if scan_interval > 0:
            self._should_poll = True

    @callback
    def async_register_callbacks(self):
        """Register callbacks to update hass after device was changed."""

        # noinspection PyUnusedLocal
        async def after_update_callback(device):
            """Call after device was updated."""
            if self._hass is not None:
                self._state = self._device.temperature
                self._available = True
                self.async_write_ha_state()

        self._device.register_device_updated_cb(after_update_callback)

    @property
    def should_poll(self):
        """No polling needed within Buspro unless explicitly set."""
        return self._should_poll

    async def async_update(self):
        await self._device.read_sensor_status()

    @property
    def name(self):
        """Return the display name of this sensor."""
        return self._device.name

    @property
    def available(self):
        """Return True if entity is available."""
        connected = self._hass.data[DATA_BUSPRO].connected
        return connected and self._state is not None

    @property
    def native_value(self):
        """Return the state of the sensor."""
        if self._state is None:
            return None

        state = self._state
        if self._offset is not None and state != 0:
            state = state + int(self._offset)

        return state

    @property
    def device_class(self):
        """Return the class of this sensor."""
        return self._attr_device_class

    @property
    def state_class(self):
        """Return the state class of this sensor."""
        return self._attr_state_class

    @property
    def unit_of_measurement(self):
        """Return the unit this state is expressed in."""
        return self._attr_native_unit_of_measurement

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        attributes = {}
        attributes['state_class'] = self.state_class
        return attributes

    @property
    def unique_id(self):
        """Return the unique id."""
        return f"{self._device.device_identifier}-{self._sensor_type}"

async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the HDL Buspro sensor platform."""
    gateway = hass.data[DOMAIN][config_entry.entry_id]["gateway"]
    devices = hass.data[DOMAIN][config_entry.entry_id]["devices"]
    
    entities = []
    
    # Add all discovered sensor devices
    for device in devices.get("sensor", []):
        # Each sensor device might have multiple sensor types
        for sensor_type, config in SENSOR_TYPES.items():
            entities.append(
                BusproSensor(
                    gateway,
                    device["subnet_id"],
                    device["device_id"],
                    f"{device['name']} {config['name']}",
                    sensor_type,
                    config,
                )
            )
    
    async_add_entities(entities)

class BusproSensor(SensorEntity):
    """Representation of a HDL Buspro Sensor."""

    def __init__(
        self,
        gateway,
        subnet_id: int,
        device_id: int,
        name: str,
        sensor_type: int,
        config: dict,
    ):
        """Initialize the sensor."""
        self._gateway = gateway
        self._subnet_id = subnet_id
        self._device_id = device_id
        self._name = name
        self._sensor_type = sensor_type
        self._config = config
        self._available = True
        self._state = None

        # Set entity properties from config
        self._attr_device_class = config["device_class"]
        self._attr_state_class = config["state_class"]
        self._attr_native_unit_of_measurement = config["unit"]

    @property
    def should_poll(self) -> bool:
        """No polling needed within Buspro."""
        return False

    @property
    def name(self) -> str:
        """Return the display name of this sensor."""
        return self._name

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return self._available

    @property
    def native_value(self) -> Optional[float]:
        """Return the state of the sensor."""
        return self._state

    async def async_update(self) -> None:
        """Fetch new state data for this sensor."""
        try:
            response = await self._gateway.send_message(
                [self._subnet_id, self._device_id],
                [OPERATION_READ_STATUS],
                [self._sensor_type]
            )
            
            if response:
                # Apply multiplier to convert raw value to actual value
                self._state = response[0] * self._config["multiplier"]
                self._available = True
        except Exception as err:
            _LOGGER.error("Error updating sensor state: %s", err)
            self._available = False

    @property
    def unique_id(self) -> str:
        """Return a unique ID."""
        return f"sensor_{self._subnet_id}_{self._device_id}_{self._sensor_type}"