"""HDL Buspro gateway module."""
import asyncio
import logging
import socket
import time
from datetime import timedelta
from typing import Any, Dict, List, Optional, Tuple
import binascii

from homeassistant.core import HomeAssistant

from .const import (
    LOGGER,
    CONF_GATEWAY_HOST,
    CONF_GATEWAY_PORT,
    CONF_DEVICE_SUBNET_ID,
    CONF_DEVICE_ID,
    CONF_POLL_INTERVAL,
    CONF_TIMEOUT,
    OPERATION_DISCOVERY,
    OPERATION_READ_STATUS,
    OPERATION_SINGLE_CHANNEL,
    OPERATION_SCENE_CONTROL,
    OPERATION_UNIVERSAL_SWITCH,
)

from .pybuspro.transport import UDPClient
from .pybuspro.transport.network_interface import NetworkInterface
from .pybuspro.helpers import TelegramHelper

from .discovery import BusproDiscovery

_LOGGER = logging.getLogger(__name__)

class BusproGateway:
    """HDL Buspro gateway."""

    def __init__(
        self,
        hass,
        host: str,
        port: int = 6000,
        timeout: int = 2,
        poll_interval: int = 60,
        device_subnet_id: int = 0,
        device_id: int = 1,
    ):
        """Initialize the HDL Buspro gateway."""
        self.hass = hass
        self.gateway_host = host
        self.gateway_port = port
        self.timeout = timeout
        self.poll_interval = poll_interval
        self.device_subnet_id = device_subnet_id
        self.device_id = device_id
        
        # Создаем помощник для работы с телеграммами
        self.telegram_helper = TelegramHelper()
        
        # UDP клиент для коммуникации с шлюзом
        self._udp_client = None
        
        # Сетевой интерфейс для отправки телеграмм
        self._network_interface = None
        
        # Задача поллинга
        self._polling_task = None
        
        # Флаг работы шлюза
        self._running = False
        
        # Время последнего обновления
        self._last_update = 0
        
        # Коллбеки и обработчики
        self._callbacks = {}
        self._message_listeners = []
        self.discovery_callback = None
        
        # Добавляем атрибут для хранения ответов от устройств
        self._pending_telegrams = {}

    async def start(self):
        """Start the gateway."""
        _LOGGER.info(f"Запуск шлюза HDL Buspro {self.gateway_host}:{self.gateway_port}")
        
        if self._running:
            _LOGGER.debug("Шлюз HDL Buspro уже запущен")
            return
            
        try:
            # Создаем UDP клиент и сетевой интерфейс для коммуникации с шлюзом
            self._udp_client = UDPClient(
                self,  # передаем себя как родителя
                self.gateway_host,
                self._handle_received_data,
                self.gateway_port,
            )
            
            # Инициализируем сетевой интерфейс
            self._network_interface = NetworkInterface(
                self,  # передаем себя как родителя
                (self.gateway_host, self.gateway_port),
                self.device_subnet_id,
                self.device_id,
                self.gateway_host,
                self.gateway_port
            )
            
            # Регистрируем обработчики
            self._callbacks = {}
            self._message_listeners = []
            
            # Запускаем UDP клиент
            await self._udp_client.start()
            
            # Запускаем сетевой интерфейс
            await self._network_interface.start()
            
            # Запускаем задачу поллинга, если интервал больше 0
            if self.poll_interval > 0:
                self._polling_task = self.hass.loop.create_task(self._polling_loop())
                
            self._running = True
            _LOGGER.info(f"Шлюз HDL Buspro запущен успешно")
            
        except Exception as e:
            _LOGGER.error(f"Ошибка при запуске шлюза HDL Buspro: {e}")
            raise

    async def stop(self):
        """Stop the gateway."""
        _LOGGER.info(f"Остановка шлюза HDL Buspro")
        
        if not self._running:
            _LOGGER.debug("Шлюз HDL Buspro уже остановлен")
            return
            
        # Останавливаем задачу поллинга
        if self._polling_task:
            self._polling_task.cancel()
            self._polling_task = None
            
        # Останавливаем сетевой интерфейс
        if self._network_interface:
            await self._network_interface.stop()
            self._network_interface = None
            
        # Останавливаем UDP клиент
        if self._udp_client:
            await self._udp_client.stop()
            self._udp_client = None
            
        self._running = False
        _LOGGER.info(f"Шлюз HDL Buspro остановлен")

    async def _polling_loop(self):
        """Polling loop for devices."""
        try:
            _LOGGER.info(f"Запуск цикла опроса устройств с интервалом {self.poll_interval} секунд")
            poll_interval = timedelta(seconds=self.poll_interval)
            await self._poll_devices(poll_interval)
        except asyncio.CancelledError:
            _LOGGER.debug("Цикл опроса устройств остановлен")
        except Exception as e:
            _LOGGER.error(f"Ошибка в цикле опроса устройств: {e}")

    @property
    def connected(self) -> bool:
        """Return True if gateway is connected."""
        return self._connected

    async def send_message(self, target_address, operation_code, data=None, timeout=2.0):
        """Send message to the HDL Buspro gateway."""
        if not self._udp_client:
            _LOGGER.error(f"UDP клиент не инициализирован")
            return None
            
        try:
            # Создаем телеграмму с правильными ключами
            telegram = {
                "target_subnet_id": target_address[0],
                "target_device_id": target_address[1],
                "source_subnet_id": self.device_subnet_id,
                "source_device_id": self.device_id,
                "operate_code": (operation_code[0] << 8) | operation_code[1],
                "data": data if data is not None else [],
            }
            
            # Если это сообщение широковещательного типа или команда без ответа,
            # просто отправляем сообщение без ожидания ответа
            if target_address[1] == 0xFF or operation_code[0] == 0:
                buffer = self.telegram_helper.build_send_buffer(telegram)
                if buffer:
                    _LOGGER.debug(f"Отправка широковещательного сообщения: subnet_id={target_address[0]}, "
                                f"device_id={target_address[1]}, opcode=0x{telegram['operate_code']:04X}")
                    await self._udp_client.send(buffer, self.gateway_host, self.gateway_port)
                    return {"status": "sent"}
            
            # Генерируем уникальный ключ для callback
            callback_key = (target_address[0], target_address[1], telegram["operate_code"])
            
            # Создаем future для получения результата
            future = asyncio.Future()
            
            # Создаем функцию обработки ответа
            def handle_response(response_telegram):
                # Преобразуем ответ в нужный формат
                return {
                    "subnet_id": response_telegram.get("source_subnet_id"),
                    "device_id": response_telegram.get("source_device_id"),
                    "operate_code": response_telegram.get("operate_code"),
                    "data": response_telegram.get("data", []),
                }
            
            # Создаем таймер для таймаута
            timeout_handle = self.hass.loop.call_later(
                timeout, 
                self._handle_timeout, 
                callback_key, 
                future
            )
            
            # Регистрируем callback
            self._callbacks[callback_key] = (handle_response, future, timeout_handle)
            
            # Отправляем сообщение через сетевой интерфейс
            success = await self._network_interface.send_telegram(telegram)
            if not success:
                _LOGGER.error(f"Не удалось отправить телеграмму для устройства {target_address[0]}.{target_address[1]}")
                self._callbacks.pop(callback_key, None)
                if timeout_handle:
                    timeout_handle.cancel()
                return None
                
            _LOGGER.debug(f"Отправка сообщения: subnet_id={target_address[0]}, "
                        f"device_id={target_address[1]}, opcode=0x{telegram['operate_code']:04X}")
            
            # Ожидаем результат с таймаутом
            try:
                return await asyncio.wait_for(future, timeout)
            except asyncio.TimeoutError:
                _LOGGER.warning(f"Таймаут при ожидании ответа от {target_address[0]}.{target_address[1]}")
                return {"status": "timeout"}
                
        except Exception as e:
            _LOGGER.error(f"Ошибка при отправке сообщения: {e}")
            return None

    async def _process_message(self, telegram):
        """Process incoming messages."""
        try:
            # Извлекаем данные из телеграммы
            source_subnet_id = telegram.get("source_subnet_id", 0)
            source_device_id = telegram.get("source_device_id", 0)
            operate_code = telegram.get("operate_code", 0)
            data = telegram.get("data", [])
            
            _LOGGER.debug(f"Обработка сообщения от {source_subnet_id}.{source_device_id}, код: 0x{operate_code:04X}, данные: {data}")
            
            # Обработка сообщения обнаружения устройств
            if operate_code == OPERATION_DISCOVERY and len(data) >= 2:
                # Получаем тип устройства из данных (первые два байта)
                device_type = (data[0] << 8) | data[1]
                _LOGGER.info(f"ОБНАРУЖЕНО УСТРОЙСТВО HDL: подсеть {source_subnet_id}, ID {source_device_id}, тип 0x{device_type:04X}")
                
                # Вывести дополнительную информацию о типе устройства
                device_info = {
                    "subnet_id": source_subnet_id,
                    "device_id": source_device_id,
                    "device_type": device_type,
                    "raw_data": data,
                    "receive_time": time.time(),
                }
                
                # Добавляем устройство в список для discovery
                if self.discovery_callback:
                    await self.discovery_callback(device_info)
                    _LOGGER.debug(f"Вызван callback обнаружения для устройства {source_subnet_id}.{source_device_id}")
                    
            # Обработка ответа на запрос статуса
            elif operate_code == OPERATION_READ_STATUS and len(data) >= 2:
                channel = data[0] if len(data) > 0 else 0
                value = data[1] if len(data) > 1 else 0
                
                # Формируем ключ для устройства
                device_key = f"{source_subnet_id}.{source_device_id}.{channel}"
                
                _LOGGER.debug(f"Получен статус устройства {device_key}: значение={value}")
                
                # Вызываем все зарегистрированные обратные вызовы для этого устройства
                if device_key in self._callbacks:
                    for callback_func in self._callbacks.get(device_key, []):
                        try:
                            if asyncio.iscoroutinefunction(callback_func):
                                await callback_func(source_subnet_id, source_device_id, channel, value, telegram)
                            else:
                                callback_func(source_subnet_id, source_device_id, channel, value, telegram)
                        except Exception as ex:
                            _LOGGER.error(f"Ошибка в обратном вызове для {device_key}: {ex}")
            
            # Обрабатываем другие типы сообщений
            else:
                # Оповещаем всех слушателей о полученном сообщении
                for listener in self._message_listeners:
                    try:
                        if asyncio.iscoroutinefunction(listener):
                            await listener(telegram)
                        else:
                            listener(telegram)
                    except Exception as ex:
                        _LOGGER.error(f"Ошибка при вызове слушателя сообщений: {ex}")
        
        except Exception as ex:
            _LOGGER.error(f"Ошибка при обработке сообщения: {ex}")
            import traceback
            _LOGGER.error(traceback.format_exc())

    def register_callback(self, subnet_id, device_id, channel, callback):
        """Регистрирует функцию обратного вызова для конкретного устройства."""
        device_key = f"{subnet_id}.{device_id}.{channel}"
        
        if device_key not in self._callbacks:
            self._callbacks[device_key] = []
            
        if callback not in self._callbacks[device_key]:
            self._callbacks[device_key].append(callback)
            _LOGGER.debug(f"Зарегистрирован обратный вызов для устройства {device_key}")
            
        # Запрашиваем текущее состояние устройства после регистрации колбэка
        self.send_hdl_command(subnet_id, device_id, OPERATION_READ_STATUS, [channel])
            
    def unregister_callback(self, subnet_id, device_id, channel, callback):
        """Удаляет функцию обратного вызова для устройства."""
        device_key = f"{subnet_id}.{device_id}.{channel}"
        
        if device_key in self._callbacks and callback in self._callbacks[device_key]:
            self._callbacks[device_key].remove(callback)
            _LOGGER.debug(f"Удален обратный вызов для устройства {device_key}")
            
            # Если список колбэков пуст, удаляем ключ
            if not self._callbacks[device_key]:
                del self._callbacks[device_key]

    async def _poll_devices(self, interval: timedelta) -> None:
        """Poll devices at regular intervals."""
        try:
            while self._running:
                _LOGGER.debug("Опрос устройств...")
                # Реализуем опрос всех устройств
                for device_key in self._callbacks:
                    try:
                        # Разбираем ключ устройства на составляющие
                        subnet_id, device_id, channel = device_key.split('.')
                        
                        # Отправляем запрос на чтение состояния
                        self.send_hdl_command(
                            int(subnet_id), 
                            int(device_id), 
                            OPERATION_READ_STATUS, 
                            [int(channel)]
                        )
                        
                        # Добавляем небольшую задержку между запросами
                        await asyncio.sleep(0.1)
                        
                    except Exception as ex:
                        _LOGGER.error(f"Ошибка при опросе устройства {device_key}: {ex}")
                
                # Обновляем время последнего обновления
                self._last_update = time.time()
                
                # Ждем до следующего опроса
                await asyncio.sleep(interval.total_seconds())
                
        except asyncio.CancelledError:
            _LOGGER.debug("Задача опроса устройств отменена")
        
        except Exception as err:
            _LOGGER.error(f"Ошибка при опросе устройств: {err}")

    async def _receive_data(self) -> None:
        """Receive data from UDP gateway."""
        sock = None
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind(("0.0.0.0", self.port))
            sock.setblocking(False)
            self._connected = True  # Устанавливаем флаг подключения
            _LOGGER.info(f"UDP сервер запущен на порту {self.port}")
            
            loop = asyncio.get_event_loop()
            
            while self._running:
                try:
                    data, addr = await loop.sock_recvfrom(sock, 1024)
                    
                    # Обрабатываем полученные данные
                    _LOGGER.debug(f"Получено сообщение от {addr}: {data.hex()}")
                    
                    # Передаем полученное сообщение на обработку
                    await self._process_message(data)
                    
                except (asyncio.CancelledError, GeneratorExit):
                    _LOGGER.debug("Получение данных отменено")
                    break
                except Exception as ex:
                    _LOGGER.error(f"Ошибка при получении данных: {ex}")
                    self._connected = False
                    await asyncio.sleep(1)  # Пауза перед повторным подключением
                    self._connected = True
        
        except Exception as ex:
            _LOGGER.error(f"Ошибка при настройке UDP сокета: {ex}")
            self._connected = False
        
        finally:
            if sock:
                sock.close()
            self._connected = False
            _LOGGER.info("UDP сервер остановлен") 

    def send_hdl_command(self, subnet_id, device_id, operation, data=None):
        """Отправка команды HDL устройству."""
        try:
            # Проверяем, что UDP клиент инициализирован
            if not self._udp_client:
                _LOGGER.error("UDP клиент не инициализирован. Не могу отправить команду.")
                return False
                
            # Формируем заголовок HDL сообщения
            header = bytearray([0x48, 0x44, 0x4C, 0x4D, 0x49, 0x52, 0x41, 0x43, 0x4C, 0x45, 0x42, 0x45, 0x41])
            
            # Подготавливаем данные команды
            command = bytearray([
                self.device_subnet_id,  # Наш subnet ID для отправителя
                subnet_id,              # Subnet ID получателя
                self.device_id,         # Наш device ID для отправителя
                device_id,              # Device ID получателя
                operation               # Код операции
            ])
            
            # Добавляем дополнительные данные, если они есть
            if data:
                if isinstance(data, list):
                    command.extend(data)
                else:
                    command.append(data)
            
            # Формируем полное сообщение
            message = header + command
            
            # Создаем телеграмму с правильными ключами
            telegram = {
                "target_subnet_id": subnet_id,    # Используем правильный ключ
                "target_device_id": device_id,    # Используем правильный ключ
                "source_subnet_id": self.device_subnet_id,
                "source_device_id": self.device_id,
                "operate_code": operation,
                "data": data if isinstance(data, list) else [data] if data is not None else []
            }
            
            # Отправляем телеграмму через сетевой интерфейс
            _LOGGER.debug(f"Отправка команды {operation:02x} для {subnet_id}.{device_id} через шлюз {self.gateway_host}:{self.gateway_port}")
            
            # Используем метод send_telegram через сетевой интерфейс
            self.hass.async_create_task(self._network_interface.send_telegram(telegram))
            return True
            
        except Exception as ex:
            _LOGGER.error(f"Ошибка при отправке команды: {ex}")
            return False

    async def send_telegram(self, telegram):
        """Отправить телеграмму HDL Buspro и ожидать ответа."""
        try:
            # Создаем уникальный ID запроса
            request_id = f"{telegram.get('target_subnet_id', 0)}.{telegram.get('target_device_id', 0)}.{telegram.get('operate_code', 0)}"
            
            _LOGGER.debug(f"Отправка телеграммы ID={request_id}: {telegram}")
            
            # Создаем future для ожидания ответа
            response_future = self.hass.loop.create_future()
            
            # Увеличиваем таймаут с 2 до 5 секунд
            timeout_value = 5
            
            # Ключ тайм-аута для отмены запроса по тайм-ауту
            timeout_handle = self.hass.loop.call_later(
                timeout_value, self._handle_telegram_timeout, request_id, response_future
            )
            
            # Сохранение ожидающего запроса
            self._pending_telegrams[request_id] = {
                "future": response_future,
                "timeout_handle": timeout_handle,
                "sent_at": time.time()
            }
            
            # Максимальное количество попыток отправки
            max_retries = 3
            retry_count = 0
            success = False
            
            # Пробуем отправить несколько раз с задержкой
            while retry_count < max_retries and not success:
                success = await self._network_interface.send_telegram(telegram)
                if success:
                    break
                
                retry_count += 1
                if retry_count < max_retries:
                    _LOGGER.debug(f"Retry {retry_count}/{max_retries} sending telegram to {telegram.get('target_subnet_id', 0)}.{telegram.get('target_device_id', 0)}")
                    await asyncio.sleep(0.5)  # Добавляем задержку между попытками
            
            if not success:
                # Очистка при неудаче отправки
                self._cleanup_pending_telegram(request_id)
                _LOGGER.error(f"Failed to send telegram to {telegram.get('target_subnet_id', 0)}.{telegram.get('target_device_id', 0)} after {max_retries} attempts")
                return None
            
            # Ожидание ответа
            try:
                response = await asyncio.wait_for(response_future, timeout=timeout_value)
                return response
            except asyncio.TimeoutError:
                _LOGGER.warning(f"Timeout waiting for response from {telegram.get('target_subnet_id', 0)}.{telegram.get('target_device_id', 0)}")
                return None
                
        except Exception as e:
            _LOGGER.error(f"Error sending telegram: {e}")
            import traceback
            _LOGGER.error(traceback.format_exc())
            return None

    def _handle_telegram_timeout(self, request_id, future):
        """Handle telegram request timeout."""
        if not future.done():
            future.set_exception(asyncio.TimeoutError(f"Telegram request {request_id} timed out"))
        self._cleanup_pending_telegram(request_id)
        
    def _cleanup_pending_telegram(self, request_id):
        """Clean up pending telegram request."""
        if request_id in self._pending_telegrams:
            pending = self._pending_telegrams.pop(request_id)
            if "timeout_handle" in pending and pending["timeout_handle"]:
                pending["timeout_handle"].cancel()

    async def _handle_received_data(self, data, sender_ip, sender_port):
        """Обработка полученных данных."""
        try:
            # Если данные пустые или короткие, игнорируем
            if not data or len(data) < 12:
                _LOGGER.debug(f"Получены некорректные данные от {sender_ip}:{sender_port}")
                return
                
            # Разбираем полученную телеграмму
            telegram = self.telegram_helper.parse_telegram(data)
            if not telegram:
                _LOGGER.debug(f"Не удалось разобрать телеграмму от {sender_ip}:{sender_port}")
                return
                
            # Логируем полученные данные
            source_subnet_id = telegram.get("source_subnet_id", 0)
            source_device_id = telegram.get("source_device_id", 0)
            operate_code = telegram.get("operate_code", 0)
            
            _LOGGER.debug(f"Получена телеграмма от {source_subnet_id}.{source_device_id}, код операции: 0x{operate_code:04X}")
            
            # Проверяем, является ли эта телеграмма ответом на ожидающий запрос
            # Пробуем найти подходящие запросы в нескольких вариантах
            request_ids = [
                # Точное совпадение subnet_id, device_id и operate_code
                f"{source_subnet_id}.{source_device_id}.{operate_code}",
                # Совпадение subnet_id, device_id с любым operate_code (для некоторых устройств)
                f"{source_subnet_id}.{source_device_id}.*",
                # Ответ на broadcast запрос с конкретным operate_code
                f"*.*.{operate_code}"
            ]
            
            found = False
            for request_id in request_ids:
                if request_id in self._pending_telegrams:
                    found = True
                    # Обрабатываем полученный ответ
                    self._handle_telegram_response(request_id, telegram)
                    break
                    
                # Проверяем шаблоны с wildcards
                if '*' in request_id:
                    pattern = request_id.replace('.', '\\.').replace('*', '.*')
                    import re
                    for pending_id in list(self._pending_telegrams.keys()):
                        if re.match(pattern, pending_id):
                            found = True
                            # Обрабатываем полученный ответ
                            self._handle_telegram_response(pending_id, telegram)
                            break
                    
                    if found:
                        break
            
            # Если это не ответ на запрос, обрабатываем сообщение как событие
            if not found:
                self._process_message(telegram)
                
        except Exception as e:
            _LOGGER.error(f"Ошибка при обработке полученных данных: {e}")
            import traceback
            _LOGGER.error(traceback.format_exc())

    async def register_for_discovery(self, callback):
        """Register callback for device discovery."""
        self.discovery_callback = callback
        _LOGGER.info(f"Зарегистрирован обработчик обнаружения устройств")
        
        # Отладочно выводим список всех зарегистрированных колбэков
        _LOGGER.debug(f"Callback для обнаружения: {callback}")
        _LOGGER.debug(f"Текущие колбэки для устройств: {self._callbacks.keys()}")
        
        return True

    def _handle_timeout(self, callback_key, future):
        """Handle timeout for message response."""
        # Удаляем callback
        self._callbacks.pop(callback_key, None)
        
        # Устанавливаем результат как таймаут, если future еще не выполнен
        if not future.done():
            future.set_result({"status": "timeout"}) 

    async def send_discovery_packet(self, subnet_id: int) -> bool:
        """Отправить пакет обнаружения устройств в подсети."""
        try:
            _LOGGER.info(f"Отправка пакета обнаружения для подсети {subnet_id}")
            
            # Создаем правильную телеграмму с необходимыми полями
            telegram = {
                "target_subnet_id": subnet_id,  # Явно указываем целевую подсеть
                "target_device_id": 0xFF,       # Broadcast в пределах подсети
                "source_subnet_id": self.device_subnet_id,
                "source_device_id": self.device_id,
                "operate_code": OPERATION_DISCOVERY,
                "data": []
            }
            
            # Отправляем пакет через сетевой интерфейс
            success = await self._network_interface.send_telegram(telegram)
            
            if not success:
                _LOGGER.error(f"Не удалось отправить пакет обнаружения для подсети {subnet_id}")
                
            return success
                
        except Exception as e:
            _LOGGER.error(f"Ошибка при отправке пакета обнаружения: {e}")
            import traceback
            _LOGGER.error(traceback.format_exc())
            return False 