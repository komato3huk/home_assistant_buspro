"""HDL Buspro device discovery implementation."""
import logging
from typing import Dict, List, Optional

from .const import DOMAIN, OPERATION_READ_STATUS
from .pybuspro.core.hdl_device import HDLDevice

_LOGGER = logging.getLogger(__name__)

DEVICE_TYPES = {
    "light": [0x0001, 0x0002],  # Dimmer, Switch
    "cover": [0x0003],          # Curtain/Shutter
    "climate": [0x0004],        # HVAC
    "sensor": [0x0005],         # Various sensors
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
            "sensor": []
        }
        self._device_status: Dict[str, Dict] = {}  # Stores the last status of each device

    async def scan_network(self) -> Dict[str, List[dict]]:
        """Scan the network for devices."""
        try:
            # Send broadcast discovery message
            response = await self.hdl_device.send_message(
                [0xFF, 0xFF],  # Broadcast address
                [0x000D],      # Discovery operation code
                []             # Empty payload for discovery
            )
            
            # Process response and categorize devices
            for device in response:
                device_type = self._determine_device_type(device)
                if device_type:
                    device_info = {
                        "subnet_id": device["subnet_id"],
                        "device_id": device["device_id"],
                        "device_type": device["type"],
                        "name": f"{device_type.capitalize()} {device['subnet_id']}.{device['device_id']}"
                    }
                    self.discovered_devices[device_type].append(device_info)
            
            return self.discovered_devices

        except Exception as err:
            _LOGGER.error("Error during device discovery: %s", err)
            return self.discovered_devices

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
                    device_key = f"{subnet_id}.{device_id}"
                    
                    try:
                        # Read status based on device type
                        if device_type == "light":
                            # Read channel 1 for lights (brightness)
                            response = await self.hdl_device.send_message(
                                [subnet_id, device_id],
                                [OPERATION_READ_STATUS],
                                [1]  # Channel 1
                            )
                            if response:
                                updated_status[device_key] = {
                                    "type": device_type,
                                    "state": response[0] > 0,  # On/Off
                                    "brightness": response[0]  # 0-255 for brightness
                                }
                        
                        elif device_type == "cover":
                            # Read channel 1 for cover (position)
                            response = await self.hdl_device.send_message(
                                [subnet_id, device_id],
                                [OPERATION_READ_STATUS],
                                [1]  # Channel 1
                            )
                            if response:
                                updated_status[device_key] = {
                                    "type": device_type,
                                    "position": response[0]  # 0-255 for position
                                }
                        
                        elif device_type == "climate":
                            # Read temperature and mode
                            temp_response = await self.hdl_device.send_message(
                                [subnet_id, device_id],
                                [OPERATION_READ_STATUS],
                                [1]  # Channel 1 for temperature
                            )
                            
                            mode_response = await self.hdl_device.send_message(
                                [subnet_id, device_id],
                                [OPERATION_READ_STATUS],
                                [2]  # Channel 2 for mode
                            )
                            
                            if temp_response and mode_response:
                                updated_status[device_key] = {
                                    "type": device_type,
                                    "current_temperature": temp_response[0] / 10,
                                    "target_temperature": temp_response[1] / 10 if len(temp_response) > 1 else None,
                                    "mode": mode_response[0]
                                }
                        
                        elif device_type == "sensor":
                            # Read sensor values from multiple channels
                            response = await self.hdl_device.send_message(
                                [subnet_id, device_id],
                                [OPERATION_READ_STATUS],
                                [1, 2, 3, 4]  # Multiple channels for different sensors
                            )
                            if response:
                                updated_status[device_key] = {
                                    "type": device_type,
                                    "values": response
                                }
                    
                    except Exception as err:
                        _LOGGER.error("Error polling device %s.%s: %s", subnet_id, device_id, err)
            
            # Update the device status dictionary
            self._device_status.update(updated_status)
            return self._device_status
        
        except Exception as err:
            _LOGGER.error("Error polling devices: %s", err)
            return self._device_status

    def _determine_device_type(self, device: dict) -> Optional[str]:
        """Determine the type of device based on its characteristics."""
        device_type_id = device.get("type")
        
        for device_type, type_ids in DEVICE_TYPES.items():
            if device_type_id in type_ids:
                return device_type
                
        return None

    def get_devices_by_type(self, device_type: str) -> List[dict]:
        """Get all discovered devices of a specific type."""
        return self.discovered_devices.get(device_type, [])
        
    def get_device_status(self, subnet_id: int, device_id: int) -> Optional[Dict]:
        """Get the current status of a device."""
        device_key = f"{subnet_id}.{device_id}"
        return self._device_status.get(device_key) 