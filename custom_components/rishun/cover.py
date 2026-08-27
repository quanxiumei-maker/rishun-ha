import logging
from typing import Any
from homeassistant.components.cover import CoverEntity
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
        if dev["moduleType"] == 5:
            entities.append(RishunCover(coordinator, api_client, dev))

    if entities:
        async_add_entities(entities)


class RishunCover(CoordinatorEntity, CoverEntity):
    def __init__(self, coordinator: RishunDataCoordinator, api_client: CloudApiClient, device: dict):
        super().__init__(coordinator)
        self._api_client = api_client
        self._device = device
        self._device_id = device["deviceId"]
        self._module_type = device["moduleType"]

        self._attr_unique_id = f"{DOMAIN}_cover_{self._device_id}"
        self._attr_name = device.get("pointName", f"窗帘-{self._device_id}")

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, str(self._device_id))},
            "name": self._attr_name,
            "manufacturer": "日顺智能",
            "model": "电动窗帘",
        }

    @property
    def is_closed(self) -> bool:
        state = self.coordinator.data.get(self._device_id)
        return state.get("position", 0) == 0 if state else True

    @property
    def current_cover_position(self) -> int:
        state = self.coordinator.data.get(self._device_id)
        return state.get("position", 0) if state else 0

    async def async_open_cover(self, **kwargs: Any) -> None:
        if await self._api_client.open_cover(self._module_type, self._device_id):
            self.coordinator.update_local_state(self._device_id, "open")
        self.async_write_ha_state()

    async def async_close_cover(self, **kwargs: Any) -> None:
        if await self._api_client.close_cover(self._module_type, self._device_id):
            self.coordinator.update_local_state(self._device_id, "close")
        self.async_write_ha_state()

    async def async_stop_cover(self, **kwargs: Any) -> None:
        # stop 不改变状态，但发送指令后可以刷新一下
        await self._api_client.stop_cover(self._module_type, self._device_id)
        # 不更新位置，但可以触发重绘
        self.async_write_ha_state()