from __future__ import annotations
from datetime import time

from homeassistant.const import CONF_NAME
from homeassistant.components.time import TimeEntity
from homeassistant.helpers.entity import DeviceInfo

from .entity import async_device_device_info_fn
from .qingping import Qingping
from .qingping.alarm import Alarm
from .qingping.configuration import Configuration
from .qingping.events import DEVICE_CONFIG_UPDATE, ALARMS_UPDATE
from .const import ALARM_SLOTS_COUNT

async def async_setup_entry(hass, config_entry, async_add_entities):
    instance: Qingping = config_entry.runtime_data
    entities = [
        NighttimeStart(instance, config_entry),
        NighttimeEnd(instance, config_entry)
    ]

    for slot in range(ALARM_SLOTS_COUNT):
        entities.append(AlarmTime(instance, config_entry, slot))

    async_add_entities(entities)


class NighttimeStart(TimeEntity):
    _attr_has_entity_name = True
    _attr_translation_key = "night_start_time"

    def __init__(self, instance, config_entry):
        self._instance: Qingping = instance
        self._config_entry = config_entry
        self._attr_unique_id = f"{instance.name}_nighttime_start_time"
        self._attr_icon = "mdi:clock-in"
        self._attr_native_value = None
        instance.eventbus.add_listener(DEVICE_CONFIG_UPDATE, self.config_updated)

    @property
    def device_info(self) -> DeviceInfo:
        return async_device_device_info_fn(self._instance, self._config_entry.data[CONF_NAME])

    async def config_updated(self, config: Configuration):
        self._attr_native_value = config.night_time_start_time
        self.schedule_update_ha_state()

    async def async_set_value(self, value: time) -> None:
        await self._instance.set_nighttime_start_time(value)


class NighttimeEnd(TimeEntity):
    _attr_has_entity_name = True
    _attr_translation_key = "night_end_time"

    def __init__(self, instance, config_entry):
        self._instance: Qingping = instance
        self._config_entry = config_entry
        self._attr_unique_id = f"{instance.name}_nighttime_end_time"
        self._attr_icon = "mdi:clock-out"
        self._attr_native_value = None
        instance.eventbus.add_listener(DEVICE_CONFIG_UPDATE, self.config_updated)

    @property
    def device_info(self) -> DeviceInfo:
        return async_device_device_info_fn(self._instance, self._config_entry.data[CONF_NAME])

    async def config_updated(self, config: Configuration):
        self._attr_native_value = config.night_time_end_time
        self.schedule_update_ha_state()

    async def async_set_value(self, value: time) -> None:
        await self._instance.set_nighttime_end_time(value)


class AlarmTime(TimeEntity):
    """Time entity for a single alarm slot."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:alarm"

    def __init__(self, instance: Qingping, config_entry, slot: int):
        self._instance = instance
        self._config_entry = config_entry
        self._slot = slot
        self._attr_unique_id = f"{instance.name}_alarm_{slot}_time"
        self._attr_name = f"Alarm {slot + 1} Time"
        self._attr_native_value = None
        self._attr_available = False

        instance.eventbus.add_listener(ALARMS_UPDATE, self.alarms_updated)

    @property
    def device_info(self) -> DeviceInfo:
        return async_device_device_info_fn(self._instance, self._config_entry.data[CONF_NAME])

    async def async_set_value(self, value: time) -> None:
        await self._instance.set_alarm(
            self._slot,
            None,
            value,
            None,
            None
        )

    async def alarms_updated(self, alarms: list[Alarm]):
        if self._slot < len(alarms):
            alarm = alarms[self._slot]
            self._attr_available = True
            self._attr_native_value = alarm.time if alarm.is_configured else None
        else:
            self._attr_available = False
            self._attr_native_value = None
        self.schedule_update_ha_state()
