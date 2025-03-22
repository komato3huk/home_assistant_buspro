"""HDL Device module for interacting with HDL Buspro devices."""
import logging
import asyncio
from typing import List, Dict, Any, Optional, Tuple, Callable

from ..transport.network_interface import NetworkInterface
from ..helpers.enums import OperateCode

_LOGGER = logging.getLogger(__name__)

class HDLDevice:
    """Class for interacting with HDL Buspro devices."""
    
    def __init__(self, host: str, port: int, loop=None):
        """Initialize HDL device handler."""
        self.host = host
        self.port = port
        self.loop = loop or asyncio.get_event_loop()
        self.network_interface = None
        self.started = False
        self.connected = False
        self._callbacks = []
        
    async def start(self):
        """Start the HDL device connection."""
        if self.started:
            return
            
        try:
            self.network_interface = NetworkInterface(self, (self.host, self.port))
            self.network_interface.register_callback(self._handle_message)
            await self.network_interface.start()
            self.started = True
            self.connected = True
            _LOGGER.info("Connected to HDL Buspro gateway at %s:%s", self.host, self.port)
        except Exception as err:
            self.connected = False
            _LOGGER.error("Failed to connect to HDL Buspro gateway: %s", err)
            raise
        
    async def stop(self):
        """Stop the HDL device connection."""
        if self.network_interface:
            await self.network_interface.stop()
            self.network_interface = None
        self.started = False
        self.connected = False
    
    async def send_message(self, address: List[int], operate_code: List[int], payload: List[int]) -> List:
        """Send a message to the HDL Buspro bus and return the response."""
        if not self.started:
            await self.start()
            
        if not self.connected:
            _LOGGER.error("Not connected to HDL Buspro gateway")
            return []
            
        try:
            # Format address to subnet_id, device_id
            subnet_id, device_id = address
            
            # Create message
            message = {
                "subnet_id": subnet_id,
                "device_id": device_id,
                "operate_code": operate_code[0],
                "data": payload
            }
            
            # Send message and wait for response
            response = await self.network_interface.send_message(message)
            
            # Process response based on operation code
            if operate_code[0] == 0x000D:  # Discovery
                return self._process_discovery_response(response)
            else:
                return self._process_standard_response(response)
                
        except Exception as err:
            _LOGGER.error("Error sending message to HDL Buspro: %s", err)
            return []
    
    def _process_discovery_response(self, response: Dict) -> List:
        """Process discovery response from HDL devices."""
        devices = []
        if not response or "devices" not in response:
            return devices
            
        for device in response["devices"]:
            devices.append({
                "subnet_id": device.get("subnet_id", 0),
                "device_id": device.get("device_id", 0),
                "type": device.get("type", 0),
                "name": f"Device {device.get('subnet_id', 0)}.{device.get('device_id', 0)}"
            })
            
        return devices
    
    def _process_standard_response(self, response: Dict) -> List:
        """Process standard response from HDL devices."""
        if not response or "data" not in response:
            return []
            
        return response["data"]
    
    def _handle_message(self, message: Dict):
        """Handle incoming messages from HDL Buspro bus."""
        for callback in self._callbacks:
            callback(message)
    
    def register_device_updated_cb(self, callback: Callable):
        """Register a callback for device updates."""
        if callback not in self._callbacks:
            self._callbacks.append(callback)
    
    def unregister_device_updated_cb(self, callback: Callable):
        """Unregister a callback for device updates."""
        if callback in self._callbacks:
            self._callbacks.remove(callback) 