import logging
from datetime import timedelta
from typing import Dict, List, Optional

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import DOMAIN, DEFAULT_SCAN_INTERVAL
from rishun_api import CloudApiClient

_LOGGER = logging.getLogger(__name__)


class RishunDataCoordinator(DataUpdateCoordinator):
    """
    数据协调器
    - 管理设备状态，控制成功后立即更新本地状态
    - 定时轮询云端状态，失败时自动保留上一次有效数据
    """

    def __init__(
        self,
        hass: HomeAssistant,
        api_client: CloudApiClient,
        device_list: List[Dict],
        update_interval: int = DEFAULT_SCAN_INTERVAL,
    ):
        self.api_client = api_client
        self.device_list = device_list
        self.device_ids = [dev["deviceId"] for dev in device_list]

        # 调用基类初始化
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_coordinator",
            update_interval=timedelta(seconds=update_interval),
        )

        # 强制初始化为空字典，避免 None
        self.data = {}
        # 缓存最后一次成功获取的数据（用于轮询失败时恢复）
        self._last_valid_data = {}

    async def _async_update_data(self) -> Dict[int, Dict]:
        """
        从云端获取最新状态
        - 成功获取数据时：更新缓存并返回新数据
        - 获取失败或返回空时：返回缓存数据（保持原状态）
        """
        if not self.device_ids:
            self._last_valid_data = {}
            return {}

        try:
            states = await self.api_client.query_states(self.device_ids)
            if states:
                # 查询成功且数据有效，更新缓存
                self._last_valid_data = states
                _LOGGER.debug("Fetched states: %s", states)
                return states
            else:
                # 查询成功但返回空（可能是云端无数据），保留旧状态
                _LOGGER.warning("Query states returned empty, keeping previous data")
                return self._last_valid_data
        except Exception as e:
            # 查询异常，保留旧状态
            _LOGGER.error("Query states failed: %s, keeping previous data", e)
            return self._last_valid_data

    def update_local_state(self, device_id: int, action: str, value: Optional[int] = None) -> None:
        """
        控制成功后立即更新本地状态（同时更新缓存）
        这样即使下次轮询失败，状态也不会丢失
        """
        # 确保 data 是字典
        if not isinstance(self.data, dict):
            self.data = {}

        if device_id not in self.data:
            self.data[device_id] = {}

        # 根据动作更新状态
        if action == "on":
            self.data[device_id]["on"] = True
        elif action == "off":
            self.data[device_id]["on"] = False
        elif action == "set_brightness":
            self.data[device_id]["on"] = True
            self.data[device_id]["brightness"] = value
        elif action == "open":
            self.data[device_id]["position"] = 100
        elif action == "close":
            self.data[device_id]["position"] = 0
        # stop 不改变位置
        elif action == "set_temperature":
            self.data[device_id]["target_temperature"] = value
        elif action == "set_mode":
            self.data[device_id]["mode"] = value
        elif action == "set_wind_speed":
            self.data[device_id]["wind_speed"] = value

        # 同步更新缓存，确保缓存始终是最新的有效数据
        self._last_valid_data = self.data.copy()

        # 通知所有监听器（实体）刷新
        self.async_update_listeners()