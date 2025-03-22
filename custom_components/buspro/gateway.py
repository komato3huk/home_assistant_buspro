"""HDL Buspro Gateway."""
import asyncio
import logging
import time
from typing import Any, Dict, List, Optional, Tuple

from homeassistant.core import HomeAssistant
from homeassistant.helpers.event import async_track_time_interval
import homeassistant.util.dt as dt_util

from .pybuspro.core.hdl_device import HDLDevice
from .discovery import BusproDiscovery

_LOGGER = logging.getLogger(__name__)

class BusproGateway:
    """Manages the HDL Buspro gateway."""

    def __init__(
        self,
        hass: HomeAssistant,
        hdl_device: HDLDevice,
        discovery: BusproDiscovery,
        poll_interval: int = 30,
    ) -> None:
        """Initialize the gateway."""
        self.hass = hass
        self.hdl_device = hdl_device
        self.discovery = discovery
        self.poll_interval = poll_interval
        self._callbacks = []
        self._polling_task = None
        self._connected = False
        self._last_update = None

    async def start(self) -> None:
        """Start the gateway."""
        try:
            # Initialize the network interface
            await self.hdl_device.start()
            self._connected = True
            
            # Start polling
            if self.poll_interval > 0:
                self._polling_task = async_track_time_interval(
                    self.hass,
                    self._poll_devices,
                    dt_util.timedelta(seconds=self.poll_interval),
                )
                
            _LOGGER.info("HDL Buspro gateway started")
        except Exception as err:
            self._connected = False
            _LOGGER.error("Failed to start HDL Buspro gateway: %s", err)
            raise

    async def stop(self) -> None:
        """Stop the gateway."""
        try:
            # Stop the network interface
            await self.hdl_device.stop()
            self._connected = False
            
            # Cancel polling task
            if self._polling_task:
                self._polling_task()
                self._polling_task = None
                
            _LOGGER.info("HDL Buspro gateway stopped")
        except Exception as err:
            _LOGGER.error("Failed to stop HDL Buspro gateway: %s", err)

    async def send_message(
        self,
        target_address: List[int],
        operation_code: List[int],
        data: List[int],
    ) -> Optional[List[int]]:
        """Send a message to a device and return the response."""
        if not self._connected:
            _LOGGER.error("Cannot send message: Gateway not connected")
            return None
            
        try:
            response = await self.hdl_device.send_message(
                target_address, operation_code, data
            )
            self._last_update = time.time()
            return response
        except Exception as err:
            _LOGGER.error("Failed to send message: %s", err)
            return None

    def register_callback(self, callback) -> None:
        """Register a callback for data updates."""
        self._callbacks.append(callback)

    def remove_callback(self, callback) -> None:
        """Remove a callback."""
        if callback in self._callbacks:
            self._callbacks.remove(callback)

    async def _poll_devices(self, *args) -> None:
        """Poll all devices to update their status."""
        if not self._connected:
            return
            
        try:
            # Perform a device update (you can customize this based on your needs)
            devices = await self.discovery.poll_devices()
            
            # Call all registered callbacks
            for callback in self._callbacks:
                await callback(devices)
                
            self._last_update = time.time()
            _LOGGER.debug("Devices polled successfully")
        except Exception as err:
            _LOGGER.error("Error polling devices: %s", err) 