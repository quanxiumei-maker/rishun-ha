# sensor.py
import logging
from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature, PERCENTAGE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import RishunDataCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """设置传感器实体"""
    entry_data = hass.data[DOMAIN][config_entry.entry_id]
    coordinator = entry_data["coordinator"]
    device_list = entry_data["device_list"]

    entities = []
    for dev in device_list:
        if dev["moduleType"] == 30:  # 空气质量模块
            device_id = dev["deviceId"]
            base_name = dev.get("pointName", f"传感器-{device_id}")
            entities.extend([
                RishunSensor(
                    coordinator, device_id, f"{base_name} 温度", "temperature",
                    SensorDeviceClass.TEMPERATURE, UnitOfTemperature.CELSIUS,
                ),
                RishunSensor(
                    coordinator, device_id, f"{base_name} 湿度", "humidity",
                    SensorDeviceClass.HUMIDITY, PERCENTAGE,
                ),
                RishunSensor(
                    coordinator, device_id, f"{base_name} PM2.5", "pm25",
                    SensorDeviceClass.PM25, "µg/m³",  # 使用字符串
                ),
                RishunSensor(
                    coordinator, device_id, f"{base_name} CO2", "co2",
                    SensorDeviceClass.CO2, "ppm",    # 使用字符串
                ),
                RishunSensor(
                    coordinator, device_id, f"{base_name} CH2O", "ch2o",
                    None, "mg/m³",
                ),
                RishunSensor(
                    coordinator, device_id, f"{base_name} TVOC", "tvoc",
                    None, "ppb",    # 使用字符串
                ),
            ])

    if entities:
        async_add_entities(entities)


class RishunSensor(CoordinatorEntity):
    """通用的传感器实体，根据 key 从 coordinator 数据中读取值"""

    def __init__(
        self,
        coordinator: RishunDataCoordinator,
        device_id: int,
        name: str,
        key: str,
        device_class: str | None,
        unit: str | None,
    ):
        super().__init__(coordinator)
        self._device_id = device_id
        self._key = key
        self._attr_unique_id = f"{DOMAIN}_sensor_{device_id}_{key}"
        self._attr_name = name
        self._attr_device_class = device_class
        self._attr_native_unit_of_measurement = unit

    @property
    def native_value(self) -> float | None:
        """返回传感器当前值"""
        state = self.coordinator.data.get(self._device_id)
        if state:
            return state.get(self._key)
        return None

    @property
    def device_info(self):
        """设备信息，用于将传感器关联到同一个设备"""
        return {
            "identifiers": {(DOMAIN, str(self._device_id))},
            "name": self._attr_name,
            "manufacturer": "日顺智能",
            "model": "空气质量传感器",
        }