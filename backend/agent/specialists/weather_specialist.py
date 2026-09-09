"""VESPER Weather Specialist Agent.

Routes weather-related queries through the Open-Meteo weather tool and returns
structured weather cards for the HUD alongside natural Alfred butler speech.

Handles:
  - Current real-time weather conditions
  - Multi-day weather forecasts
  - Imminent precipitation checks ("will it rain today?", "do I need an umbrella?")

Default location: Palghar, Maharashtra. Falls back to Mumbai.
Users can override by specifying any city name in their query.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from backend.agent.specialists.base import BaseSpecialist, SpecialistResult

logger = logging.getLogger("vesper.agent.specialists.weather")


class WeatherSpecialist(BaseSpecialist):
    """Specialist for meteorological intelligence and weather-related queries."""

    @property
    def name(self) -> str:
        return "weather"

    @property
    def description(self) -> str:
        return "Fetches real-time weather, multi-day forecasts, and precipitation alerts using Open-Meteo."

    def get_capabilities(self) -> str:
        return (
            "Handles weather queries: current conditions, temperature, humidity, wind, UV index, "
            "multi-day forecasts, and imminent rain/storm precipitation checks for any city. "
            "Defaults to Palghar/Mumbai when no location is specified."
        )

    def get_tool_schemas(self) -> List[Dict[str, Any]]:
        return [
            {
                "name": "get_current_weather",
                "description": "Fetches real-time weather conditions for a city (temperature, humidity, condition, UV index, wind speed, precipitation probability).",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "location": {
                            "type": "string",
                            "description": "City name (e.g. 'Palghar', 'Mumbai', 'London'). Omit to use the default city.",
                        }
                    },
                    "required": [],
                },
            },
            {
                "name": "get_weather_forecast",
                "description": "Returns a daily weather forecast for 1-7 days (max/min temperature, condition, rain probability).",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "location": {
                            "type": "string",
                            "description": "City name. Omit to use the default city.",
                        },
                        "days": {
                            "type": "integer",
                            "description": "Number of forecast days (1-7). Defaults to 3.",
                        },
                    },
                    "required": [],
                },
            },
            {
                "name": "check_rain",
                "description": "Checks if rain or storms are expected in the next 1-6 hours. Use for 'will it rain', 'do I need an umbrella', 'is it going to storm'.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "location": {
                            "type": "string",
                            "description": "City name. Omit to use the default city.",
                        },
                        "hours_ahead": {
                            "type": "integer",
                            "description": "How many hours ahead to check (default 3, max 6).",
                        },
                    },
                    "required": [],
                },
            },
        ]

    async def execute(
        self, action: str, params: Dict[str, Any], context: Optional[Dict[str, Any]] = None
    ) -> SpecialistResult:
        if action == "get_current_weather":
            return await self._get_current_weather(params)
        elif action == "get_weather_forecast":
            return await self._get_weather_forecast(params)
        elif action == "check_rain":
            return await self._check_rain(params)
        return SpecialistResult(
            success=False,
            action=action,
            error=f"Unknown weather action: '{action}'.",
        )

    async def _get_current_weather(self, params: Dict[str, Any]) -> SpecialistResult:
        from backend.agent.tools.weather_tool import get_current_weather
        location = params.get("location") or None
        data = await get_current_weather(location)

        if "error" in data:
            return SpecialistResult(
                success=False,
                action="get_current_weather",
                error=data["error"],
                speech_summary=f"I was unable to retrieve weather data, sir. {data['error']}",
            )

        city = data.get("city", "your location")
        temp = data.get("temperature_c")
        feels = data.get("feels_like_c")
        condition = data.get("condition", "Unknown")
        humidity = data.get("humidity_pct")
        wind = data.get("wind_speed_kmh")
        uv = data.get("uv_index")
        precip_prob = data.get("precip_probability_pct", 0)

        speech_parts = [
            f"Currently in {city}: {condition}, {temp}\u00b0C (feels like {feels}\u00b0C)."
        ]
        if humidity is not None:
            speech_parts.append(f"Humidity is at {humidity}%")
        if wind is not None:
            speech_parts.append(f"wind speed {wind:.0f} km/h")
        if uv is not None and uv > 6:
            speech_parts.append(f"UV index is elevated at {uv:.0f} - sun protection is advisable, sir")
        if precip_prob and precip_prob > 40:
            speech_parts.append(f"There is a {precip_prob}% chance of precipitation at present")

        speech = ". ".join(speech_parts) + "."

        card = {
            "type": "weather_card",
            "city": city,
            "country": data.get("country", ""),
            "condition": condition,
            "condition_code": data.get("condition_code"),
            "temperature_c": temp,
            "feels_like_c": feels,
            "humidity_pct": humidity,
            "wind_speed_kmh": wind,
            "uv_index": uv,
            "precip_probability_pct": precip_prob,
            "observed_at": data.get("observed_at"),
        }

        return SpecialistResult(
            success=True,
            action="get_current_weather",
            speech_summary=speech,
            data=data,
            card_payload=card,
        )

    async def _get_weather_forecast(self, params: Dict[str, Any]) -> SpecialistResult:
        from backend.agent.tools.weather_tool import get_forecast
        location = params.get("location") or None
        days = int(params.get("days", 3))
        data = await get_forecast(location, days)

        if "error" in data:
            return SpecialistResult(
                success=False,
                action="get_weather_forecast",
                error=data["error"],
                speech_summary=f"I was unable to retrieve the forecast, sir. {data['error']}",
            )

        city = data.get("city", "your location")
        forecast_days = data.get("days", [])

        if not forecast_days:
            return SpecialistResult(
                success=False,
                action="get_weather_forecast",
                error="No forecast data returned.",
                speech_summary="No forecast data was available, sir.",
            )

        lines = []
        for d in forecast_days[:days]:
            date_str = d.get("date", "")
            cond = d.get("condition", "Unknown")
            high = d.get("temp_max_c")
            low = d.get("temp_min_c")
            rain = d.get("precip_probability_pct", 0)
            lines.append(f"{date_str}: {cond}, {high}\u00b0C/{low}\u00b0C, rain {rain}%")

        speech = f"Here is the {days}-day forecast for {city}: " + "; ".join(lines) + "."

        card = {
            "type": "weather_forecast_card",
            "city": city,
            "country": data.get("country", ""),
            "days": forecast_days,
            "hourly_today": data.get("hourly_today", [])[:5],
        }

        return SpecialistResult(
            success=True,
            action="get_weather_forecast",
            speech_summary=speech,
            data=data,
            card_payload=card,
        )

    async def _check_rain(self, params: Dict[str, Any]) -> SpecialistResult:
        from backend.agent.tools.weather_tool import check_imminent_precipitation
        location = params.get("location") or None
        hours_ahead = int(params.get("hours_ahead", 3))
        hours_ahead = max(1, min(hours_ahead, 6))
        data = await check_imminent_precipitation(location, hours_ahead=hours_ahead, threshold_pct=50)

        if "error" in data:
            return SpecialistResult(
                success=False,
                action="check_rain",
                error=data["error"],
                speech_summary=f"I was unable to check precipitation conditions, sir. {data['error']}",
            )

        city = data.get("city", "your location")
        rain_likely = data.get("rain_likely", False)
        prob = data.get("max_probability_pct", 0)
        onset = data.get("onset_time")
        cond_at_onset = data.get("condition_at_onset")

        if rain_likely:
            onset_str = f" starting around {onset}" if onset else ""
            speech = (
                f"Yes, sir. Rain is likely in {city}{onset_str} "
                f"with a {prob}% probability. "
                f"{'Condition: ' + cond_at_onset + '.' if cond_at_onset else ''} "
                "I would recommend carrying an umbrella."
            ).strip()
        else:
            speech = (
                f"No significant precipitation is expected in {city} within the next {hours_ahead} hours, sir. "
                "The skies look clear for now."
            )

        card = {
            "type": "weather_rain_card",
            "city": city,
            "country": data.get("country", ""),
            "rain_likely": rain_likely,
            "max_probability_pct": prob,
            "onset_time": onset,
            "condition_at_onset": cond_at_onset,
            "hours_checked": hours_ahead,
        }

        return SpecialistResult(
            success=True,
            action="check_rain",
            speech_summary=speech,
            data=data,
            card_payload=card,
        )
