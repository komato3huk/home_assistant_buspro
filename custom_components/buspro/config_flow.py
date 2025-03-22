"""Config flow for HDL Buspro integration."""
import asyncio
import logging
import ipaddress
import socket
from typing import Any, Dict, Optional

import voluptuous as vol

from homeassistant import config_entries, core, exceptions
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.const import CONF_HOST, CONF_PORT, CONF_TIMEOUT
import homeassistant.helpers.config_validation as cv

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

_LOGGER = logging.getLogger(__name__)

# Схема данных для настройки
DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Optional(CONF_PORT, default=DEFAULT_PORT): int,
        vol.Optional(CONF_TIMEOUT, default=DEFAULT_TIMEOUT): int,
        vol.Optional(CONF_DEVICE_SUBNET_ID, default=DEFAULT_DEVICE_SUBNET_ID): vol.All(
            vol.Coerce(int), vol.Range(min=0, max=255)
        ),
        vol.Optional(CONF_DEVICE_ID, default=DEFAULT_DEVICE_ID): vol.All(
            vol.Coerce(int), vol.Range(min=0, max=255)
        ),
        vol.Optional(CONF_POLL_INTERVAL, default=DEFAULT_POLL_INTERVAL): vol.All(
            vol.Coerce(int), vol.Range(min=5, max=300)
        ),
    }
)

class BusproFlowHandler(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for HDL Buspro."""

    VERSION = 1
    CONNECTION_CLASS = config_entries.CONN_CLASS_LOCAL_PUSH

    def __init__(self):
        """Initialize the config flow."""
        self.discovery = None
        self._discovered_devices = {}
        self._errors = {}
        self.host = None
        self.port = None

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        errors = {}

        if user_input is not None:
            host = user_input[CONF_HOST]
            port = user_input[CONF_PORT]
            timeout = user_input[CONF_TIMEOUT]
            subnet_id = user_input[CONF_DEVICE_SUBNET_ID]
            device_id = user_input[CONF_DEVICE_ID]
            poll_interval = user_input[CONF_POLL_INTERVAL]

            try:
                # Проверяем, что хост доступен
                await self.validate_host(host, port, timeout)

                # Создаем уникальный идентификатор для этого соединения
                await self.async_set_unique_id(f"{host}:{port}")
                self._abort_if_unique_id_configured()

                # Возвращаем данные для создания записи
                return self.async_create_entry(
                    title=f"HDL Buspro ({host}:{port})",
                    data={
                        CONF_HOST: host,
                        CONF_PORT: port,
                        CONF_TIMEOUT: timeout,
                        CONF_DEVICE_SUBNET_ID: subnet_id,
                        CONF_DEVICE_ID: device_id,
                        CONF_POLL_INTERVAL: poll_interval,
                    },
                )
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except InvalidHost:
                errors["host"] = "invalid_host"
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected error")
                errors["base"] = "unknown"

        # Показываем форму с возможными ошибками
        return self.async_show_form(
            step_id="user", data_schema=DATA_SCHEMA, errors=errors
        )

    async def validate_host(self, host, port, timeout):
        """Validate if the host is reachable."""
        try:
            # Проверяем валидность IP-адреса
            ipaddress.ip_address(host)
            
            # Проверяем, что хост доступен
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.settimeout(timeout)
            
            try:
                # Проверим, может ли сокет быть связан с указанным адресом
                sock.bind(("0.0.0.0", 0))
                
                # Для проверки доступности шлюза, просто пытаемся отправить пустой пакет
                sock.sendto(b"", (host, port))
                return True
            except socket.error as err:
                _LOGGER.error(f"Ошибка при подключении к {host}:{port}: {err}")
                raise CannotConnect
            finally:
                sock.close()
        except ValueError:
            raise InvalidHost

    async def async_step_import(self, user_input=None):
        """Import a config entry from configuration.yaml."""
        # Мы преобразуем значения из YAML в соответствующие типы
        # и вызываем шаг 'user', чтобы обработать ввод
        return await self.async_step_user(user_input)

    async def async_step_select_devices(self, user_input: Optional[Dict[str, Any]] = None):
        """Handle device selection."""
        if user_input is not None:
            # Save the configuration
            return self.async_create_entry(
                title=f"HDL Buspro {self.host}",
                data={
                    CONF_HOST: self.host,
                    CONF_PORT: self.port,
                    "devices": self._discovered_devices
                }
            )

        # Show device selection form
        device_count = sum(len(devices) for devices in self._discovered_devices.values())
        
        return self.async_show_form(
            step_id="select_devices",
            description_placeholders={
                "light_count": len(self._discovered_devices.get("light", [])),
                "cover_count": len(self._discovered_devices.get("cover", [])),
                "climate_count": len(self._discovered_devices.get("climate", [])),
                "sensor_count": len(self._discovered_devices.get("sensor", [])),
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
        self._config_entry = config_entry

    async def async_step_init(self, user_input=None):
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        options = {
            vol.Optional(
                CONF_POLL_INTERVAL,
                default=self._config_entry.options.get(
                    CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL
                ),
            ): int,
            vol.Optional(
                CONF_TIMEOUT,
                default=self._config_entry.options.get(
                    CONF_TIMEOUT, DEFAULT_TIMEOUT
                ),
            ): int,
            vol.Optional(
                CONF_DEVICE_SUBNET_ID,
                default=self._config_entry.options.get(
                    CONF_DEVICE_SUBNET_ID, DEFAULT_DEVICE_SUBNET_ID
                ),
            ): int,
            vol.Optional(
                CONF_DEVICE_ID,
                default=self._config_entry.options.get(
                    CONF_DEVICE_ID, DEFAULT_DEVICE_ID
                ),
            ): int,
            vol.Optional(
                CONF_GATEWAY_HOST,
                default=self._config_entry.options.get(
                    CONF_GATEWAY_HOST, self._config_entry.data.get(CONF_GATEWAY_HOST, DEFAULT_GATEWAY_HOST)
                ),
            ): str,
            vol.Optional(
                CONF_GATEWAY_PORT,
                default=self._config_entry.options.get(
                    CONF_GATEWAY_PORT, self._config_entry.data.get(CONF_GATEWAY_PORT, DEFAULT_GATEWAY_PORT)
                ),
            ): int,
        }

        return self.async_show_form(step_id="init", data_schema=vol.Schema(options))


class CannotConnect(exceptions.HomeAssistantError):
    """Error to indicate we cannot connect."""


class InvalidHost(exceptions.HomeAssistantError):
    """Error to indicate the host is invalid."""
