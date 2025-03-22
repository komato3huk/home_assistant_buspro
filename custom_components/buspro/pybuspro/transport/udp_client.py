"""UDP client for HDL Buspro protocol."""
import asyncio
import logging
from typing import Callable, Optional, Tuple

_LOGGER = logging.getLogger(__name__)

class UDPClient:
    """UDP client for sending and receiving messages from HDL Buspro devices."""

    def __init__(
        self,
        loop: asyncio.AbstractEventLoop,
        data_callback: Callable,
        target_host: str = None,
        target_port: int = 6000,
    ):
        """Initialize UDP client.

        Args:
            loop: asyncio event loop
            data_callback: callback function for received data
            target_host: target host for sending messages
            target_port: target port for sending messages
        """
        self.loop = loop
        self.data_callback = data_callback
        self.target_host = target_host
        self.target_port = target_port
        self.transport = None
        self.protocol = None

    async def start(self):
        """Start UDP client."""
        _LOGGER.info(f"Запуск UDP клиента для HDL Buspro")
        
        # Создаем протокол и транспорт
        self.transport, self.protocol = await self.loop.create_datagram_endpoint(
            lambda: self._UDPClientProtocol(self.data_callback),
            local_addr=("0.0.0.0", 0),
            allow_broadcast=True,
        )
        
        _LOGGER.info(f"UDP клиент запущен")

    async def stop(self):
        """Stop UDP client."""
        _LOGGER.info(f"Остановка UDP клиента")
        
        if self.transport:
            self.transport.close()
            self.transport = None
            self.protocol = None
            
        _LOGGER.info(f"UDP клиент остановлен")

    async def send(self, data, host=None, port=None):
        """Send data to target host."""
        if not self.transport:
            _LOGGER.error(f"UDP клиент не запущен")
            return False
            
        try:
            target_host = host or self.target_host or "255.255.255.255"
            target_port = port or self.target_port or 6000
            
            self.transport.sendto(data, (target_host, target_port))
            _LOGGER.debug(f"Отправлены данные на {target_host}:{target_port}: {data.hex()}")
            return True
            
        except Exception as e:
            _LOGGER.error(f"Ошибка при отправке данных: {e}")
            return False

    class _UDPClientProtocol(asyncio.DatagramProtocol):
        """UDP protocol for handling received data."""

        def __init__(self, data_callback):
            """Initialize protocol."""
            self.data_callback = data_callback
            self.transport = None
            super().__init__()

        def connection_made(self, transport):
            """Called when connection is made."""
            self.transport = transport

        def datagram_received(self, data, addr):
            """Called when data is received."""
            if self.data_callback:
                asyncio.create_task(self._process_data(data, addr))

        async def _process_data(self, data, addr):
            """Process received data."""
            try:
                await self.data_callback(data, addr)
            except Exception as e:
                _LOGGER.error(f"Ошибка при обработке полученных данных: {e}")

        def error_received(self, exc):
            """Called when an error is received."""
            _LOGGER.error(f"Ошибка UDP: {exc}")

        def connection_lost(self, exc):
            """Called when connection is lost."""
            if exc:
                _LOGGER.error(f"Соединение UDP закрыто с ошибкой: {exc}")
            else:
                _LOGGER.debug(f"Соединение UDP закрыто")
            self.transport = None
