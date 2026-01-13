"""Helper functions for HSL HRT integration."""

import logging
from . import graph_client
from .const import (
    STOP_ID_QUERY,
    STOP_ID_BY_GTFS_QUERY,
)

_LOGGER = logging.getLogger(__name__)


async def _set_headers(apikey: str):
    """Set Digitransit API headers."""
    graph_client.headers["digitransit-subscription-key"] = apikey
    graph_client.headers["Ocp-Apim-Subscription-Key"] = apikey
    graph_client.headers["Accept"] = "application/json"


# ---------------------------------------------------------
# STOP LOOKUP
# ---------------------------------------------------------

async def lookup_stops(apikey: str, name_query: str):
    """
    Return a list of stops matching a partial name.
    Output format:
    [
        {"name": "...", "code": "...", "gtfsId": "..."},
        ...
    ]
    """
    await _set_headers(apikey)

    stops = []

    # Try multiple case variations for better matching
    for attempt in (name_query, name_query.upper(), name_query.lower()):
        variables = {"id": attempt}

        try:
            _LOGGER.warning("lookup_stops variables=%s", variables)
            data = await graph_client.execute_async(
                query=STOP_ID_QUERY,
                variables=variables
            )
        except Exception as e:
            _LOGGER.error("Stop lookup failed for '%s': %s", attempt, e)
            continue

        result = data.get("data", {}).get("stops", [])
        if result:
            stops = result
            break

    return [
        {
            "name": s.get("name"),
            "code": s.get("code"),
            "gtfsId": s.get("gtfsId"),
        }
        for s in stops
    ]


# ---------------------------------------------------------
# ROUTE LOOKUP
# ---------------------------------------------------------

async def lookup_routes(apikey: str, gtfs_id: str):
    """
    Return all routes serving a stop.
    Output format:
    [
        {"shortName": "550", "patterns": [...]},
        ...
    ]
    """
    await _set_headers(apikey)

    variables = {"ids": [gtfs_id]}

    try:
        data = await graph_client.execute_async(
            query=STOP_ID_BY_GTFS_QUERY,
            variables=variables
        )
    except Exception as e:
        _LOGGER.error("Route lookup failed for %s: %s", gtfs_id, e)
        return []

    stops = data.get("data", {}).get("stops", [])
    if not stops:
        return []

    routes = stops[0].get("routes", [])
    return [
        {
            "shortName": r.get("shortName"),
            "patterns": r.get("patterns", []),
        }
        for r in routes
        if r.get("shortName")
    ]


# ---------------------------------------------------------
# DESTINATION LOOKUP
# ---------------------------------------------------------

async def lookup_destinations(apikey: str, gtfs_id: str, route_short_name: str):
    """
    Return all destination headsigns for a route at a stop.
    Output format:
    ["Itäkeskus", "Westendinasema", ...]
    """
    if route_short_name.upper() == "ALL":
        return ["ALL"]

    routes = await lookup_routes(apikey, gtfs_id)

    dests = set()
    for r in routes:
        if r["shortName"].lower() == route_short_name.lower():
            for p in r.get("patterns", []):
                head = p.get("headsign")
                if head:
                    dests.add(head)

    return sorted(list(dests)) or ["ALL"]
