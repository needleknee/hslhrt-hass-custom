"""Sensor platform for HSL HRT routes."""

from homeassistant.util import Throttle
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from homeassistant.const import ATTR_ATTRIBUTION

from .const import (
    _LOGGER,
    DOMAIN,
    COORDINATOR,
    STOP_GTFS,
    STOP_NAME,
    STOP_CODE,
    ROUTE,
    ATTR_ROUTE,
    ATTR_DEST,
    ATTR_ARR_TIME,
    ATTR_STOP_NAME,
    ATTR_STOP_CODE,
    ATTR_STOP_GTFS,
    DICT_KEY_ROUTE,
    DICT_KEY_ROUTES,
    DICT_KEY_DEST,
    DICT_KEY_ARRIVAL,
    ATTRIBUTION,
    ALL,
)

SENSOR_TYPES = {ROUTE: ["Route", None]}

PARALLEL_UPDATES = 1


async def async_setup_entry(hass, config_entry, async_add_entities):
    """Set up the HSL HRT Sensor."""
    name = config_entry.data.get(STOP_GTFS, "")

    coordinator = hass.data[DOMAIN][config_entry.entry_id][COORDINATOR]

    entity_list = []

    for sensor_type in SENSOR_TYPES:
        entity_list.append(HSLHRTRouteSensor(name, coordinator, sensor_type))

    async_add_entities(entity_list, False)


class HSLHRTRouteSensor(CoordinatorEntity):
    """Implementation of a HSL HRT sensor."""

    _attr_icon = "mdi:bus"
    _attr_has_entity_name= True
    
    def __init__(self, name, coordinator, sensor_type):
        super().__init__(coordinator)
    
        self.client_name = name
        self.type = sensor_type
    
        self._attr_name = "Route"
        self._attr_native_unit_of_measurement = SENSOR_TYPES[sensor_type][1]
    
        self._attr_unique_id = base_unique_id(
            coordinator.gtfs_id,
            coordinator.route,
            coordinator.dest
        )

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, self.coordinator.gtfs_id)},
            "name": self.coordinator.route_data[STOP_NAME],
            "manufacturer": "HSL / Digitransit",
            "model": "Routing API v2",
        }

    @property
    def native_value(self):
        """Return the current route."""
        data = self.coordinator.route_data

        if not data or not data.get(DICT_KEY_ROUTES):
            return None

        # First route is the primary one
        primary = data[DICT_KEY_ROUTES][0]
        return primary.get(DICT_KEY_ROUTE)

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        data = self.coordinator.route_data
        
        if not data or not data.get(DICT_KEY_ROUTES):
            return {ATTR_ATTRIBUTION: ATTRIBUTION}
            
        routes = []
        for rt in data[DICT_KEY_ROUTES][1:]:
            routes.append({
                ATTR_ROUTE: rt[DICT_KEY_ROUTE],
                ATTR_DEST: rt[DICT_KEY_DEST] or "Unavailable",
                ATTR_ARR_TIME: rt[DICT_KEY_ARRIVAL],
            })

        primary = data[DICT_KEY_ROUTES][0]
        
        return {
            ATTR_ROUTE: primary[DICT_KEY_ROUTE],
            ATTR_DEST: primary[DICT_KEY_DEST] or "Unavailable",
            ATTR_ARR_TIME: primary[DICT_KEY_ARRIVAL],
            "ROUTES": routes,
            ATTR_STOP_NAME: data[STOP_NAME],
            ATTR_STOP_CODE: data[STOP_CODE],
            ATTR_STOP_GTFS: data[STOP_GTFS],
            ATTR_ATTRIBUTION: ATTRIBUTION,
        }
