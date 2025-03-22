"""UDP client for HDL Buspro protocol."""
import logging
import asyncio
import socket
from typing import Callable, Tuple, Any

_LOGGER = logging.getLogger(__name__)

class UDPClient:
    """UDP client for HDL Buspro communication."""
    
    def __init__(self, parent, gateway_host: str, callback=None):
        """Initialize the UDP client."""
        self.parent = parent
        self.gateway_host = gateway_host
        self.callback = callback
        self.transport = None
        self.protocol = None
        
    async def start(self) -> bool:
        """Start the UDP client."""
        try:
            # Create a UDP socket
            self.transport, self.protocol = await asyncio.get_event_loop().create_datagram_endpoint(
                lambda: _UDPClientProtocol(self.callback),
                local_addr=('0.0.0.0', 0)
            )
            return True
        except Exception as err:
            _LOGGER.error("Failed to start UDP client: %s", err)
            return False
    
    async def stop(self) -> None:
        """Stop the UDP client."""
        if self.transport:
            self.transport.close()
            self.transport = None
    
    async def send_message(self, message: bytes) -> None:
        """Send a UDP message."""
        if not self.transport:
            await self.start()
            
        try:
            # Port hardcoded to 6000 as it's the standard for HDL Buspro
            self.transport.sendto(message, (self.gateway_host, 6000))
        except Exception as err:
            _LOGGER.error("Failed to send UDP message: %s", err)


class _UDPClientProtocol(asyncio.DatagramProtocol):
    """UDP protocol for HDL Buspro communication."""
    
    def __init__(self, callback: Callable = None):
        """Initialize the UDP protocol."""
        self.callback = callback
        
    def connection_made(self, transport: asyncio.transports.DatagramTransport) -> None:
        """Called when connection is established."""
        pass
        
    def datagram_received(self, data: bytes, addr: Tuple[str, int]) -> None:
        """Called when data is received."""
        if self.callback:
            self.callback(data, addr)
            
    def error_received(self, exc) -> None:
        """Called when error is received."""
        _LOGGER.error("UDP protocol error: %s", exc)
        
    def connection_lost(self, exc) -> None:
        """Called when connection is lost."""
        if exc:
            _LOGGER.warning("UDP connection lost: %s", exc)
