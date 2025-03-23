"""Network interface for HDL Buspro protocol."""
import logging
import asyncio
import socket
from typing import Tuple, Dict, Any, List, Callable, Optional
from .udp_client import UDPClient
from ..helpers.telegram_helper import TelegramHelper
# from ..devices.control import Control
import binascii
import time

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
        self._connected = False
        self._running = False
        self._udp_client = None
        self._read_task = None
        self._th = TelegramHelper()
        self._init_udp_client()
        
    def _init_udp_client(self):
        self._udp_client = UDPClient(self.parent, self.hdl_gateway_host, self._udp_request_received)

    def _udp_request_received(self, data, address):
        """Callback for received UDP data."""
        if not data:
            _LOGGER.warning("Получены пустые UDP данные от %s", address)
            return
            
        try:
            # Создаем телеграмму из полученных данных
            telegram = self._th.build_telegram_from_udp_data(data, address)
            
            if not telegram:
                _LOGGER.warning("Не удалось создать телеграмму из данных: %s", binascii.hexlify(data).decode())
                return
                
            _LOGGER.debug(
                "Получена телеграмма от %d.%d, код операции: 0x%04X, адрес: %s", 
                telegram.get("source_subnet_id", 0), telegram.get("source_device_id", 0),
                telegram.get("operate_code", 0), address
            )
            
            # Уведомляем все обратные вызовы
            for callback in self.callbacks:
                try:
                    callback(telegram)
                except Exception as e:
                    _LOGGER.error("Ошибка в обратном вызове обработки телеграммы: %s", e)
                    import traceback
                    _LOGGER.error(traceback.format_exc())
                    
        except Exception as e:
            _LOGGER.error("Ошибка при обработке UDP данных от %s: %s", address, e)
            import traceback
            _LOGGER.error(traceback.format_exc())

    async def start(self):
        """Start the network interface."""
        try:
            # Initialize UDP client уже не нужно, так как мы сделали это в _init_udp_client
            await self._udp_client.start()
            
            self._running = True
            self._connected = True
            self._read_task = asyncio.create_task(self._read_loop())
            
            _LOGGER.info("Network interface started, connected to %s:%s", 
                        self.hdl_gateway_host, self.hdl_gateway_port)
            return True
        except Exception as err:
            _LOGGER.error("Failed to start network interface: %s", err)
            self._running = False
            self._connected = False
            return False
    
    async def stop(self):
        """Stop the network interface."""
        if self._read_task:
            self._read_task.cancel()
            try:
                await self._read_task
            except asyncio.CancelledError:
                pass
            
        if self.writer:
            self.writer.close()
            await self.writer.wait_closed()
            
        self._connected = False
        self._running = False
        
    async def _read_loop(self):
        """Read data from UDP client continuously."""
        base_sleep_time = 0.1  # Базовое время сна в секундах
        max_sleep_time = 1.0   # Максимальное время сна в секундах
        min_sleep_time = 0.01  # Минимальное время сна в секундах
        
        sleep_time = base_sleep_time  # Текущее время сна
        idle_counter = 0        # Счётчик бездействия
        max_idle_count = 100    # Максимальное количество итераций бездействия
        message_counter = 0     # Счётчик сообщений для отладки
        last_activity_time = time.time()  # Время последней активности
        
        _LOGGER.info("Запуск цикла чтения данных UDP")
        
        while self._connected and self._running:
            try:
                # В этой реализации нет непрерывного чтения,
                # так как UDP-клиент вызывает обратный вызов при получении данных
                
                # Ждём указанное время
                await asyncio.sleep(sleep_time)
                
                # Если долгое время нет активности, увеличиваем интервал сна
                if time.time() - last_activity_time > 5.0:  # 5 секунд бездействия
                    idle_counter += 1
                    
                    # Адаптивно увеличиваем время сна до максимального значения
                    if idle_counter > max_idle_count:
                        sleep_time = min(sleep_time * 1.1, max_sleep_time)
                        idle_counter = 0
                        
                        if sleep_time >= max_sleep_time:
                            _LOGGER.debug("Низкая активность UDP, увеличен интервал ожидания до %s сек", sleep_time)
                else:
                    # При наличии активности постепенно уменьшаем время сна
                    idle_counter = 0
                    sleep_time = max(sleep_time * 0.9, min_sleep_time)
                    
                # Периодически выводим статистику (каждые ~30 секунд)
                message_counter += 1
                if message_counter % 300 == 0:  # Примерно каждые 30 секунд при базовом sleep_time
                    _LOGGER.debug("Статистика UDP: активность %s сек назад, интервал ожидания %s сек", 
                                 time.time() - last_activity_time, sleep_time)
                    
            except asyncio.CancelledError:
                _LOGGER.info("Цикл чтения данных UDP остановлен")
                break
            except Exception as err:
                _LOGGER.error("Ошибка в цикле чтения данных UDP: %s", err)
                
                # В случае ошибки увеличиваем время ожидания
                sleep_time = max_sleep_time
                await asyncio.sleep(sleep_time)
                
        _LOGGER.info("Завершён цикл чтения данных UDP")
                
    @property
    def connected(self):
        """Return if the network interface is connected."""
        return self._running and self._connected and self._udp_client is not None

    async def send_message(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """Send a message to the HDL Buspro bus through the gateway and return the response."""
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
            
            # Логируем отправку через шлюз
            _LOGGER.debug(
                "Sending message through gateway %s:%s to device %d.%d: operation=%04X, data=%s",
                self.hdl_gateway_host, self.hdl_gateway_port,
                telegram["target_subnet_id"], telegram["target_device_id"],
                telegram["operation_code"], telegram["data"]
            )
            
            # Send the telegram through the gateway
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
            _LOGGER.error("Error sending message through gateway: %s", err)
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
    
    def register_callback(self, callback):
        """Register a callback for received messages."""
        if callback not in self.callbacks:
            self.callbacks.append(callback)
        
    def unregister_callback(self, callback):
        """Unregister a callback."""
        if callback in self.callbacks:
            self.callbacks.remove(callback)

    async def _send_message(self, message):
        """Send message through UDP client."""
        if not self._udp_client:
            _LOGGER.error("Cannot send message: UDP client not initialized")
            return False
            
        try:
            result = await self._udp_client.send_message(message)
            if not result:
                _LOGGER.warning("Message was not sent successfully through gateway")
            return result
        except Exception as err:
            _LOGGER.error("Error sending message through UDP client: %s", err)
            return False

    async def send_telegram(self, telegram):
        """Send telegram through HDL Buspro gateway.
        
        Args:
            telegram: Telegram dictionary with target_subnet_id, target_device_id, etc.
            
        Returns:
            bool: True if message was sent successfully
        """
        try:
            if not self._udp_client:
                _LOGGER.error("Невозможно отправить телеграмму: UDP клиент не инициализирован")
                return False
                
            # Создаем буфер для отправки
            message = self._th.build_send_buffer(telegram)
            
            if not message:
                _LOGGER.error("Не удалось создать буфер отправки из телеграммы: %s", telegram)
                return False
            
            # Логируем отправку через шлюз
            _LOGGER.debug(
                "Отправка телеграммы через шлюз %s:%s на устройство %d.%d, данные: %s",
                self.hdl_gateway_host, self.hdl_gateway_port,
                telegram.get("target_subnet_id", 0), telegram.get("target_device_id", 0),
                binascii.hexlify(message).decode()
            )
            
            # Отправляем сообщение через UDP клиент
            result = await self._udp_client.send(
                message,
                host=self.hdl_gateway_host,
                port=self.hdl_gateway_port
            )
            
            if not result:
                _LOGGER.warning(
                    "Не удалось отправить телеграмму на устройство %d.%d через шлюз %s:%s",
                    telegram.get("target_subnet_id", 0), telegram.get("target_device_id", 0),
                    self.hdl_gateway_host, self.hdl_gateway_port
                )
                
            return result
            
        except Exception as err:
            _LOGGER.error("Ошибка при отправке телеграммы через шлюз: %s", err)
            import traceback
            _LOGGER.error(traceback.format_exc())
            return False
