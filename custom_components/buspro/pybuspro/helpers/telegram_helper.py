"""Telegram helper for HDL Buspro protocol."""
from typing import Dict, Any, Tuple
import traceback
from struct import *
import logging
import binascii

from .enums import DeviceType
from .generics import Generics
from ..core.telegram import Telegram
from ..devices.control import *

_LOGGER = logging.getLogger(__name__)

class TelegramHelper:
    """Helper class for working with HDL Buspro telegrams."""
    
    def build_telegram_from_udp_data(self, data: bytes, address: Tuple[str, int] = None) -> Dict[str, Any]:
        """Build telegram dictionary from UDP data."""
        if not data:
            _LOGGER.error(f"Пустые данные UDP")
            return None
            
        # Проверяем минимальный размер пакета
        min_length = 15
        if len(data) < min_length:
            _LOGGER.error(f"Неверный формат данных UDP: длина {len(data)} < {min_length}")
            return None

        try:
            # Проверяем и декодируем заголовок
            # Пытаемся найти сигнатуру 'HDLMIRACLE'
            header_start = 2
            header_length = 10
            
            if header_start + header_length <= len(data):
                header = data[header_start:header_start + header_length].decode('ascii', errors='ignore')
                if "HDLMIRACLE" not in header:
                    # Пробуем найти сигнатуру в других позициях
                    header_found = False
                    for i in range(0, min(20, len(data) - header_length)):
                        test_header = data[i:i + header_length].decode('ascii', errors='ignore')
                        if "HDLMIRACLE" in test_header:
                            header_start = i
                            header = test_header
                            header_found = True
                            _LOGGER.debug(f"Нестандартная позиция заголовка: {header_start}")
                            break
                    
                    if not header_found:
                        _LOGGER.warning(f"Неверный заголовок пакета, не найден 'HDLMIRACLE': {binascii.hexlify(data).decode()}")
                        # Для отладки выводим все возможные интерпретации строк в пакете
                        for i in range(0, len(data) - 3):
                            try:
                                test_str = data[i:i+10].decode('ascii', errors='ignore')
                                if any(c.isalpha() for c in test_str):
                                    _LOGGER.debug(f"Возможный заголовок с позиции {i}: {test_str}")
                            except:
                                pass
                        return None
            else:
                _LOGGER.warning(f"Данные слишком короткие для заголовка: {binascii.hexlify(data).decode()}")
                return None
            
            _LOGGER.debug(f"Обработка UDP пакета от {address if address else 'неизвестного источника'}: {binascii.hexlify(data).decode()}")
        except Exception as e:
            _LOGGER.error(f"Ошибка при чтении заголовка пакета: {e}, данные: {binascii.hexlify(data).decode()}")
            import traceback
            _LOGGER.error(traceback.format_exc())
            return None

        telegram = {}
        try:
            # Стандартные позиции после заголовка HDLMIRACLE
            source_subnet_pos = header_start + header_length
            source_device_pos = source_subnet_pos + 1
            operate_code_high_pos = source_device_pos + 1
            operate_code_low_pos = operate_code_high_pos + 1
            target_subnet_pos = operate_code_low_pos + 1
            target_device_pos = target_subnet_pos + 1
            
            # Проверяем, что у нас достаточно данных для извлечения всех полей
            if target_device_pos + 1 > len(data):
                _LOGGER.warning(f"Недостаточно данных для декодирования телеграммы: {binascii.hexlify(data).decode()}")
                return None
            
            telegram["source_subnet_id"] = data[source_subnet_pos]
            telegram["source_device_id"] = data[source_device_pos]
            
            telegram["operate_code"] = (data[operate_code_high_pos] << 8) | data[operate_code_low_pos]
            
            telegram["target_subnet_id"] = data[target_subnet_pos]
            telegram["target_device_id"] = data[target_device_pos]
            
            # Определяем, где начинаются полезные данные
            data_start = target_device_pos + 1
            
            # Если есть байт длины данных, считываем его
            if data_start < len(data):
                data_length = data[data_start]
                data_start += 1
                
                # Проверяем, что данные не выходят за пределы пакета
                if data_start + data_length <= len(data):
                    telegram["data"] = list(data[data_start:data_start + data_length])
                else:
                    # Берем все оставшиеся данные, если длина указана некорректно
                    telegram["data"] = list(data[data_start:])
            else:
                telegram["data"] = []
                
            _LOGGER.debug(
                f"Telegram: Источник: {telegram['source_subnet_id']}.{telegram['source_device_id']}, "
                f"Код: 0x{telegram['operate_code']:04X}, "
                f"Цель: {telegram['target_subnet_id']}.{telegram['target_device_id']}, "
                f"Данные: {telegram['data']}"
            )
            
            # Особая обработка для пакетов с кодом обнаружения устройств
            if telegram["operate_code"] == 0xFA3:
                device_type = 0
                if len(telegram["data"]) >= 2:
                    device_type = (telegram["data"][0] << 8) | telegram["data"][1]
                _LOGGER.info(
                    f"Обнаружено устройство: {telegram['source_subnet_id']}.{telegram['source_device_id']}, "
                    f"Тип: 0x{device_type:04X}, "
                    f"Данные: {telegram['data']}"
                )
                
            return telegram
            
        except Exception as e:
            _LOGGER.error(f"Ошибка при разборе телеграммы: {e}, данные: {binascii.hexlify(data).decode()}")
            import traceback
            _LOGGER.error(traceback.format_exc())
            return None

    @staticmethod
    def replace_none_values(telegram: Telegram):
        if telegram is None:
            return None
        if telegram.payload is None:
            telegram.payload = []
        if telegram.source_address is None:
            telegram.source_address = [200, 200]
        if telegram.source_device_type is None:
            telegram.source_device_type = DeviceType.PyBusPro
        return telegram

    def build_send_buffer(self, telegram: Dict[str, Any]) -> bytes:
        """Build send buffer from telegram dictionary.
        
        Args:
            telegram: Telegram dictionary with target_subnet_id, target_device_id, etc.
            
        Returns:
            bytes: Send buffer for UDP transmission
        """
        try:
            if not isinstance(telegram, dict):
                _LOGGER.error(f"Неверный формат телеграммы, ожидался словарь: {telegram}")
                return None
                
            # Проверяем наличие необходимых полей
            required_fields = ["target_subnet_id", "target_device_id", "operate_code"]
            for field in required_fields:
                if field not in telegram:
                    _LOGGER.error(f"В телеграмме отсутствует обязательное поле: {field}")
                    return None
                    
            # Получаем значения полей
            source_subnet_id = telegram.get("source_subnet_id", 1)
            source_device_id = telegram.get("source_device_id", 1)
            operate_code = telegram.get("operate_code", 0)
            target_subnet_id = telegram.get("target_subnet_id")
            target_device_id = telegram.get("target_device_id")
            data = telegram.get("data", [])
            
            # Проверяем, что data - это список
            if not isinstance(data, list):
                try:
                    data = list(data)
                except (TypeError, ValueError):
                    _LOGGER.error(f"Не удалось преобразовать данные в список: {data}")
                    data = []
            
            # Создаем буфер отправки
            buffer = bytearray()
            
            # Добавляем заголовок
            buffer.extend(b"\xAA\xAA")  # Начальные байты
            buffer.extend(b"HDLMIRACLE") # Сигнатура
            
            # Добавляем адрес источника
            buffer.append(source_subnet_id & 0xFF)
            buffer.append(source_device_id & 0xFF)
            
            # Добавляем код операции (2 байта)
            buffer.append((operate_code >> 8) & 0xFF)
            buffer.append(operate_code & 0xFF)
            
            # Добавляем адрес назначения
            buffer.append(target_subnet_id & 0xFF)
            buffer.append(target_device_id & 0xFF)
            
            # Добавляем длину данных и сами данные
            buffer.append(len(data) & 0xFF)
            buffer.extend(data)
            
            # Добавляем CRC
            crc = self._calculate_crc(buffer)
            buffer.append(crc & 0xFF)
            
            _LOGGER.debug(
                f"Создан буфер отправки: {binascii.hexlify(buffer).decode()}, "
                f"Источник: {source_subnet_id}.{source_device_id}, "
                f"Код: 0x{operate_code:04X}, "
                f"Цель: {target_subnet_id}.{target_device_id}, "
                f"Данные: {data}"
            )
            
            return bytes(buffer)
            
        except Exception as e:
            _LOGGER.error(f"Ошибка при создании буфера отправки: {e}")
            import traceback
            _LOGGER.error(traceback.format_exc())
            return None
            
    def _calculate_crc(self, buffer: bytearray) -> int:
        """Calculate CRC for buffer.
        
        Args:
            buffer: Buffer to calculate CRC for
            
        Returns:
            int: CRC value
        """
        crc = 0
        for i in range(len(buffer)):
            crc += buffer[i]
        return crc & 0xFF

    def _calculate_crc_from_telegram(self, telegram):
        length_of_data_package = 11 + len(telegram.payload)
        crc_buf_length = length_of_data_package - 2
        send_buf = telegram.udp_data[:-2]
        crc_buf = send_buf[-crc_buf_length:]
        crc_buf_as_bytes = bytes(crc_buf)
        crc = self._crc16(crc_buf_as_bytes)
        
        return pack(">H", crc)

    def _check_crc(self, telegram):
        # crc = data[-2:]
        calculated_crc = self._calculate_crc_from_telegram(telegram)
        if calculated_crc == telegram.crc:
            return True
        return False

    @staticmethod
    def _crc16(data: bytes):
        xor_in = 0x0000  # initial value
        xor_out = 0x0000  # final XOR value
        poly = 0x1021  # generator polinom (normal form)
    
        reg = xor_in
        for octet in data:
            # reflect in
            for i in range(8):
                topbit = reg & 0x8000
                if octet & (0x80 >> i):
                    topbit ^= 0x8000
                reg <<= 1
                if topbit:
                    reg ^= poly
            reg &= 0xFFFF
            # reflect out
        return reg ^ xor_out
