"""Config flow for HSL HRT integration."""

import voluptuous as vol
import re
import aiohttp
from aiohttp import ContentTypeError, ClientError

from homeassistant import config_entries, core
from homeassistant.core import callback
from homeassistant.helpers import config_validation as cv

from . import base_unique_id, graph_client

from .const import (
    _LOGGER,
    STOP_ID_QUERY,
    STOP_ID_BY_GTFS_QUERY,
    DOMAIN,
    NAME_CODE,
    STOP_CODE,
    STOP_NAME,
    STOP_GTFS,
    ERROR,
    ALL,
    VAR_NAME_CODE,
    ROUTE,
    DESTINATION,
    APIKEY,
)

api_key = None


async def validate_user_config(hass: core.HomeAssistant, data):
    """Validate input configuration for HSL HRT."""

    name_code = data[NAME_CODE].strip()
    route = data[ROUTE]
    dest = data[DESTINATION]
    apikey = data[APIKEY]

    errors = ""
    stop_code = None
    stop_name = None
    stop_gtfs = None
    ret_route = None
    ret_dest = None

    # Quick validation for API key
    if not apikey:
        return {
            STOP_CODE: None,
            STOP_NAME: None,
            STOP_GTFS: None,
            ROUTE: None,
            DESTINATION: None,
            ERROR: "missing_apikey",
            APIKEY: apikey,
        }

    #
    # Detect GTFS ID
    #
    GTFS_ID_REGEX = re.compile(r"^HSL:\d+$")
    is_gtfs_id = GTFS_ID_REGEX.match(name_code)

    #
    # 1. GTFS ID → query via ids:
    #
    if is_gtfs_id:
        stop_gtfs = name_code
        variables = {"ids": [stop_gtfs]}

        graph_client.headers["digitransit-subscription-key"] = apikey
        graph_client.headers["Ocp-Apim-Subscription-Key"] = apikey
        graph_client.headers["Accept"] = "application/json"

        hsl_data = await graph_client.execute_async(
            query=STOP_ID_BY_GTFS_QUERY,
            variables=variables
        )

        stops_data = hsl_data.get("data", {}).get("stops", [])

        if not stops_data:
            return {
                STOP_CODE: None,
                STOP_NAME: None,
                STOP_GTFS: None,
                ROUTE: None,
                DESTINATION: None,
                ERROR: "invalid_name_code",
                APIKEY: apikey,
            }

    #
    # 2. NAME SEARCH (default)
    #
    else:
        stops_data = []
        for attempt in (name_code, name_code.upper(), name_code.lower()):
            variables = {VAR_NAME_CODE: attempt}

            graph_client.headers["digitransit-subscription-key"] = apikey
            graph_client.headers["Ocp-Apim-Subscription-Key"] = apikey
            graph_client.headers["Accept"] = "application/json"

            hsl_data = await graph_client.execute_async(
                query=STOP_ID_QUERY,
                variables=variables
            )

            stops_data = hsl_data.get("data", {}).get("stops", [])
            if stops_data:
                break

        if not stops_data:
            return {
                STOP_CODE: None,
                STOP_NAME: None,
                STOP_GTFS: None,
                ROUTE: None,
                DESTINATION: None,
                ERROR: "invalid_name_code",
                APIKEY: apikey,
            }

        # Extract GTFS ID from name search result
        stop_gtfs = stops_data[0].get("gtfsId")

        # Now fetch full stop info via ids:
        variables = {"ids": [stop_gtfs]}

        hsl_data = await graph_client.execute_async(
            query=STOP_ID_BY_GTFS_QUERY,
            variables=variables
        )

        stops_data = hsl_data.get("data", {}).get("stops", [])

    #
    # Extract stop info
    #
    stop_data = stops_data[0]
    stop_gtfs = stop_data.get("gtfsId")
    stop_name = stop_data.get("name")
    stop_code = stop_data.get("code")

    #
    # Route/destination filtering
    #
    routes = stop_data.get("routes", [])

    if route.lower() != ALL:
        for rt in routes:
            if rt.get("shortName", "").lower() == route.lower():
                ret_route = route
                break
        if ret_route is None:
            return {
                STOP_CODE: stop_code,
                STOP_NAME: stop_name,
                STOP_GTFS: stop_gtfs,
                ROUTE: None,
                DESTINATION: None,
                ERROR: "invalid_route",
                APIKEY: apikey,
            }

    if dest.lower() != ALL:
        for rt in routes:
            for pattern in rt.get("patterns", []):
                head = pattern.get("headsign", "")
                if dest.lower() in head.lower():
                    ret_dest = head
                    break
        if ret_dest is None:
            return {
                STOP_CODE: stop_code,
                STOP_NAME: stop_name,
                STOP_GTFS: stop_gtfs,
                ROUTE: ret_route,
                DESTINATION: None,
                ERROR: "invalid_destination",
                APIKEY: apikey,
            }

    #
    # Success
    #
    return {
        STOP_CODE: stop_code,
        STOP_NAME: stop_name,
        STOP_GTFS: stop_gtfs,
        ROUTE: ret_route or route,
        DESTINATION: ret_dest or dest,
        ERROR: "",
        APIKEY: apikey,
    }


class HSLHRTConfigFlowHandler(config_entries.ConfigFlow, domain=DOMAIN):
    """Config flow handler for FMI."""

    VERSION = 1
    CONNECTION_CLASS = config_entries.CONN_CLASS_CLOUD_POLL

    async def async_step_user(self, user_input=None):
        """Handle user step."""
        # Display an option for the user to provide Stop Name/Code for the integration
        errors = {}
        valid = {}

        if user_input is not None:
            valid = await validate_user_config(self.hass, user_input)
            await self.async_set_unique_id(
                base_unique_id(valid[STOP_GTFS], valid[ROUTE], valid[DESTINATION])
            )
            self._abort_if_unique_id_configured()
            if valid.get(ERROR, "") == "":
                title = ""
                if valid[ROUTE] is not None:
                    title = f"{valid[STOP_NAME]}({valid[STOP_CODE]}) {valid[ROUTE]}"
                elif valid[DESTINATION] is not None:
                    title = (
                        f"{valid[STOP_NAME]}({valid[STOP_CODE]}) {valid[DESTINATION]}"
                    )
                else:
                    title = f"{valid[STOP_NAME]}({valid[STOP_CODE]}) ALL"
                return self.async_create_entry(title=title, data=valid)
            else:
                reason = valid.get(ERROR, "Configuration Error!")
                _LOGGER.error(reason)
                return self.async_abort(reason=reason)

        data_schema = vol.Schema(
            {
                vol.Required(
                    NAME_CODE,
                    description={
                        "suggested_value": "",
                        "description": (
                            "Enter a stop name (e.g. 'Kuusisaarentie') or a GTFS ID "
                            "(e.g. 'HSL:1303298'). Stop codes like 'H1415' are no longer supported."
                        )
                    },
                ): str,
                vol.Required(
                    ROUTE,
                    description={
                        "suggested_value": "ALL",
                        "description": (
                            "Optional: Filter by route short name (e.g. '550'). "
                            "Use 'ALL' to include all routes."
                        )
                    },
                ): str,
                vol.Required(
                    DESTINATION,
                    description={
                        "suggested_value": "ALL",
                        "description": (
                            "Optional: Filter by destination headsign (e.g. 'Itäkeskus'). "
                            "Use 'ALL' to include all destinations."
                        )
                    },
                ): str,
                vol.Required(
                    APIKEY,
                    description={
                        "suggested_value": "",
                        "description": (
                            "Enter your Digitransit API key. You can create one at "
                            "https://portal-api.digitransit.fi/"
                        )
                    },
                ): str,
            }
        )

        return self.async_show_form(
            step_id="user",
            data_schema=data_schema,
            description_placeholders={ 
                "info": ( 
                    "Provide a stop name or GTFS ID. Stop codes are deprecated and "   
                    "no longer supported by the Routing API v2." 
                ) 
            },
            errors=errors,
        )
