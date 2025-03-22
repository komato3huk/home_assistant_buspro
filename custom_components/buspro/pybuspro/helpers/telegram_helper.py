"""Telegram helper for HDL Buspro protocol."""
from typing import Dict, Any, Tuple
import traceback
from struct import *

from .enums import DeviceType
from .generics import Generics
from ..core.telegram import Telegram
from ..devices.control import *


class TelegramHelper:
    """Helper class for HDL Buspro telegrams."""
    
    def build_telegram_from_udp_data(self, data: bytes, address: Tuple[str, int]) -> Dict[str, Any]:
        """Build telegram dictionary from UDP data."""
        # Basic validation
        if not data or len(data) < 7:
            return {}
            
        # Check header
        if data[0] != 0xAA or data[1] != 0xAA:
            return {}
            
        # Parse header
        subnet_id = data[2]
        device_id = data[3]
        operate_code = (data[4] << 8) | data[5]
        data_length = data[6]
        
        # Parse data
        payload = list(data[7:7+data_length]) if data_length > 0 else []
        
        # Create telegram
        telegram = {
            "source_address": address,
            "subnet_id": subnet_id,
            "device_id": device_id,
            "operate_code": operate_code,
            "data": payload
        }
        
        return telegram

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
        # If the telegram is a dictionary (legacy format), convert to bytes
        if isinstance(telegram, dict):
            subnet_id = telegram.get("subnet_id", 0)
            device_id = telegram.get("device_id", 0)
            operate_code = telegram.get("operate_code", 0)
            data = telegram.get("data", [])
            
            # Build packet
            packet = bytearray()
            
            # Header
            packet.extend([0xAA, 0xAA])
            
            # Address
            packet.append(subnet_id)
            packet.append(device_id)
            
            # Operation code (2 bytes)
            packet.append((operate_code >> 8) & 0xFF)
            packet.append(operate_code & 0xFF)
            
            # Data length
            packet.append(len(data))
            
            # Data
            packet.extend(data)
            
            # CRC (simple sum of all bytes)
            crc = sum(packet) & 0xFF
            packet.append(crc)
            
            return bytes(packet)
            
        # Handle Telegram object (newer format)
        send_buf = bytearray([192, 168, 1, 15])
        # noinspection SpellCheckingInspection
        send_buf.extend('HDLMIRACLE'.encode())
        send_buf.append(0xAA)
        send_buf.append(0xAA)

        if telegram is None:
            return None

        if telegram.payload is None:
            telegram.payload = []

        length_of_data_package = 11 + len(telegram.payload)
        send_buf.append(length_of_data_package)

        if telegram.source_address is not None:
            sender_subnet_id, sender_device_id = telegram.source_address
        else:
            sender_subnet_id = 200
            sender_device_id = 200

        send_buf.append(sender_subnet_id)
        send_buf.append(sender_device_id)

        if telegram.source_device_type is not None:
            source_device_type_hex = telegram.source_device_type.value
            send_buf.append(source_device_type_hex[0])
            send_buf.append(source_device_type_hex[1])
        else:
            send_buf.append(0)
            send_buf.append(0)

        operate_code_hex = telegram.operate_code.value
        send_buf.append(operate_code_hex[0])
        send_buf.append(operate_code_hex[1])

        target_subnet_id, target_device_id = telegram.target_address
        send_buf.append(target_subnet_id)
        send_buf.append(target_device_id)

        for byte in telegram.payload:
            send_buf.append(byte)

        crc_0, crc_1 = self._calculate_crc(length_of_data_package, send_buf)
        send_buf.append(crc_0)
        send_buf.append(crc_1)

        return send_buf

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
