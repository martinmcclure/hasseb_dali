"""The Hasseb DALI Master light controller integration."""

from __future__ import annotations

from dali.driver import hasseb

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

_PLATFORMS: list[Platform] = [Platform.LIGHT]

type HassebDaliConfigEntry = ConfigEntry[hasseeb.SyncHassebDALIUSBDriver]  # noqa: F821

async def async_setup_entry(hass: HomeAssistant, entry: HassebDaliConfigEntry) -> bool:
    """Set up Hasseb DALI Master light controller from a config entry."""

    # TODO 1. Create API instance
    # TODO 2. Validate the API connection (and authentication)
    # TODO 3. Store an API object for your platforms to access
    # entry.runtime_data = MyAPI(...)

    await hass.config_entries.async_forward_entry_setups(entry, _PLATFORMS)

    return True

async def async_unload_entry(hass: HomeAssistant, entry: HassebDaliConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, _PLATFORMS)
