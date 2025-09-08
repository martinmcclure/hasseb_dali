"""Config flow for the Hasseb DALI Master light controller integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from dali.driver import hasseb

from homeassistant.components import usb
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_entry_flow

from .const import DOMAIN




class HassebDaliMasterConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Hasseb DALI Master light controller."""

    def __init__(self) -> None:
        """Set up flow instance."""
        self._dev_path: str | None = None

    async def async_step_usb(self, discovery_info: UsbServiceInfo) -> ConfigFlowResult:
        """Handle USB Discovery."""
        device = discovery_info.device
        dev_path = await self.hass.async_add_executor_job(usb.get_serial_by_id, device)
        unique_id = _generate_unique_id(discovery_info)
        await self.async_set_unique_id(unique_id)
        return self.async_create_entry(
            title=user_input.get(CONF_NAME, DEFAULT_NAME),
            data={
                CONF_DEVICE: self._dev_path
            }
        )

async def _async_has_devices(hass: HomeAssistant) -> bool:
    """Return if there are devices that can be discovered."""
    devices = await hass.async_add_executor_job(hasseb.SyncHassebDALIUSBDriverFactory)
    return len(devices) > 0


config_entry_flow.register_discovery_flow(DOMAIN, "Hasseb DALI Master light controller", _async_has_devices)
