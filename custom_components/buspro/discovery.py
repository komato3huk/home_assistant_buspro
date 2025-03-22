"""Discovery module for HDL Buspro."""
import logging
import asyncio
import socket
from typing import Dict, List, Any, Optional, Callable

from .const import (
    OPERATION_DISCOVERY,
    LIGHT,
    SWITCH,
    COVER,
    CLIMATE,
    SENSOR,
    BINARY_SENSOR,
)

_LOGGER = logging.getLogger(__name__)

class BusproDiscovery:
    """Class for HDL Buspro device discovery."""

    def __init__(
        self,
        hass,
        gateway_host: str,
        gateway_port: int = 6000,
        broadcast_address: str = "255.255.255.255",
        device_subnet_id: int = 0,
        device_id: int = 1,
    ):
        """Initialize the HDL Buspro discovery service."""
        self.hass = hass
        self.gateway_host = gateway_host
        self.gateway_port = gateway_port
        self.broadcast_address = broadcast_address
        self.device_subnet_id = device_subnet_id
        self.device_id = device_id
        self.devices = {
            LIGHT: [],
            SWITCH: [],
            COVER: [],
            CLIMATE: [],
            SENSOR: [],
            BINARY_SENSOR: [],
        }
        self._callbacks = []

    async def discover_devices(self, subnet_id: int = None, timeout: int = 5) -> Dict[str, List[Dict[str, Any]]]:
        """Discover HDL Buspro devices."""
        # Если subnet_id не указан, используем стандартную подсеть 1
        if subnet_id is None:
            subnet_id = 1

        _LOGGER.info(f"Начинаем поиск устройств HDL Buspro в подсети {subnet_id}...")

        # В реальной имплементации здесь будет отправка discovery-пакетов через UDP
        # и анализ ответов от устройств

        # Пока что имитируем поиск устройств с помощью предопределенного списка
        # В этом примере мы предполагаем, что у нас есть 3 реле, 2 диммера, и 1 контроллер штор

        # Очищаем список устройств перед обнаружением
        for device_type in self.devices:
            self.devices[device_type] = []

        # Симуляция обнаружения устройств
        # В реальном кейсе здесь будет отправка discovery-пакетов и обработка ответов
        await self._simulated_discovery(subnet_id)

        # Логируем результаты обнаружения
        total_devices = sum(len(devices) for devices in self.devices.values())
        _LOGGER.info(f"Обнаружено устройств HDL Buspro: {total_devices}")
        for device_type, devices in self.devices.items():
            if devices:
                _LOGGER.info(f"- {device_type}: {len(devices)}")

        # Вызываем коллбеки для уведомления о завершении обнаружения
        for callback in self._callbacks:
            callback(self.devices)

        return self.devices

    async def _simulated_discovery(self, subnet_id: int):
        """Симуляция обнаружения устройств для тестирования."""
        # В реальной имплементации здесь будет отправка discovery-пакетов
        # и обработка ответов

        # Добавляем реальное устройство климат-контроля
        self.devices[CLIMATE].extend([
            {
                "subnet_id": 1,
                "device_id": 4,
                "channel": 1,
                "name": "Теплый пол 1.4",
                "model": "HDL-MFHC01.431",
                "device_type": 0x0073,  # Тип устройства для Floor Heating Controller
            }
        ])

        # Добавляем контроллер штор
        self.devices[COVER].extend([
            {
                "subnet_id": 1,
                "device_id": 3,
                "channel": 1,
                "name": "Шторы гостиная",
                "model": "HDL-MW02.431",
            },
            {
                "subnet_id": 1,
                "device_id": 3,
                "channel": 2,
                "name": "Шторы спальня",
                "model": "HDL-MW02.431", 
            }
        ])

        # Добавляем сенсор температуры (необходим для отображения температуры)
        self.devices[SENSOR].extend([
            {
                "subnet_id": 1,
                "device_id": 4,  # Тот же адрес, что и у климат-контроллера
                "channel": 1,
                "name": "Температура пола 1.4",
                "model": "HDL-MFHC01.431",
                "type": "temperature",
            }
        ])

        # Эмулируем дополнительные устройства для тестирования
        # Добавляем диммеры (light)
        self.devices[LIGHT].extend([
            {
                "subnet_id": subnet_id,
                "device_id": 2,
                "channel": 1,
                "name": f"Свет 1 ({subnet_id}.2.1)",
                "model": "HDL-MDT0402.433",
            },
            {
                "subnet_id": subnet_id,
                "device_id": 2,
                "channel": 2,
                "name": f"Свет 2 ({subnet_id}.2.2)",
                "model": "HDL-MDT0402.433",
            },
        ])

        # Добавляем реле (switch)
        self.devices[SWITCH].extend([
            {
                "subnet_id": subnet_id,
                "device_id": 5,
                "channel": 1,
                "name": f"Розетка 1 ({subnet_id}.5.1)",
                "model": "HDL-MR0810.433",
            },
            {
                "subnet_id": subnet_id,
                "device_id": 5,
                "channel": 2,
                "name": f"Розетка 2 ({subnet_id}.5.2)",
                "model": "HDL-MR0810.433",
            },
        ])

        # Добавляем сенсор движения (binary_sensor)
        self.devices[BINARY_SENSOR].extend([
            {
                "subnet_id": subnet_id,
                "device_id": 6,
                "channel": 1,
                "name": f"Датчик движения ({subnet_id}.6.1)",
                "model": "HDL-MSPU05.433",
                "type": "motion",
            }
        ])

    def register_callback(self, callback: Callable):
        """Register a callback for device discovery."""
        self._callbacks.append(callback)

    def unregister_callback(self, callback: Callable):
        """Unregister a callback for device discovery."""
        if callback in self._callbacks:
            self._callbacks.remove(callback)

    def get_devices(self) -> Dict[str, List[Dict[str, Any]]]:
        """Get all discovered devices."""
        return self.devices

    def get_devices_by_type(self, device_type: str) -> List[Dict[str, Any]]:
        """Get devices by type."""
        return self.devices.get(device_type, [])

    def get_device_by_address(self, subnet_id: int, device_id: int, channel: int = None) -> Optional[Dict[str, Any]]:
        """Get a device by its address."""
        for device_type, devices in self.devices.items():
            for device in devices:
                if device["subnet_id"] == subnet_id and device["device_id"] == device_id:
                    if channel is None or device.get("channel") == channel:
                        return device
        return None

    async def send_discovery_packet(self, subnet_id: int = None) -> bool:
        """Send a discovery packet to find HDL Buspro devices."""
        try:
            # Если subnet_id не указан, используем стандартную подсеть 1
            if subnet_id is None:
                subnet_id = 1

            # Формируем discovery-пакет
            # Заголовок HDL
            header = bytearray([0x48, 0x44, 0x4C, 0x4D, 0x49, 0x52, 0x41, 0x43, 0x4C, 0x45, 0x42, 0x45, 0x41])
            
            # Данные пакета
            # [наш subnet_id, целевой subnet_id, наш device_id, целевой device_id, код операции]
            data = bytearray([
                self.device_subnet_id,  # Наш subnet_id (обычно 0 для контроллера)
                subnet_id,  # Целевой subnet_id
                self.device_id,  # Наш device_id (обычно 1 для контроллера)
                0xFF,  # Целевой device_id (0xFF для всех устройств)
                OPERATION_DISCOVERY >> 8,  # Старший байт кода операции
                OPERATION_DISCOVERY & 0xFF,  # Младший байт кода операции
                0x00  # Дополнительные данные (если нужны)
            ])
            
            packet = header + data
            
            # Создаем UDP сокет
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            
            try:
                # Отправляем пакет
                sock.sendto(packet, (self.broadcast_address, self.gateway_port))
                _LOGGER.debug(f"Отправлен discovery-пакет в подсеть {subnet_id}")
                
                return True
            finally:
                sock.close()
                
        except Exception as err:
            _LOGGER.error(f"Ошибка при отправке discovery-пакета: {err}")
            return False 

    def _process_discovery_response(self, subnet_id: int, device_id: int, device_type: int, discovery_data: bytes) -> None:
        """Process discovery response from a device."""
        try:
            _LOGGER.debug(f"Обработка ответа обнаружения от устройства {subnet_id}.{device_id}, тип: 0x{device_type:X}")
            
            # Получаем модель устройства и другие параметры из данных
            model = "HDL"  # По умолчанию
            
            # Определяем тип устройства на основе device_type
            if device_type == 0x0001:  # Пример: Реле
                self._add_device_to_type(SWITCH, subnet_id, device_id, model=model)
                # Добавляем несколько каналов для устройства
                for channel in range(1, 5):  # Предполагаем 4 канала
                    self._add_device_to_type(SWITCH, subnet_id, device_id, channel=channel, model=model)
            elif device_type == 0x0002:  # Пример: Диммер
                self._add_device_to_type(LIGHT, subnet_id, device_id, model=model)
                # Добавляем несколько каналов для устройства
                for channel in range(1, 3):  # Предполагаем 2 канала
                    self._add_device_to_type(LIGHT, subnet_id, device_id, channel=channel, model=model)
            elif device_type == 0x0003:  # Пример: Контроллер штор
                self._add_device_to_type(COVER, subnet_id, device_id, model=model)
                # Обычно один канал
                self._add_device_to_type(COVER, subnet_id, device_id, channel=1, model=model)
            elif device_type == 0x0004:  # Пример: Термостат
                self._add_device_to_type(CLIMATE, subnet_id, device_id, model=model)
                # Обычно один канал
                self._add_device_to_type(CLIMATE, subnet_id, device_id, channel=1, model=model)
            elif device_type == 0x0005:  # Пример: Сенсор
                self._add_device_to_type(SENSOR, subnet_id, device_id, model=model)
                # Различные типы сенсоров
                self._add_device_to_type(SENSOR, subnet_id, device_id, channel=1, type="temperature", model=model)
                self._add_device_to_type(SENSOR, subnet_id, device_id, channel=2, type="humidity", model=model)
                self._add_device_to_type(SENSOR, subnet_id, device_id, channel=3, type="illuminance", model=model)
                # Сенсор движения как бинарный сенсор
                self._add_device_to_type(BINARY_SENSOR, subnet_id, device_id, channel=1, type="motion", model=model)
            else:
                _LOGGER.debug(f"Неизвестный тип устройства: 0x{device_type:X} для {subnet_id}.{device_id}")
                
        except Exception as ex:
            _LOGGER.error(f"Ошибка при обработке ответа обнаружения от {subnet_id}.{device_id}: {ex}")
            
    def _add_device_to_type(self, device_type: str, subnet_id: int, device_id: int, channel: int = None, type: str = None, model: str = None) -> None:
        """Add device to specific type list."""
        # Проверяем, существует ли уже устройство с таким адресом
        device_exists = False
        for device in self.devices[device_type]:
            if device["subnet_id"] == subnet_id and device["device_id"] == device_id:
                if channel is not None and device.get("channel") == channel:
                    device_exists = True
                    break
        
        if not device_exists:
            device_info = {
                "subnet_id": subnet_id,
                "device_id": device_id,
                "model": model or "HDL",
            }
            
            if channel is not None:
                device_info["channel"] = channel
                
            if type is not None:
                device_info["type"] = type
                
            # Создаем удобное имя для устройства
            if channel is not None:
                if type is not None:
                    device_info["name"] = f"{type.capitalize()} {subnet_id}.{device_id}.{channel}"
                else:
                    device_info["name"] = f"{device_type.capitalize()} {subnet_id}.{device_id}.{channel}"
            else:
                device_info["name"] = f"{device_type.capitalize()} {subnet_id}.{device_id}"
                
            self.devices[device_type].append(device_info)
            _LOGGER.debug(f"Добавлено устройство {device_type}: {device_info['name']}") 