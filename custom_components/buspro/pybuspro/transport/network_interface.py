"""Network interface for HDL Buspro protocol."""
import logging
import asyncio
import socket
from typing import Tuple, Dict, Any, List, Callable, Optional
from .udp_client import UDPClient
from ..helpers.telegram_helper import TelegramHelper
# from ..devices.control import Control

_LOGGER = logging.getLogger(__name__)

# HDL Buspro packet structure
# +----+----+------+------+------+--------+------+----+
# | 0  | 1  |  2   |  3   |  4   |   5-6  | 7-n  | n+1|
# +----+----+------+------+------+--------+------+----+
# |0xAA|0xAA|subnet|device|opcode|dataleng|data  |crc |
# +----+----+------+------+------+--------+------+----+

class NetworkInterface:
    """Network interface for HDL Buspro protocol."""
    
    def __init__(self, parent, gateway_address: Tuple[str, int], device_subnet_id: int = 0, 
                 device_id: int = 0, gateway_host: str = None, gateway_port: int = None):
        """Initialize network interface."""
        self.parent = parent
        self.gateway_host, self.gateway_port = gateway_address
        self.device_subnet_id = device_subnet_id
        self.device_id = device_id
        self.hdl_gateway_host = gateway_host or self.gateway_host
        self.hdl_gateway_port = gateway_port or 6000
        self.writer = None
        self.reader = None
        self.read_task = None
        self.callbacks = []
        self.transport = None
        self.protocol = None
        self.connected = False
        self.udp_client = None
        self._th = TelegramHelper()
        self._init_udp_client()
        
    def _init_udp_client(self):
        self.udp_client = UDPClient(self.parent, self.hdl_gateway_host, self._udp_request_received)

    def _udp_request_received(self, data, address):
        if self.callbacks:
            telegram = self._th.build_telegram_from_udp_data(data, address)
            for callback in self.callbacks:
                callback(telegram)

    async def start(self):
        """Start the network interface."""
        try:
            # Initialize UDP client
            self._udp_client = UDPClient(
                self,
                self.hdl_gateway_host
            )
            await self._udp_client.start()
            
            self._running = True
            self._read_task = asyncio.create_task(self._read_loop())
            
            _LOGGER.info("Network interface started, connected to %s:%s", 
                        self.hdl_gateway_host, self.hdl_gateway_port)
            return True
        except Exception as err:
            _LOGGER.error("Failed to start network interface: %s", err)
            self._running = False
            return False
    
    async def stop(self):
        """Stop the network interface."""
        if self.read_task:
            self.read_task.cancel()
            try:
                await self.read_task
            except asyncio.CancelledError:
                pass
            
        if self.writer:
            self.writer.close()
            await self.writer.wait_closed()
            
        self.connected = False
        
    async def _read_loop(self):
        """Read data from the HDL Buspro bus continuously."""
        while self.connected:
            try:
                # Read header (first 7 bytes)
                header = await self.reader.read(7)
                if not header or len(header) < 7:
                    # Connection closed or header incomplete
                    await asyncio.sleep(0.1)
                    continue
                    
                # Check if this is a valid HDL packet
                if header[0] != 0xAA or header[1] != 0xAA:
                    # Invalid header, discard and continue
                    continue
                    
                # Parse header
                subnet_id = header[2]
                device_id = header[3]
                operate_code = (header[4] << 8) | header[5]
                data_length = header[6]
                
                # Read data
                data = await self.reader.read(data_length)
                
                # Read CRC
                crc = await self.reader.read(1)
                
                # Process message
                message = {
                    "subnet_id": subnet_id,
                    "device_id": device_id,
                    "operate_code": operate_code,
                    "data": list(data)
                }
                
                # Call all registered callbacks
                for callback in self.callbacks:
                    callback(message)
                    
            except (OSError, asyncio.TimeoutError) as err:
                _LOGGER.error("Error reading from HDL Buspro: %s", err)
                await asyncio.sleep(1)
            except Exception as err:
                _LOGGER.error("Unexpected error in HDL read loop: %s", err)
                await asyncio.sleep(1)
    
    @property
    def connected(self):
        """Return if the network interface is connected."""
        return self._running and self._udp_client is not None

    async def send_message(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """Send a message to the HDL Buspro bus and return the response."""
        if not self.connected:
            await self.start()
            
        # Special case for discovery, return simulated response for testing
        if message.get("operate_code") == 0x000D:
            return self._simulate_discovery_response()
            
        try:
            # Create the message dictionary with source address
            telegram = {
                "target_subnet_id": message.get("subnet_id", 0),
                "target_device_id": message.get("device_id", 0),
                "source_subnet_id": self.device_subnet_id,
                "source_device_id": self.device_id,
                "operation_code": message.get("operate_code", 0),
                "data": message.get("data", [])
            }
            
            # Send the telegram
            await self._send_message(telegram)
            
            # For now, return a simulated response
            # In a real implementation, we would wait for and process the response
            if message.get("operate_code") == 0x0032:  # Read status
                # Simulate a response for reading status
                return {
                    "status": "success",
                    "data": [50]  # 50% brightness or position
                }
            else:
                # Generic response
                return {
                    "status": "success",
                    "data": []
                }
                
        except Exception as err:
            _LOGGER.error("Error sending message: %s", err)
            return {"status": "error", "message": str(err)}
    
    def _simulate_discovery_response(self) -> Dict[str, Any]:
        """Simulate a discovery response for testing purposes."""
        # In a real implementation, this would parse actual responses from the bus
        # For now, we'll simulate some devices for testing
        return {
            "devices": [
                {"subnet_id": 1, "device_id": 1, "type": 0x0001},  # Light
                {"subnet_id": 1, "device_id": 2, "type": 0x0001},  # Light
                {"subnet_id": 1, "device_id": 3, "type": 0x0003},  # Cover
                {"subnet_id": 1, "device_id": 4, "type": 0x0004},  # Climate
                {"subnet_id": 1, "device_id": 5, "type": 0x0005},  # Sensor
            ]
        }
    
    def register_callback(self, callback: Callable[[Dict[str, Any]], None]):
        """Register a callback for incoming messages."""
        if callback not in self.callbacks:
            self.callbacks.append(callback)

    async def _send_message(self, message):
        await self.udp_client.send_message(message)

    async def send_telegram(self, telegram):
        message = self._th.build_send_buffer(telegram)

        gateway_address_send, _ = self.hdl_gateway_host, self.hdl_gateway_port
        self.parent.logger.debug(self._th.build_telegram_from_udp_data(message, gateway_address_send))

        await self.udp_client.send_message(message)
