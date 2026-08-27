import logging
from typing import Any

from homeassistant.components.light import LightEntity, ColorMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import RishunDataCoordinator
from rishun_api import CloudApiClient

_LOGGER = logging.getLogger(__name__)


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
        if module_type in (4, 6):
            entities.append(RishunLight(coordinator, api_client, dev))

    if entities:
        async_add_entities(entities)


class RishunLight(CoordinatorEntity, LightEntity):
    def __init__(
        self,
        coordinator: RishunDataCoordinator,
        api_client: CloudApiClient,
        device: dict,
    ):
        super().__init__(coordinator)
        self._api_client = api_client
        self._device = device
        self._device_id = device["deviceId"]
        self._module_type = device["moduleType"]

        self._attr_unique_id = f"{DOMAIN}_light_{self._device_id}"
        self._attr_name = device.get("pointName", f"灯光-{self._device_id}")

        if self._module_type == 6:
            self._attr_supported_color_modes = {ColorMode.BRIGHTNESS}
            self._attr_color_mode = ColorMode.BRIGHTNESS
        else:
            self._attr_supported_color_modes = {ColorMode.ONOFF}
            self._attr_color_mode = ColorMode.ONOFF

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, str(self._device_id))},
            "name": self._attr_name,
            "manufacturer": "日顺智能",
            "model": "调光灯光" if self._module_type == 6 else "继电器灯光",
        }

    @property
    def is_on(self) -> bool:
        state = self.coordinator.data.get(self._device_id)
        return state.get("on", False) if state else False

    @property
    def brightness(self) -> int | None:
        if self._module_type != 6:
            return None
        state = self.coordinator.data.get(self._device_id)
        return state.get("brightness", 255) if state else 255

    async def async_turn_on(self, **kwargs: Any) -> None:
        brightness = kwargs.get("brightness")
        if brightness is not None and self._module_type == 6:
            if await self._api_client.set_brightness(self._module_type, self._device_id, brightness):
                self.coordinator.update_local_state(self._device_id, "set_brightness", brightness)
        else:
            if await self._api_client.turn_on(self._module_type, self._device_id):
                self.coordinator.update_local_state(self._device_id, "on")
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        if await self._api_client.turn_off(self._module_type, self._device_id):
            self.coordinator.update_local_state(self._device_id, "off")
        self.async_write_ha_state()