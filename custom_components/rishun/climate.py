import logging
from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACMode,
    FAN_AUTO,
    FAN_LOW,
    FAN_MEDIUM,
    FAN_HIGH,
)
from homeassistant.const import UnitOfTemperature
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import RishunDataCoordinator
from rishun_api import CloudApiClient

_LOGGER = logging.getLogger(__name__)

HVAC_TO_MODE = {
    HVACMode.COOL: 1,
    HVACMode.HEAT: 2,
    HVACMode.FAN_ONLY: 3,
    HVACMode.DRY: 4,
}
MODE_TO_HVAC = {v: k for k, v in HVAC_TO_MODE.items()}

FAN_TO_SPEED = {
    FAN_LOW: 1,
    FAN_MEDIUM: 2,
    FAN_HIGH: 3,
    FAN_AUTO: 11,
}
SPEED_TO_FAN = {v: k for k, v in FAN_TO_SPEED.items()}

DEFAULT_TARGET_TEMPERATURE = 25.0


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    entry_data = hass.data[DOMAIN][config_entry.entry_id]
    coordinator = entry_data["coordinator"]
    api_client = entry_data["api_client"]
    device_list = entry_data["device_list"]

    entities = []
    for dev in device_list:
        module_type = dev["moduleType"]
        if module_type == 7:
            entities.append(RishunAC(coordinator, api_client, dev))
        elif module_type == 10:
            entities.append(RishunFloorHeating(coordinator, api_client, dev))
        elif module_type == 11:
            entities.append(RishunFreshAir(coordinator, api_client, dev))

    if entities:
        async_add_entities(entities)


class RishunAC(CoordinatorEntity, ClimateEntity):
    def __init__(self, coordinator: RishunDataCoordinator, api_client: CloudApiClient, device: dict):
        super().__init__(coordinator)
        self._api_client = api_client
        self._device = device
        self._device_id = device["deviceId"]
        self._module_type = device["moduleType"]

        self._attr_unique_id = f"{DOMAIN}_ac_{self._device_id}"
        self._attr_name = device.get("pointName", f"空调-{self._device_id}")
        self._attr_temperature_unit = UnitOfTemperature.CELSIUS
        self._attr_hvac_modes = [HVACMode.OFF, HVACMode.COOL, HVACMode.HEAT, HVACMode.DRY, HVACMode.FAN_ONLY]
        self._attr_fan_modes = [FAN_AUTO, FAN_LOW, FAN_MEDIUM, FAN_HIGH]
        self._attr_supported_features = ClimateEntityFeature.TARGET_TEMPERATURE | ClimateEntityFeature.FAN_MODE
        self.min_temp = 16
        self.max_temp = 32
        # ★★★ 温度步长设为1度 ★★★
        self._attr_target_temperature_step = 1.0

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, str(self._device_id))},
            "name": self._attr_name,
            "manufacturer": "日顺智能",
            "model": "空调",
        }

    @property
    def hvac_mode(self) -> str | None:
        state = self.coordinator.data.get(self._device_id)
        if not state or not state.get("on"):
            return HVACMode.OFF
        mode = state.get("mode")
        return MODE_TO_HVAC.get(mode, HVACMode.OFF)

    @property
    def current_temperature(self) -> float | None:
        state = self.coordinator.data.get(self._device_id)
        return state.get("current_temperature") if state else None

    @property
    def target_temperature(self) -> float | None:
        state = self.coordinator.data.get(self._device_id)
        if state and "target_temperature" in state:
            return state["target_temperature"]
        return DEFAULT_TARGET_TEMPERATURE

    @property
    def fan_mode(self) -> str | None:
        state = self.coordinator.data.get(self._device_id)
        if state:
            speed = state.get("wind_speed")
            return SPEED_TO_FAN.get(speed, FAN_AUTO)
        return FAN_AUTO

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        if hvac_mode == HVACMode.OFF:
            if await self._api_client.turn_off(self._module_type, self._device_id):
                self.coordinator.update_local_state(self._device_id, "off")
                _LOGGER.debug("AC %s turned off", self._device_id)
            else:
                _LOGGER.error("Failed to turn off AC %s", self._device_id)
        else:
            current_state = self.coordinator.data.get(self._device_id)
            is_on = current_state.get("on") if current_state else False

            if not is_on:
                if await self._api_client.turn_on(self._module_type, self._device_id):
                    self.coordinator.update_local_state(self._device_id, "on")
                    _LOGGER.debug("AC %s turned on", self._device_id)
                else:
                    _LOGGER.error("Failed to turn on AC %s", self._device_id)
                    return

            mode = HVAC_TO_MODE.get(hvac_mode)
            if mode is not None:
                if await self._api_client.set_mode(self._module_type, self._device_id, mode):
                    self.coordinator.update_local_state(self._device_id, "set_mode", mode)
                    _LOGGER.debug("AC %s mode set to %s", self._device_id, mode)
                else:
                    _LOGGER.error("Failed to set mode for AC %s", self._device_id)

        self.async_write_ha_state()

    async def async_set_temperature(self, **kwargs) -> None:
        temp = kwargs.get("temperature")
        if temp is not None:
            value = temp

            current_state = self.coordinator.data.get(self._device_id)
            is_on = current_state.get("on") if current_state else False

            if not is_on:
                _LOGGER.debug("AC %s is off, turning on before setting temperature", self._device_id)
                if await self._api_client.turn_on(self._module_type, self._device_id):
                    self.coordinator.update_local_state(self._device_id, "on")
                    _LOGGER.debug("AC %s turned on", self._device_id)
                else:
                    _LOGGER.error("Failed to turn on AC %s, temperature not set", self._device_id)
                    return

            self.coordinator.update_local_state(self._device_id, "set_temperature", value)
            _LOGGER.debug("Local temperature updated to %s for device %s", temp, self._device_id)

            result = await self._api_client.set_temperature(self._module_type, self._device_id, value)
            if result:
                _LOGGER.debug("Cloud temperature set success for %s", self._device_id)
            else:
                _LOGGER.warning("Cloud temperature set failed for %s, local state retained", self._device_id)
            self.async_write_ha_state()
        else:
            _LOGGER.warning("No temperature provided in kwargs")

    async def async_set_fan_mode(self, fan_mode: str) -> None:
        speed = FAN_TO_SPEED.get(fan_mode)
        if speed is not None:
            if await self._api_client.set_wind_speed(self._module_type, self._device_id, speed):
                self.coordinator.update_local_state(self._device_id, "set_wind_speed", speed)
                _LOGGER.debug("AC %s fan speed set to %s", self._device_id, speed)
            else:
                _LOGGER.error("Failed to set fan speed for AC %s", self._device_id)
            self.async_write_ha_state()


class RishunFloorHeating(CoordinatorEntity, ClimateEntity):
    def __init__(self, coordinator: RishunDataCoordinator, api_client: CloudApiClient, device: dict):
        super().__init__(coordinator)
        self._api_client = api_client
        self._device = device
        self._device_id = device["deviceId"]
        self._module_type = device["moduleType"]

        self._attr_unique_id = f"{DOMAIN}_floor_heating_{self._device_id}"
        self._attr_name = device.get("pointName", f"地暖-{self._device_id}")
        self._attr_temperature_unit = UnitOfTemperature.CELSIUS
        self._attr_hvac_modes = [HVACMode.OFF, HVACMode.HEAT]
        self._attr_supported_features = ClimateEntityFeature.TARGET_TEMPERATURE
        self.min_temp = 16
        self.max_temp = 32
        # ★★★ 温度步长设为1度 ★★★
        self._attr_target_temperature_step = 1.0

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, str(self._device_id))},
            "name": self._attr_name,
            "manufacturer": "日顺智能",
            "model": "地暖",
        }

    @property
    def hvac_mode(self) -> str | None:
        state = self.coordinator.data.get(self._device_id)
        if state and state.get("on"):
            return HVACMode.HEAT
        return HVACMode.OFF

    @property
    def current_temperature(self) -> float | None:
        state = self.coordinator.data.get(self._device_id)
        return state.get("current_temperature") if state else None

    @property
    def target_temperature(self) -> float | None:
        state = self.coordinator.data.get(self._device_id)
        if state and "target_temperature" in state:
            return state["target_temperature"]
        return DEFAULT_TARGET_TEMPERATURE

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        if hvac_mode == HVACMode.OFF:
            if await self._api_client.turn_off(self._module_type, self._device_id):
                self.coordinator.update_local_state(self._device_id, "off")
                _LOGGER.debug("Floor heating %s turned off", self._device_id)
            else:
                _LOGGER.error("Failed to turn off floor heating %s", self._device_id)
        else:
            if await self._api_client.turn_on(self._module_type, self._device_id):
                self.coordinator.update_local_state(self._device_id, "on")
                _LOGGER.debug("Floor heating %s turned on", self._device_id)
            else:
                _LOGGER.error("Failed to turn on floor heating %s", self._device_id)
        self.async_write_ha_state()

    async def async_set_temperature(self, **kwargs) -> None:
        temp = kwargs.get("temperature")
        if temp is not None:
            value = temp

            current_state = self.coordinator.data.get(self._device_id)
            is_on = current_state.get("on") if current_state else False

            if not is_on:
                _LOGGER.debug("Floor heating %s is off, turning on before setting temperature", self._device_id)
                if await self._api_client.turn_on(self._module_type, self._device_id):
                    self.coordinator.update_local_state(self._device_id, "on")
                    _LOGGER.debug("Floor heating %s turned on", self._device_id)
                else:
                    _LOGGER.error("Failed to turn on floor heating %s, temperature not set", self._device_id)
                    return

            self.coordinator.update_local_state(self._device_id, "set_temperature", value)
            _LOGGER.debug("Local temperature updated to %s for device %s", temp, self._device_id)

            result = await self._api_client.set_temperature(self._module_type, self._device_id, value)
            if result:
                _LOGGER.debug("Cloud temperature set success for %s", self._device_id)
            else:
                _LOGGER.warning("Cloud temperature set failed for %s, local state retained", self._device_id)
            self.async_write_ha_state()
        else:
            _LOGGER.warning("No temperature provided in kwargs")


class RishunFreshAir(CoordinatorEntity, ClimateEntity):
    def __init__(self, coordinator: RishunDataCoordinator, api_client: CloudApiClient, device: dict):
        super().__init__(coordinator)
        self._api_client = api_client
        self._device = device
        self._device_id = device["deviceId"]
        self._module_type = device["moduleType"]

        self._attr_unique_id = f"{DOMAIN}_fresh_air_{self._device_id}"
        self._attr_name = device.get("pointName", f"新风-{self._device_id}")
        self._attr_hvac_modes = [HVACMode.OFF, HVACMode.FAN_ONLY]
        self._attr_fan_modes = [FAN_LOW, FAN_MEDIUM, FAN_HIGH]
        self._attr_supported_features = ClimateEntityFeature.FAN_MODE

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, str(self._device_id))},
            "name": self._attr_name,
            "manufacturer": "日顺智能",
            "model": "新风系统",
        }

    @property
    def hvac_mode(self) -> str | None:
        state = self.coordinator.data.get(self._device_id)
        if state and state.get("on"):
            return HVACMode.FAN_ONLY
        return HVACMode.OFF

    @property
    def fan_mode(self) -> str | None:
        state = self.coordinator.data.get(self._device_id)
        if state:
            speed = state.get("wind_speed")
            return SPEED_TO_FAN.get(speed, FAN_LOW)
        return FAN_LOW

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        if hvac_mode == HVACMode.OFF:
            if await self._api_client.turn_off(self._module_type, self._device_id):
                self.coordinator.update_local_state(self._device_id, "off")
                _LOGGER.debug("Fresh air %s turned off", self._device_id)
            else:
                _LOGGER.error("Failed to turn off fresh air %s", self._device_id)
        else:
            if await self._api_client.turn_on(self._module_type, self._device_id):
                self.coordinator.update_local_state(self._device_id, "on")
                _LOGGER.debug("Fresh air %s turned on", self._device_id)
            else:
                _LOGGER.error("Failed to turn on fresh air %s", self._device_id)
        self.async_write_ha_state()

    async def async_set_fan_mode(self, fan_mode: str) -> None:
        speed = FAN_TO_SPEED.get(fan_mode)
        if speed is not None:
            if await self._api_client.set_wind_speed(self._module_type, self._device_id, speed):
                self.coordinator.update_local_state(self._device_id, "set_wind_speed", speed)
                _LOGGER.debug("Fresh air %s fan speed set to %s", self._device_id, speed)
            else:
                _LOGGER.error("Failed to set fan speed for fresh air %s", self._device_id)
            self.async_write_ha_state()