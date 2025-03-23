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
        self._parent = parent
        self._data_callback = data_callback
        self._host = target_host
        self._port = target_port
        self._transport = None
        self._protocol = None

    async def start(self):
        """Start UDP client."""
        _LOGGER.info(f"Запуск UDP клиента для HDL Buspro")
        
        try:
            # Создаем протокол и транспорт
            loop = asyncio.get_event_loop()
            self._transport, self._protocol = await loop.create_datagram_endpoint(
                lambda: self._UDPClientProtocol(self._data_callback),
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
        
        if self._transport:
            self._transport.close()
            self._transport = None
            self._protocol = None
            
        _LOGGER.info(f"UDP клиент остановлен")
        return True

    async def send(self, data, host=None, port=None):
        """Send data to the UDP server.
        
        Args:
            data: Data to send (must be bytes)
            host: Host to send to (default: self._host)
            port: Port to send to (default: self._port)
            
        Returns:
            bool: True if message was sent, False otherwise
        """
        if not isinstance(data, bytes):
            _LOGGER.error("Данные для отправки должны быть в формате bytes")
            return False
            
        if not self._transport:
            await self.start()
            if not self._transport:
                _LOGGER.error(f"Невозможно отправить данные: транспорт не инициализирован")
                return False
                
        try:
            target_host = host or self._host
            target_port = port or self._port
            
            _LOGGER.debug(f"Отправка UDP пакета на {target_host}:{target_port}, размер {len(data)} байт")
            
            # Отправляем данные
            self._transport.sendto(data, (target_host, target_port))
            
            # Добавляем небольшую задержку, чтобы не перегружать сеть
            await asyncio.sleep(0.05)
            
            return True
        except (OSError, asyncio.TimeoutError) as exc:
            _LOGGER.error(f"Ошибка сети при отправке данных на {host}:{port}: {exc}")
            return False
        except Exception as exc:
            _LOGGER.error(f"Непредвиденная ошибка при отправке данных: {exc}")
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
                host=self._host,
                port=self._port
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
