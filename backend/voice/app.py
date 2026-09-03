"""VESPER Voice Subsystem Microservice.

Runs as an isolated process on port 8002.
Exposes REST and WebSocket endpoints for low-latency audio processing:
  - POST /transcribe: One-shot STT (audio upload -> text)
  - POST /synthesize: One-shot TTS (text -> streaming MP3)
  - WebSocket /ws/voice: Bi-directional streaming audio pipeline
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import FastAPI, File, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from backend.voice.pipeline import VoicePipelineSession
from backend.voice.stt import GroqSpeechToText
from backend.voice.tts.manager import TTSManager

logger = logging.getLogger("vesper.voice")

app = FastAPI(
    title="VESPER Voice Subsystem",
    version="2.0.0",
    description="Real-time WebRTC VAD, Groq Whisper STT, and Google/Azure/Piper TTS.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

tts_manager = TTSManager()
stt_client = GroqSpeechToText()


class SynthesizeRequest(BaseModel):
    text: str
    preferred_provider: Optional[str] = None


@app.get("/health")
async def health_check():
    """Returns subsystem health and available TTS providers."""
    available_providers = [p.name for p in tts_manager.get_active_providers()]
    return {
        "status": "ok",
        "service": "vesper-voice",
        "stt_engine": "groq-whisper-large-v3-turbo",
        "available_tts_providers": available_providers,
        "default_voice": "en-GB-Neural2-B",
    }


@app.post("/transcribe")
async def transcribe_endpoint(file: UploadFile = File(...)):
    """Transcribes an uploaded audio file (WAV/MP3/M4A) via Groq Cloud Whisper."""
    try:
        audio_bytes = await file.read()
        text = await stt_client.transcribe_wav(audio_bytes)
        return {"text": text, "filename": file.filename}
    except Exception as e:
        logger.error(f"[VOICE.API] Transcribe failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/synthesize")
async def synthesize_endpoint(req: SynthesizeRequest):
    """Streams synthesized MP3 audio for the given text."""
    if not req.text.strip():
        raise HTTPException(status_code=400, detail="Text cannot be empty.")

    async def _audio_generator():
        async for chunk in tts_manager.stream_speech(req.text):
            yield chunk

    return StreamingResponse(
        _audio_generator(),
        media_type="audio/mpeg",
        headers={"Content-Disposition": "inline; filename=response.mp3"},
    )


@app.websocket("/ws/voice")
async def websocket_voice_endpoint(websocket: WebSocket):
    """Full-duplex WebSocket endpoint for continuous microphone audio streaming."""
    await websocket.accept()
    session = VoicePipelineSession(stt_client=stt_client, tts_manager=tts_manager)

    try:
        while True:
            # Receive raw binary PCM audio frame or JSON control packet
            message = await websocket.receive()

            if "bytes" in message and message["bytes"]:
                raw_pcm = message["bytes"]
                transcript = await session.ingest_audio_chunk(raw_pcm)

                if transcript:
                    # Completed utterance detected and transcribed
                    await websocket.send_json({
                        "type": "TRANSCRIPT",
                        "text": transcript,
                    })

            elif "text" in message and message["text"]:
                import json
                try:
                    data = json.loads(message["text"])
                    if data.get("type") == "INTERRUPT":
                        session.interrupt()
                        await websocket.send_json({"type": "INTERRUPT_ACK"})
                    elif data.get("type") == "SYNTHESIZE":
                        text_to_speak = data.get("text", "")
                        async for chunk in session.stream_response(text_to_speak):
                            await websocket.send_bytes(chunk)
                except Exception as parse_err:
                    logger.warning(f"[VOICE.WS] Invalid JSON frame: {parse_err}")

    except WebSocketDisconnect:
        logger.info("[VOICE.WS] Client disconnected.")
    except Exception as e:
        logger.error(f"[VOICE.WS] WebSocket error: {e}", exc_info=True)
