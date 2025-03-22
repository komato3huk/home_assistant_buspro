"""HDL Buspro gateway module."""
import asyncio
import logging
import socket
import time
from datetime import timedelta
from typing import Any, Dict, List, Optional, Tuple

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from .const import (
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
        hass: HomeAssistant,
        discovery: BusproDiscovery,
        port: int = 10000,
        poll_interval: int = 30,
    ) -> None:
        """Initialize the gateway."""
        self.hass = hass
        self.discovery = discovery
        self.port = port
        self.poll_interval = poll_interval
        self._callbacks = {}
        self._polling_task = None
        self._running = False
        self._connected = False
        self._last_update = None

    async def start(self) -> None:
        """Start gateway."""
        if not self._polling_task:
            # Запускаем задачу опроса устройств
            self._polling_task = asyncio.create_task(
                self._poll_devices(timedelta(seconds=self.poll_interval))
            )
            _LOGGER.debug("Запущена задача опроса устройств")
            
            # Запускаем получение данных по UDP
            self._receive_task = asyncio.create_task(self._receive_data())
            _LOGGER.debug("Запущена задача получения данных по UDP")
            
            self._running = True

    async def stop(self) -> None:
        """Stop gateway."""
        self._running = False
        
        if self._polling_task:
            self._polling_task.cancel()
            try:
                await self._polling_task
            except asyncio.CancelledError:
                _LOGGER.debug("Задача опроса устройств успешно отменена")
            self._polling_task = None
            
        if hasattr(self, '_receive_task') and self._receive_task:
            self._receive_task.cancel()
            try:
                await self._receive_task
            except asyncio.CancelledError:
                _LOGGER.debug("Задача получения данных успешно отменена")
            self._receive_task = None
            
        self._connected = False
        _LOGGER.info("Шлюз HDL Buspro остановлен")

    @property
    def connected(self) -> bool:
        """Return True if gateway is connected."""
        return self._connected

    async def send_message(
        self,
        target_address: List[int],
        operation_code: List[int],
        data: List[int],
    ) -> Optional[List[int]]:
        """Send a message to a device and return the response."""
        if not self._connected:
            _LOGGER.error("Cannot send message: Gateway not connected")
            return None
            
        try:
            response = await self.hdl_device.send_message(
                target_address, operation_code, data
            )
            self._last_update = time.time()
            return response
        except Exception as err:
            _LOGGER.error("Failed to send message: %s", err)
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
                self._last_update = dt_util.utcnow()
                
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