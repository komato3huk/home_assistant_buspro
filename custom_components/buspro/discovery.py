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
            
            # Новые типы из списка пользователя
            0x0b21: "HDL-MPTL4C.48",      # Granite Display
            0x0b2c: "HDL-MPR0210-S.40",   # Power Interface- With 2CH 10A Relay
            0x0857: "HDL-MPR0210-E.40",   # 2CH 10A Flush-mounted Switching Actuator
            0x0dee: "HDL-MSD04T.40",      # 4 zone dry contact module with temp. sensor
            0x1637: "HDL-MHRCU-Ⅱ.433",    # RCU Room Control Unit
            
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
            0x012C: "HDL-WS4M",           # 4-клавишная настенная панель
            0x012D: "HDL-TS4M",           # 4-клавишная сенсорная панель
            0x012E: "HDL-TS8M",           # 8-клавишная сенсорная панель
            0x012F: "HDL-TS12M",          # 12-клавишная сенсорная панель
            0x0130: "HDL-MP6B",           # 6-кнопочная панель
            0x0131: "HDL-MP12B",          # 12-кнопочная панель
            
            # Контроллеры климата
            0x0073: "HDL-MFHC01.431",     # Контроллер теплого пола
            0x0174: "HDL-MPWPID01.48",    # Модуль управления вентиляторами (фанкойлами)
            0x0270: "HDL-MAC01.431",      # Модуль управления кондиционерами (Air Conditioner Module)
            0x0077: "HDL-DRY-4Z",         # Сухой контакт 4-зоны
            0x0175: "HDL-MTAC.433",       # Термостат
            0x0274: "HDL-MFAN01.432",     # Модуль управления вентиляторами
            0x0275: "HDL-MFAN02.432",     # Двухканальный модуль управления вентиляторами
            
            # Модули освещения
            0x0178: "HDL-MPDI06.40K",     # 6-канальный модуль диммера
            0x0251: "HDL-MD0X04.40",      # 4-канальный модуль диммера для светодиодов
            0x0254: "HDL-MLED02.40K",     # 2-канальный модуль управления LED
            0x0255: "HDL-MLED01.40K",     # 1-канальный модуль управления LED
            0x0260: "HDL-DN-DT0601",      # 6-канальный универсальный диммер
            0x026D: "HDL-MDT0601",        # 6-канальный диммер нового типа
            0x0272: "HDL-MLED04.40K",     # 4-канальный модуль управления LED
            0x0273: "HDL-MLED10.40K",     # 10-канальный модуль управления LED
            0x0179: "HDL-MPDI08.40K",     # 8-канальный модуль диммера
            0x017A: "HDL-MPDI12.40K",     # 12-канальный модуль диммера
            0x017B: "HDL-MD0104.40",      # 1-канальный диммер высокой мощности
            0x025E: "HDL-MDT0402",        # 4-канальный диммер
            0x025F: "HDL-MDT0602",        # 6-канальный диммер
            0x0261: "HDL-MDLED0605.432",  # 6-канальный LED-диммер
            0x0262: "HDL-MDLED0805.432",  # 8-канальный LED-диммер
            
            # Модули штор/роллет
            0x0180: "HDL-MW02.431",       # 2-канальный модуль управления шторами/жалюзи
            0x0182: "HDL-MW04.431",       # 4-канальный модуль управления шторами/жалюзи
            0x0181: "HDL-MW01.431",       # 1-канальный модуль управления шторами/жалюзи
            0x0183: "HDL-MW06.431",       # 6-канальный модуль управления шторами/жалюзи
            
            # Реле
            0x0188: "HDL-MR0810.433",     # 8-канальный релейный модуль 10A
            0x0189: "HDL-MR1610.431",     # 16-канальный релейный модуль 10A
            0x018A: "HDL-MR0416.432",     # 4-канальный релейный модуль 16A
            0x01AC: "HDL-R0816",          # 8-канальное реле
            0x0187: "HDL-MR0410.431",     # 4-канальный релейный модуль 10A
            0x018B: "HDL-MR0816.432",     # 8-канальный релейный модуль 16A
            0x01A1: "HDL-R1216",          # 12-канальное реле 16A
            0x01A2: "HDL-R2416",          # 24-канальное реле 16A
            0x0230: "HDL-MR1216.4C",      # 12-канальный релейный модуль
            
            # Сенсоры и мультисенсоры
            0x018C: "HDL-MSPU05.4C",      # Мультисенсор (движение, освещенность, ИК)
            0x018D: "HDL-MS05M.4C",       # Сенсор движения
            0x018E: "HDL-MS12.2C",        # 12-в-1 мультисенсор
            0x0134: "HDL-CMS-12in1",      # 12-в-1 датчик
            0x0135: "HDL-CMS-8in1",       # 8-в-1 датчик
            0x0150: "HDL-MSP07M",         # Мультисенсор
            0x0151: "HDL-MTS10.2WI",      # Датчик температуры
            0x0152: "HDL-MECO.4C",        # Датчик CO2
            0x0153: "HDL-MTHS.4C",        # Датчик температуры и влажности
            
            # Логика и безопасность
            0x0453: "HDL-DN-Logic960",    # Логический модуль
            0x0BE9: "HDL-DN-SEC250K",     # Модуль безопасности
            0x0BEA: "HDL-GSM.431",        # GSM модуль
            0x0BEB: "HDL-MCM08.431",      # Модуль управления безопасностью
            
            # Шлюзы и интерфейсы
            0x0192: "HDL-MBUS01.431",     # HDL Buspro интерфейс
            0x0195: "HDL-MNETC.431",      # Ethernet-HDL шлюз
            0x0196: "HDL-MWGW01.431",     # WiFi шлюз
            0x0197: "HDL-MGSM.431",       # GSM шлюз
            0x01A8: "HDL-MZONEC01.431",   # Шлюз мультизоны
            
            # DMX модули
            0x0210: "HDL-MDMX512.432",    # DMX512 интерфейс

            # Специальные и неизвестные типы 
            0xFFFE: "HDL-Custom",         # Кастомное устройство
            0xFFFF: "HDL-Unknown",        # Неизвестное устройство
        }
        
        return model_map.get(device_type, f"HDL-Unknown-0x{device_type:04X}")

    def _classify_device_by_type(self, device_type: int, subnet_id: int, device_id: int, model: str, name: str) -> Dict[str, Any]:
        """Классифицировать устройство по его типу."""
        # Определяем категорию устройства и количество каналов на основе типа
        
        # RCU - Room Control Unit (центр управления)
        if device_type == 0x1637:  # HDL-MHRCU-Ⅱ.433
            _LOGGER.info(f"Обнаружен модуль управления комнатой HDL-MHRCU-Ⅱ.433: {subnet_id}.{device_id}")
            # Модуль может управлять множеством функций, включая климат
            return {
                "category": CLIMATE,
                "channels": 1,
            }
        
        # Релейные модули скрытого монтажа и с интерфейсом питания
        elif device_type in [0x0857, 0x0b2c]:  # HDL-MPR0210-E.40, HDL-MPR0210-S.40
            _LOGGER.info(f"Обнаружен 2-канальный релейный модуль: {subnet_id}.{device_id} - {model}")
            # Эти модули имеют по 2 канала реле
            return {
                "category": SWITCH,
                "channels": 2,
            }
        
        # Модуль сухих контактов с датчиком температуры
        elif device_type == 0x0dee:  # HDL-MSD04T.40
            _LOGGER.info(f"Обнаружен модуль сухих контактов с датчиком температуры: {subnet_id}.{device_id}")
            
            # Добавляем сенсор температуры
            temp_device = {
                "subnet_id": subnet_id,
                "device_id": device_id,
                "channel": 1,
                "name": f"{name} Temp",
                "model": model,
                "type": "temperature",
            }
            self.devices[SENSOR].append(temp_device)
            
            # Добавляем 4 канала сухих контактов как бинарные сенсоры
            for i in range(1, 5):
                contact_device = {
                    "subnet_id": subnet_id,
                    "device_id": device_id,
                    "channel": i,
                    "name": f"{name} Contact {i}",
                    "model": model,
                    "type": "dry_contact",
                }
                self.devices[BINARY_SENSOR].append(contact_device)
            
            return {
                "category": BINARY_SENSOR,
                "channels": 4,
            }
        
        # Granite Display
        elif device_type == 0x0b21:  # HDL-MPTL4C.48
            _LOGGER.info(f"Обнаружен экран Granite Display: {subnet_id}.{device_id}")
            
            # Добавляем сенсор температуры для экрана
            temp_device = {
                "subnet_id": subnet_id,
                "device_id": device_id,
                "channel": 1,
                "name": f"{name} Temp",
                "model": model,
                "type": "temperature",
            }
            self.devices[SENSOR].append(temp_device)
            
            # Возвращаем тип климата, так как экраны управляют кондиционерами
            return {
                "category": CLIMATE,
                "channels": 1,
            }
        
        # DLP панели и интерфейсы управления
        elif device_type in [0x0028, 0x002A, 0x0086, 0x0095, 0x009C]:
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
        
        # Обычные панели управления
        elif device_type in [0x0010, 0x0011, 0x0012, 0x0013, 0x0014, 0x012B, 0x012C, 0x012D, 0x012E, 0x012F, 0x0130, 0x0131]:
            # Определяем количество кнопок/каналов в зависимости от модели
            buttons_map = {
                0x0010: 8,   # MPL8.48 - 8 кнопок
                0x0011: 4,   # MPL4.48 - 4 кнопки
                0x0012: 4,   # MPT4.46 - 4 кнопки
                0x0013: 4,   # MPE04.48 - 4 кнопки
                0x0014: 2,   # MP2B.48 - 2 кнопки
                0x012B: 8,   # WS8M - 8 кнопок
                0x012C: 4,   # WS4M - 4 кнопки
                0x012D: 4,   # TS4M - 4 кнопки
                0x012E: 8,   # TS8M - 8 кнопок
                0x012F: 12,  # TS12M - 12 кнопок
                0x0130: 6,   # MP6B - 6 кнопок
                0x0131: 12,  # MP12B - 12 кнопок
            }
            
            buttons_count = buttons_map.get(device_type, 4)
            
            # Добавляем каждую кнопку как двоичный сенсор
            for i in range(1, buttons_count + 1):
                button_device = {
                    "subnet_id": subnet_id,
                    "device_id": device_id,
                    "channel": i,
                    "name": f"{name} Button {i}",
                    "model": model,
                    "type": "button",
                }
                self.devices[BINARY_SENSOR].append(button_device)
            
            # Возвращаем BINARY_SENSOR как основной тип устройства
            return {
                "category": BINARY_SENSOR,
                "channels": buttons_count,
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
        elif device_type in [0x0178, 0x0179, 0x017A, 0x017B, 0x0251, 0x0254, 0x0255, 0x025E, 0x025F, 0x0260, 0x0261, 0x0262, 0x026D, 0x0272, 0x0273]:
            # Определяем количество каналов по типу устройства
            channels_map = {
                0x0178: 6,   # MPDI06.40K - 6 каналов
                0x0179: 8,   # MPDI08.40K - 8 каналов
                0x017A: 12,  # MPDI12.40K - 12 каналов
                0x017B: 1,   # MD0104.40 - 1 канал
                0x0251: 4,   # MD0X04.40 - 4 канала
                0x0254: 2,   # MLED02.40K - 2 канала
                0x0255: 1,   # MLED01.40K - 1 канал
                0x025E: 4,   # MDT0402 - 4 канала
                0x025F: 6,   # MDT0602 - 6 каналов
                0x0260: 6,   # DN-DT0601 - 6 каналов
                0x0261: 6,   # MDLED0605.432 - 6 каналов
                0x0262: 8,   # MDLED0805.432 - 8 каналов
                0x026D: 6,   # MDT0601 - 6 каналов
                0x0272: 4,   # MLED04.40K - 4 канала
                0x0273: 10,  # MLED10.40K - 10 каналов
            }
            return {
                "category": LIGHT,
                "channels": channels_map.get(device_type, 1),
            }
        
        # Релейные модули (выключатели)
        elif device_type in [0x0187, 0x0188, 0x0189, 0x018A, 0x018B, 0x01A1, 0x01A2, 0x01AC, 0x0230]:
            # Определяем количество каналов по типу устройства
            channels_map = {
                0x0187: 4,   # MR0410.431 - 4 канала
                0x0188: 8,   # MR0810.433 - 8 каналов
                0x0189: 16,  # MR1610.431 - 16 каналов
                0x018A: 4,   # MR0416.432 - 4 канала
                0x018B: 8,   # MR0816.432 - 8 каналов
                0x01A1: 12,  # R1216 - 12 каналов
                0x01A2: 24,  # R2416 - 24 канала
                0x01AC: 8,   # R0816 - 8 каналов
                0x0230: 12,  # MR1216.4C - 12 каналов
            }
            return {
                "category": SWITCH,
                "channels": channels_map.get(device_type, 8),
            }
        
        # Модули управления шторами/жалюзи
        elif device_type in [0x0180, 0x0181, 0x0182, 0x0183]:
            # Определяем количество каналов по типу устройства
            channels_map = {
                0x0180: 2,  # MW02.431 - 2 канала
                0x0181: 1,  # MW01.431 - 1 канал
                0x0182: 4,  # MW04.431 - 4 канала
                0x0183: 6,  # MW06.431 - 6 каналов
            }
            
            # Каждый канал управляет одной шторой/роллетой
            channels = channels_map.get(device_type, 1)
            for i in range(1, channels + 1):
                cover_device = {
                    "subnet_id": subnet_id,
                    "device_id": device_id,
                    "channel": i,
                    "name": f"{name} CH{i}",
                    "model": model,
                }
                self.devices[COVER].append(cover_device)
            
            return {
                "category": COVER,
                "channels": channels,
            }
        
        # Модули управления климатом
        elif device_type in [0x0073, 0x0174, 0x0175, 0x0270, 0x0274, 0x0275, 0x0077]:
            # Определяем количество каналов по типу устройства
            channels_map = {
                0x0073: 4,  # MFHC01.431 - до 4-х зон
                0x0174: 1,  # MPWPID01.48 - 1 канал
                0x0175: 1,  # MTAC.433 - 1 канал термостата
                0x0270: 1,  # MAC01.431 - 1 канал для управления кондиционером
                0x0274: 1,  # MFAN01.432 - 1 канал управления вентилятором
                0x0275: 2,  # MFAN02.432 - 2 канала управления вентиляторами
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
        
        # Сенсоры и мультисенсоры
        elif device_type in [0x018C, 0x018D, 0x018E, 0x0134, 0x0135, 0x0150, 0x0151, 0x0152, 0x0153]:
            # Создаем основное устройство как сенсор
            sensor_device = {
                "subnet_id": subnet_id,
                "device_id": device_id,
                "channel": 1,
                "name": name,
                "model": model,
                "type": "multisensor",
            }
            self.devices[SENSOR].append(sensor_device)
            
            # Добавляем датчик движения, если это мультисенсор
            if device_type in [0x018C, 0x018E, 0x0134, 0x0135, 0x0150]:
                motion_device = {
                    "subnet_id": subnet_id,
                    "device_id": device_id,
                    "channel": 2,
                    "name": f"{name} Motion",
                    "model": model,
                    "type": "motion",
                }
                self.devices[BINARY_SENSOR].append(motion_device)
            
            # Возвращаем тип сенсора
            return {
                "category": SENSOR,
                "channels": 1,
                "sensor_type": "multisensor",
            }
        
        # DMX модули
        elif device_type in [0x0210]:
            # DMX модули интегрируем как модули освещения
            return {
                "category": LIGHT,
                "channels": 6,  # Предполагаем 6 каналов по умолчанию
            }
        
        # Шлюзы и интерфейсы
        elif device_type in [0x0192, 0x0195, 0x0196, 0x0197, 0x01A8]:
            # Пока не добавляем шлюзы в устройства Home Assistant
            _LOGGER.info(f"Обнаружен шлюз/интерфейс: {model} ({subnet_id}.{device_id})")
            return None
        
        # Логика и безопасность
        elif device_type in [0x0453, 0x0BE9, 0x0BEA, 0x0BEB]:
            # Эти устройства пока не интегрируем с Home Assistant
            _LOGGER.info(f"Обнаружен модуль логики/безопасности: {model} ({subnet_id}.{device_id})")
            return None
        
        # Неизвестные типы устройств
        else:
            _LOGGER.warning(f"Неизвестный тип устройства: 0x{device_type:04X} ({subnet_id}.{device_id})")
            # Сохраняем неизвестный тип для отладки
            self.unknown_device_types.add(device_type)
            return None

    def add_known_devices(self):
        """Добавить известные устройства, которые могут не обнаруживаться автоматически."""
        _LOGGER.info("Добавление известных устройств HDL...")
        
        # Модули кондиционеров MAC01.431
        ac_modules = [
            {"subnet_id": 1, "device_id": 4, "name": "Dnevna plafon"},
            {"subnet_id": 1, "device_id": 5, "name": "Spavaca 1 plafonski"},
            {"subnet_id": 1, "device_id": 6, "name": "Spavaca 2 plafonski"},
            {"subnet_id": 1, "device_id": 7, "name": "Master soba plafonski"},
            {"subnet_id": 1, "device_id": 8, "name": "Podni k. dnevna soba"},
            {"subnet_id": 1, "device_id": 9, "name": "Podni k. master soba"},
            {"subnet_id": 1, "device_id": 10, "name": "Podni k. spavaca 1"},
            {"subnet_id": 1, "device_id": 11, "name": "Spavaca soba 2"}
        ]
        
        for ac in ac_modules:
            device_info = {
                "category": CLIMATE,
                "type": 0x0F47,  # MAC01.431
                "model": "HDL-MAC01.431",
                "name": ac["name"],
                "channels": 1,
                "subnet_id": ac["subnet_id"],
                "device_id": ac["device_id"],
                "features": ["temperature", "fan_speed", "mode"]
            }
            
            # Проверяем, что такого устройства еще нет в списке
            if not any(d.get("subnet_id") == ac["subnet_id"] and d.get("device_id") == ac["device_id"] for d in self.devices[CLIMATE]):
                _LOGGER.info(f"Добавлен кондиционер MAC01.431 с адресом {ac['subnet_id']}.{ac['device_id']} - {ac['name']}")
                self.devices[CLIMATE].append(device_info)
        
        # Модули штор MW02.431
        curtain_modules = [
            {"subnet_id": 1, "device_id": 2, "name": "Roletne 1", "channels": 2},
            {"subnet_id": 1, "device_id": 3, "name": "Roletne 2", "channels": 2}
        ]
        
        for curtain in curtain_modules:
            for i in range(1, curtain["channels"] + 1):
                device_info = {
                    "subnet_id": curtain["subnet_id"],
                    "device_id": curtain["device_id"],
                    "channel": i,
                    "name": f"{curtain['name']} CH{i}",
                    "model": "HDL-MW02.431",
                }
                
                # Проверяем, что такого устройства еще нет в списке
                if not any(d.get("subnet_id") == curtain["subnet_id"] and 
                           d.get("device_id") == curtain["device_id"] and
                           d.get("channel") == i for d in self.devices[COVER]):
                    _LOGGER.info(f"Добавлено устройство штор с адресом {curtain['subnet_id']}.{curtain['device_id']} канал {i} - {curtain['name']}")
                    self.devices[COVER].append(device_info)
        
        # Диммер MDT04015.532
        dimmer_info = {
            "subnet_id": 1,
            "device_id": 1,
            "name": "Dimer",
            "model": "HDL-MDT04015.532",
            "channels": 4
        }
        
        for i in range(1, dimmer_info["channels"] + 1):
            device_info = {
                "subnet_id": dimmer_info["subnet_id"],
                "device_id": dimmer_info["device_id"],
                "channel": i,
                "name": f"{dimmer_info['name']} CH{i}",
                "model": dimmer_info["model"],
            }
            
            # Проверяем, что такого устройства еще нет в списке
            if not any(d.get("subnet_id") == dimmer_info["subnet_id"] and 
                       d.get("device_id") == dimmer_info["device_id"] and
                       d.get("channel") == i for d in self.devices[LIGHT]):
                _LOGGER.info(f"Добавлен диммер канал {i} с адресом {dimmer_info['subnet_id']}.{dimmer_info['device_id']}")
                self.devices[LIGHT].append(device_info)
                
        # Granite Display - экраны управления
        granite_displays = [
            {"subnet_id": 1, "device_id": 18, "name": "Dnevna soba"},
            {"subnet_id": 1, "device_id": 17, "name": "Master soba"},
            {"subnet_id": 1, "device_id": 25, "name": "Spavaca soba 1"},
            {"subnet_id": 1, "device_id": 28, "name": "Spavaca soba 2"}
        ]
        
        for display in granite_displays:
            # Добавляем сенсор температуры для экрана
            temp_device = {
                "subnet_id": display["subnet_id"],
                "device_id": display["device_id"],
                "channel": 1,
                "name": f"{display['name']} Temp",
                "model": "HDL-MPTL4C.48",
                "type": "temperature",
            }
            
            # Проверяем, что такого устройства еще нет в списке
            if not any(d.get("subnet_id") == display["subnet_id"] and 
                       d.get("device_id") == display["device_id"] and
                       d.get("channel") == 1 and d.get("type") == "temperature" 
                       for d in self.devices[SENSOR]):
                _LOGGER.info(f"Добавлен сенсор температуры Granite Display с адресом {display['subnet_id']}.{display['device_id']} - {display['name']}")
                self.devices[SENSOR].append(temp_device)

        # 2-канальные релейные модули MPR0210-E.40 скрытой установки
        relay_modules = [
            {"subnet_id": 1, "device_id": 12, "name": "Dnevna soba 1"},
            {"subnet_id": 1, "device_id": 13, "name": "Dnevna soba 2"},
            {"subnet_id": 1, "device_id": 14, "name": "Spavaca soba 1-1"},
            {"subnet_id": 1, "device_id": 15, "name": "Spavaca soba 1-2"},
            {"subnet_id": 1, "device_id": 19, "name": "Spavaca soba 2-1"},
            {"subnet_id": 1, "device_id": 20, "name": "Spavaca soba 2-2"},
            {"subnet_id": 1, "device_id": 21, "name": "Master soba 1"},
            {"subnet_id": 1, "device_id": 22, "name": "Master soba 2"},
            {"subnet_id": 1, "device_id": 23, "name": "Kupatilo 1"},
            {"subnet_id": 1, "device_id": 24, "name": "Kupatilo 2"}
        ]
        
        for relay in relay_modules:
            # Каждый модуль имеет 2 канала
            for i in range(1, 3):
                device_info = {
                    "subnet_id": relay["subnet_id"],
                    "device_id": relay["device_id"],
                    "channel": i,
                    "name": f"{relay['name']} CH{i}",
                    "model": "HDL-MPR0210-E.40",
                }
                
                # Проверяем, что такого устройства еще нет в списке
                if not any(d.get("subnet_id") == relay["subnet_id"] and 
                           d.get("device_id") == relay["device_id"] and
                           d.get("channel") == i for d in self.devices[SWITCH]):
                    _LOGGER.info(f"Добавлен релейный модуль с адресом {relay['subnet_id']}.{relay['device_id']} канал {i} - {relay['name']}")
                    self.devices[SWITCH].append(device_info)

        # Модули сухих контактов MSD04T.40
        dry_contact_modules = [
            {"subnet_id": 1, "device_id": 30, "name": "Dnevna soba DC"},
            {"subnet_id": 1, "device_id": 31, "name": "Spavaca 1 DC"},
            {"subnet_id": 1, "device_id": 32, "name": "Spavaca 2 DC"},
            {"subnet_id": 1, "device_id": 33, "name": "Master soba DC"},
            {"subnet_id": 1, "device_id": 34, "name": "Kupatilo DC"},
            {"subnet_id": 1, "device_id": 35, "name": "Kuhinja DC"},
            {"subnet_id": 1, "device_id": 36, "name": "Hodnik DC"}
        ]
        
        for dc_module in dry_contact_modules:
            # Добавляем сенсор температуры
            temp_device = {
                "subnet_id": dc_module["subnet_id"],
                "device_id": dc_module["device_id"],
                "channel": 1,
                "name": f"{dc_module['name']} Temp",
                "model": "HDL-MSD04T.40",
                "type": "temperature",
            }
            
            # Проверяем, что такого устройства еще нет в списке
            if not any(d.get("subnet_id") == dc_module["subnet_id"] and 
                       d.get("device_id") == dc_module["device_id"] and
                       d.get("channel") == 1 and d.get("type") == "temperature" 
                       for d in self.devices[SENSOR]):
                _LOGGER.info(f"Добавлен сенсор температуры модуля сухих контактов с адресом {dc_module['subnet_id']}.{dc_module['device_id']} - {dc_module['name']}")
                self.devices[SENSOR].append(temp_device)
            
            # Добавляем 4 канала сухих контактов
            for i in range(1, 5):
                device_info = {
                    "subnet_id": dc_module["subnet_id"],
                    "device_id": dc_module["device_id"],
                    "channel": i,
                    "name": f"{dc_module['name']} Contact {i}",
                    "model": "HDL-MSD04T.40",
                    "type": "dry_contact",
                }
                
                # Проверяем, что такого устройства еще нет в списке
                if not any(d.get("subnet_id") == dc_module["subnet_id"] and 
                           d.get("device_id") == dc_module["device_id"] and
                           d.get("channel") == i and d.get("type") == "dry_contact" 
                           for d in self.devices[BINARY_SENSOR]):
                    _LOGGER.info(f"Добавлен сухой контакт с адресом {dc_module['subnet_id']}.{dc_module['device_id']} канал {i} - {dc_module['name']}")
                    self.devices[BINARY_SENSOR].append(device_info)

        # Модуль RCU (Room Control Unit)
        rcu_module = {
            "subnet_id": 1, 
            "device_id": 40, 
            "name": "Centralni upravljac",
            "model": "HDL-MHRCU-Ⅱ.433"
        }
        
        device_info = {
            "subnet_id": rcu_module["subnet_id"],
            "device_id": rcu_module["device_id"],
            "name": rcu_module["name"],
            "model": rcu_module["model"],
            "category": CLIMATE,
            "channels": 1
        }
        
        # Проверяем, что такого устройства еще нет в списке
        if not any(d.get("subnet_id") == rcu_module["subnet_id"] and 
                   d.get("device_id") == rcu_module["device_id"] 
                   for d in self.devices[CLIMATE]):
            _LOGGER.info(f"Добавлен модуль управления комнатой RCU с адресом {rcu_module['subnet_id']}.{rcu_module['device_id']} - {rcu_module['name']}")
            self.devices[CLIMATE].append(device_info)

# Создаем альтернативное имя для BusproDiscovery для обратной совместимости
DeviceDiscovery = BusproDiscovery 