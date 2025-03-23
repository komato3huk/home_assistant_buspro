"""UDP client for HDL Buspro protocol."""
import asyncio
import logging
import binascii
from typing import Callable, Optional, Tuple, Dict, Any

_LOGGER = logging.getLogger(__name__)

class UDPClient:
    """UDP client for sending and receiving messages from HDL Buspro devices."""

    def __init__(
        self,
        parent,
        target_host: str,
        data_callback: Callable,
        target_port: int = 6000,
    ):
        """Initialize UDP client.

        Args:
            parent: parent object (usually the network interface)
            target_host: target host for sending messages
            data_callback: callback function for received data
            target_port: target port for sending messages
        """
        self.parent = parent
        self.data_callback = data_callback
        self.target_host = target_host
        self.target_port = target_port
        self.transport = None
        self.protocol = None

    async def start(self):
        """Start UDP client."""
        _LOGGER.info(f"Запуск UDP клиента для HDL Buspro")
        
        try:
            # Создаем протокол и транспорт
            loop = asyncio.get_event_loop()
            self.transport, self.protocol = await loop.create_datagram_endpoint(
                lambda: self._UDPClientProtocol(self.data_callback),
                local_addr=("0.0.0.0", 0),
                allow_broadcast=True,
            )
            
            _LOGGER.info(f"UDP клиент запущен")
            return True
        except Exception as e:
            _LOGGER.error(f"Ошибка при запуске UDP клиента: {e}")
            import traceback
            _LOGGER.error(traceback.format_exc())
            return False

    async def stop(self):
        """Stop UDP client."""
        _LOGGER.info(f"Остановка UDP клиента")
        
        if self.transport:
            self.transport.close()
            self.transport = None
            self.protocol = None
            
        _LOGGER.info(f"UDP клиент остановлен")
        return True

    async def send(self, data, host=None, port=None) -> bool:
        """Send data to target host."""
        if not self.transport:
            _LOGGER.error(f"UDP клиент не запущен")
            return False
            
        try:
            target_host = host or self.target_host or "255.255.255.255"
            target_port = port or self.target_port or 6000
            
            self.transport.sendto(data, (target_host, target_port))
            _LOGGER.debug(f"Отправлены данные на {target_host}:{target_port}: {binascii.hexlify(data).decode()}")
            return True
            
        except Exception as e:
            _LOGGER.error(f"Ошибка при отправке данных: {e}")
            import traceback
            _LOGGER.error(traceback.format_exc())
            return False
    
    async def send_message(self, message):
        """Send message through UDP client.
        
        Args:
            message: Telegram dictionary or HDL message
            
        Returns:
            bool: True if message was sent
        """
        try:
            # Преобразуем старый формат в новый, если необходимо
            if "subnet_id" in message and "target_subnet_id" not in message:
                message["target_subnet_id"] = message["subnet_id"]
                
            if "device_id" in message and "target_device_id" not in message:
                message["target_device_id"] = message["device_id"]
                
            # Создаем буфер отправки с помощью TelegramHelper
            from ..helpers.telegram_helper import TelegramHelper
            th = TelegramHelper()
            send_buffer = th.build_send_buffer(message)
            
            if not send_buffer:
                _LOGGER.error(f"Не удалось создать буфер отправки для сообщения")
                return False
                
            # Отправляем буфер
            return await self.send(
                send_buffer,
                self.gateway_host,
                self.gateway_port
            )
        except Exception as e:
            _LOGGER.error(f"Ошибка при отправке сообщения через UDP: {e}")
            import traceback
            _LOGGER.error(traceback.format_exc())
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
            _LOGGER.debug("UDP соединение установлено")

        def datagram_received(self, data, addr):
            """Called when data is received."""
            _LOGGER.debug(f"Получены данные от {addr}: {binascii.hexlify(data).decode()}")
            if self.data_callback:
                self.data_callback(data, addr)

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
