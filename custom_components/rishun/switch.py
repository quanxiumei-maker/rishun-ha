import logging
from homeassistant.components.switch import SwitchEntity
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
        if dev["moduleType"] == 2:
            entities.append(RishunSwitch(coordinator, api_client, dev))

    if entities:
        async_add_entities(entities)


class RishunSwitch(CoordinatorEntity, SwitchEntity):
    def __init__(self, coordinator: RishunDataCoordinator, api_client: CloudApiClient, device: dict):
        super().__init__(coordinator)
        self._api_client = api_client
        self._device = device
        self._device_id = device["deviceId"]
        self._module_type = device["moduleType"]

        self._attr_unique_id = f"{DOMAIN}_switch_{self._device_id}"
        self._attr_name = device.get("pointName", f"开关-{self._device_id}")

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, str(self._device_id))},
            "name": self._attr_name,
            "manufacturer": "日顺智能",
            "model": "面板开关",
        }

    @property
    def is_on(self) -> bool:
        state = self.coordinator.data.get(self._device_id)
        return state.get("on", False) if state else False

    async def async_turn_on(self, **kwargs) -> None:
        if await self._api_client.turn_on(self._module_type, self._device_id):
            self.coordinator.update_local_state(self._device_id, "on")
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs) -> None:
        if await self._api_client.turn_off(self._module_type, self._device_id):
            self.coordinator.update_local_state(self._device_id, "off")
        self.async_write_ha_state()