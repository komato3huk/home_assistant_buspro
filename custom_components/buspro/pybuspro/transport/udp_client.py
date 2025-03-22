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
    
    async def send_message(self, message):
        """Send a UDP message through the HDL Buspro gateway."""
        if not self.transport:
            await self.start()
            
        try:
            # Если это уже байты, отправляем как есть
            if isinstance(message, bytes):
                data = message
            # Если это словарь или другой объект, нужно сериализовать
            else:
                # В реальной реализации здесь должна быть сериализация объекта в байты
                # Для простоты просто преобразуем в строку, а затем в байты
                data = str(message).encode('utf-8')
                
            # Порт по умолчанию 6000, но можно переопределить через параметр port
            port = getattr(self.parent, "hdl_gateway_port", 6000)
            
            # Логируем отправку на шлюз
            _LOGGER.debug("Sending UDP message to gateway %s:%s", self.gateway_host, port)
            
            # Отправляем сообщение на шлюз
            self.transport.sendto(data, (self.gateway_host, port))
            return True
        except Exception as err:
            _LOGGER.error("Failed to send UDP message to gateway: %s", err)
            return False


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
