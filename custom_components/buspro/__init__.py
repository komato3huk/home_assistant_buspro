"""
Support for Buspro devices.

For more details about this component, please refer to the documentation at
https://home-assistant.io/...
"""

import logging
import asyncio
from typing import Dict, List, Optional, Any
from datetime import timedelta

import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from homeassistant.const import (
    CONF_HOST, 
    CONF_PORT, 
    CONF_NAME,
    CONF_TIMEOUT,
    Platform,
    CONF_SCAN_INTERVAL,
)
from homeassistant.const import (
    EVENT_HOMEASSISTANT_STOP,
)
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.typing import ConfigType
from homeassistant.helpers.event import async_track_time_interval

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
    DEFAULT_HOST,
)
from .discovery import BusproDiscovery, DeviceDiscovery
from .gateway import BusproGateway

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [
    Platform.LIGHT,
    Platform.COVER,
    Platform.CLIMATE,
    Platform.BINARY_SENSOR,
    Platform.SENSOR,
    Platform.SWITCH,
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

# Схема для сервиса сканирования устройств
SCAN_DEVICES_SCHEMA = vol.Schema({
    vol.Optional("subnet_id"): vol.All(vol.Coerce(int), vol.Range(min=1, max=254)),
    vol.Optional("timeout", default=5): vol.All(vol.Coerce(int), vol.Range(min=1, max=60)),
})

CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: vol.Schema(
            {
                vol.Required(CONF_HOST): cv.string,
                vol.Optional(CONF_PORT, default=DEFAULT_PORT): cv.port,
                vol.Optional(CONF_TIMEOUT, default=DEFAULT_TIMEOUT): cv.positive_int,
                vol.Optional(CONF_DEVICE_SUBNET_ID, default=DEFAULT_DEVICE_SUBNET_ID): vol.All(
                    vol.Coerce(int), vol.Range(min=0, max=255)
                ),
                vol.Optional(CONF_DEVICE_ID, default=DEFAULT_DEVICE_ID): vol.All(
                    vol.Coerce(int), vol.Range(min=0, max=255)
                ),
                vol.Optional(CONF_POLL_INTERVAL, default=DEFAULT_POLL_INTERVAL): vol.All(
                    vol.Coerce(int), vol.Range(min=5, max=300)
                ),
                vol.Optional(CONF_GATEWAY_HOST): cv.string,
                vol.Optional(CONF_GATEWAY_PORT): cv.port,
            }
        )
    },
    extra=vol.ALLOW_EXTRA,
)

async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up HDL Buspro integration from YAML."""
    if DOMAIN not in config:
        return True
        
    # Создаем хранилище данных в hass
    hass.data.setdefault(DOMAIN, {})
    
    # Извлекаем конфигурацию
    domain_config = config[DOMAIN]
    
    # Импортируем конфигурацию в config entries
    hass.async_create_task(
        hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": "import"},
            data=domain_config,
        )
    )
    
    return True

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up HDL Buspro from a config entry."""
    _LOGGER.info(f"Настройка интеграции HDL Buspro из config entry: {entry.data}")
    
    # Получаем настройки из конфигурации
    host = entry.data[CONF_HOST]
    port = entry.data.get(CONF_PORT, DEFAULT_PORT)
    gateway_port = entry.data.get(CONF_GATEWAY_PORT, DEFAULT_GATEWAY_PORT)
    device_subnet_id = entry.data.get(CONF_DEVICE_SUBNET_ID, DEFAULT_DEVICE_SUBNET_ID)
    device_id = entry.data.get(CONF_DEVICE_ID, DEFAULT_DEVICE_ID)
    timeout = entry.data.get(CONF_TIMEOUT, DEFAULT_TIMEOUT)
    poll_interval = entry.data.get(CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL)
    
    # Создаем шлюз HDL Buspro
    gateway = BusproGateway(
        hass=hass,
        host=host,
        port=gateway_port,
        timeout=timeout,
        poll_interval=poll_interval,
        device_subnet_id=device_subnet_id,
        device_id=device_id,
    )
    
    # Запускаем шлюз
    await gateway.start()
    
    # Создаем объект обнаружения устройств
    discovery = BusproDiscovery(
        hass=hass,
        gateway_host=host,
        gateway_port=gateway_port,
        broadcast_address=host,
        device_subnet_id=device_subnet_id,
        device_id=device_id,
    )
    
    # Устанавливаем ссылки между объектами
    discovery.gateway = gateway
    
    # Запускаем обнаружение устройств
    await discovery.discover_devices()
    
    # Сохраняем объекты в hass.data
    if DOMAIN not in hass.data:
        hass.data[DOMAIN] = {}
        
    hass.data[DOMAIN][entry.entry_id] = {
        "gateway": gateway,
        "discovery": discovery,
    }
    
    # Регистрируем платформы
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    
    # Регистрируем функцию для выгрузки entry
    entry.async_on_unload(entry.add_update_listener(_update_listener))
    
    # Регистрируем сервис сканирования устройств
    async def handle_scan_devices(call: ServiceCall) -> None:
        """Обработчик сервиса сканирования устройств."""
        subnet_id = call.data.get("subnet_id")
        timeout = call.data.get("timeout", 5)
        
        _LOGGER.info(f"Запуск сканирования устройств Buspro (подсеть: {subnet_id or 'все'}, таймаут: {timeout}с)")
        
        try:
            await discovery.discover_devices(subnet_id=subnet_id, timeout=timeout)
            _LOGGER.info("Сканирование устройств Buspro завершено")
        except Exception as e:
            _LOGGER.error(f"Ошибка при сканировании устройств Buspro: {e}")
    
    hass.services.async_register(
        DOMAIN,
        "scan_devices",
        handle_scan_devices,
        schema=SCAN_DEVICES_SCHEMA,
    )
    
    return True

async def async_update_options(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Update options for the HDL Buspro integration."""
    await hass.config_entries.async_reload(entry.entry_id)

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    _LOGGER.info("Выгрузка интеграции HDL Buspro")
    
    # Останавливаем платформы
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    
    if unload_ok:
        # Останавливаем шлюз
        gateway = hass.data[DOMAIN][entry.entry_id]["gateway"]
        await gateway.stop()
        
        # Удаляем данные
        hass.data[DOMAIN].pop(entry.entry_id)
        
        _LOGGER.info("Интеграция HDL Buspro успешно выгружена")
    
    return unload_ok

async def _update_listener(hass: HomeAssistant, entry: ConfigEntry):
    """Handle options update."""
    await hass.config_entries.async_reload(entry.entry_id)

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
