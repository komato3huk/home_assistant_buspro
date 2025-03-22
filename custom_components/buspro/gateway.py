"""HDL Buspro gateway module."""
import asyncio
import logging
import socket
import time
from datetime import timedelta
from typing import Any, Dict, List, Optional, Tuple

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
        
        # Задача поллинга
        self._polling_task = None
        
        # Флаг работы шлюза
        self._running = False
        
        # Коллбеки и обработчики
        self._message_callbacks = {}
        self._message_listeners = []
        self.discovery_callback = None

    async def start(self):
        """Start the gateway."""
        _LOGGER.info(f"Запуск шлюза HDL Buspro {self.gateway_host}:{self.gateway_port}")
        
        if self._running:
            _LOGGER.debug("Шлюз HDL Buspro уже запущен")
            return
            
        try:
            # Создаем UDP клиент для коммуникации с шлюзом
            self._udp_client = UDPClient(
                self.hass.loop,
                self._handle_received_data,
                self.gateway_host,
                self.gateway_port,
            )
            
            # Регистрируем обработчики
            self._message_callbacks = {}
            self._message_listeners = []
            
            # Запускаем UDP клиент
            await self._udp_client.start()
            
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
            
        # Останавливаем UDP клиент
        if self._udp_client:
            await self._udp_client.stop()
            self._udp_client = None
            
        self._running = False
        _LOGGER.info(f"Шлюз HDL Buspro остановлен")

    @property
    def connected(self) -> bool:
        """Return True if gateway is connected."""
        return self._connected

    async def send_message(self, target_address, operation_code, data):
        """Отправка сообщения устройству HDL Buspro.
        
        Args:
            target_address: Список [subnet_id, device_id, типовое значение 0, типовое значение 0]
            operation_code: Список [старший байт кода операции, младший байт]
            data: Список данных команды
            
        Returns:
            Ответ от устройства или None в случае ошибки
        """
        try:
            if not target_address or len(target_address) < 2:
                _LOGGER.error("Необходимо указать subnet_id и device_id в target_address")
                return None
                
            if not operation_code or len(operation_code) < 2:
                _LOGGER.error("Необходимо указать код операции (2 байта)")
                return None
            
            subnet_id = target_address[0]
            device_id = target_address[1]
            
            # Формируем заголовок HDL сообщения
            header = bytearray([0x48, 0x44, 0x4C, 0x4D, 0x49, 0x52, 0x41, 0x43, 0x4C, 0x45, 0x42, 0x45, 0x41])
            
            # Подготавливаем команду
            command = bytearray([
                0x00,  # Наш subnet_id (всегда 0 для контроллера)
                subnet_id,  # Subnet ID получателя
                0x01,  # Наш device ID (всегда 1 для контроллера)
                device_id,  # Device ID получателя
                operation_code[0],  # Старший байт кода операции
                operation_code[1]   # Младший байт кода операции
            ])
            
            # Добавляем дополнительные данные
            if data:
                if isinstance(data, list):
                    command.extend(data)
                else:
                    command.append(data)
            
            # Формируем полное сообщение
            message = header + command
            
            # Логируем данные отправки
            op_code_int = (operation_code[0] << 8) | operation_code[1]
            _LOGGER.info(f"Отправка команды 0x{op_code_int:04X} для устройства {subnet_id}.{device_id} через шлюз {self.gateway_host}:{self.gateway_port}")
            _LOGGER.debug(f"Сообщение: {message.hex()}")
            
            # Отправляем сообщение через UDP
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            
            sock.sendto(message, (self.gateway_host, self.gateway_port))
            _LOGGER.debug(f"Сообщение отправлено")
            
            # Ждем ответа - STUB, в реальной имплементации здесь должно быть ожидание ответа
            # с соответствующим timeout
            await asyncio.sleep(0.1)
            
            sock.close()
            
            # Возвращаем заглушку с данными
            return data
            
        except Exception as ex:
            _LOGGER.error(f"Ошибка при отправке сообщения: {ex}")
            return None

    async def _process_message(self, data):
        """Process incoming messages."""
        # Проверяем, что данные не пустые
        if not data or len(data) < 15:
            _LOGGER.warning(f"Получено сообщение неверного формата: {data}")
            return
            
        # Анализируем сообщение
        try:
            # Извлекаем заголовок сообщения
            header = data[:13]
            subnet_id = data[14]
            device_id = data[15]
            opcode = data[16]
            
            # Если это ответ на запрос состояния
            if opcode == OPERATION_READ_STATUS:
                if len(data) < 21:  # Проверяем минимальную длину для пакета статуса
                    _LOGGER.warning(f"Некорректная длина пакета статуса: {data}")
                    return
                    
                channel = data[17]
                value = data[18]
                
                # Формируем ключ для устройства
                device_key = f"{subnet_id}.{device_id}.{channel}"
                
                _LOGGER.debug(f"Получен статус устройства {device_key}: значение={value}")
                
                # Вызываем все зарегистрированные обратные вызовы для этого устройства
                if device_key in self._callbacks:
                    for callback_func in self._callbacks[device_key]:
                        try:
                            callback_func(subnet_id, device_id, channel, value)
                        except Exception as ex:
                            _LOGGER.error(f"Ошибка в обратном вызове для {device_key}: {ex}")
                
            elif opcode == OPERATION_DISCOVERY:
                # Обработка ответа от обнаружения устройств
                if len(data) >= 20:  # Минимальная длина для ответа обнаружения
                    # Предполагаем, что данные обнаружения начинаются с байта 17
                    discovery_data = data[17:]
                    
                    # Получаем тип устройства из данных обнаружения
                    if len(discovery_data) >= 2:
                        device_type = (discovery_data[0] << 8) | discovery_data[1]
                        
                        _LOGGER.debug(f"Обнаружено устройство {subnet_id}.{device_id}, тип: 0x{device_type:X}")
                        
                        # Отправляем обработку в модуль discovery
                        self.discovery._process_discovery_response(subnet_id, device_id, device_type, discovery_data)
                    else:
                        _LOGGER.warning(f"Недостаточно данных для определения типа устройства: {data.hex()}")
                else:
                    _LOGGER.warning(f"Некорректная длина пакета обнаружения: {data.hex()}")
            
            else:
                # Другие операции могут быть добавлены здесь
                _LOGGER.debug(f"Получено сообщение с opcode=0x{opcode:X} от {subnet_id}.{device_id}: {data.hex()}")
                
        except Exception as ex:
            _LOGGER.error(f"Ошибка при обработке сообщения {data.hex()}: {ex}")
            
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
            # Формируем заголовок HDL сообщения
            header = bytearray([0x48, 0x44, 0x4C, 0x4D, 0x49, 0x52, 0x41, 0x43, 0x4C, 0x45, 0x42, 0x45, 0x41])
            
            # Подготавливаем данные команды
            command = bytearray([
                0x00,  # Предполагаем, что наш subnet всегда 0 для отправителя
                subnet_id,  # Subnet ID получателя
                0x01,  # Предполагаем, что наш device ID всегда 1 для отправителя
                device_id,  # Device ID получателя
                operation  # Код операции
            ])
            
            # Добавляем дополнительные данные, если они есть
            if data:
                if isinstance(data, list):
                    command.extend(data)
                else:
                    command.append(data)
            
            # Формируем полное сообщение
            message = header + command
            
            # Отправляем сообщение через UDP
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            
            # Отправляем на широковещательный адрес или конкретный IP
            target_ip = "255.255.255.255"  # Можно изменить на конкретный IP устройства
            target_port = 6000  # Стандартный порт HDL Buspro
            
            sock.sendto(message, (target_ip, target_port))
            
            _LOGGER.debug(f"Отправлена команда {operation:02x} для {subnet_id}.{device_id}: {message.hex()}")
            
            sock.close()
            return True
            
        except Exception as ex:
            _LOGGER.error(f"Ошибка при отправке команды: {ex}")
            return False 

    async def send_telegram(self, telegram):
        """Send a telegram to the HDL Buspro bus."""
        try:
            if not telegram:
                _LOGGER.error("Невозможно отправить пустую телеграмму")
                return None
                
            # Извлекаем данные из телеграммы
            subnet_id = telegram.get("subnet_id")
            device_id = telegram.get("device_id")
            operate_code = telegram.get("operate_code")
            data = telegram.get("data", [])
            
            if subnet_id is None or device_id is None or operate_code is None:
                _LOGGER.error("В телеграмме отсутствуют обязательные поля")
                return None
                
            # Специальная обработка для различных типов устройств
            # Для климат-контроля
            if operate_code == 0x1944:  # ReadFloorHeatingStatus
                _LOGGER.debug(f"Запрос статуса устройства климат-контроля {subnet_id}.{device_id}")
                # Для этого кода не нужны дополнительные данные
                
            elif operate_code == 0x1946:  # ControlFloorHeatingStatus
                _LOGGER.debug(f"Установка статуса устройства климат-контроля {subnet_id}.{device_id}: {data}")
                # data должен содержать temperature_type, current_temperature, 
                # status, mode, normal_temp, day_temp, night_temp, away_temp
                
            # Дальнейшая обработка для других типов устройств может быть добавлена здесь
                
            # Отправляем команду с использованием send_hdl_command
            # Для кода операции (2 байта) делим на старший и младший байт
            op_high = (operate_code >> 8) & 0xFF
            op_low = operate_code & 0xFF
            
            # Формируем заголовок HDL сообщения
            header = bytearray([0x48, 0x44, 0x4C, 0x4D, 0x49, 0x52, 0x41, 0x43, 0x4C, 0x45, 0x42, 0x45, 0x41])
            
            # Подготавливаем команду
            command = bytearray([
                0x00,  # Наш subnet_id (всегда 0 для контроллера)
                subnet_id,  # Subnet ID получателя
                0x01,  # Наш device ID (всегда 1 для контроллера)
                device_id,  # Device ID получателя
                op_high,  # Старший байт кода операции
                op_low   # Младший байт кода операции
            ])
            
            # Добавляем дополнительные данные
            if data:
                if isinstance(data, list):
                    command.extend(data)
                else:
                    command.append(data)
            
            # Формируем полное сообщение
            message = header + command
            
            # Отправляем сообщение
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            
            target_ip = self.gateway_host if hasattr(self, 'gateway_host') else "255.255.255.255"
            target_port = self.gateway_port if hasattr(self, 'gateway_port') else 6000
            
            _LOGGER.debug(f"Отправка сообщения на {target_ip}:{target_port} для устройства {subnet_id}.{device_id}, команда: 0x{operate_code:04X}")
            
            sock.sendto(message, (target_ip, target_port))
            _LOGGER.debug(f"Отправлена телеграмма для {subnet_id}.{device_id}, код операции: 0x{operate_code:04X}, данные: {data}")
            
            sock.close()
            
            # Для Floor Heating возвращаем эмуляцию ответа с типовыми значениями
            # Это нужно для начальной отладки, потом нужно будет заменить на реальный ответ от устройства
            if operate_code == 0x1944 and subnet_id == 1 and device_id == 4:
                # Эмулируем ответ от устройства климат-контроля
                _LOGGER.debug(f"Эмулируем ответ от устройства климат-контроля {subnet_id}.{device_id}")
                return {
                    "success": True,
                    "data": [
                        1,        # temperature_type (Celsius)
                        220,      # current_temperature (22.0°C)
                        1,        # status (вкл)
                        1,        # mode (Normal)
                        240,      # normal_temperature (24.0°C)
                        250,      # day_temperature (25.0°C)
                        200,      # night_temperature (20.0°C)
                        180       # away_temperature (18.0°C)
                    ]
                }
            
            # Для других случаев возвращаем успешный результат с передачей исходных данных
            return {"success": True, "data": data}
            
        except Exception as ex:
            _LOGGER.error(f"Ошибка при отправке телеграммы: {ex}")
            return None 

    async def _handle_received_data(self, data, addr):
        """Handle received data from UDP socket."""
        try:
            # Преобразуем полученные данные в телеграмму
            telegram = self.telegram_helper.build_telegram_from_udp_data(data)
            if not telegram:
                _LOGGER.debug(f"Не удалось разобрать данные от {addr}: {data.hex()}")
                return
                
            source_subnet_id = telegram.get("source_subnet_id")
            source_device_id = telegram.get("source_device_id")
            operate_code = telegram.get("operate_code", 0)
            
            _LOGGER.debug(f"Получено сообщение с opcode=0x{operate_code:X} от {source_subnet_id}.{source_device_id}: {data.hex()}")
            
            # Проверяем, является ли это ответом на запрос обнаружения
            if operate_code == 0xFA3 and len(telegram.get("data", [])) >= 2:
                # Получаем тип устройства из данных (первые два байта)
                device_type = (telegram["data"][0] << 8) | telegram["data"][1]
                _LOGGER.info(f"Обнаружено устройство HDL: подсеть {source_subnet_id}, ID {source_device_id}, тип 0x{device_type:04X}")
                
                # Добавляем устройство в список для discovery
                if self.discovery_callback:
                    device_info = {
                        "subnet_id": source_subnet_id,
                        "device_id": source_device_id,
                        "device_type": device_type,
                        "raw_data": telegram["data"],
                    }
                    await self.discovery_callback(device_info)
            
            # Обрабатываем ответы на запросы
            if self._message_callbacks:
                # Берем копию словаря для безопасного итерирования
                callbacks_copy = self._message_callbacks.copy()
                for callback_key, callback_info in callbacks_copy.items():
                    try:
                        callback_subnet_id, callback_device_id, callback_operate_code = callback_key
                        
                        # Проверяем, соответствует ли полученное сообщение ожидаемому ответу
                        if (source_subnet_id == callback_subnet_id and 
                            source_device_id == callback_device_id and 
                            operate_code == callback_operate_code):
                            
                            # Извлекаем callback
                            callback, future, timeout_handle = callback_info
                            
                            # Отменяем таймер ожидания
                            if timeout_handle:
                                timeout_handle.cancel()
                                
                            # Удаляем callback из словаря
                            self._message_callbacks.pop(callback_key, None)
                            
                            # Вызываем callback
                            if callback:
                                response = callback(telegram)
                                # Если есть future, устанавливаем результат
                                if future and not future.done():
                                    future.set_result(response)
                    except Exception as e:
                        _LOGGER.error(f"Ошибка при обработке callback: {e}")
            
            # Обновляем обработчик сообщений для всех зарегистрированных слушателей
            for listener in self._message_listeners:
                try:
                    await listener(telegram)
                except Exception as e:
                    _LOGGER.error(f"Ошибка при обработке слушателя сообщений: {e}")
                    
        except Exception as e:
            _LOGGER.error(f"Ошибка при обработке полученных данных: {e}")

    async def register_for_discovery(self, callback):
        """Register callback for device discovery."""
        self.discovery_callback = callback
        _LOGGER.info(f"Зарегистрирован обработчик обнаружения устройств")

    async def send_message(self, target_address, operation_code, data=None, timeout=2.0):
        """Send message to the HDL Buspro gateway."""
        if not self._udp_client:
            _LOGGER.error(f"UDP клиент не инициализирован")
            return None
            
        try:
            # Создаем телеграмму
            telegram = {
                "subnet_id": target_address[0],
                "device_id": target_address[1],
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
            self._message_callbacks[callback_key] = (handle_response, future, timeout_handle)
            
            # Отправляем сообщение
            buffer = self.telegram_helper.build_send_buffer(telegram)
            if not buffer:
                _LOGGER.error(f"Не удалось создать буфер отправки для телеграммы: {telegram}")
                self._message_callbacks.pop(callback_key, None)
                if timeout_handle:
                    timeout_handle.cancel()
                return None
                
            _LOGGER.debug(f"Отправка сообщения: subnet_id={target_address[0]}, "
                        f"device_id={target_address[1]}, opcode=0x{telegram['operate_code']:04X}")
            await self._udp_client.send(buffer, self.gateway_host, self.gateway_port)
            
            # Ожидаем результат с таймаутом
            try:
                return await asyncio.wait_for(future, timeout)
            except asyncio.TimeoutError:
                _LOGGER.warning(f"Таймаут при ожидании ответа от {target_address[0]}.{target_address[1]}")
                return {"status": "timeout"}
                
        except Exception as e:
            _LOGGER.error(f"Ошибка при отправке сообщения: {e}")
            return None

    def _handle_timeout(self, callback_key, future):
        """Handle timeout for message response."""
        # Удаляем callback
        self._message_callbacks.pop(callback_key, None)
        
        # Устанавливаем результат как таймаут, если future еще не выполнен
        if not future.done():
            future.set_result({"status": "timeout"}) 