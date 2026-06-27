from __future__ import annotations

from homeassistant.const import CONF_NAME
from homeassistant.components.button import ButtonEntity
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.util import dt as dt_util

from .entity import async_device_device_info_fn
from .qingping import Qingping


async def async_setup_entry(hass, config_entry, async_add_entities):
    instance: Qingping = config_entry.runtime_data
    async_add_entities([
        SyncTimeButton(instance, config_entry)
    ])


class SyncTimeButton(ButtonEntity):
    """Button to synchronize the clock with Home Assistant time."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:clock-check"

    def __init__(self, instance: Qingping, config_entry):
        self._instance: Qingping = instance
        self._config_entry = config_entry
        self._attr_unique_id = f"{instance.name}_sync_time"
        self._attr_translation_key = "sync_time"

    @property
    def device_info(self) -> DeviceInfo:
        return async_device_device_info_fn(self._instance, self._config_entry.data[CONF_NAME])

    async def async_press(self) -> None:
        now = dt_util.now()
        timezone_offset = int(now.utcoffset().total_seconds() / 60)
        timestamp = int(now.timestamp())
        await self._instance.set_time(timestamp, timezone_offset)
