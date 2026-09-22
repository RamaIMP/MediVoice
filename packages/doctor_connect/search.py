"""Real addresses only; appointment and WhatsApp actions remain simulations."""
import logging
import math
import re
from copy import deepcopy
from urllib.parse import urlencode

import httpx

from packages.doctor_connect.demo import DOCTORS


class _RedactQueryKeys(logging.Filter):
    def filter(self, record):
        record.msg = re.sub(r"(?i)(apiKey=)[^&\s\"']+", r"\1[REDACTED]", record.getMessage())
        record.args = ()
        return True


# httpx logs complete request URLs at INFO, including query authentication.
logging.getLogger("httpx").addFilter(_RedactQueryKeys())


def _coordinates(position):
    lat, lng = position["lat"], position["lng"]
    if (not all(type(v) in (float, int) and math.isfinite(v) for v in (lat, lng))
            or not -90 <= lat <= 90 or not -180 <= lng <= 180):
        raise ValueError("Invalid coordinates")
    return lat, lng


async def _here_search(settings, client, area):
    key = settings.here_api_key.get_secret_value()
    response = await client.get("https://geocode.search.hereapi.com/v1/geocode",
                                params={"q": area[:100], "limit": 1, "apiKey": key}, timeout=10)
    response.raise_for_status()
    items = response.json().get("items", [])
    if not items:
        return []
    lat, lng = _coordinates(items[0]["position"])
    response = await client.get("https://discover.search.hereapi.com/v1/discover",
                                params={"at": f"{lat},{lng}", "q": "doctors and hospitals",
                                        "limit": 3, "apiKey": key}, timeout=10)
    response.raise_for_status()
    doctors = []
    for item in response.json().get("items", [])[:3]:
        if item.get("resultType") != "place":
            continue
        name, address = item.get("title"), item.get("address", {}).get("label")
        if not all(isinstance(v, str) and v.strip() for v in (name, address)):
            continue
        lat, lng = _coordinates(item["position"])
        doctors.append(dict(id=f"real-{len(doctors) + 1}", name=name, clinic=address,
                            specialty="Doctor / hospital listing", channel="WhatsApp",
                            whatsapp=True, phone=False, booking=False, real=True,
                            position={"lat": lat, "lng": lng}, attributions=["HERE"]))
    return doctors


async def search_doctors(settings, client, area="", location=None):
    def fallback(reason):
        return dict(doctors=deepcopy(DOCTORS), source="dummy", area=area,
                    search_notice=reason + " Showing fictional demo doctors. Nothing will be booked.")

    if settings.doctor_search_mode == "dummy":
        return fallback("Dummy search mode is selected.")
    provider = settings.doctor_search_provider
    key = settings.here_api_key if provider == "here" else settings.google_places_api_key
    if not settings._present(key):
        return fallback("Live search is not configured.")
    if not area.strip() and location is None:
        return dict(doctors=[], source="location", area="", search_notice="Tap Use my location, or choose your area and city.")
    try:
        origin = _coordinates(location) if location is not None else None
        if provider == "here":
            if origin:
                return fallback("Please enter your area for HERE search.")
            doctors = await _here_search(settings, client, area)
            if not doctors:
                return fallback("No matching live listings were found.")
            return dict(doctors=doctors, source="here", area=area,
                        search_notice="Real HERE listings · Demo booking. WhatsApp preview only; no verified WhatsApp contact.")
        body = {"textQuery": "doctors and hospitals in " + area[:100], "pageSize": 3}
        endpoint = "searchText"
        if origin:
            area = "Near your current location · within 5 km"
            endpoint = "searchNearby"
            body = {"includedTypes": ["doctor", "hospital"], "maxResultCount": 3,
                    "rankPreference": "DISTANCE", "locationRestriction": {"circle": {
                        "center": {"latitude": origin[0], "longitude": origin[1]}, "radius": 5000}}}
        response = await client.post(
            "https://places.googleapis.com/v1/places:" + endpoint,
            headers={"X-Goog-Api-Key": settings.google_places_api_key.get_secret_value(),
                     "X-Goog-FieldMask": "places.id,places.displayName,places.formattedAddress,places.attributions" + (",places.location" if origin else "")},
            json=body,
            timeout=10,
        )
        response.raise_for_status()
        doctors = []
        for place in response.json().get("places", [])[:3]:
            name = place["displayName"]["text"]
            address = place["formattedAddress"]
            place_id = place["id"]
            if not all(isinstance(v, str) and v.strip() for v in (name, address, place_id)):
                raise ValueError("Incomplete listing")
            doctors.append(dict(
                id=f"real-{len(doctors) + 1}", name=name, clinic=address,
                specialty="Doctor / hospital listing", channel="WhatsApp",
                whatsapp=True, phone=False, booking=False, real=True,
                maps_url="https://www.google.com/maps/search/?" + urlencode(
                    {"api": 1, "query": name + " " + address, "query_place_id": place_id}),
                attributions=[a.get("provider", "") for a in place.get("attributions", [])
                              if isinstance(a, dict)],
            ))
            if origin and place.get("location"):
                lat, lng = _coordinates({"lat": place["location"]["latitude"], "lng": place["location"]["longitude"]})
                a, b = map(math.radians, origin)
                c, d = map(math.radians, (lat, lng))
                h = math.sin((c-a)/2)**2 + math.cos(a)*math.cos(c)*math.sin((d-b)/2)**2
                doctors[-1]["distance_km"] = round(12742 * math.asin(math.sqrt(min(1, max(0, h)))), 1)
        if not doctors:
            return fallback("No matching live listings were found.")
        return dict(doctors=doctors, source="google", area=area,
                    search_notice="Real listings · Demo booking. WhatsApp preview only; no verified WhatsApp contact.")
    except (httpx.HTTPError, ValueError, KeyError, TypeError, AttributeError):
        return fallback("Live search is unavailable.")
