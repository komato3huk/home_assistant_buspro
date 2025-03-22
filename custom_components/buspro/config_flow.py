"""Config flow for HDL Buspro integration."""
import asyncio
import logging
import ipaddress
from typing import Any, Dict, Optional

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.const import CONF_HOST, CONF_PORT, CONF_TIMEOUT

from .const import (
    DOMAIN,
    DEFAULT_PORT,
    DEFAULT_TIMEOUT,
    CONF_DEVICE_SUBNET_ID,
    CONF_DEVICE_ID,
    CONF_POLL_INTERVAL,
    DEFAULT_POLL_INTERVAL,
    DEFAULT_DEVICE_SUBNET_ID,
    DEFAULT_DEVICE_ID,
    CONF_GATEWAY_HOST,
    CONF_GATEWAY_PORT,
    DEFAULT_GATEWAY_HOST,
    DEFAULT_GATEWAY_PORT,
)
from .discovery import BusproDiscovery
from .pybuspro.core.hdl_device import HDLDevice

_LOGGER = logging.getLogger(__name__)

# Validation schema for gateway connection
STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Optional(CONF_PORT, default=DEFAULT_PORT): int,
        vol.Optional(CONF_TIMEOUT, default=DEFAULT_TIMEOUT): int,
        vol.Optional(CONF_DEVICE_SUBNET_ID, default=DEFAULT_DEVICE_SUBNET_ID): int,
        vol.Optional(CONF_DEVICE_ID, default=DEFAULT_DEVICE_ID): int,
        vol.Optional(CONF_POLL_INTERVAL, default=DEFAULT_POLL_INTERVAL): int,
        vol.Optional(CONF_GATEWAY_HOST, default=DEFAULT_GATEWAY_HOST): str,
        vol.Optional(CONF_GATEWAY_PORT, default=DEFAULT_GATEWAY_PORT): int,
    }
)

class BusproConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for HDL Buspro."""

    VERSION = 1
    CONNECTION_CLASS = config_entries.CONN_CLASS_LOCAL_PUSH

    def __init__(self):
        """Initialize the config flow."""
        self.discovery = None
        self.discovered_devices = {}
        self.host = None
        self.port = None

    async def async_step_user(self, user_input: Optional[Dict[str, Any]] = None) -> FlowResult:
        """Handle the initial step."""
        errors = {}

        if user_input is not None:
            # Validate IP address
            try:
                ipaddress.ip_address(user_input[CONF_HOST])
            except ValueError:
                errors[CONF_HOST] = "invalid_host"

            # Если указан IP шлюза, проверяем его тоже
            if user_input.get(CONF_GATEWAY_HOST):
                try:
                    ipaddress.ip_address(user_input[CONF_GATEWAY_HOST])
                except ValueError:
                    errors[CONF_GATEWAY_HOST] = "invalid_host"

            # Validate subnet ID and device ID
            if not 0 <= user_input[CONF_DEVICE_SUBNET_ID] <= 255:
                errors[CONF_DEVICE_SUBNET_ID] = "invalid_subnet_id"
            if not 0 <= user_input[CONF_DEVICE_ID] <= 255:
                errors[CONF_DEVICE_ID] = "invalid_device_id"

            if not errors:
                try:
                    # Test connection to gateway
                    await self._test_connection(
                        user_input[CONF_HOST],
                        user_input[CONF_PORT],
                        user_input[CONF_TIMEOUT]
                    )

                    # Create entry with connection data
                    return self.async_create_entry(
                        title=f"HDL Buspro Gateway ({user_input[CONF_HOST]})",
                        data=user_input
                    )
                except asyncio.TimeoutError:
                    errors["base"] = "cannot_connect"
                except Exception as e:
                    _LOGGER.exception("Unexpected exception")
                    errors["base"] = "unknown"

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )

    @staticmethod
    async def _test_connection(host, port, timeout):
        """Test if we can connect to the HDL Buspro gateway."""
        try:
            _, writer = await asyncio.wait_for(
                asyncio.open_connection(host, port),
                timeout=timeout
            )
            writer.close()
            await writer.wait_closed()
        except (OSError, asyncio.TimeoutError) as err:
            _LOGGER.error("Failed to connect to HDL Buspro gateway: %s", err)
            raise

    async def async_step_select_devices(self, user_input: Optional[Dict[str, Any]] = None):
        """Handle device selection."""
        if user_input is not None:
            # Save the configuration
            return self.async_create_entry(
                title=f"HDL Buspro {self.host}",
                data={
                    CONF_HOST: self.host,
                    CONF_PORT: self.port,
                    "devices": self.discovered_devices
                }
            )

        # Show device selection form
        device_count = sum(len(devices) for devices in self.discovered_devices.values())
        
        return self.async_show_form(
            step_id="select_devices",
            description_placeholders={
                "light_count": len(self.discovered_devices.get("light", [])),
                "cover_count": len(self.discovered_devices.get("cover", [])),
                "climate_count": len(self.discovered_devices.get("climate", [])),
                "sensor_count": len(self.discovered_devices.get("sensor", [])),
                "total_count": device_count
            }
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Get the options flow for this handler."""
        return BusproOptionsFlowHandler(config_entry)


class BusproOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle Buspro options."""

    def __init__(self, config_entry):
        """Initialize options flow."""
        self.config_entry = config_entry

    async def async_step_init(self, user_input=None):
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        options = {
            vol.Optional(
                CONF_POLL_INTERVAL,
                default=self.config_entry.options.get(
                    CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL
                ),
            ): int,
            vol.Optional(
                CONF_TIMEOUT,
                default=self.config_entry.options.get(
                    CONF_TIMEOUT, DEFAULT_TIMEOUT
                ),
            ): int,
            vol.Optional(
                CONF_DEVICE_SUBNET_ID,
                default=self.config_entry.options.get(
                    CONF_DEVICE_SUBNET_ID, DEFAULT_DEVICE_SUBNET_ID
                ),
            ): int,
            vol.Optional(
                CONF_DEVICE_ID,
                default=self.config_entry.options.get(
                    CONF_DEVICE_ID, DEFAULT_DEVICE_ID
                ),
            ): int,
            vol.Optional(
                CONF_GATEWAY_HOST,
                default=self.config_entry.options.get(
                    CONF_GATEWAY_HOST, self.config_entry.data.get(CONF_GATEWAY_HOST, DEFAULT_GATEWAY_HOST)
                ),
            ): str,
            vol.Optional(
                CONF_GATEWAY_PORT,
                default=self.config_entry.options.get(
                    CONF_GATEWAY_PORT, self.config_entry.data.get(CONF_GATEWAY_PORT, DEFAULT_GATEWAY_PORT)
                ),
            ): int,
        }

        return self.async_show_form(step_id="init", data_schema=vol.Schema(options))
