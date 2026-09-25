import json

import httpx
import pytest

from packages.doctor_connect.search import search_doctors
from packages.shared.settings import Settings
from packages.voice.pipeline import Pipeline


def config(**kwargs):
    return Settings(_env_file=None, google_places_api_key="test", **kwargs)


async def test_location_search_uses_nearby_and_shared_booking_state():
    calls = []
    def handler(request):
        calls.append(request)
        assert request.url.path.endswith(":searchNearby")
        body = json.loads(request.content)
        assert body["locationRestriction"]["circle"]["center"] == {"latitude": 12, "longitude": 77}
        assert body["rankPreference"] == "DISTANCE"
        return httpx.Response(200, json={"places": [{"id": "place", "displayName": {"text": "Clinic"},
            "formattedAddress": "Clinic address", "location": {"latitude": 12.01, "longitude": 77}}]})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        pipeline = Pipeline(config(), client)
        result = await pipeline.care_command("search_location", {"lat": 12, "lng": 77}, 0)
        assert result["care_state"]["doctors"][0]["distance_km"] == 1.1
        assert "location" not in result["care_state"]  # User coordinates are not persisted in state.
        for action, value in [("select", "real-1"), ("yes", ""), ("set_date", "2026-10-01"),
                              ("set_time", "10:00"), ("set_patient", "Demo"), ("yes", ""), ("yes", "")]:
            result = await pipeline.care_command(action, value, pipeline.care_state["revision"])
        assert result["care_state"]["stage"] == "handoff"
    assert len(calls) == 1


@pytest.mark.parametrize("location", [{"lat": True, "lng": 77}, {"lat": 100, "lng": 77}, {}, {"lat": "12", "lng": 77}])
async def test_invalid_location_never_reaches_provider(location):
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r: pytest.fail("Invalid location sent"))) as client:
        result = await search_doctors(config(), client, location=location)
    assert result["source"] == "dummy"


async def test_here_real_listing_and_booking(caplog):
    caplog.set_level("INFO", logger="httpx")
    calls = []
    def handler(request):
        calls.append(request)
        assert request.url.params["apiKey"] == "private-here-test-key"
        if request.url.host == "geocode.search.hereapi.com":
            assert request.url.params["q"] == "Bengaluru"
            return httpx.Response(200, json={"items": [{"position": {"lat": 12.97, "lng": 77.59}}]})
        assert request.url.host == "discover.search.hereapi.com"
        assert request.url.params["at"] == "12.97,77.59"
        return httpx.Response(200, json={"items": [{"resultType": "place", "title": "Test Hospital",
            "address": {"label": "Test Street, Bengaluru"}, "position": {"lat": 12.98, "lng": 77.6}}]})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        pipeline = Pipeline(config(doctor_search_provider="here", here_api_key="private-here-test-key"), client)
        result = await pipeline.care_command("search", "Bengaluru", 0)
        assert result["care_state"]["source"] == "here"
        assert result["text"] == "I have listed the doctors on screen. Please tap the doctor you want to book."
        for action, value in [("select", "real-1"), ("yes", ""), ("set_date", "tomorrow"),
                              ("set_time", "10 am"), ("set_patient", "Test"), ("yes", ""), ("yes", "")]:
            result = await pipeline.care_command(action, value, pipeline.care_state["revision"])
        assert result["care_state"]["stage"] == "handoff"
        assert "Nothing has been sent or booked" in result["text"]
    assert len(calls) == 2
    assert "private-here-test-key" not in caplog.text


@pytest.mark.parametrize("payload,status", [({}, 401), ({}, 429), ({}, 500),
    ({"items": []}, 200), ({"items": [{"position": {"lat": 999, "lng": 0}}]}, 200)])
async def test_here_errors_fall_back_without_google(payload, status):
    def handler(request):
        assert request.url.host.endswith("hereapi.com")
        return httpx.Response(status, json=payload)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await search_doctors(config(doctor_search_provider="here", here_api_key="test"), client, "Delhi")
    assert result["source"] == "dummy"


async def test_here_missing_key_does_not_use_google():
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r: pytest.fail("No network expected"))) as client:
        result = await search_doctors(config(doctor_search_provider="here"), client, "Delhi")
    assert result["source"] == "dummy"


@pytest.mark.parametrize("failure", ["timeout", "empty", "malformed", "rate_limit"])
async def test_here_discover_failure_is_safe(failure):
    def handler(request):
        if request.url.host == "geocode.search.hereapi.com":
            return httpx.Response(200, json={"items": [{"position": {"lat": 12, "lng": 77}}]})
        if failure == "timeout":
            raise httpx.ReadTimeout("Timed out", request=request)
        if failure == "rate_limit":
            return httpx.Response(429)
        return httpx.Response(200, json={"items": [] if failure == "empty" else [None]})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await search_doctors(config(doctor_search_provider="here", here_api_key="test"), client, "Delhi")
    assert result["source"] == "dummy"


@pytest.mark.parametrize("status", [200, 403, 429, 500])
async def test_empty_or_failed_search_falls_back(status):
    async with httpx.AsyncClient(transport=httpx.MockTransport(
        lambda r: httpx.Response(status, json={"places": []})
    )) as client:
        result = await search_doctors(config(), client, "Bengaluru")
    assert result["source"] == "dummy"
    assert result["doctors"][0]["id"] == "demo-1"
    assert "fictional" in result["search_notice"]


async def test_missing_area_and_forced_dummy_make_no_requests():
    def handler(request):
        pytest.fail("Should not call Google")
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        assert (await search_doctors(config(), client))["source"] == "location"
        assert (await search_doctors(config(doctor_search_mode="dummy"), client, "Delhi"))["source"] == "dummy"


async def test_real_listing_booking_is_simulated_and_shared_with_voice_state():
    calls = []
    def handler(request):
        calls.append(request)
        assert request.url.host == "places.googleapis.com"
        assert json.loads(request.content)["textQuery"] == "doctors and hospitals in Bengaluru"
        assert "patient" not in request.content.decode()
        return httpx.Response(200, json={"places": [{
            "id": "place-id", "displayName": {"text": "Example Hospital"},
            "formattedAddress": "Example Road, Bengaluru",
        }]})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        pipeline = Pipeline(config(), client)
        result = await pipeline.care_command("search", "Bengaluru", 0)
        assert result["care_state"]["source"] == "google"
        assert result["text"] == "I have listed the doctors on screen. Please tap the doctor you want to book."
        for action, value in [("select", "real-1"), ("yes", ""), ("set_date", "tomorrow"),
                              ("set_time", "10 am"), ("set_patient", "Test"), ("yes", ""), ("yes", "")]:
            result = await pipeline.care_command(action, value, pipeline.care_state["revision"])
        assert result["care_state"]["stage"] == "handoff"
        assert "Nothing has been sent or booked" in result["text"]
        assert len(calls) == 1
