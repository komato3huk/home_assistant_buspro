"""
Support for Buspro devices.

For more details about this component, please refer to the documentation at
https://home-assistant.io/...
"""

import logging
import asyncio
from typing import Dict, List, Optional

import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from homeassistant.const import (
    CONF_HOST, 
    CONF_PORT, 
    CONF_NAME,
    CONF_TIMEOUT,
    Platform,
)
from homeassistant.const import (
    EVENT_HOMEASSISTANT_STOP,
)
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry

from .const import (
    DOMAIN,
    DEFAULT_PORT,
    DEFAULT_TIMEOUT,
    DEFAULT_POLL_INTERVAL,
    DEFAULT_DEVICE_SUBNET_ID,
    DEFAULT_DEVICE_ID,
    CONF_DEVICE_SUBNET_ID,
    CONF_DEVICE_ID,
    CONF_POLL_INTERVAL,
    CONF_GATEWAY_HOST,
    CONF_GATEWAY_PORT,
    DEFAULT_GATEWAY_HOST,
    DEFAULT_GATEWAY_PORT,
)
from .discovery import BusproDiscovery
from .gateway import BusproGateway
from .pybuspro.core.hdl_device import HDLDevice

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [
    Platform.LIGHT,
    Platform.COVER,
    Platform.CLIMATE,
    Platform.SENSOR,
]

DEFAULT_CONF_NAME = ""

DEFAULT_SCENE_NAME = "BUSPRO SCENE"
DEFAULT_SEND_MESSAGE_NAME = "BUSPRO MESSAGE"

SERVICE_BUSPRO_SEND_MESSAGE = "send_message"
SERVICE_BUSPRO_ACTIVATE_SCENE = "activate_scene"
SERVICE_BUSPRO_UNIVERSAL_SWITCH = "set_universal_switch"

SERVICE_BUSPRO_ATTR_OPERATE_CODE = "operate_code"
SERVICE_BUSPRO_ATTR_ADDRESS = "address"
SERVICE_BUSPRO_ATTR_PAYLOAD = "payload"
SERVICE_BUSPRO_ATTR_SCENE_ADDRESS = "scene_address"
SERVICE_BUSPRO_ATTR_SWITCH_NUMBER = "switch_number"
SERVICE_BUSPRO_ATTR_STATUS = "status"

"""{ "address": [1,74], "scene_address": [3,5] }"""
SERVICE_BUSPRO_ACTIVATE_SCENE_SCHEMA = vol.Schema({
    vol.Required(SERVICE_BUSPRO_ATTR_ADDRESS): vol.Any([cv.positive_int]),
    vol.Required(SERVICE_BUSPRO_ATTR_SCENE_ADDRESS): vol.Any([cv.positive_int]),
})

"""{ "address": [1,74], "operate_code": [4,12], "payload": [1,75,0,3] }"""
SERVICE_BUSPRO_SEND_MESSAGE_SCHEMA = vol.Schema({
    vol.Required(SERVICE_BUSPRO_ATTR_ADDRESS): vol.Any([cv.positive_int]),
    vol.Required(SERVICE_BUSPRO_ATTR_OPERATE_CODE): vol.Any([cv.positive_int]),
    vol.Required(SERVICE_BUSPRO_ATTR_PAYLOAD): vol.Any([cv.positive_int]),
})

"""{ "address": [1,100], "switch_number": 100, "status": 1 }"""
SERVICE_BUSPRO_UNIVERSAL_SWITCH_SCHEMA = vol.Schema({
    vol.Required(SERVICE_BUSPRO_ATTR_ADDRESS): vol.Any([cv.positive_int]),
    vol.Required(SERVICE_BUSPRO_ATTR_SWITCH_NUMBER): vol.Any(cv.positive_int),
    vol.Required(SERVICE_BUSPRO_ATTR_STATUS): vol.Any(cv.positive_int),
})

CONFIG_SCHEMA = vol.Schema({
    DOMAIN: vol.Schema({
        vol.Required(CONF_HOST): cv.string,
        vol.Required(CONF_PORT): cv.port,
        vol.Optional(CONF_NAME, default=DEFAULT_CONF_NAME): cv.string,
        vol.Optional(CONF_TIMEOUT, default=DEFAULT_TIMEOUT): cv.positive_int,
        vol.Optional(CONF_DEVICE_SUBNET_ID, default=DEFAULT_DEVICE_SUBNET_ID): cv.positive_int,
        vol.Optional(CONF_DEVICE_ID, default=DEFAULT_DEVICE_ID): cv.positive_int,
        vol.Optional(CONF_POLL_INTERVAL, default=DEFAULT_POLL_INTERVAL): cv.positive_int,
    })
}, extra=vol.ALLOW_EXTRA)

async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the HDL Buspro component."""
    hass.data.setdefault(DOMAIN, {})
    return True

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up HDL Buspro from a config entry."""
    # Create HDL Buspro device
    host = entry.data.get(CONF_HOST)
    port = entry.data.get(CONF_PORT, DEFAULT_PORT)
    timeout = entry.data.get(CONF_TIMEOUT, DEFAULT_TIMEOUT)
    subnet_id = entry.data.get(CONF_DEVICE_SUBNET_ID, DEFAULT_DEVICE_SUBNET_ID)
    device_id = entry.data.get(CONF_DEVICE_ID, DEFAULT_DEVICE_ID)
    poll_interval = entry.data.get(CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL)
    gateway_host = entry.data.get(CONF_GATEWAY_HOST, DEFAULT_GATEWAY_HOST)
    gateway_port = entry.data.get(CONF_GATEWAY_PORT, DEFAULT_GATEWAY_PORT)
    
    # Если шлюз не указан, используем тот же адрес, что и для основного подключения
    if not gateway_host:
        gateway_host = host
    
    # Initialize options if they don't exist yet
    if not entry.options:
        options = {
            CONF_TIMEOUT: timeout,
            CONF_DEVICE_SUBNET_ID: subnet_id,
            CONF_DEVICE_ID: device_id,
            CONF_POLL_INTERVAL: poll_interval,
            CONF_GATEWAY_HOST: gateway_host,
            CONF_GATEWAY_PORT: gateway_port,
        }
        hass.config_entries.async_update_entry(entry, options=options)
    else:
        # Use values from options if set
        timeout = entry.options.get(CONF_TIMEOUT, timeout)
        subnet_id = entry.options.get(CONF_DEVICE_SUBNET_ID, subnet_id)
        device_id = entry.options.get(CONF_DEVICE_ID, device_id)
        poll_interval = entry.options.get(CONF_POLL_INTERVAL, poll_interval)
        gateway_host = entry.options.get(CONF_GATEWAY_HOST, gateway_host)
        gateway_port = entry.options.get(CONF_GATEWAY_PORT, gateway_port)
    
    _LOGGER.debug(
        "Connecting to HDL Buspro at %s:%s with device address %d.%d, gateway: %s:%s",
        host, port, subnet_id, device_id, gateway_host, gateway_port
    )
    
    # Create HDL device with source address
    hdl_device = HDLDevice(
        host, 
        port, 
        subnet_id=subnet_id, 
        device_id=device_id,
        gateway_host=gateway_host,
        gateway_port=gateway_port
    )
    
    # Create discovery service
    discovery = BusproDiscovery(hdl_device)
    
    # Create gateway
    gateway = BusproGateway(hass, hdl_device, discovery, poll_interval)
    
    # Perform initial discovery
    discovered_devices = await discovery.scan_network()
    
    # If no devices were discovered, log warning but continue
    if not discovered_devices:
        _LOGGER.warning("No HDL Buspro devices discovered")
    else:
        _LOGGER.info("Discovered %d HDL Buspro devices", len(discovered_devices))
    
    # Store data in hass
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {
        "gateway": gateway,
        "devices": discovered_devices,
    }
    
    # Initialize gateway
    await gateway.start()
    
    # Set up all platforms
    hass.async_create_task(
        hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    )
    
    # Register services
    # TODO: Add services
    
    # Register update listener for options
    entry.async_on_unload(entry.add_update_listener(async_update_options))
    
    return True

async def async_update_options(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Update options for the HDL Buspro integration."""
    await hass.config_entries.async_reload(entry.entry_id)

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    # Get gateway instance
    gateway = hass.data[DOMAIN][entry.entry_id]["gateway"]
    
    # Stop gateway
    await gateway.stop()
    
    # Unload platforms
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    
    # Remove config entry from hass
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
        
    return unload_ok

class BusproModule:
    """Representation of Buspro Object."""

    def __init__(self, hass, host, port):
        """Initialize of Buspro module."""
        self.hass = hass
        self.connected = False
        self.hdl = None
        self.gateway_address_send_receive = ((host, port), ('', port))
        self.init_hdl()

    def init_hdl(self):
        """Initialize of Buspro object."""
        # noinspection PyUnresolvedReferences
        from .pybuspro.buspro import Buspro
        self.hdl = Buspro(self.gateway_address_send_receive, self.hass.loop)
        # self.hdl.register_telegram_received_all_messages_cb(self.telegram_received_cb)

    async def start(self):
        """Start Buspro object. Connect to tunneling device."""
        await self.hdl.start(state_updater=False)
        self.hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, self.stop)
        self.connected = True

    # noinspection PyUnusedLocal
    async def stop(self, event):
        """Stop Buspro object. Disconnect from tunneling device."""
        await self.hdl.stop()

    async def service_activate_scene(self, call):
        """Service for activatign a __scene"""
        # noinspection PyUnresolvedReferences
        from .pybuspro.devices.scene import Scene

        attr_address = call.data.get(SERVICE_BUSPRO_ATTR_ADDRESS)
        attr_scene_address = call.data.get(SERVICE_BUSPRO_ATTR_SCENE_ADDRESS)
        scene = Scene(self.hdl, attr_address, attr_scene_address, DEFAULT_SCENE_NAME)
        await scene.run()

    async def service_send_message(self, call):
        """Service for send an arbitrary message"""
        # noinspection PyUnresolvedReferences
        from .pybuspro.devices.generic import Generic

        attr_address = call.data.get(SERVICE_BUSPRO_ATTR_ADDRESS)
        attr_payload = call.data.get(SERVICE_BUSPRO_ATTR_PAYLOAD)
        attr_operate_code = call.data.get(SERVICE_BUSPRO_ATTR_OPERATE_CODE)
        generic = Generic(self.hdl, attr_address, attr_payload, attr_operate_code, DEFAULT_SEND_MESSAGE_NAME)
        await generic.run()

    async def service_set_universal_switch(self, call):
        # noinspection PyUnresolvedReferences
        from .pybuspro.devices.universal_switch import UniversalSwitch

        attr_address = call.data.get(SERVICE_BUSPRO_ATTR_ADDRESS)
        attr_switch_number = call.data.get(SERVICE_BUSPRO_ATTR_SWITCH_NUMBER)
        universal_switch = UniversalSwitch(self.hdl, attr_address, attr_switch_number)

        status = call.data.get(SERVICE_BUSPRO_ATTR_STATUS)
        if status == 1:
            await universal_switch.set_on()
        else:
            await universal_switch.set_off()

    def register_services(self):

        """ activate_scene """
        self.hass.services.async_register(
            DOMAIN, SERVICE_BUSPRO_ACTIVATE_SCENE,
            self.service_activate_scene,
            schema=SERVICE_BUSPRO_ACTIVATE_SCENE_SCHEMA)

        """ send_message """
        self.hass.services.async_register(
            DOMAIN, SERVICE_BUSPRO_SEND_MESSAGE,
            self.service_send_message,
            schema=SERVICE_BUSPRO_SEND_MESSAGE_SCHEMA)

        """ universal_switch """
        self.hass.services.async_register(
            DOMAIN, SERVICE_BUSPRO_UNIVERSAL_SWITCH,
            self.service_set_universal_switch,
            schema=SERVICE_BUSPRO_UNIVERSAL_SWITCH_SCHEMA)

    '''
    def telegram_received_cb(self, telegram):
        #     """Call invoked after a KNX telegram was received."""
        #     self.hass.bus.fire('knx_event', {
        #         'address': str(telegram.group_address),
        #         'data': telegram.payload.value
        #     })
        # _LOGGER.info(f"Callback: '{telegram}'")
        return False
    '''
