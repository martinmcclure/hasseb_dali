"""Config flow for the Hasseb DALI Master light controller integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.components import usb
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

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

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle a flow initiated by the user."""
        if self._async_in_progress():
            return self.async_abort(reason="already_in_progress")
        # ports = await self.hass.async_add_executor_job(serial.tools.list_ports.comports)
        # existing_devices = [
        #     entry.data[CONF_DEVICE] for entry in self._async_current_entries()
        # ]
        # unused_ports = [
        #     usb.human_readable_device_name(
        #         port.device,
        #         port.serial_number,
        #         port.manufacturer,
        #         port.description,
        #         port.vid,
        #         port.pid,
        #     )
        #     for port in ports
        #     if port.device not in existing_devices
        # ]
        # if not unused_ports:
        #     return self.async_abort(reason="no_devices_found")

        errors = {}
        if user_input is not None and user_input.get(CONF_DEVICE, "").strip():
            # port = ports[unused_ports.index(str(user_input[CONF_DEVICE]))]
            dev_path = await self.hass.async_add_executor_job(
                usb.get_serial_by_id, port.device
            )
            unique_id = _generate_unique_id(dev_path)
            await self.async_set_unique_id(unique_id)
            try:
                await self._validate_device(dev_path)
            except TimeoutError:
                errors[CONF_DEVICE] = "timeout_connect"
            # except RAVEnConnectionError:
            #     errors[CONF_DEVICE] = "cannot_connect"
            else:
                return await self.async_step_meters()

        schema = vol.Schema({vol.Required(CONF_DEVICE): vol.In(unused_ports)})
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)


