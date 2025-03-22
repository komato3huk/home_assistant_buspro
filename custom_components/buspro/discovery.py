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

        # Очищаем предыдущие результаты обнаружения
        for device_type in self.devices:
            self.devices[device_type] = []

        # Запускаем реальное обнаружение устройств
        try:
            # Отправляем запрос обнаружения для каждой подсети от 1 до 254
            for current_subnet in range(1, 255):
                success = await self.send_discovery_packet(current_subnet)
                if success:
                    _LOGGER.debug(f"Запрос обнаружения отправлен в подсеть {current_subnet}")
                else:
                    _LOGGER.warning(f"Не удалось отправить запрос обнаружения в подсеть {current_subnet}")
                
                # Делаем небольшую паузу между запросами
                await asyncio.sleep(0.1)
            
            # Даем время устройствам ответить
            _LOGGER.info(f"Ожидаем ответы от устройств ({timeout} сек)...")
            await asyncio.sleep(timeout)
        
        except Exception as e:
            _LOGGER.error(f"Ошибка при обнаружении устройств: {e}")
            # Если произошла ошибка, используем симуляцию как запасной вариант
            _LOGGER.warning("Использую симуляцию обнаружения устройств в качестве запасного варианта")
            await self._simulated_discovery(subnet_id)

        # Логируем результаты обнаружения
        total_devices = sum(len(devices) for devices in self.devices.values())
        _LOGGER.info(f"Обнаружено устройств HDL Buspro: {total_devices}")
        for device_type, devices in self.devices.items():
            if devices:
                _LOGGER.info(f"- {device_type}: {len(devices)}")
                for device in devices:
                    _LOGGER.info(f"  * {device.get('name', 'Unnamed')} ({device.get('subnet_id')}.{device.get('device_id')}.{device.get('channel', 0)})")

        # Вызываем коллбеки для уведомления о завершении обнаружения
        for callback in self._callbacks:
            callback(self.devices)

        return self.devices

    async def _simulated_discovery(self, subnet_id: int):
        """Симуляция обнаружения устройств для тестирования."""
        # Очищаем предыдущие результаты обнаружения
        for device_type in self.devices:
            self.devices[device_type] = []
            
        # Добавляем устройства климат-контроля (теплый пол)
        self.devices[CLIMATE].extend([
            {
                "subnet_id": 1,
                "device_id": 4,
                "channel": 1,
                "name": "Теплый пол 1.4.1",
                "model": "HDL-MFHC01.431",
                "device_type": 0x0073,  # Тип устройства для Floor Heating Controller
            }
        ])

        # Добавляем контроллер штор (рольставни)
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

        # Добавляем сенсоры температуры
        self.devices[SENSOR].extend([
            {
                "subnet_id": 1,
                "device_id": 4,  # Тот же адрес, что и у климат-контроллера
                "channel": 1,
                "name": "Температура пола 1.4.1",
                "model": "HDL-MFHC01.431",
                "type": "temperature",
            }
        ])

        # Добавляем диммеры (освещение)
        self.devices[LIGHT].extend([
            {
                "subnet_id": subnet_id,
                "device_id": 2,
                "channel": 1,
                "name": f"Свет 1 {subnet_id}.2.1",
                "model": "HDL-MDT0402.433",  # Модель диммера
            },
            {
                "subnet_id": subnet_id,
                "device_id": 2,
                "channel": 2,
                "name": f"Свет 2 {subnet_id}.2.2",
                "model": "HDL-MDT0402.433",  # Модель диммера
            },
        ])

        # Добавляем реле (выключатели)
        self.devices[SWITCH].extend([
            {
                "subnet_id": subnet_id,
                "device_id": 5,
                "channel": 1,
                "name": f"Розетка 1 {subnet_id}.5.1",
                "model": "HDL-MR0810.433",  # Модель реле
            },
            {
                "subnet_id": subnet_id,
                "device_id": 5,
                "channel": 2,
                "name": f"Розетка 2 {subnet_id}.5.2",
                "model": "HDL-MR0810.433",  # Модель реле
            },
            {
                "subnet_id": subnet_id,
                "device_id": 5,
                "channel": 3,
                "name": f"Розетка 3 {subnet_id}.5.3",
                "model": "HDL-MR0810.433",  # Модель реле
            },
            {
                "subnet_id": subnet_id,
                "device_id": 5,
                "channel": 4,
                "name": f"Розетка 4 {subnet_id}.5.4",
                "model": "HDL-MR0810.433",  # Модель реле
            }
        ])

        # Добавляем бинарные сенсоры (датчики)
        self.devices[BINARY_SENSOR].extend([
            {
                "subnet_id": subnet_id,
                "device_id": 6,
                "channel": 1,
                "name": f"Датчик движения {subnet_id}.6.1",
                "model": "HDL-MSPU05.4C",  # Модель мультисенсора
            }
        ])
        
        _LOGGER.info(f"Результаты симулированного обнаружения устройств в подсети {subnet_id}:")
        for device_type, devices in self.devices.items():
            if devices:
                _LOGGER.info(f"- {device_type}: {len(devices)} устройств")
                for device in devices:
                    _LOGGER.info(f"  * {device['name']} ({device['subnet_id']}.{device['device_id']}.{device['channel']})")

        # Вызываем коллбеки для уведомления о завершении обнаружения
        for callback in self._callbacks:
            callback(self.devices)

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

    def _process_discovery_response(self, subnet_id: int, device_id: int, device_type: int, data: list) -> None:
        """Process a discovery response from a device.
        
        Args:
            subnet_id: Subnet ID устройства
            device_id: Device ID устройства
            device_type: Тип устройства (из данных ответа)
            data: Данные ответа
        """
        _LOGGER.debug(f"Обработка ответа на запрос обнаружения от устройства {subnet_id}.{device_id}, тип: 0x{device_type:04X}")
        
        # Определяем модель и название устройства на основе его типа
        model = self._get_model_by_type(device_type)
        base_name = f"HDL {subnet_id}.{device_id}"
        
        # Определяем тип устройства и количество каналов
        device_info = self._classify_device_by_type(device_type, subnet_id, device_id, model, base_name)
        
        if device_info:
            # Добавляем обнаруженное устройство в соответствующий список
            device_category = device_info["category"]
            channels = device_info["channels"]
            
            # Для многоканальных устройств добавляем каждый канал как отдельное устройство
            for channel in range(1, channels + 1):
                channel_device = {
                    "subnet_id": subnet_id,
                    "device_id": device_id,
                    "channel": channel,
                    "name": f"{base_name} CH{channel}",
                    "model": model,
                    "type": device_info.get("sensor_type", None),
                    "device_type": device_type
                }
                
                if device_category in self.devices:
                    self.devices[device_category].append(channel_device)
                    _LOGGER.debug(f"Добавлено устройство {device_category}: {channel_device['name']}")

    def _get_model_by_type(self, device_type: int) -> str:
        """Получить модель устройства по его типу."""
        # Мапинг известных типов устройств на модели
        model_map = {
            # Панели управления и DLP
            0x0010: "HDL-MPL8.48",        # 8-кнопочная панель
            0x0011: "HDL-MPL4.48",        # 4-кнопочная панель
            0x0012: "HDL-MPT4.46",        # 4-кнопочная сенсорная панель
            0x0013: "HDL-MPE04.48",       # 4-кнопочная европейская панель
            0x0014: "HDL-MP2B.48",        # 2-кнопочная панель
            0x0028: "HDL-DLP",            # DLP панель
            0x002A: "HDL-DLP-EU",         # Европейская DLP панель
            0x0086: "HDL-DLP2",           # DLP2 панель
            0x0095: "HDL-DLP-OLD",        # Старая DLP панель
            0x009C: "HDL-DLPv2",          # DLP v2 панель
            
            # Сенсорные экраны
            0x0100: "HDL-MPTL14.46",      # Сенсорный экран Granite
            0x01CC: "HDL-MPTLC43.46",     # Сенсорный экран Granite Classic 4.3"
            0x01CD: "HDL-MPTLC70.46",     # Сенсорный экран Granite Classic 7"
            0x03E8: "HDL-MPTL4.3.47",     # Сенсорный экран Granite Display 4.3"
            0x03E9: "HDL-MPTL7.47",       # Сенсорный экран Granite Display 7"
            
            # Сенсорные панели
            0x012B: "HDL-WS8M",           # 8-клавишная настенная панель
            
            # Контроллеры климата
            0x0073: "HDL-MFHC01.431",     # Контроллер теплого пола
            0x0174: "HDL-MPWPID01.48",    # Модуль управления вентиляторами (фанкойлами)
            0x0270: "HDL-MAC01.331",      # Модуль управления кондиционерами
            0x0077: "HDL-DRY-4Z",         # Сухой контакт 4-зоны
            
            # Модули освещения
            0x0178: "HDL-MPDI06.40K",     # 6-канальный модуль диммера
            0x0251: "HDL-MD0X04.40",      # 4-канальный модуль диммера для светодиодов
            0x0254: "HDL-MLED02.40K",     # 2-канальный модуль управления LED
            0x0255: "HDL-MLED01.40K",     # 1-канальный модуль управления LED
            0x0260: "HDL-DN-DT0601",      # 6-канальный универсальный диммер
            0x026D: "HDL-MDT0601",        # 6-канальный диммер нового типа
            
            # Модули штор/роллет
            0x0180: "HDL-MW02.431",       # 2-канальный модуль управления шторами/жалюзи
            0x0182: "HDL-MW04.431",       # 4-канальный модуль управления шторами/жалюзи
            
            # Реле
            0x0188: "HDL-MR0810.433",     # 8-канальный релейный модуль 10A
            0x0189: "HDL-MR1610.431",     # 16-канальный релейный модуль 10A
            0x018A: "HDL-MR0416.432",     # 4-канальный релейный модуль 16A
            0x01AC: "HDL-R0816",          # 8-канальное реле
            
            # Сенсоры и мультисенсоры
            0x018C: "HDL-MSPU05.4C",      # Мультисенсор (движение, освещенность, ИК)
            0x018D: "HDL-MS05M.4C",       # Сенсор движения
            0x018E: "HDL-MS12.2C",        # 12-в-1 мультисенсор
            0x0134: "HDL-CMS-12in1",      # 12-в-1 датчик
            0x0135: "HDL-CMS-8in1",       # 8-в-1 датчик
            0x0150: "HDL-MSP07M",         # Мультисенсор
            
            # Логика и безопасность
            0x0453: "HDL-DN-Logic960",    # Логический модуль
            0x0BE9: "HDL-DN-SEC250K",     # Модуль безопасности
            
            # Шлюзы и интерфейсы
            0x0192: "HDL-MBUS01.431",     # HDL Buspro интерфейс
            0x0195: "HDL-MNETC.431",      # Ethernet-HDL шлюз

            # Специальные и неизвестные типы 
            0xFFFE: "HDL-Custom",         # Кастомное устройство
            0xFFFF: "HDL-Unknown",        # Неизвестное устройство
        }
        
        return model_map.get(device_type, f"HDL-Unknown-0x{device_type:04X}")

    def _classify_device_by_type(self, device_type: int, subnet_id: int, device_id: int, model: str, name: str) -> Dict[str, Any]:
        """Классифицировать устройство по его типу."""
        # Определяем категорию устройства и количество каналов на основе типа
        
        # DLP панели и интерфейсы управления    
        if device_type in [0x0028, 0x002A, 0x0086, 0x0095, 0x009C]:  # DLP панели всех версий
            # Добавляем сенсор температуры для DLP
            temp_device = {
                "subnet_id": subnet_id,
                "device_id": device_id,
                "channel": 1,
                "name": f"{name} Temp",
                "model": model,
                "type": "temperature",
            }
            self.devices[SENSOR].append(temp_device)
            
            # Добавляем универсальные переключатели для DLP
            for i in range(1, 13):  # 12 страниц кнопок
                button_device = {
                    "subnet_id": subnet_id,
                    "device_id": device_id,
                    "channel": 100 + i,  # Универсальные переключатели начинаются с 100
                    "name": f"{name} Button {i}",
                    "model": model,
                    "type": "universal_switch",
                }
                self.devices[BINARY_SENSOR].append(button_device)
            
            # Возвращаем климат-контроль как основной тип устройства
            return {
                "category": CLIMATE,
                "channels": 1,
            }
        
        # Сенсорные экраны Granite (0x0100)
        elif device_type in [0x0100, 0x01CC, 0x01CD, 0x03E8, 0x03E9]:  # Все модели Granite
            # Добавляем сенсор температуры для экрана Granite
            temp_device = {
                "subnet_id": subnet_id,
                "device_id": device_id,
                "channel": 1,
                "name": f"{name} Temp",
                "model": model,
                "type": "temperature",
            }
            self.devices[SENSOR].append(temp_device)
            
            # Добавляем универсальные переключатели для страниц экрана Granite
            for i in range(1, 13):  # Предполагаем до 12 страниц
                button_device = {
                    "subnet_id": subnet_id,
                    "device_id": device_id,
                    "channel": 100 + i,  # Универсальные переключатели начинаются с 100
                    "name": f"{name} Page {i}",
                    "model": model,
                    "type": "universal_switch",
                }
                self.devices[BINARY_SENSOR].append(button_device)
            
            # Экраны Granite также могут управлять климатом, поэтому возвращаем CLIMATE
            return {
                "category": CLIMATE,
                "channels": 1,
            }
        
        # Диммеры освещения
        elif device_type in [0x0178, 0x0251, 0x0254, 0x0255, 0x0260, 0x026D]:
            # Определяем количество каналов по типу устройства
            channels_map = {
                0x0178: 6,  # MPDI06.40K - 6 каналов
                0x0251: 4,  # MD0X04.40 - 4 канала
                0x0254: 2,  # MLED02.40K - 2 канала
                0x0255: 1,  # MLED01.40K - 1 канал
                0x0260: 6,  # DN-DT0601 - 6 каналов
                0x026D: 6,  # MDT0601 - 6 каналов
            }
            return {
                "category": LIGHT,
                "channels": channels_map.get(device_type, 1),
            }
        
        # Релейные модули (выключатели)
        elif device_type in [0x0188, 0x0189, 0x018A, 0x01AC]:
            # Определяем количество каналов по типу устройства
            channels_map = {
                0x0188: 8,   # MR0810.433 - 8 каналов
                0x0189: 16,  # MR1610.431 - 16 каналов
                0x018A: 4,   # MR0416.432 - 4 канала
                0x01AC: 8,   # R0816 - 8 каналов
            }
            return {
                "category": SWITCH,
                "channels": channels_map.get(device_type, 8),
            }
        
        # Модули управления шторами/жалюзи
        elif device_type in [0x0180, 0x0182]:
            # Определяем количество каналов по типу устройства
            channels_map = {
                0x0180: 2,  # MW02.431 - 2 канала
                0x0182: 4,  # MW04.431 - 4 канала
            }
            return {
                "category": COVER,
                "channels": channels_map.get(device_type, 2),
            }
        
        # Модули управления системами отопления/охлаждения
        elif device_type in [0x0073, 0x0174, 0x0270, 0x0077]:
            # Определяем количество каналов по типу устройства
            channels_map = {
                0x0073: 4,  # MFHC01.431 - до 4-х зон
                0x0174: 1,  # MPWPID01.48 - 1 канал
                0x0270: 1,  # MAC01.331 - 1 канал
                0x0077: 4,  # DRY-4Z - 4 зоны (сухие контакты для климатического оборудования)
            }
            
            # Добавляем сенсоры температуры для этих устройств
            temp_device = {
                "subnet_id": subnet_id,
                "device_id": device_id,
                "channel": 1,
                "name": f"{name} Temp",
                "model": model,
                "type": "temperature",
            }
            self.devices[SENSOR].append(temp_device)
            
            return {
                "category": CLIMATE,
                "channels": channels_map.get(device_type, 1),
            }
        
        # Мультисенсоры
        elif device_type in [0x018C, 0x018D, 0x018E, 0x0134, 0x0135, 0x0150]:
            # Добавляем сенсор движения
            motion_device = {
                "subnet_id": subnet_id,
                "device_id": device_id,
                "channel": 1,
                "name": f"{name} Motion",
                "model": model,
                "type": "motion",
            }
            self.devices[BINARY_SENSOR].append(motion_device)
            
            # Добавляем сенсор освещенности
            lux_device = {
                "subnet_id": subnet_id,
                "device_id": device_id,
                "channel": 2,
                "name": f"{name} Lux",
                "model": model,
                "type": "illuminance",
            }
            self.devices[SENSOR].append(lux_device)
            
            # Для расширенного мультисенсора добавляем дополнительные сенсоры
            if device_type in [0x018E, 0x0134]:  # MS12.2C и CMS-12in1
                # Добавляем сенсор температуры
                temp_device = {
                    "subnet_id": subnet_id,
                    "device_id": device_id,
                    "channel": 3,
                    "name": f"{name} Temp",
                    "model": model,
                    "type": "temperature",
                }
                self.devices[SENSOR].append(temp_device)
                
                # Добавляем сенсор влажности
                humid_device = {
                    "subnet_id": subnet_id,
                    "device_id": device_id,
                    "channel": 4,
                    "name": f"{name} Humidity",
                    "model": model,
                    "type": "humidity",
                }
                self.devices[SENSOR].append(humid_device)
            
            # Возвращаем None, так как мы уже добавили устройства напрямую
            return None
        
        # Панели управления
        elif device_type in [0x0010, 0x0011, 0x0012, 0x0013, 0x0014]:
            # Определяем количество кнопок по типу устройства
            buttons_map = {
                0x0010: 8,  # MPL8.48 - 8 кнопок
                0x0011: 4,  # MPL4.48 - 4 кнопки
                0x0012: 4,  # MPT4.46 - 4 кнопки
                0x0013: 4,  # MPE04.48 - 4 кнопки
                0x0014: 2,  # MP2B.48 - 2 кнопки
            }
            
            channels = buttons_map.get(device_type, 4)
            
            # Добавляем кнопки как бинарные сенсоры для отслеживания нажатий
            for i in range(1, channels + 1):
                button_device = {
                    "subnet_id": subnet_id,
                    "device_id": device_id,
                    "channel": i,
                    "name": f"{name} Button {i}",
                    "model": model,
                    "type": "button",
                }
                self.devices[BINARY_SENSOR].append(button_device)
            
            # Возвращаем None, так как мы уже добавили устройства напрямую
            return None
        
        # Шлюзы и интерфейсы
        elif device_type in [0x0192, 0x0195]:
            # Не добавляем шлюзы и интерфейсы как устройства управления
            return None
        
        # Неизвестные типы устройств
        else:
            _LOGGER.warning(f"Неизвестный тип устройства: 0x{device_type:04X}")
            return {
                "category": BINARY_SENSOR,  # По умолчанию как бинарный сенсор
                "channels": 1,
            }

# Создаем альтернативное имя для BusproDiscovery для обратной совместимости
DeviceDiscovery = BusproDiscovery 