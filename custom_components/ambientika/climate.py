"""Platform for climate control integration."""
from __future__ import annotations

import logging

from ambientika_py import Device, DeviceStatus, FanSpeed, OperatingMode
import ambientika_py as ambientika
import voluptuous as vol

from homeassistant.components.climate import PLATFORM_SCHEMA, ClimateEntity
from homeassistant.components.climate.const import ClimateEntityFeature, HVACMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME, TEMP_CELSIUS
from homeassistant.core import HomeAssistant

# Import the device class from the component that you want to support
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType

_LOGGER = logging.getLogger(__name__)

# Validation of the user's configuration
PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Required(CONF_HOST, default = "https://app.ambientika.eu:4521"): cv.string, # type: ignore
    vol.Required(CONF_USERNAME): cv.string,
    vol.Required(CONF_PASSWORD): cv.string,
})

async def async_setup_entry(
    _hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Ambientika platform."""
    # Assign configuration variables.
    # The configuration check takes care they are present.
    config = entry.data
    host = config[CONF_HOST]
    username = config[CONF_USERNAME]
    password = config[CONF_PASSWORD]

    # Setup connection with devices/cloud
    api = await ambientika.authenticate(username, password, host)

    # Verify that passed in configuration works
    if not api:
        _LOGGER.error("Could not connect to Ambientika API")
        return

    houses = await api.houses()

    if not houses:
        raise Exception

    devices = [(device, await device.status()) for house in houses for room in house.rooms for device in room.devices]

    # Add devices
    async_add_entities(AmbientikaFan(device, state) for device, state in devices)


class AmbientikaFan(ClimateEntity):
    """Representation of an Awesome Light."""

    _device: Device
    _state: DeviceStatus

    def __init__(self, device: Device, initial_state: DeviceStatus) -> None:
        """Initialize an AwesomeLight."""
        self._device = device
        self._state = initial_state

    @property
    def name(self) -> str:
        """Return the display name of this light."""
        return self._device.name

    @property
    def current_humidity(self) -> int | None:
        """Return the current humidity."""
        return self._state["humidity"]

    @property
    def current_temperature(self) -> float | None:
        """Return the current temperature."""
        return self._state["temperature"]
    
    @property
    def fan_mode(self) -> str | None:
        """Returns the current fan mode."""
        return self._state["fan_speed"].name
    
    @property
    def fan_modes(self) -> list[str] | None:
        """Returns the set of available fan modes."""
        return [name for name, _ in FanSpeed.__members__.items()]
    
    @property
    def hvac_mode(self) -> HVACMode | None:
        if self._state["operating_mode"] == OperatingMode.Off:
            return HVACMode.OFF
        else:
            return HVACMode.FAN_ONLY
    
    @property
    def hvac_modes(self) -> list[HVACMode]:
        return [HVACMode.OFF, HVACMode.FAN_ONLY]
    
    @property
    def temperature_unit(self) -> str:
        return TEMP_CELSIUS
    
    @property
    def preset_mode(self) -> str | None:
        return self._state["operating_mode"].name
    
    @property
    def preset_modes(self) -> list[str] | None:
        return [name for name, _ in OperatingMode.__members__.items()]

    @property
    def unique_id(self) -> str | None:
        """Return the unique ID of the device."""
        return self._device.serial_number

    @property
    def supported_features(self) -> ClimateEntityFeature:
        return ClimateEntityFeature.FAN_MODE | ClimateEntityFeature.PRESET_MODE

    @property
    def is_on(self) -> bool | None:
        """Return true if device is on."""
        return self._state["operating_mode"] != OperatingMode.Off

    async def async_set_fan_mode(self, fan_mode: str) -> None:
        """Set the fan mode."""
        if await self._device.change_mode({
            "operating_mode": self._state["operating_mode"],
            "fan_speed": FanSpeed[fan_mode],
            "humidity_level": self._state["humidity_level"]
        }):
            self._state["fan_speed"] = FanSpeed[fan_mode]

    async def async_set_hvac_mode(self, hvac_mode: HVACMode):
        """Set the new HVAC Mode."""
        if hvac_mode == HVACMode.OFF and self._state["operating_mode"] != OperatingMode.Off:
            if await self._device.change_mode({
                "operating_mode": OperatingMode.Off,
                "fan_speed": self._state["fan_speed"],
                "humidity_level": self._state["humidity_level"]
            }):
                self._state["last_operating_mode"] = self._state["operating_mode"]
                self._state["operating_mode"] = OperatingMode.Off
        elif hvac_mode == HVACMode.FAN_ONLY and self._state["operating_mode"] == OperatingMode.Off:
            if await self._device.change_mode({
                "operating_mode": self._state["last_operating_mode"],
                "fan_speed": self._state["fan_speed"],
                "humidity_level": self._state["humidity_level"]
            }):
                self._state["operating_mode"] = self._state["last_operating_mode"]
                self._state["last_operating_mode"] = OperatingMode.Off

    async def async_set_preset_mode(self, preset_mode: str):
        """Set the fan operation mode."""
        if await self._device.change_mode({
            "operating_mode": OperatingMode[preset_mode],
            "fan_speed": self._state["fan_speed"],
            "humidity_level": self._state["humidity_level"]
        }):
            self._state["last_operating_mode"] = self._state["operating_mode"]
            self._state["operating_mode"] = self._state["last_operating_mode"]

    async def async_update(self) -> None:
        """Fetch new state data for this device."""
        status = await self._device.status()
        if status:
            self._state = status
        else:
            raise Exception
