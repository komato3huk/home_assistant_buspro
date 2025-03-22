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
        if not data or len(data) < 15:
            _LOGGER.error(f"Неверный формат данных UDP: {data}, длина: {len(data) if data else 0}")
            return None

        try:
            header = data[2:12].decode('ascii')
            if header != "HDLMIRACLE":
                _LOGGER.warning(f"Неверный заголовок пакета: {header}, полный пакет: {binascii.hexlify(data).decode()}")
                return None
            
            _LOGGER.debug(f"Обработка UDP пакета от {address if address else 'неизвестного источника'}: {binascii.hexlify(data).decode()}")
        except Exception as e:
            _LOGGER.error(f"Ошибка при чтении заголовка пакета: {e}, данные: {binascii.hexlify(data).decode()}")
            return None

        telegram = {}
        try:
            telegram["source_subnet_id"] = data[12]
            telegram["source_device_id"] = data[13]
            
            telegram["operate_code"] = (data[14] << 8) | data[15]
            
            telegram["target_subnet_id"] = data[16]
            telegram["target_device_id"] = data[17]
            
            data_length = len(data) - 20
            if data_length > 0:
                telegram["data"] = list(data[20:20 + data_length])
            else:
                telegram["data"] = []
                
            _LOGGER.debug(
                f"Telegram: Источник: {telegram['source_subnet_id']}.{telegram['source_device_id']}, "
                f"Код: 0x{telegram['operate_code']:04X}, "
                f"Цель: {telegram['target_subnet_id']}.{telegram['target_device_id']}, "
                f"Данные: {telegram['data']}"
            )
            
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

    # noinspection SpellCheckingInspection
    def build_send_buffer(self, telegram):
        """Build buffer from telegram for sending."""
        if not isinstance(telegram, dict):
            _LOGGER.error(f"Неверный формат телеграммы: {telegram}")
            return None
            
        try:
            if "subnet_id" not in telegram or "device_id" not in telegram:
                _LOGGER.error(f"В телеграмме отсутствуют обязательные поля: {telegram}")
                return None
                
            operate_code = telegram.get("operate_code", 0x0000)
            data = telegram.get("data", [])
            
            buffer = bytearray()
            
            buffer.extend(b'\x0A\x00\x50\x0A\x48\x44\x4C\x4D\x49\x52\x41\x43\x4C\x45')
            
            buffer.append(telegram.get("source_subnet_id", 0x01))
            buffer.append(telegram.get("source_device_id", 0x01))
            
            buffer.append((operate_code >> 8) & 0xFF)
            buffer.append(operate_code & 0xFF)
            
            buffer.append(telegram["subnet_id"])
            buffer.append(telegram["device_id"])
            
            data_length = len(data)
            buffer.append(data_length)
            
            if data_length > 0:
                buffer.extend(data)
                
            crc = 0
            for i in range(14, len(buffer)):
                crc += buffer[i]
            buffer.append((crc >> 8) & 0xFF)
            buffer.append(crc & 0xFF)
            
            _LOGGER.debug(f"Отправка телеграммы: {binascii.hexlify(buffer).decode()}")
            
            return buffer
            
        except Exception as e:
            _LOGGER.error(f"Ошибка при создании буфера отправки: {e}, телеграмма: {telegram}")
            return None

    def _calculate_crc(self, length_of_data_package, send_buf):
        crc_buf_length = length_of_data_package - 2
        crc_buf = send_buf[-crc_buf_length:]
        crc_buf_as_bytes = bytes(crc_buf)
        crc = self._crc16(crc_buf_as_bytes)

        return pack(">H", crc)

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
