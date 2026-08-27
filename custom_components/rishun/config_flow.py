from __future__ import annotations

import logging
from typing import Dict, Optional

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.helpers import aiohttp_client

from .const import (
    DOMAIN,
    CONF_PHONE,
    CONF_PASSWORD,
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_API_BASE,
)
from rishun_api import CloudApiClient

_LOGGER = logging.getLogger(__name__)


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self):
        self._api_client: Optional[CloudApiClient] = None
        self._phone: str = ""
        self._password: str = ""
        self._houses: Dict[str, str] = {}
        self._selected_house_id: str = ""
        self._device_data: Dict = {}
        self._gw_mac: str = ""

    async def async_step_user(self, user_input: Optional[Dict] = None):
        """第一步：输入手机号和密码"""
        errors = {}
        if user_input is not None:
            phone = user_input.get(CONF_PHONE, "").strip()
            password = user_input.get(CONF_PASSWORD, "").strip()

            if not phone or not password:
                errors["base"] = "手机号和密码不能为空"
            else:
                try:
                    session = aiohttp_client.async_get_clientsession(self.hass)
                    self._api_client = CloudApiClient(session, DEFAULT_API_BASE)
                    json_result = await self._api_client.check_user(phone, password)
                    _LOGGER.info("=== Login API response ===")
                    _LOGGER.info("Response: %s", json_result)

                    code = json_result.get("code")

                    if code == 500:
                        errors["base"] = json_result.get("msg", "手机号或密码错误")

                    elif code == 0:
                        _LOGGER.info("✅ Code=0: Direct device data returned.")
                        self._phone = phone
                        self._password = password
                        self._device_data = await self._house_data_handle(json_result)
                        if not self._device_data.get("deviceData"):
                            errors["base"] = "该账号下没有设备"
                        else:
                            return await self.async_step_finish()

                    elif code == 200:
                        _LOGGER.info("✅ Code=200: Multiple houses returned.")
                        self._phone = phone
                        self._password = password
                        houses_data = json_result.get("data", [])
                        _LOGGER.info("Raw houses_data: %s", houses_data)

                        self._houses = {item["id"]: item["name"] for item in houses_data}
                        _LOGGER.info("Parsed houses: %s", self._houses)

                        if not self._houses:
                            errors["base"] = "该账号下没有房屋"
                        else:
                            return await self.async_step_house_select()

                    else:
                        errors["base"] = f"登录失败，未知错误码: {code}"

                except Exception as e:
                    _LOGGER.exception("登录异常")
                    errors["base"] = f"登录异常: {str(e)}"

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required(CONF_PHONE, default=user_input.get(CONF_PHONE, "") if user_input else ""): str,
                vol.Required(CONF_PASSWORD, default=user_input.get(CONF_PASSWORD, "") if user_input else ""): str,
            }),
            errors=errors,
        )

    async def async_step_house_select(self, user_input: Optional[Dict] = None):
        """第二步：选择房屋（多个房屋时）"""
        errors = {}

        if user_input is None:
            _LOGGER.info("=== Entering house selection ===")
            _LOGGER.info("Available houses: %s", self._houses)

        if user_input is not None:
            self._selected_house_id = user_input["house_id"]
            _LOGGER.info("=== User selected house ID: %s ===", self._selected_house_id)
            _LOGGER.info("Selected house name: %s", self._houses.get(self._selected_house_id, "Unknown"))

            try:
                json_result = await self._api_client.get_dev_by_house(self._selected_house_id)
                _LOGGER.info("=== Raw JSON from get_dev_by_house ===")
                _LOGGER.info("Result: %s", json_result)

                self._device_data = await self._house_data_handle(json_result)
                _LOGGER.info("Parsed device_data: %s", self._device_data)

                if not self._device_data.get("deviceData"):
                    errors["base"] = "该房屋下没有设备"
                else:
                    return await self.async_step_finish()

            except Exception as e:
                _LOGGER.exception("获取设备失败")
                errors["base"] = f"获取设备失败: {str(e)}"

        house_options = {hid: name for hid, name in self._houses.items()}
        _LOGGER.info("House options for dropdown: %s", house_options)

        return self.async_show_form(
            step_id="house_select",
            data_schema=vol.Schema({
                vol.Required("house_id", default=list(house_options.keys())[0]): vol.In(house_options),
            }),
            errors=errors,
        )

    async def async_step_finish(self, user_input: Optional[Dict] = None):
        """第三步：完成配置，设置更新间隔"""
        if user_input is not None:
            scan_interval = user_input.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        else:
            scan_interval = DEFAULT_SCAN_INTERVAL

        config_data = self._device_data.copy()
        config_data[CONF_SCAN_INTERVAL] = scan_interval
        config_data[CONF_PHONE] = self._phone
        config_data[CONF_PASSWORD] = self._password

        house_name = self._houses.get(self._selected_house_id, "我的房屋") if self._houses else "日顺设备"
        _LOGGER.info("=== Configuration complete ===")
        _LOGGER.info("Title: %s", f"日顺智能 ({house_name})")
        _LOGGER.info("Device count: %s", len(config_data.get("deviceData", [])))

        return self.async_create_entry(
            title=f"日顺智能 ({house_name})",
            data=config_data,
        )

    # ============================================================
    # 设备数据解析（核心修改：直接使用数字，不再映射）
    # ============================================================
    async def _house_data_handle(self, json_data: dict) -> dict:
        """
        解析设备数据：
        使用云端的 deviceId (int) 作为唯一标识，
        module_type 直接从 byteData 第一个字段获取（原始数字）
        """
        _LOGGER.debug("=== Starting _house_data_handle ===")
        _LOGGER.debug("Input json_data keys: %s", json_data.keys() if json_data else "None")

        try:
            data = json_data.get("data")
            _LOGGER.debug("data type: %s, length: %s", type(data), len(data) if data else 0)
            if not data or not isinstance(data, list) or len(data) == 0:
                _LOGGER.warning("data is empty or not a list")
                return {"batch": True, "deviceData": [], "host": ""}

            first_item = data[0]
            gwMac = first_item.get("gwMac", "")
            _LOGGER.debug("gwMac: %s", gwMac)

            area_data = first_item.get("areaList", [])
            _LOGGER.debug("area_data length: %s", len(area_data))

        except Exception as e:
            _LOGGER.exception("Failed to extract data from json: %s", e)
            return {"batch": True, "deviceData": [], "host": ""}

        deviceData = []
        seen_ids = set()

        for area_idx, area in enumerate(area_data):
            _LOGGER.debug("Processing area %s: %s", area_idx, area.get("areaInfo", "No areaInfo"))
            device_list = area.get("deviceInfoList", [])
            _LOGGER.debug("  deviceInfoList length: %s", len(device_list))

            for dev_idx, dev in enumerate(device_list):
                _LOGGER.debug("  Device %s: %s", dev_idx, dev.get("deviceName", "No name"))
                instruct_list = dev.get("instructInfoList", [])
                if not instruct_list:
                    _LOGGER.debug("    No instructInfoList, skip")
                    continue

                first_instruct = instruct_list[0]
                if not isinstance(first_instruct, dict):
                    _LOGGER.debug("    first_instruct not dict, skip")
                    continue

                in_device = first_instruct.get("inDevice")
                if not isinstance(in_device, dict):
                    _LOGGER.debug("    inDevice not dict, skip")
                    continue

                # ★★★ 获取云端 deviceId ★★★
                device_id = in_device.get("deviceId")
                _LOGGER.debug("    deviceId: %s (type: %s)", device_id, type(device_id))
                if device_id is None:
                    _LOGGER.debug("    No deviceId, skip")
                    continue

                # 解析 byteData
                cmd = in_device.get("byteData")
                if not isinstance(cmd, str) or len(cmd) < 8:
                    _LOGGER.debug("    byteData invalid: %s", cmd)
                    continue

                byte = cmd.split("_")
                if len(byte) < 4:
                    _LOGGER.debug("    byteData split len < 4: %s", byte)
                    continue

                try:
                    # ★★★ 核心改动：直接取数字，不做任何映射 ★★★
                    module_type = int(byte[0], 16)
                    module_addr = int(byte[1], 16)
                    point_addr = int(byte[3], 16)
                    _LOGGER.debug("    module_type: %s, module_addr: %s, point_addr: %s", module_type, module_addr, point_addr)

                except Exception as e:
                    _LOGGER.debug("    Error parsing byteData: %s", e)
                    continue

                # 过滤：特殊模块只取 pointAddr == 1
                # if module_type in (7, 10, 11, 30) and point_addr != 1:
                #     _LOGGER.debug("    Filtered: module_type %s point_addr %s != 1, skip", module_type, point_addr)
                #     continue

                # 去重
                if device_id in seen_ids:
                    _LOGGER.debug("    Duplicate device_id %s, skip", device_id)
                    continue
                seen_ids.add(device_id)

                device_entry = {
                    "deviceId": device_id,
                    "moduleType": module_type,
                    "moduleAddr": module_addr,   # 保留但不使用
                    "pointAddr": point_addr,     # 保留但不使用
                    "pointName": dev.get("deviceName", f"设备-{device_id}"),
                }
                _LOGGER.debug("    ✅ Adding device: %s", device_entry)
                deviceData.append(device_entry)

        _LOGGER.info("=== Total parsed devices: %s ===", len(deviceData))
        result = {
            "batch": True,
            "deviceData": deviceData,
            "host": gwMac,
        }
        _LOGGER.debug("=== _house_data_handle result: %s", result)
        return result