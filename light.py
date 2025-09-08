"""Platform for light integration."""
from __future__ import annotations

import logging

import voluptuous as vol

# Import the device class from the component that you want to support
import homeassistant.helpers.config_validation as cv
from homeassistant.components.light import (ATTR_BRIGHTNESS, PLATFORM_SCHEMA,
                                            LightEntity)
from homeassistant.const import CONF_NAME, CONF_HOST, CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType
from homeassistant.helpers import entity_platform, service
from datetime import timedelta

_LOGGER = logging.getLogger(__name__)

# Validation of the user's configuration
# PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
#     vol.Required(CONF_HOST): cv.string,
#     vol.Optional(CONF_USERNAME, default='admin'): cv.string,
#     vol.Optional(CONF_PASSWORD): cv.string,
# })

CONF_MAX_GEARS = "max_gears"
CONF_DRIVERS = "drivers"
CONF_MAX_BUSES = "max_buses"
CONF_READDRESS = "readdress"

MAX_RANGE = 64
MAX_BUSES = 4

DRIVER_SCHEMA = vol.Schema({
    vol.Required(CONF_NAME): cv.string,
    vol.Optional(CONF_MAX_GEARS, default=MAX_RANGE): cv.positive_int,
    vol.Optional(CONF_READDRESS, default=False): cv.boolean,
})

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Optional(CONF_MAX_BUSES, default=MAX_BUSES): cv.positive_int,
    vol.Required(CONF_DRIVERS, default=[]): vol.All(cv.ensure_list, [DRIVER_SCHEMA]),
})

CHANGE_SHORT_ADDRESS_SCHEMA = {
    vol.Required('short_address'): cv.positive_int
}

SERVICE_WIPE_SHORT_ADDRESS = "wipe_short_address"
SERVICE_CHANGE_SHORT_ADDRESS = "change_short_address"
SERVICE_IDENTIFY_DEVICE = "identify_device"

async def async_setup_entry(hass, config_entry, async_add_entities):
    """Set up entry."""
    setup_platform(hass, config_entry, async_add_entities)

def setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType | None = None
) -> None:
    """Set up the DALI Light platform."""

    from dali.address import Broadcast, Short
    from dali.command import YesNoResponse, Response
    import dali.gear.general as gear
    from dali.driver.hasseb import SyncHassebDALIUSBDriverFactory
    from dali.driver.hasseb import SyncHassebDALIUSBDriver
    import threading
    from dali.sequences import Commissioning
    from dali.exceptions import ResponseError
    from collections import namedtuple

    # Stores a gear's short address and its serial. Used to reduce the number of
    # I/O operations during setup - if it takes too long, HA may stop the integration
    # from loading
    LampSerial = namedtuple('LampSerial', 'lamp serial')

    # @XXX this doesn't look like it's the proper way to do things - but it works
    platform = entity_platform.EntityPlatform(hass=hass, logger=_LOGGER, domain="light", platform_name="hasseb_dali", platform=None, scan_interval=timedelta(seconds=3), entity_namespace="light")

    platform.async_register_entity_service(
        SERVICE_WIPE_SHORT_ADDRESS,
        {},
        func = "wipe_short_address"
    )

    platform.async_register_entity_service(
        SERVICE_IDENTIFY_DEVICE,
        {},
        func = "identify_device"
    )

    platform.async_register_entity_service(
        SERVICE_CHANGE_SHORT_ADDRESS,
        CHANGE_SHORT_ADDRESS_SCHEMA,
        func = "change_short_address"
    )

    dali_drivers = SyncHassebDALIUSBDriverFactory()

    for idx, dali_driver in enumerate(dali_drivers):
        _LOGGER.debug("Found DALI driver")
        lock = threading.RLock() # @TODO this ok?

        driver_config = config[CONF_DRIVERS][idx]
        readdress = driver_config[CONF_READDRESS]

        dali_driver.send(gear.Terminate())
        dali_driver.send(gear.Initialise())

        fix_collisions = False
        first_run = True

        while fix_collisions or first_run:
            _LOGGER.debug("first run = {}, fix collisions = {}".format(first_run, fix_collisions))

            if readdress:
                _LOGGER.warning("readdress is set - all short addresses will be wiped and new ones assigned!")

            dali_driver.run_sequence(Commissioning(readdress=readdress), commissioning_progress_cb)

            fix_collisions = False

            lamps = []
            for lamp in range(0, driver_config[CONF_MAX_GEARS]):
                serial = 0

                try:
                    _LOGGER.debug("Searching for Gear on address <{}>".format(lamp))
                    r = dali_driver.send(gear.QueryControlGearPresent(Short(lamp)))

                    if isinstance(r, YesNoResponse) and r.value:
                        _LOGGER.debug("Found lamp!")

                        # @TODO skip short addr collision check if readdress?
                        _LOGGER.debug("Testing for short address collision")

                        try:
                            serial = build_serial(dali_driver, Short(lamp)) # store in tuple or smth

                        except ResponseError as e:
                            _LOGGER.warning("Short address collision detected on address {}! \
                            Offending gears will have their addresses deleted and re-assigned.".format(lamp))

                            dali_driver.send(gear.DTR0(255))
                            dali_driver.send(gear.SetShortAddress(Short(lamp)))

                            # Run commissioning process one more time
                            if first_run:
                                fix_collisions = True

                        lamps.append(LampSerial(Short(lamp), serial))

                except Exception as e: # @TODO this is not true anymore
                    # This will often mean that the driver wasn't found
                    _LOGGER.error("Error while QueryControlGearPresent: {}".format(e))
                    _LOGGER.error("Hasseb DALI master not found")
                    break

            first_run = False

        add_devices([DALILight(dali_driver, lock, driver_config[CONF_NAME], l.lamp, idx, l.serial) for l in lamps])
        add_devices([DALIBus(dali_driver, lock, driver_config[CONF_NAME], [l.lamp for l in lamps], config[CONF_MAX_BUSES], idx)])

        dali_driver.send(gear.Terminate())

    # """Set up the Awesome Light platform."""
    # # Assign configuration variables.
    # # The configuration check takes care they are present.
    # host = config[CONF_HOST]
    # username = config[CONF_USERNAME]
    # password = config.get(CONF_PASSWORD)
    #
    # # Setup connection with devices/cloud
    # hub = awesomelights.Hub(host, username, password)
    #
    # # Verify that passed in configuration works
    # if not hub.is_valid_login():
    #     _LOGGER.error("Could not connect to AwesomeLight hub")
    #     return
    #
    # # Add devices
    # add_entities(AwesomeLight(light) for light in hub.lights())
    #

class DALILight(LightEntity):
    """Representation of an DALI light."""

    def __init__(self, driver, driver_lock, controller_name, ballast, bus_index, serial):
        from dali.gear.general import QueryActualLevel
        from dali.command import ResponseError, MissingResponse

        """Initialize a DALI light."""
        self._brightness = 0
        self._state = False
        self._name = "{} {}".format(controller_name, ballast.address)
        self.attributes = {"short_address": ballast.address}

        self.driver = driver
        self.driver_lock = driver_lock
        self.addr = ballast

        self._unique_id = serial

        try:
            with self.driver_lock:
                cmd = QueryActualLevel(self.addr)
                r = self.driver.send(cmd)
                if r.value != None and r.value < 255:
                    self._brightness = r.value
                    if r.value > 0:
                        r.state = True

        except ResponseError as e:
            _LOGGER.error("Response error on __init__")
        except MissingResponse as e:
            self._brightness = None
            self._state = None

    @property
    def name(self):
        """Return the display name of this light."""
        return self._name

    @property
    def unique_id(self):
        """The unique ID is calculated based on its bus index and its short address,
        so that conflicts don't arise from having lamps with the same short address in
        different buses. """
        return self._unique_id

    @property
    def brightness(self):
        """Return the brightness of the light."""
        return self._brightness

    @property
    def device_state_attributes(self):
        """Show Device Attributes."""
        return self.attributes

    @property
    def is_on(self):
        """Return true if light is on."""
        return self._state

    @property
    def supported_features(self):
        """Flag supported features."""
        return SUPPORT_DALI

    def turn_on(self, **kwargs):
        """Instruct the light to turn on."""
        from dali.gear.general import DAPC

        with self.driver_lock:
            try:
                self._brightness = kwargs.get(ATTR_BRIGHTNESS, 254)
                _LOGGER.debug("turn on {}".format(self._brightness))
                cmd = DAPC(self.addr, 254 if self._brightness==255 else self._brightness)
                r = self.driver.send(cmd)
                if self._brightness > 0:
                    self._state = True
            except usb.core.USBError as e:
                _LOGGER.error("Can't turn_on {}: {}".format(self._name, e))
        self.schedule_update_ha_state()

    def turn_off(self, **kwargs):
        """Instruct the light to turn off."""
        from dali.gear.general import Off

        with self.driver_lock:
            try:
                cmd = Off(self.addr)
                r = self.driver.send(cmd)
                self._state = False
            except usb.core.USBError as e:
                _LOGGER.error("Can't turn_on {}: {}".format(self._name, e))
        self.schedule_update_ha_state()

    @property
    def should_poll(self):
        """Polling is now needed so that DALI bus and DALI light states will sync"""
        return True

    def update(self):
        """Fetch update state."""
        from dali.gear.general import QueryActualLevel
        from dali.command import ResponseError, MissingResponse
        import usb

        with self.driver_lock:
            try:
                r = self.driver.send(QueryActualLevel(self.addr))
                _LOGGER.debug("DALI Light update: new brightness is {}".format(r))
                if r:
                    self._brightness = r.value
                    if 0 < int(self._brightness) < 255:
                        self._state = True
                    else:
                        self._state = False
                else:
                    _LOGGER.error("return value = {}", r)
            except usb.core.USBError as e:
                _LOGGER.error("Can't update {}: {}".format(self._name, e))
            except ResponseError as e:
                _LOGGER.error("ResponseError QueryActualLevel")
            except MissingResponse as e:
                self._brightness = None

    def wipe_short_address(self):
        _LOGGER.warning("Gear {} will have its short address deleted and will no longer respond to commands until next commissioning".format(self.addr))
        self.change_short_address(255)

    def identify_device(self):
        import usb
        from dali.gear.general import IdentifyDevice

        with self.driver_lock:
            try:
                cmd = IdentifyDevice(self.addr)
                r = self.driver.send(cmd)
            except usb.core.USBError as e:
                _LOGGER.error("Can't identify_device {}: {}".format(self._name, e))

    def change_short_address(self, short_address):
        import usb
        from dali.address import Short
        from dali.gear.general import SetShortAddress
        from dali.gear.general import DTR0

        new_address = ((short_address << 1) | 1) if (short_address != 255) else short_address

        # @XXX pair this condition with the one above? what is more readable?
        if short_address != 255:
            _LOGGER.warning("Gear {} will change address to: {}".format(self.addr, short_address))

        with self.driver_lock:
            try:
                # Put new address in DTR0
                cmd = DTR0(new_address)
                r = self.driver.send(cmd)

                # Set DTR0 content as short address
                cmd = SetShortAddress(self.addr)
                r = self.driver.send(cmd)

                if (short_address != 255):
                    self.addr = Short(short_address)
                else:
                    self.addr = None

            # @TODO figure out which kind of errors may occur
            except Exception as e:
                _LOGGER.error("Exception: {}", e)

class DALIBus(LightEntity):
    """Representation of a DALI bus."""

    def __init__(self, driver, driver_lock, controller_name, ballasts, max_buses, bus_index):
        from dali.gear.general import QueryActualLevel
        from dali.command import ResponseError, MissingResponse
        from dali.address import Broadcast

        """Initialize a DALI bus."""
        self._brightness = 0
        self._state = False
        self._name = "{} bus".format(controller_name)

        self.lamp_addresses = ballasts
        self.attributes = {"short_addresses": [ballast.address for ballast in ballasts] }

        self.driver = driver
        self.driver_lock = driver_lock
        self.addr = Broadcast()

        # Unique IDs for DALI buses are allocated after the last lamp ID range
        self._unique_id = max_buses * MAX_RANGE + bus_index

        self.calculate_bus_state()

    def calculate_bus_state(self):
        from dali.gear.general import QueryActualLevel
        from dali.command import ResponseError, MissingResponse
        import usb

        """The state of a DALI bus will be the same state as the lights hanging
        from it if all of them are consistent. If they are not, the state of the
        bus will be off. """

        try:
            with self.driver_lock:
                last_brightness = None

                for lamp_address in self.lamp_addresses:
                    # Query brightness
                    result = self.driver.send(QueryActualLevel(lamp_address))
                    _LOGGER.debug("DALI Bus update: lamp {} brightness is {}".format(lamp_address.address, result.value))

                    # Check if brightness is a valid value
                    # If so, and if it's either the first light or if it has the same value as the lights
                    # checked before, save value and keep checking
                    if result.value != None and int(result.value) < 255 and (last_brightness == None or last_brightness == int(result.value)):
                        last_brightness = int(result.value)

                    else: # if not, bus status is not consistent; stop checking
                        _LOGGER.debug("Lamp {} returned invalid or different value; bus status is not consistent")
                        last_brightness = None
                        break

            _LOGGER.debug("DALI Bus update: new brightness is {}".format(last_brightness))

            self._brightness = last_brightness
            if self._brightness == None:
                self._state = None
            elif self._brightness > 0:
                self._state = True
            else:
                self._state = False

        # @XXX should unify these if I can't different causes / behavior
        except usb.core.USBError as e:
            _LOGGER.error("USB Error {}: {}".format(self._name, e))
            self._brightness = None
            self._state = None
        except ResponseError as e:
            _LOGGER.error("Response Error in QueryActualLevel: {}: {}".format(self._name, e))
            self._brightness = None
            self._state = None
        except MissingResponse as e:
            _LOGGER.error("Missing response: {}: {}".format(self._name, e))
            self._brightness = None
            self._state = None

    @property
    def name(self):
        """Return the display name of this light."""
        return self._name

    @property
    def unique_id(self):
        """The unique ID for a bus has to be outside the range of possible lamp
        unique IDs. As lamp IDs span in the ranges 0..63 for bus 0, 64..127 for bus
        1, and so on, bus IDs begin *after* the last possible lamp ID, indicated by
        64 * max_buses."""
        return self._unique_id

    @property
    def brightness(self):
        """Return the brightness of the light."""
        return self._brightness

    @property
    def device_state_attributes(self):
        """Show Device Attributes."""
        return self.attributes

    @property
    def is_on(self):
        """Return true if light is on."""
        return self._state

    @property
    def supported_features(self):
        """Flag supported features."""
        return SUPPORT_DALI

    def turn_on(self, **kwargs):
        """Instruct the light to turn on."""
        from dali.gear.general import DAPC

        with self.driver_lock:
            try:
                self._brightness = kwargs.get(ATTR_BRIGHTNESS, 254)
                _LOGGER.debug("turn on {}".format(self._brightness))
                cmd = DAPC(self.addr, 254 if self._brightness==255 else self._brightness)
                r = self.driver.send(cmd)
                if self._brightness > 0:
                    self._state = True
            except usb.core.USBError as e:
                _LOGGER.error("Can't turn_on {}: {}".format(self._name, e))
        self.schedule_update_ha_state()

    def turn_off(self, **kwargs):
        """Instruct the light to turn off."""
        from dali.gear.general import Off

        with self.driver_lock:
            try:
                cmd = Off(self.addr)
                r = self.driver.send(cmd)
                self._state = False
            except usb.core.USBError as e:
                _LOGGER.error("Can't turn_on {}: {}".format(self._name, e))
        self.schedule_update_ha_state()

    @property
    def should_poll(self):
        """Polling is now needed so that DALI bus and DALI light states will sync"""
        return True

    def update(self):
        """Fetch update state."""
        self.calculate_bus_state()

    def wipe_short_address(self):
        _LOGGER.warning("All gears will have its short address deleted and will no longer respond to commands until next commissioning".format(self.addr))
        self.change_short_address(255)

    def identify_device(self):
        import usb
        from dali.gear.general import IdentifyDevice

        with self.driver_lock:
            try:
                cmd = IdentifyDevice(self.addr)
                r = self.driver.send(cmd)
            except usb.core.USBError as e:
                _LOGGER.error("Can't identify_device {}: {}".format(self._name, e))

    def change_short_address(self, short_address):
        from dali.gear.general import SetShortAddress, DTR0

        new_address = ((short_address << 1) | 1) if (short_address != 255) else short_address

        # @XXX pair this condition with the one above? what is more readable?
        if short_address != 255:
            _LOGGER.warning("All gears will change address to: {}".format(short_address))

        try:
            # Put new address in DTR0
            cmd = DTR0(new_address)
            r = self.driver.send(cmd)

            # Set DTR0 content as short address
            cmd = SetShortAddress(self.addr)
            r = self.driver.send(cmd)

        # @TODO figure out which kind of errors may occur
        except Exception as e:
            _LOGGER.error("Exception: {}", e)
# class AwesomeLight(LightEntity):
#     """Representation of an Awesome Light."""
#
#     def __init__(self, light) -> None:
#         """Initialize an AwesomeLight."""
#         self._light = light
#         self._name = light.name
#         self._state = None
#         self._brightness = None
#
#     @property
#     def name(self) -> str:
#         """Return the display name of this light."""
#         return self._name
#
#     @property
#     def brightness(self):
#         """Return the brightness of the light.
#
#         This method is optional. Removing it indicates to Home Assistant
#         that brightness is not supported for this light.
#         """
#         return self._brightness
#
#     @property
#     def is_on(self) -> bool | None:
#         """Return true if light is on."""
#         return self._state
#
#     def turn_on(self, **kwargs: Any) -> None:
#         """Instruct the light to turn on.
#
#         You can skip the brightness part if your light does not support
#         brightness control.
#         """
#         self._light.brightness = kwargs.get(ATTR_BRIGHTNESS, 255)
#         self._light.turn_on()
#
#     def turn_off(self, **kwargs: Any) -> None:
#         """Instruct the light to turn off."""
#         self._light.turn_off()
#
#     def update(self) -> None:
#         """Fetch new state data for this light.
#
#         This is the only method that should fetch new data for Home Assistant.
#         """
#         self._light.update()
#         self._state = self._light.is_on()
#         self._brightness = self._light.brightness
