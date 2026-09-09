"""VESPER Weather Tool — Open-Meteo Integration.

Provides real-time weather data, multi-day forecasts, and imminent precipitation
detection using the free Open-Meteo API (no API key required).

Default city: Palghar, Maharashtra, India.
Fallback city: Mumbai, Maharashtra, India.

Geocoding is handled dynamically via Open-Meteo Geocoding API, allowing any
city to be resolved by name (e.g., "London", "Palghar", "Mumbai").
"""

from __future__ import annotations

import asyncio
import datetime
import logging
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger("vesper.agent.tools.weather")

# Default locations
DEFAULT_CITY = "Palghar"
FALLBACK_CITY = "Mumbai"

# WMO Weather Interpretation Code -> human-readable description
WMO_CODES: Dict[int, str] = {
    0: "Clear sky",
    1: "Mainly clear",
    2: "Partly cloudy",
    3: "Overcast",
    45: "Foggy",
    48: "Depositing rime fog",
    51: "Light drizzle",
    53: "Moderate drizzle",
    55: "Dense drizzle",
    61: "Slight rain",
    63: "Moderate rain",
    65: "Heavy rain",
    71: "Slight snowfall",
    73: "Moderate snowfall",
    75: "Heavy snowfall",
    77: "Snow grains",
    80: "Slight rain showers",
    81: "Moderate rain showers",
    82: "Violent rain showers",
    85: "Slight snow showers",
    86: "Heavy snow showers",
    95: "Thunderstorm",
    96: "Thunderstorm with slight hail",
    99: "Thunderstorm with heavy hail",
}

_TIMEOUT = httpx.Timeout(8.0)


async def _http_get(url: str, params: Dict[str, Any]) -> Dict[str, Any]:
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.get(url, params=params)
        resp.raise_for_status()
        return resp.json()


async def get_coordinates(location: str) -> Optional[Dict[str, Any]]:
    """Resolves a city name to geographic coordinates via Open-Meteo Geocoding API."""
    try:
        data = await _http_get(
            "https://geocoding-api.open-meteo.com/v1/search",
            {"name": location, "count": 1, "language": "en", "format": "json"},
        )
        results = data.get("results", [])
        if results:
            r = results[0]
            return {
                "name": r.get("name", location),
                "country": r.get("country", ""),
                "latitude": r.get("latitude"),
                "longitude": r.get("longitude"),
                "timezone": r.get("timezone", "auto"),
            }
        logger.warning(f"[WeatherTool] No geocoding results for '{location}'")
        return None
    except Exception as e:
        logger.warning(f"[WeatherTool] Geocoding failed for '{location}': {e}")
        return None


async def get_current_weather(location: Optional[str] = None) -> Dict[str, Any]:
    """Fetches real-time weather conditions for a given city (defaults to Palghar)."""
    city = location or DEFAULT_CITY
    coords = await get_coordinates(city)
    if not coords:
        if city != FALLBACK_CITY:
            coords = await get_coordinates(FALLBACK_CITY)
        if not coords:
            return {"error": f"Unable to geocode '{city}'."}

    lat, lon = coords["latitude"], coords["longitude"]
    tz = coords.get("timezone", "auto")

    params = {
        "latitude": lat,
        "longitude": lon,
        "timezone": tz,
        "current": [
            "temperature_2m",
            "apparent_temperature",
            "relative_humidity_2m",
            "weather_code",
            "wind_speed_10m",
            "uv_index",
            "precipitation_probability",
            "precipitation",
        ],
    }

    try:
        data = await _http_get("https://api.open-meteo.com/v1/forecast", params)
    except Exception as e:
        return {"error": f"Weather API request failed: {e}"}

    current = data.get("current", {})
    wmo = int(current.get("weather_code", 0))
    condition = WMO_CODES.get(wmo, "Unknown")

    return {
        "city": coords["name"],
        "country": coords["country"],
        "latitude": lat,
        "longitude": lon,
        "temperature_c": current.get("temperature_2m"),
        "feels_like_c": current.get("apparent_temperature"),
        "humidity_pct": current.get("relative_humidity_2m"),
        "condition": condition,
        "condition_code": wmo,
        "wind_speed_kmh": current.get("wind_speed_10m"),
        "uv_index": current.get("uv_index"),
        "precip_probability_pct": current.get("precipitation_probability"),
        "precipitation_mm": current.get("precipitation"),
        "observed_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
    }


async def get_forecast(location: Optional[str] = None, days: int = 3) -> Dict[str, Any]:
    """Returns daily max/min temperatures, precipitation probability, and condition for N days."""
    city = location or DEFAULT_CITY
    coords = await get_coordinates(city)
    if not coords:
        if city != FALLBACK_CITY:
            coords = await get_coordinates(FALLBACK_CITY)
        if not coords:
            return {"error": f"Unable to geocode '{city}'."}

    lat, lon = coords["latitude"], coords["longitude"]
    tz = coords.get("timezone", "auto")
    days = max(1, min(days, 7))

    params = {
        "latitude": lat,
        "longitude": lon,
        "timezone": tz,
        "forecast_days": days,
        "daily": [
            "temperature_2m_max",
            "temperature_2m_min",
            "weather_code",
            "precipitation_probability_max",
            "precipitation_sum",
            "uv_index_max",
            "wind_speed_10m_max",
        ],
        "hourly": [
            "temperature_2m",
            "weather_code",
            "precipitation_probability",
        ],
    }

    try:
        data = await _http_get("https://api.open-meteo.com/v1/forecast", params)
    except Exception as e:
        return {"error": f"Forecast API request failed: {e}"}

    daily = data.get("daily", {})
    dates = daily.get("time", [])
    forecast_days: List[Dict[str, Any]] = []

    for i, date in enumerate(dates[:days]):
        wmo = int(daily.get("weather_code", [0] * days)[i] if daily.get("weather_code") else 0)
        forecast_days.append({
            "date": date,
            "condition": WMO_CODES.get(wmo, "Unknown"),
            "condition_code": wmo,
            "temp_max_c": (daily.get("temperature_2m_max") or [None] * days)[i],
            "temp_min_c": (daily.get("temperature_2m_min") or [None] * days)[i],
            "precip_probability_pct": (daily.get("precipitation_probability_max") or [None] * days)[i],
            "precip_sum_mm": (daily.get("precipitation_sum") or [None] * days)[i],
            "uv_index_max": (daily.get("uv_index_max") or [None] * days)[i],
            "wind_speed_max_kmh": (daily.get("wind_speed_10m_max") or [None] * days)[i],
        })

    hourly = data.get("hourly", {})
    hourly_times = hourly.get("time", [])
    today = datetime.date.today().isoformat()
    hourly_today: List[Dict[str, Any]] = []
    for i, t in enumerate(hourly_times):
        if t.startswith(today):
            wmo_h = int((hourly.get("weather_code") or [0] * len(hourly_times))[i])
            hourly_today.append({
                "time": t,
                "temperature_c": (hourly.get("temperature_2m") or [None] * len(hourly_times))[i],
                "condition": WMO_CODES.get(wmo_h, "Unknown"),
                "precip_probability_pct": (hourly.get("precipitation_probability") or [None] * len(hourly_times))[i],
            })

    return {
        "city": coords["name"],
        "country": coords["country"],
        "days": forecast_days,
        "hourly_today": hourly_today[:12],
    }


async def check_imminent_precipitation(
    location: Optional[str] = None,
    hours_ahead: int = 2,
    threshold_pct: int = 50,
) -> Dict[str, Any]:
    """Checks whether rain or storms are expected within the next N hours.

    Returns probability, onset time, and intensity classification.
    """
    city = location or DEFAULT_CITY
    coords = await get_coordinates(city)
    if not coords:
        if city != FALLBACK_CITY:
            coords = await get_coordinates(FALLBACK_CITY)
        if not coords:
            return {"error": f"Unable to geocode '{city}'.", "rain_likely": False}

    lat, lon = coords["latitude"], coords["longitude"]
    tz = coords.get("timezone", "auto")

    params = {
        "latitude": lat,
        "longitude": lon,
        "timezone": tz,
        "forecast_days": 1,
        "hourly": [
            "precipitation_probability",
            "weather_code",
            "precipitation",
        ],
    }

    try:
        data = await _http_get("https://api.open-meteo.com/v1/forecast", params)
    except Exception as e:
        return {"error": f"Precipitation check failed: {e}", "rain_likely": False}

    hourly = data.get("hourly", {})
    times = hourly.get("time", [])
    probs = hourly.get("precipitation_probability") or []
    codes = hourly.get("weather_code") or []
    precips = hourly.get("precipitation") or []

    now = datetime.datetime.now()
    rain_likely = False
    max_prob = 0
    onset_time: Optional[str] = None
    max_intensity = 0.0

    for i, t in enumerate(times):
        try:
            slot_dt = datetime.datetime.fromisoformat(t)
        except ValueError:
            continue
        delta_hours = (slot_dt - now).total_seconds() / 3600
        if 0 <= delta_hours <= hours_ahead:
            prob = int(probs[i]) if i < len(probs) and probs[i] is not None else 0
            precip = float(precips[i]) if i < len(precips) and precips[i] is not None else 0.0
            if prob >= threshold_pct:
                rain_likely = True
                if prob > max_prob:
                    max_prob = prob
                    onset_time = t
                max_intensity = max(max_intensity, precip)

    wmo_at_onset = None
    if onset_time:
        idx = times.index(onset_time) if onset_time in times else -1
        if idx >= 0 and idx < len(codes):
            wmo_at_onset = int(codes[idx]) if codes[idx] is not None else None

    return {
        "city": coords["name"],
        "country": coords["country"],
        "rain_likely": rain_likely,
        "max_probability_pct": max_prob,
        "onset_time": onset_time,
        "max_precipitation_mm": max_intensity,
        "condition_at_onset": WMO_CODES.get(wmo_at_onset, "Unknown") if wmo_at_onset is not None else None,
        "hours_checked": hours_ahead,
        "threshold_pct": threshold_pct,
    }
