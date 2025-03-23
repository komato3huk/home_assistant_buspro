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
        # Хранение информации о неизвестных типах устройств
        self.unknown_device_types = set()
        self._callbacks = []

    async def add_callback(self, callback):
        """Register a callback function to be called when discovery is complete."""
        self._callbacks.append(callback)
        _LOGGER.debug(f"Добавлен callback для обнаружения устройств (всего: {len(self._callbacks)})")

    async def process_device_discovery(self, device_info):
        """Process device discovery info received from gateway."""
        try:
            subnet_id = device_info.get("subnet_id")
            device_id = device_info.get("device_id")
            device_type = device_info.get("device_type")
            raw_data = device_info.get("raw_data", [])
            
            _LOGGER.info(f"[DISCOVERY] Обработка устройства: {subnet_id}.{device_id}, тип: 0x{device_type:04X}")
            _LOGGER.debug(f"[DISCOVERY] Сырые данные: {raw_data}")
            
            # Получаем модель и название по типу устройства
            model = self._get_model_by_type(device_type)
            name = f"{model} {subnet_id}.{device_id}"
            
            _LOGGER.info(f"[DISCOVERY] Модель: {model}")
            
            # Классифицируем устройство по его типу
            device_info = self._classify_device_by_type(device_type, subnet_id, device_id, model, name)
            
            # Добавляем устройство отдельно в лог для наглядности
            _LOGGER.info(f"****************************************")
            _LOGGER.info(f"** УСТРОЙСТВО HDL: {name}")
            _LOGGER.info(f"** Адрес: {subnet_id}.{device_id}")
            _LOGGER.info(f"** Тип: 0x{device_type:04X}")
            _LOGGER.info(f"** Модель: {model}")
            
            if device_info:
                _LOGGER.info(f"** Категория: {device_info.get('category', 'Неизвестно')}")
                _LOGGER.info(f"** Каналы: {device_info.get('channels', 0)}")
                
                # Добавляем информацию о самом устройстве в устройства для Home Assistant
                device_category = device_info.get('category')
                channels = device_info.get('channels', 1)
                
                # Формируем уникальный ключ устройства для проверки наличия дубликатов
                device_key = f"{subnet_id}.{device_id}.{device_type}"
                
                if device_key in self._processed_devices:
                    _LOGGER.debug(f"[DISCOVERY] Устройство {device_key} уже обработано, пропускаем")
                else:
                    # Запоминаем, что это устройство уже обработано
                    if not hasattr(self, '_processed_devices'):
                        self._processed_devices = set()
                    self._processed_devices.add(device_key)
                    
                    _LOGGER.info(f"[DISCOVERY] Добавляем {channels} каналов устройства в категорию {device_category}")
            else:
                _LOGGER.warning(f"[DISCOVERY] Не удалось классифицировать устройство с типом 0x{device_type:04X}")
                
            _LOGGER.info(f"****************************************")
            
        except Exception as e:
            _LOGGER.error(f"Ошибка при обработке информации об обнаруженном устройстве: {e}")
            import traceback
            _LOGGER.error(traceback.format_exc())

    async def discover_devices(self, subnet_id: int = None, timeout: int = 10) -> Dict[str, List[Dict[str, Any]]]:
        """Discover HDL Buspro devices."""
        # Всегда включаем подсеть 1 независимо от настроек
        subnets_to_scan = [1]
        if subnet_id and subnet_id != 1:
            subnets_to_scan.append(subnet_id)
            
        _LOGGER.info(f"=====================================")
        _LOGGER.info(f"НАЧАЛО ПОИСКА УСТРОЙСТВ HDL BUSPRO")
        _LOGGER.info(f"Сканирование подсетей: {subnets_to_scan}")
        _LOGGER.info(f"Через шлюз: {self.gateway_host}:{self.gateway_port}")
        _LOGGER.info(f"=====================================")

        # Очищаем предыдущие результаты обнаружения
        for device_type in self.devices:
            self.devices[device_type] = []

        # Регистрируем обработчик обнаружения устройств в шлюзе
        await self.gateway.register_for_discovery(self.process_device_discovery)
        
        # Запускаем реальное обнаружение устройств
        try:
            # Сначала отправляем широковещательный запрос для обнаружения всех устройств
            await self._send_broadcast_discovery()
            
            # Даем время устройствам ответить
            await asyncio.sleep(2.0)
            
            # Затем перебираем все указанные подсети
            for current_subnet in subnets_to_scan:
                # Отправляем запрос на обнаружение всех устройств в подсети
                await self._send_subnet_discovery(current_subnet)
                
                # Даем время устройствам ответить
                await asyncio.sleep(1.0)
                
                # Повторяем запрос для надежности
                await self._send_subnet_discovery(current_subnet)
                await asyncio.sleep(1.0)
            
            # Еще раз отправляем широковещательный запрос
            await self._send_broadcast_discovery()
            
            # Даем время устройствам ответить
            _LOGGER.info(f"Ожидание ответов от устройств ({timeout} сек)...")
            
            # Ожидаем ответы от устройств с таймаутом
            for i in range(timeout):
                await asyncio.sleep(1)
                _LOGGER.debug(f"Ожидание ответов: прошло {i+1} сек из {timeout}...")
            
            # Добавляем известные устройства, если они не были обнаружены автоматически
            self.add_known_devices()
            
            # Выводим итоговую информацию
            found_devices = 0
            for device_type, devices in self.devices.items():
                if devices:
                    _LOGGER.info(f"Найдено устройств типа {device_type}: {len(devices)}")
                    found_devices += len(devices)
            
            _LOGGER.info(f"=====================================")
            _LOGGER.info(f"ПОИСК УСТРОЙСТВ HDL BUSPRO ЗАВЕРШЕН")
            _LOGGER.info(f"Всего найдено устройств: {found_devices}")
            _LOGGER.info(f"=====================================")
            
            return self.devices
            
        except Exception as e:
            _LOGGER.error(f"Ошибка при обнаружении устройств: {e}")
            import traceback
            _LOGGER.error(traceback.format_exc())
            return self.devices
            
    async def _send_broadcast_discovery(self):
        """Отправить широковещательный запрос обнаружения."""
        _LOGGER.info(f"Отправка широковещательного запроса обнаружения...")
        await self.send_discovery_packet(0xFF)
        
    async def _send_subnet_discovery(self, subnet_id):
        """Отправить запрос обнаружения для конкретной подсети."""
        _LOGGER.info(f"Отправка запроса обнаружения для подсети {subnet_id}...")
        await self.send_discovery_packet(subnet_id)

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

    async def send_discovery_packet(self, subnet_id: int) -> bool:
        """Send discovery packet to find devices in subnet."""
        try:
            _LOGGER.info(f"Отправка запроса обнаружения для подсети {subnet_id} через шлюз {self.gateway_host}:{self.gateway_port}")
            
            # Используем метод отправки обнаружения из шлюза
            if hasattr(self.gateway, 'send_discovery_packet'):
                return await self.gateway.send_discovery_packet(subnet_id)
            else:
                # Запасной вариант, если метод не найден
                operate_code = 0x000E  # "Device Discovery" в HDL Buspro
                
                # Создаем правильную телеграмму с необходимыми полями
                telegram = {
                    "target_subnet_id": subnet_id,  # Важно! Используем правильный ключ
                    "target_device_id": 0xFF,       # Broadcast
                    "source_subnet_id": self.device_subnet_id,
                    "source_device_id": self.device_id,
                    "operate_code": operate_code,
                    "data": []
                }
                
                # Отправляем телеграмму через шлюз
                if hasattr(self.gateway, 'send_telegram'):
                    return await self.gateway.send_telegram(telegram)
                else:
                    # Совсем запасной вариант для обратной совместимости
                    result = await self.gateway.send_message(
                        [subnet_id, 0xFF, 0, 0],  # target_address - broadcast для всей подсети
                        [operate_code >> 8, operate_code & 0xFF],  # операция обнаружения
                        [],  # пустые данные
                        timeout=3.0  # увеличенный таймаут
                    )
                    return result is not None
                
        except Exception as e:
            _LOGGER.error(f"Ошибка при отправке запроса обнаружения: {e}")
            import traceback
            _LOGGER.error(traceback.format_exc())
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
            0x0112: "HDL-MPTLX.46",       # Сенсорный экран Granite X-серия
            0x010D: "HDL-MPTLPro.46",     # Сенсорный экран Granite Pro-серия
            0x03E8: "HDL-MPTL4.3.47",     # Сенсорный экран Granite Display 4.3"
            0x03E9: "HDL-MPTL7.47",       # Сенсорный экран Granite Display 7"
            
            # Сенсорные панели
            0x012B: "HDL-WS8M",           # 8-клавишная настенная панель
            
            # Контроллеры климата
            0x0073: "HDL-MFHC01.431",     # Контроллер теплого пола
            0x0174: "HDL-MPWPID01.48",    # Модуль управления вентиляторами (фанкойлами)
            0x0270: "HDL-MAC01.431",      # Модуль управления кондиционерами (Air Conditioner Module)
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
        elif device_type in [0x0100, 0x01CC, 0x01CD, 0x0112, 0x010D, 0x03E8, 0x03E9]:  # Все модели Granite
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
                0x0180: 1,  # MW02.431 - 1 роллета (канал 1 управляется через каналы 1.1 и 1.2)
                0x0182: 4,  # MWM04.431 - 4 канала
            }
            
            # Специальная обработка для MW02.431
            if device_type == 0x0180:
                _LOGGER.info(f"Обнаружен модуль управления шторами MW02.431: {subnet_id}.{device_id}")
                # Для MW02.431 канал 1 = каналы 1.1 и 1.2 (открыть/закрыть)
                # Канал 2 = каналы 2.1 и 2.2 (открыть/закрыть)
                for i in range(1, channels_map[device_type] + 1):
                    cover_device = {
                        "subnet_id": subnet_id,
                        "device_id": device_id,
                        "channel": i,
                        "name": f"{name} {i}",
                        "model": model,
                        "open_channel": i * 2 - 1,  # 1 -> 1, 2 -> 3
                        "close_channel": i * 2,     # 1 -> 2, 2 -> 4
                    }
                    self.devices[COVER].append(cover_device)
                return {
                    "category": COVER,
                    "channels": channels_map.get(device_type, 1),
                }

            channels = channels_map.get(device_type, 1)
            for i in range(1, channels + 1):
                cover_device = {
                    "subnet_id": subnet_id,
                    "device_id": device_id,
                    "channel": i,
                    "name": f"{name} {i}",
                    "model": model,
                    "open_channel": i,
                    "close_channel": i,
                }
                self.devices[COVER].append(cover_device)
                
            return {
                "category": COVER,
                "channels": channels,
            }
        
        # Модули управления системами отопления/охлаждения
        elif device_type in [0x0073, 0x0174, 0x0270, 0x0077]:
            # Определяем количество каналов по типу устройства
            channels_map = {
                0x0073: 4,  # MFHC01.431 - до 4-х зон
                0x0174: 1,  # MPWPID01.48 - 1 канал
                0x0270: 1,  # MAC01.431 - 1 канал для управления кондиционером
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
            
            # Специальная обработка для MAC01.431 - модуль кондиционирования
            if device_type == 0x0270:
                _LOGGER.info(f"Найден модуль кондиционирования MAC01.431: {subnet_id}.{device_id}")
                
                # Создаем единое устройство в категории CLIMATE
                device_info = {
                    "category": CLIMATE,
                    "type": device_type,
                    "model": model,
                    "name": f"Fancoil {subnet_id}.{device_id}",
                    "channels": 1,  # Указываем, что это одно устройство
                    "subnet_id": subnet_id,
                    "device_id": device_id,
                    "features": ["temperature", "fan_speed", "mode"]
                }
                
                # Добавляем только одно устройство в список климатических устройств
                if not any(d["subnet_id"] == subnet_id and d["device_id"] == device_id for d in self.devices[CLIMATE]):
                    self.devices[CLIMATE].append(device_info)
                
                return device_info
            
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
            # Добавляем тип в множество неизвестных типов
            self.unknown_device_types.add(device_type)
            _LOGGER.warning(f"Неизвестный тип устройства: 0x{device_type:04X} (ID: {subnet_id}.{device_id})")
            return {
                "category": BINARY_SENSOR,  # По умолчанию как бинарный сенсор
                "channels": 1,
            }

    def add_known_devices(self):
        """Добавить известные устройства, которые могут не обнаруживаться автоматически."""
        _LOGGER.info("Добавление известных устройств HDL...")
        
        # Добавляем модуль управления кондиционером MAC01.431 для адреса 1.9
        device_info = {
            "category": CLIMATE,
            "type": 0x0270,  # MAC01.431
            "model": "HDL-MAC01.431",
            "name": "Кондиционер 1.9",
            "channels": 1,
            "subnet_id": 1,
            "device_id": 9,
            "features": ["temperature", "fan_speed", "mode"]
        }
        
        # Проверяем, что такого устройства еще нет в списке
        if not any(d.get("subnet_id") == 1 and d.get("device_id") == 9 for d in self.devices[CLIMATE]):
            _LOGGER.info(f"Добавлен кондиционер MAC01.431 с адресом 1.9")
            self.devices[CLIMATE].append(device_info)
        
        # Добавляем модуль управления кондиционером MAC01.431 для адреса 1.4
        device_info = {
            "category": CLIMATE,
            "type": 0x0270,  # MAC01.431
            "model": "HDL-MAC01.431",
            "name": "Кондиционер 1.4",
            "channels": 1,
            "subnet_id": 1,
            "device_id": 4,
            "features": ["temperature", "fan_speed", "mode"]
        }
        
        # Проверяем, что такого устройства еще нет в списке
        if not any(d.get("subnet_id") == 1 and d.get("device_id") == 4 for d in self.devices[CLIMATE]):
            _LOGGER.info(f"Добавлен кондиционер MAC01.431 с адресом 1.4")
            self.devices[CLIMATE].append(device_info)
            

# Создаем альтернативное имя для BusproDiscovery для обратной совместимости
DeviceDiscovery = BusproDiscovery 