"""HDL Buspro device discovery implementation."""
import logging
from typing import Dict, List, Optional

from .const import DOMAIN, OPERATION_READ_STATUS
from .pybuspro.core.hdl_device import HDLDevice

_LOGGER = logging.getLogger(__name__)

# Расширенный список типов устройств для лучшего обнаружения
DEVICE_TYPES = {
    "light": [0x0001, 0x0002, 0xEDED, 0xEFEF, 0x0009],  # Dimmer, Switch, Relay
    "cover": [0x0003, 0xEBEB],                          # Curtain/Shutter
    "climate": [0x0004, 0xECEC],                        # HVAC
    "sensor": [0x0005, 0xEAEA, 0x0031, 0x1133],         # Various sensors
    "binary_sensor": [0x0006, 0xE9E9, 0x0010],          # Binary sensors
    "switch": [0x0007, 0xE8E8, 0x0011]                  # Switches
}

class BusproDiscovery:
    """Class to handle device discovery on HDL Buspro network."""
    
    def __init__(self, hdl_device: HDLDevice):
        """Initialize the discovery."""
        self.hdl_device = hdl_device
        self.discovered_devices: Dict[str, List[dict]] = {
            "light": [],
            "cover": [],
            "climate": [],
            "sensor": [],
            "binary_sensor": [],
            "switch": []
        }
        self._device_status: Dict[str, Dict] = {}  # Stores the last status of each device

    async def scan_network(self) -> Dict[str, List[dict]]:
        """Scan the network for devices."""
        try:
            _LOGGER.info("Начинаю поиск устройств HDL Buspro...")
            # Отправляем широковещательное сообщение всем устройствам в сети
            for subnet_id in range(1, 255):  # Сканируем все возможные подсети
                try:
                    response = await self.hdl_device.send_message(
                        [subnet_id, 0xFF],  # Broadcast in subnet
                        [0x000D],           # Discovery operation code
                        []                  # Empty payload for discovery
                    )
                    
                    if response:
                        _LOGGER.info(f"Обнаружены устройства в подсети {subnet_id}: {response}")
                        # Process response
                        self._process_discovery_response(response, subnet_id)
                except Exception as err:
                    _LOGGER.debug(f"Error scanning subnet {subnet_id}: {err}")
            
            # Подробная информация об обнаруженных устройствах
            device_count = sum(len(devices) for devices in self.discovered_devices.values())
            _LOGGER.info(f"Обнаружено всего {device_count} устройств: " + 
                         ", ".join([f"{len(devices)} {device_type}" for device_type, devices in self.discovered_devices.items() if devices]))
            
            return self.discovered_devices

        except Exception as err:
            _LOGGER.error(f"Ошибка при поиске устройств: {err}")
            return self.discovered_devices
    
    def _process_discovery_response(self, response, subnet_id):
        """Process discovery response and categorize devices."""
        if not response:
            return
            
        for device in response:
            if not isinstance(device, dict):
                continue
                
            device_id = device.get("device_id", 0)
            device_type = device.get("type", 0)
            
            # Определяем категорию устройства
            category = self._determine_device_type(device)
            if not category:
                continue
                
            # Дополнительная информация для отображения в логах
            channels = device.get("channels", 1)
            _LOGGER.debug(f"Обнаружено устройство {category} с ID {subnet_id}.{device_id}, тип: 0x{device_type:X}, каналов: {channels}")
            
            # Добавляем устройство в список обнаруженных
            for channel in range(1, channels + 1):
                device_info = {
                    "subnet_id": subnet_id,
                    "device_id": device_id,
                    "device_type": device_type,
                    "channel": channel,
                    "name": f"{category.capitalize()} {subnet_id}.{device_id}.{channel}"
                }
                
                if device_info not in self.discovered_devices[category]:
                    self.discovered_devices[category].append(device_info)

    async def poll_devices(self) -> Dict[str, Dict]:
        """Poll all devices to update their status."""
        # Reset the device status dictionary
        updated_status = {}
        
        try:
            # Iterate through all discovered devices
            for device_type, devices in self.discovered_devices.items():
                for device in devices:
                    subnet_id = device["subnet_id"]
                    device_id = device["device_id"]
                    channel = device["channel"]
                    device_key = f"{subnet_id}.{device_id}.{channel}"
                    
                    try:
                        # Read status based on device type
                        if device_type == "light":
                            # Read channel for lights (brightness)
                            response = await self.hdl_device.send_message(
                                [subnet_id, device_id],
                                [OPERATION_READ_STATUS],
                                [channel]  # Specific channel
                            )
                            if response:
                                updated_status[device_key] = {
                                    "type": device_type,
                                    "state": response[0] > 0,  # On/Off
                                    "brightness": response[0]  # 0-255 for brightness
                                }
                        
                        elif device_type == "cover":
                            # Read channel for cover (position)
                            response = await self.hdl_device.send_message(
                                [subnet_id, device_id],
                                [OPERATION_READ_STATUS],
                                [channel]  # Specific channel
                            )
                            if response:
                                updated_status[device_key] = {
                                    "type": device_type,
                                    "position": response[0]  # 0-100 for position
                                }
                        
                        elif device_type == "climate":
                            # Read temperature and mode
                            temp_response = await self.hdl_device.send_message(
                                [subnet_id, device_id],
                                [OPERATION_READ_STATUS],
                                [channel]  # Channel for temperature
                            )
                            
                            mode_response = await self.hdl_device.send_message(
                                [subnet_id, device_id],
                                [OPERATION_READ_STATUS],
                                [channel + 1]  # Next channel for mode
                            )
                            
                            if temp_response:
                                climate_data = {
                                    "type": device_type,
                                    "current_temperature": temp_response[0] / 10,
                                }
                                
                                if len(temp_response) > 1:
                                    climate_data["target_temperature"] = temp_response[1] / 10
                                
                                if mode_response:
                                    climate_data["mode"] = mode_response[0]
                                
                                updated_status[device_key] = climate_data
                        
                        elif device_type == "sensor":
                            # Read sensor values
                            response = await self.hdl_device.send_message(
                                [subnet_id, device_id],
                                [OPERATION_READ_STATUS],
                                [channel]  # Specific channel
                            )
                            if response:
                                updated_status[device_key] = {
                                    "type": device_type,
                                    "value": response[0]
                                }
                        
                        elif device_type in ["binary_sensor", "switch"]:
                            # Read status for binary device
                            response = await self.hdl_device.send_message(
                                [subnet_id, device_id],
                                [OPERATION_READ_STATUS],
                                [channel]  # Specific channel
                            )
                            if response:
                                updated_status[device_key] = {
                                    "type": device_type,
                                    "state": response[0] > 0  # True/False
                                }
                    
                    except Exception as err:
                        _LOGGER.warning(f"Ошибка при опросе устройства {device_type} {subnet_id}.{device_id}.{channel}: {err}")
            
            # Update the device status dictionary
            self._device_status.update(updated_status)
            if updated_status:
                _LOGGER.debug(f"Обновлен статус {len(updated_status)} устройств")
            return self._device_status
        
        except Exception as err:
            _LOGGER.error(f"Ошибка при опросе устройств: {err}")
            return self._device_status

    def _determine_device_type(self, device: dict) -> Optional[str]:
        """Determine the type of device based on its characteristics."""
        device_type_id = device.get("type")
        
        for device_type, type_ids in DEVICE_TYPES.items():
            if device_type_id in type_ids:
                return device_type
                
        # Если тип устройства не определен, пробуем определить по функциям
        functions = device.get("functions", [])
        if 0x0001 in functions or 0x0002 in functions:  # Диммер или выключатель
            return "light"
        elif 0x0003 in functions:  # Шторы
            return "cover"
        elif 0x0004 in functions:  # Климат
            return "climate"
        elif 0x0005 in functions:  # Датчик
            return "sensor"
        elif 0x0006 in functions:  # Бинарный датчик
            return "binary_sensor"
        elif 0x0007 in functions:  # Выключатель
            return "switch"
            
        # Если не удалось определить, считаем выключателем по умолчанию
        _LOGGER.warning(f"Неизвестный тип устройства: 0x{device_type_id:X}, добавляем как light")
        return "light"

    def get_devices_by_type(self, device_type: str) -> List[dict]:
        """Get all discovered devices of a specific type."""
        return self.discovered_devices.get(device_type, [])
        
    def get_device_status(self, subnet_id: int, device_id: int) -> Optional[Dict]:
        """Get the current status of a device."""
        device_key = f"{subnet_id}.{device_id}"
        return self._device_status.get(device_key) 