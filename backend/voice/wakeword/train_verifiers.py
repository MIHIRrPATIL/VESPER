"""VESPER Wake Word Verifier Model Generator.

Trains and exports lightweight, zero-dependency scikit-learn models
(StandardScaler + LogisticRegression) on 16-frame 96-dimensional acoustic
embeddings extracted by openWakeWord's embedding_model.onnx.
"""

import asyncio
import os
import pickle
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[3]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import numpy as np
import openwakeword
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from backend.voice.tts.piper_tts import PiperTTSProvider

MODELS_DIR = Path(__file__).resolve().parent / "models"
MODELS_DIR.mkdir(parents=True, exist_ok=True)


async def generate_dataset_for_target(target_name: str, positive_phrases: list[str], negative_phrases: list[str]):
    print(f"[VerifierTrainer] Generating dataset for '{target_name}'...")
    tts = PiperTTSProvider()
    oww = openwakeword.Model()

    voices = ["alan_medium", "cori_high", "ryan_high", "semaine"]
    speeds = [0.75, 0.85, 1.0, 1.15, 1.25]

    X = []
    y = []

    # 1. Synthesize positive samples
    for v in voices:
        try:
            tts.voice_name = v
        except Exception:
            continue
        for phrase in positive_phrases:
            for ls in speeds:
                tts.length_scale = ls
                try:
                    chunks = [c async for c in tts.synthesize_stream(phrase)]
                    pcm = b"".join(chunks)
                    if not pcm:
                        continue
                    arr = np.frombuffer(pcm, dtype=np.int16).astype(np.float32)
                    new_len = int(len(arr) * 16000 / 22050)
                    resampled = np.interp(
                        np.linspace(0, len(arr), new_len, endpoint=False),
                        np.arange(len(arr)),
                        arr,
                    ).astype(np.int16)

                    # Augment with temporal offsets, volume gain, and background noise
                    for offset in [0, 480, 960]:
                        for gain in [0.7, 1.0, 1.3]:
                            sub = (resampled[offset:] * gain).clip(-32768, 32767).astype(np.int16)
                            if np.random.rand() > 0.5:
                                noise = np.random.normal(0, 120, len(sub)).astype(np.int16)
                                sub = (sub.astype(np.int32) + noise).clip(-32768, 32767).astype(np.int16)

                            oww.reset()
                            total_chunks = len(sub) // 1280
                            for idx, i in enumerate(range(0, len(sub), 1280)):
                                chunk = sub[i : i + 1280]
                                if len(chunk) < 1280:
                                    chunk = np.pad(chunk, (0, 1280 - len(chunk)))
                                oww.predict(chunk)
                                if idx >= max(0, total_chunks - 3):
                                    feats = oww.preprocessor.get_features(16)
                                    if feats is not None and feats.size >= 1536:
                                        X.append(feats.flatten()[-1536:])
                                        y.append(1)
                except Exception as e:
                    print(f"Warning generating {phrase} ({v}): {e}")

    # 2. Synthesize negative samples
    for v in ["alan_medium", "cori_high", "ryan_high"]:
        try:
            tts.voice_name = v
        except Exception:
            continue
        for phrase in negative_phrases:
            for ls in [0.85, 1.0, 1.15]:
                tts.length_scale = ls
                try:
                    chunks = [c async for c in tts.synthesize_stream(phrase)]
                    pcm = b"".join(chunks)
                    if not pcm:
                        continue
                    arr = np.frombuffer(pcm, dtype=np.int16).astype(np.float32)
                    new_len = int(len(arr) * 16000 / 22050)
                    resampled = np.interp(
                        np.linspace(0, len(arr), new_len, endpoint=False),
                        np.arange(len(arr)),
                        arr,
                    ).astype(np.int16)

                    oww.reset()
                    total_neg = len(resampled) // 1280
                    for idx, i in enumerate(range(0, len(resampled), 1280)):
                        chunk = resampled[i : i + 1280]
                        if len(chunk) < 1280:
                            chunk = np.pad(chunk, (0, 1280 - len(chunk)))
                        oww.predict(chunk)
                        if idx >= max(0, total_neg - 2):
                            feats = oww.preprocessor.get_features(16)
                            if feats is not None and feats.size >= 1536:
                                X.append(feats.flatten()[-1536:])
                                y.append(0)
                except Exception as e:
                    pass

    # 3. Add silence, low-frequency rumble, and ambient white noise
    for _ in range(50):
        noise = np.random.randint(-250, 250, 1280 * 8, dtype=np.int16)
        oww.reset()
        for i in range(0, len(noise), 1280):
            oww.predict(noise[i : i + 1280])
        feats = oww.preprocessor.get_features(16)
        X.append(feats.flatten()[-1536:])
        y.append(0)

    # Pure silence
    for _ in range(20):
        silence = np.zeros(1280 * 8, dtype=np.int16)
        oww.reset()
        for i in range(0, len(silence), 1280):
            oww.predict(silence[i : i + 1280])
        feats = oww.preprocessor.get_features(16)
        X.append(feats.flatten()[-1536:])
        y.append(0)

    X_np = np.array(X)
    y_np = np.array(y)
    print(f"[{target_name}] Dataset size: {len(X_np)} (Pos: {np.sum(y_np == 1)}, Neg: {np.sum(y_np == 0)})")

    # Train regularized logistic regression model with balanced class weights
    model = make_pipeline(
        StandardScaler(),
        LogisticRegression(max_iter=1000, C=0.2, class_weight="balanced", random_state=42),
    )
    model.fit(X_np, y_np)

    train_acc = np.mean(model.predict(X_np) == y_np)
    print(f"[{target_name}] Model training accuracy: {train_acc * 100:.2f}%")

    out_path = MODELS_DIR / f"{target_name}_verifier.joblib"
    with open(out_path, "wb") as f:
        pickle.dump(model, f)
    print(f"[{target_name}] Model saved successfully to {out_path}")
    return model


async def main():
    common_negatives = [
        "alexa", "hey alexa", "siri", "hey siri", "google", "ok google",
        "hello", "hi there", "computer", "weather", "play music", "stop",
        "volume up", "volume down", "next track", "previous track",
        "what time is it", "good morning", "good evening", "thank you",
        "open terminal", "close window", "send email", "check calendar",
        "turn on lights", "how are you", "tell me a joke", "system status",
        "vesper", "hey vesper", "dashboard", "coffee", "meeting", "python",
    ]

    # 1. Alfred verifier (positive: alfred, hey alfred)
    alfred_positives = [
        "alfred", "Alfred", "hey alfred", "Hey Alfred", "Alfred please",
        "yes alfred", "wake up alfred", "Alfred listen", "Alfred butler",
    ]
    alfred_negatives = common_negatives + ["jarvis", "hey jarvis"]
    await generate_dataset_for_target("alfred", alfred_positives, alfred_negatives)

    # 2. Jarvis verifier (positive: jarvis, hey jarvis)
    jarvis_positives = [
        "jarvis", "Jarvis", "hey jarvis", "Hey Jarvis", "Jarvis please",
        "yes jarvis", "wake up jarvis", "Jarvis listen",
    ]
    jarvis_negatives = common_negatives + ["alfred", "hey alfred"]
    await generate_dataset_for_target("jarvis", jarvis_positives, jarvis_negatives)


if __name__ == "__main__":
    asyncio.run(main())
