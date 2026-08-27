import logging
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import aiohttp_client

from .const import DOMAIN, DEFAULT_API_BASE
from rishun_api import CloudApiClient
from .coordinator import RishunDataCoordinator

PLATFORMS = ["light", "switch", "cover", "sensor", "climate"]

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    hass.data.setdefault(DOMAIN, {})

    # 创建 API 客户端
    session = aiohttp_client.async_get_clientsession(hass)
    api_client = CloudApiClient(session, entry.data.get("api_base", DEFAULT_API_BASE))

    # 获取设备列表
    device_list = entry.data.get("deviceData", [])

    # 创建协调器
    coordinator = RishunDataCoordinator(
        hass,
        api_client,
        device_list,
        entry.data.get("scan_interval", 30),
    )
    await coordinator.async_config_entry_first_refresh()

    # 存储
    hass.data[DOMAIN][entry.entry_id] = {
        "coordinator": coordinator,
        "api_client": api_client,
        "device_list": device_list,
    }

    # 加载平台
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok