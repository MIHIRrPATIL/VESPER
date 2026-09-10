"""VESPER Proactive Weather Sentinel.

Background sentinel that monitors weather intelligence and proactively alerts
Alfred when:
  - Imminent rain is detected (>= 60% probability within 2 hours)
  - Morning commute briefing window (7:30 - 10:30 AM)
  - Extreme UV or temperature advisory is warranted
  - Calendar departure event has weather implications

All proactive alerts route through the Gateway broadcast mechanism via the
callback provided on initialization.
"""

from __future__ import annotations

import asyncio
import datetime
import json
import logging
from pathlib import Path
from typing import Any, Callable, Coroutine, Dict, Optional

logger = logging.getLogger("vesper.agent.proactive.weather_sentry")

RAIN_PROBABILITY_THRESHOLD = 60       # % - triggers imminent rain alert
CHECK_INTERVAL_SEC = 1800             # 30 minutes between standard checks
RAIN_ALERT_COOLDOWN_SEC = 10800      # 3-hour cooldown between rain alerts
MORNING_BRIEFING_START_HOUR = 7
MORNING_BRIEFING_END_HOUR = 10
UV_ALERT_THRESHOLD = 8               # UV index threshold for advisory
EXTREME_HEAT_C = 40.0                 # Celsius threshold for extreme heat advisory
EXTREME_COLD_C = 5.0                  # Celsius threshold for cold advisory


AlertCallback = Callable[[str, Dict[str, Any]], Coroutine[Any, Any, None]]


class WeatherSentry:
    """Asynchronous background sentinel for proactive weather intelligence."""

    def __init__(
        self,
        broadcast_callback: AlertCallback,
        default_location: Optional[str] = None,
    ) -> None:
        self.broadcast_callback = broadcast_callback
        self.default_location = default_location or "Palghar"
        self._task: Optional[asyncio.Task] = None
        self._morning_briefed_today: bool = False
        self._last_morning_briefing_date: Optional[datetime.date] = None
        self._last_rain_alert_time: Optional[datetime.datetime] = None
        self._running: bool = False
        self.state_file = Path(__file__).resolve().parent.parent.parent.parent / "output" / "last_weather_alert.json"
        self._load_state()

    def _load_state(self) -> None:
        """Loads previous alert timestamps from persistent storage."""
        if self.state_file.exists():
            try:
                data = json.loads(self.state_file.read_text())
                if data.get("last_rain_alert_time"):
                    self._last_rain_alert_time = datetime.datetime.fromisoformat(data["last_rain_alert_time"])
                if data.get("last_morning_briefing_date"):
                    self._last_morning_briefing_date = datetime.date.fromisoformat(data["last_morning_briefing_date"])
            except Exception as e:
                logger.debug(f"[WeatherSentry] Failed loading state: {e}")

    def _save_state(self) -> None:
        """Persists alert timestamps to survive microservice restarts."""
        try:
            self.state_file.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "last_rain_alert_time": self._last_rain_alert_time.isoformat() if self._last_rain_alert_time else None,
                "last_morning_briefing_date": self._last_morning_briefing_date.isoformat() if self._last_morning_briefing_date else None,
            }
            self.state_file.write_text(json.dumps(payload))
        except Exception as e:
            logger.warning(f"[WeatherSentry] Failed saving state: {e}")

    def start(self) -> None:
        """Starts the weather sentinel background loop."""
        if self._task and not self._task.done():
            return
        self._running = True
        self._task = asyncio.create_task(self._monitor_loop())
        logger.info("[WeatherSentry] Weather intelligence sentinel armed.")

    def stop(self) -> None:
        """Stops the weather sentinel loop."""
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
        logger.info("[WeatherSentry] Weather intelligence sentinel disarmed.")

    async def check_and_alert_departure(self, location: Optional[str] = None) -> Optional[str]:
        """Called by CalendarSentry when a physical departure event is detected.

        Returns the weather advisory string if rain is expected, else None.
        """
        from backend.agent.tools.weather_tool import check_imminent_precipitation
        loc = location or self.default_location
        try:
            result = await check_imminent_precipitation(loc, hours_ahead=3, threshold_pct=50)
            if result.get("rain_likely"):
                prob = result.get("max_probability_pct", 0)
                onset = result.get("onset_time", "")
                cond = result.get("condition_at_onset", "Rain")
                advisory = (
                    f"Meteorological advisory for your departure, sir: "
                    f"{cond} is expected with {prob}% probability in {loc}. "
                    "I would strongly recommend an umbrella."
                )
                return advisory
        except Exception as e:
            logger.warning(f"[WeatherSentry] Departure weather check failed: {e}")
        return None

    async def _monitor_loop(self) -> None:
        """Main monitoring loop, runs every 30 minutes."""
        # Initial grace period on boot to allow network & clients to settle
        await asyncio.sleep(20.0)
        while self._running:
            try:
                await self._run_checks()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning(f"[WeatherSentry] Monitor loop error: {e}")
            try:
                await asyncio.sleep(CHECK_INTERVAL_SEC)
            except asyncio.CancelledError:
                break

    async def _run_checks(self) -> None:
        from backend.agent.tools.weather_tool import (
            check_imminent_precipitation,
            get_current_weather,
        )

        now = datetime.datetime.now()
        today = now.date()

        # Morning Commute Briefing (once per day, 7:30-10:30 AM)
        if (
            MORNING_BRIEFING_START_HOUR <= now.hour < MORNING_BRIEFING_END_HOUR
            and self._last_morning_briefing_date != today
        ):
            try:
                weather = await get_current_weather(self.default_location)
                if "error" not in weather:
                    await self._broadcast_morning_briefing(weather)
                    self._last_morning_briefing_date = today
                    self._save_state()
            except Exception as e:
                logger.warning(f"[WeatherSentry] Morning briefing failed: {e}")

        # Imminent Precipitation Alert
        rain_cooldown_expired = (
            self._last_rain_alert_time is None
            or (now - self._last_rain_alert_time).total_seconds() > RAIN_ALERT_COOLDOWN_SEC
        )
        if rain_cooldown_expired:
            try:
                result = await check_imminent_precipitation(
                    self.default_location,
                    hours_ahead=2,
                    threshold_pct=RAIN_PROBABILITY_THRESHOLD,
                )
                if result.get("rain_likely"):
                    await self._broadcast_rain_alert(result)
                    self._last_rain_alert_time = now
                    self._save_state()
            except Exception as e:
                logger.warning(f"[WeatherSentry] Rain check failed: {e}")

        # Extreme Heat / UV Advisory
        try:
            weather = await get_current_weather(self.default_location)
            if "error" not in weather:
                await self._check_extreme_conditions(weather)
        except Exception as e:
            logger.warning(f"[WeatherSentry] Extreme conditions check failed: {e}")

    async def _broadcast_morning_briefing(self, weather: Dict[str, Any]) -> None:
        city = weather.get("city", self.default_location)
        temp = weather.get("temperature_c")
        condition = weather.get("condition", "Clear")
        uv = weather.get("uv_index")
        precip = weather.get("precip_probability_pct", 0)
        humidity = weather.get("humidity_pct")

        parts = [f"Good morning, sir. Your meteorological briefing for {city}:"]
        parts.append(f"{condition}, {temp}\u00b0C.")
        if humidity:
            parts.append(f"Humidity at {humidity}%.")
        if precip and precip > 30:
            parts.append(f"There is a {precip}% chance of precipitation today.")
        if uv and uv >= UV_ALERT_THRESHOLD:
            parts.append(f"UV index is {uv:.0f} - please apply sunscreen before heading out, sir.")

        speech = " ".join(parts)
        await self.broadcast_callback("weather_morning_briefing", {
            "speech": speech,
            "weather": weather,
            "type": "morning_briefing",
        })
        logger.info("[WeatherSentry] Morning briefing dispatched.")

    async def _broadcast_rain_alert(self, result: Dict[str, Any]) -> None:
        city = result.get("city", self.default_location)
        prob = result.get("max_probability_pct", 0)
        onset = result.get("onset_time", "")
        cond = result.get("condition_at_onset", "Rain")

        onset_str = f" beginning around {onset}" if onset else ""
        speech = (
            f"Sir, I should alert you: {cond} is imminent in {city}{onset_str} "
            f"with {prob}% probability. If you plan to venture outside, an umbrella is advised."
        )

        await self.broadcast_callback("weather_rain_alert", {
            "speech": speech,
            "result": result,
            "type": "rain_alert",
        })
        logger.info(f"[WeatherSentry] Rain alert dispatched. Probability={prob}%")

    async def _check_extreme_conditions(self, weather: Dict[str, Any]) -> None:
        temp = weather.get("temperature_c")
        uv = weather.get("uv_index")
        city = weather.get("city", self.default_location)

        if temp is not None and temp >= EXTREME_HEAT_C:
            speech = (
                f"Extreme heat advisory for {city}, sir: current temperature is {temp}\u00b0C. "
                "Please ensure adequate hydration and limit outdoor exposure."
            )
            await self.broadcast_callback("weather_extreme_heat", {
                "speech": speech,
                "temperature_c": temp,
                "city": city,
                "type": "extreme_heat",
            })

        elif temp is not None and temp <= EXTREME_COLD_C:
            speech = (
                f"Cold weather advisory for {city}, sir: current temperature is {temp}\u00b0C. "
                "Please dress warmly before heading out."
            )
            await self.broadcast_callback("weather_extreme_cold", {
                "speech": speech,
                "temperature_c": temp,
                "city": city,
                "type": "extreme_cold",
            })


# Module-level singleton (broadcast_callback must be injected at startup)
_weather_sentry: Optional[WeatherSentry] = None


def get_weather_sentry() -> Optional[WeatherSentry]:
    return _weather_sentry


def init_weather_sentry(callback: AlertCallback, location: Optional[str] = None) -> WeatherSentry:
    global _weather_sentry
    _weather_sentry = WeatherSentry(broadcast_callback=callback, default_location=location)
    return _weather_sentry
