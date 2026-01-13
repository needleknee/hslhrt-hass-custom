"""Config flow for HSL HRT integration."""

import voluptuous as vol
import re

from homeassistant import config_entries

from . import base_unique_id
from .helpers import (
    lookup_stops,
    lookup_routes,
    lookup_destinations,
)

from .const import (
    _LOGGER,
    DOMAIN,
    STOP_GTFS,
    STOP_NAME,
    STOP_CODE,
    ALL,
    ROUTE,
    DESTINATION,
    APIKEY,
)

GTFS_REGEX = re.compile(r"^HSL:\d+$")


class HSLHRTConfigFlowHandler(config_entries.ConfigFlow, domain=DOMAIN):
    """Config flow handler for FMI."""

    VERSION = 1
    CONNECTION_CLASS = config_entries.CONN_CLASS_CLOUD_POLL

    async def async_step_apikey(self, user_input=None):
        """Ask the user for the Digitransit API key."""
        errors = {}
    
        if user_input is not None:
            key = user_input.get(APIKEY, "").strip()
    
            if not key:
                errors["base"] = "missing_apikey"
            else:
                # Store globally
                self.hass.data.setdefault(DOMAIN, {})[APIKEY] = key
                self.existing_key = key
    
                # Now that we have the key → go to stop name step
                return await self.async_step_user()
    
        return self.async_show_form(
            step_id="apikey",
            data_schema=vol.Schema({
                vol.Required(APIKEY): str
            }),
            errors=errors,
        )

    async def async_step_user(self, user_input=None):
        """Ask for stop name or GTFS ID."""
        errors = {}
    
        # Load global API key
        self.existing_key = self.hass.data.get(DOMAIN, {}).get(APIKEY)
    
        # If no API key yet → ask for it first
        if self.existing_key is None:
            return await self.async_step_apikey()
    
        if user_input is not None:
            self.stop_query = user_input["stop_query"].strip()
    
            if GTFS_REGEX.match(self.stop_query):
                self.selected_stop = self.stop_query

                # Fetch stop info for naming
                stops = await lookup_stops(self.existing_key, self.stop_query)
                if stops:
                    s = stops[0]
                    self.selected_stop_name = s["name"]
                    self.selected_stop_code = s["code"]
                else:
                    # Fallback if lookup fails
                    self.selected_stop_name = self.stop_query
                    self.selected_stop_code = ""
                
                return await self.async_step_pick_route()
    
            return await self.async_step_pick_stop()
    
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required("stop_query"): str
            }),
            errors=errors,
        )

    async def async_step_pick_stop(self, user_input=None):
        """Show dropdown of matching stops."""
        apikey = self.existing_key
        if not apikey:
            return self.async_abort(reason="missing_apikey")

        stops = await lookup_stops(apikey, self.stop_query)

        if not stops:
            return self.async_show_form(
                step_id="user",
                errors={"base": "no_stops_found"},
                data_schema=vol.Schema({
                    vol.Required("stop_query"): str
                })
            )

        self.stops = {
            f"{s['name']} ({s['code']})": {
                "gtfsId": s["gtfsId"],
                "name": s["name"],
                "code": s["code"],
            }
            for s in stops
        }

        if user_input is not None:
            self.selected_stop = self.stops[user_input["stop"]]
            self.selected_stop = selected["gtfsId"]
            self.selected_stop_name = selected["name"]
            self.selected_stop_code = selected["code"]
            return await self.async_step_pick_route()

        return self.async_show_form(
            step_id="pick_stop",
            data_schema=vol.Schema({
                vol.Required("stop"): vol.In(list(self.stops.keys()))
            }),
        )

    async def async_step_pick_route(self, user_input=None):
        """Show dropdown of routes for the selected stop."""
        apikey = self.existing_key
        if not apikey:
            return self.async_abort(reason="missing_apikey")

        routes = await lookup_routes(apikey, self.selected_stop)
        self.routes = sorted([r["shortName"] for r in routes])

        if not self.routes:
            return self.async_abort(reason="no_routes_found")

        route_options = self.routes + [ALL]

        if user_input is not None:
            self.selected_route = user_input["route"]

            if self.selected_route == ALL:
                self.selected_dest = ALL
                return await self._create_final_entry()

            return await self.async_step_pick_dest()

        return self.async_show_form(
            step_id="pick_route",
            data_schema=vol.Schema({
                vol.Required("route"): vol.In(route_options)
            }),
        )

    async def async_step_pick_dest(self, user_input=None):
        """Show dropdown of destinations for the selected route."""
        apikey = self.existing_key
        if not apikey:
            return self.async_abort(reason="missing_apikey")

        dests = await lookup_destinations(apikey, self.selected_stop, self.selected_route)
        self.dests = sorted(dests)

        dest_options = self.dests + [ALL]
        
        if user_input is not None:
            self.selected_dest = user_input["dest"]
            return await self._create_final_entry()

        return self.async_show_form(
            step_id="pick_dest",
            data_schema=vol.Schema({
                vol.Required("dest"): vol.In(dest_options)
            }),
        )

    async def _create_final_entry(self):
        """Create the final config entry."""

        unique_id = base_unique_id(
            self.selected_stop,
            self.selected_route,
            self.selected_dest,
        )

        await self.async_set_unique_id(unique_id)
        self._abort_if_unique_id_configured()

        # Build a clean, human-friendly title
        stop_label = f"{self.selected_stop_name} ({self.selected_stop_code})"
        
        if self.selected_route == ALL:
            title = f"{stop_label} – ALL"
        elif self.selected_dest == ALL:
            title = f"{stop_label} – {self.selected_route} (ALL)"
        else:
            title = f"{stop_label} – {self.selected_route} → {self.selected_dest}"

        return self.async_create_entry(
            title=title, 
            data={
                STOP_GTFS: self.selected_stop,
                STOP_NAME: self.selected_stop_name,
                STOP_CODE: self.selected_stop_code,
                ROUTE: self.selected_route,
                DESTINATION: self.selected_dest,
                APIKEY: self.existing_key,
            },
        )
