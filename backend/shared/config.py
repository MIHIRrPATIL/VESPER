"""VESPER Centralized Configuration Loader."""

from __future__ import annotations

import os
from pathlib import Path
from dotenv import load_dotenv

# Locate and load .env from backend root
BASE_DIR = Path(__file__).resolve().parent.parent
ENV_PATH = BASE_DIR / ".env"

if ENV_PATH.exists():
    load_dotenv(ENV_PATH)
else:
    # Also attempt loading from workspace root if running from top-level
    WORKSPACE_ENV = BASE_DIR.parent / ".env"
    if WORKSPACE_ENV.exists():
        load_dotenv(WORKSPACE_ENV)

# ── Gateway Settings ─────────────────────────────────────────────────────
GATEWAY_HOST: str = os.getenv("GATEWAY_HOST", "0.0.0.0")
GATEWAY_PORT: int = int(os.getenv("GATEWAY_PORT", "8000"))
ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "info")

# ── WebSocket & Heartbeat Timing ─────────────────────────────────────────
HANDSHAKE_TIMEOUT_SECONDS: float = float(os.getenv("HANDSHAKE_TIMEOUT_SECONDS", "5.0"))
HEARTBEAT_INTERVAL_SECONDS: float = float(os.getenv("HEARTBEAT_INTERVAL_SECONDS", "15.0"))
HEARTBEAT_TIMEOUT_SECONDS: float = float(os.getenv("HEARTBEAT_TIMEOUT_SECONDS", "5.0"))
MAX_PAYLOAD_SIZE_BYTES: int = int(os.getenv("MAX_PAYLOAD_SIZE_BYTES", str(10 * 1024 * 1024)))

# ── Service Discovery URLs ───────────────────────────────────────────────
AGENT_SERVICE_URL: str = os.getenv("AGENT_SERVICE_URL", "http://localhost:8001")
VOICE_SERVICE_URL: str = os.getenv("VOICE_SERVICE_URL", "http://localhost:8002")
VISION_SERVICE_URL: str = os.getenv("VISION_SERVICE_URL", "http://localhost:8003")
SYNC_SERVICE_URL: str = os.getenv("SYNC_SERVICE_URL", "http://localhost:8004")

# ── Supabase (Cloud PostgreSQL + pgvector) ──────────────────────────────
SUPABASE_URL: str = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY: str = os.getenv("SUPABASE_KEY", "")

# ── Cloud AI Providers ───────────────────────────────────────────────────
GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")
OPENROUTER_API_KEY: str = os.getenv("OPENROUTER_API_KEY", "")
ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")

# ── Speech & Audio Providers ─────────────────────────────────────────────
GOOGLE_APPLICATION_CREDENTIALS: str = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "")
GOOGLE_CLOUD_API_KEY: str = os.getenv("GOOGLE_CLOUD_API_KEY", "")
AZURE_SPEECH_KEY: str = os.getenv("AZURE_SPEECH_KEY", "")
AZURE_SPEECH_REGION: str = os.getenv("AZURE_SPEECH_REGION", "eastus")
ELEVENLABS_API_KEY: str = os.getenv("ELEVENLABS_API_KEY", "")

# Voice Subsystem Tuning
VOICE_TTS_PROVIDER: str = os.getenv("VOICE_TTS_PROVIDER", "auto")
VOICE_PRIMARY_VOICE: str = os.getenv("VOICE_PRIMARY_VOICE", "en-GB-Neural2-B")
VOICE_SAMPLE_RATE: int = int(os.getenv("VOICE_SAMPLE_RATE", "16000"))
VOICE_VAD_MODE: int = int(os.getenv("VOICE_VAD_MODE", "2"))
VOICE_SILENCE_THRESHOLD_MS: int = int(os.getenv("VOICE_SILENCE_THRESHOLD_MS", "400"))

# ── Agent Swarm Configuration ────────────────────────────────────────────
AGENT_HOST: str = os.getenv("AGENT_HOST", "0.0.0.0")
AGENT_PORT: int = int(os.getenv("AGENT_PORT", "8001"))
AGENT_FAST_MODEL: str = os.getenv("AGENT_FAST_MODEL", "qwen/qwen3.8-27b")
AGENT_PRIMARY_MODEL: str = os.getenv("AGENT_PRIMARY_MODEL", "openrouter/free")

# ── External Specialist Integrations ──────────────────────────────────────
TAVILY_API_KEY: str = os.getenv("TAVILY_API_KEY", "")
SERPAPI_API_KEY: str = os.getenv("SERPAPI_API_KEY", "")
SPOTIFY_CLIENT_ID: str = os.getenv("SPOTIFY_CLIENT_ID", "")
SPOTIFY_CLIENT_SECRET: str = os.getenv("SPOTIFY_CLIENT_SECRET", "")
SPOTIFY_REDIRECT_URI: str = os.getenv("SPOTIFY_REDIRECT_URI", "http://localhost:8888/callback")

# Google Calendar OAuth Settings
GOOGLE_CALENDAR_CLIENT_ID: str = os.getenv("GOOGLE_CALENDAR_CLIENT_ID", "")
GOOGLE_CALENDAR_CLIENT_SECRET: str = os.getenv("GOOGLE_CALENDAR_CLIENT_SECRET", "")
GOOGLE_CALENDAR_PROJECT_ID: str = os.getenv("GOOGLE_CALENDAR_PROJECT_ID", "vesper-507516")

