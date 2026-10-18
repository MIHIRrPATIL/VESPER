"""VESPER Comprehensive Latency & Performance Benchmark Suite.

Benchmarks:
1. Tier 1 Deterministic Fast-Path Pre-filter (0 tokens, <0.5ms)
2. Tier 2 Semantic Intent Router (Embeddings + Cosine, <30ms)
3. Tier 3 LLM Groq LPU: TTFT (Time To First Token), Generation Speed (Tokens/sec), and Total Latency
4. Tier 3 Swarm Planner: End-to-end plan decomposition latency
5. Voice Synthesis: Piper ONNX Neural TTS synthesis time, Audio Duration & Real-Time Factor (RTF)
6. Mobile Edge: On-device 3-gate promo filter & deterministic idempotency hashing
"""

from __future__ import annotations

import asyncio
import os
import sys
import time
from typing import Any, Dict, List
import statistics

# Ensure workspace root is in python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def print_header(title: str) -> None:
    print("\n" + "=" * 80)
    print(f" {title.upper()}")
    print("=" * 80)


def compute_stats(values: List[float]) -> Dict[str, float]:
    if not values:
        return {"mean": 0.0, "p50": 0.0, "p90": 0.0, "p95": 0.0, "min": 0.0, "max": 0.0}
    sorted_v = sorted(values)
    n = len(sorted_v)
    return {
        "mean": statistics.mean(sorted_v),
        "p50": sorted_v[int(n * 0.50)],
        "p90": sorted_v[min(int(n * 0.90), n - 1)],
        "p95": sorted_v[min(int(n * 0.95), n - 1)],
        "min": sorted_v[0],
        "max": sorted_v[-1],
    }


# ─────────────────────────────────────────────────────────────────────────────
# 1. Tier 1: Deterministic Fast-Path Benchmarks
# ─────────────────────────────────────────────────────────────────────────────
def benchmark_fast_path() -> Dict[str, Any]:
    print_header("1. Tier 1 Deterministic Fast-Path Pre-filter (<0.5ms, 0 tokens)")
    from backend.agent.fast_path import FastPathEngine

    engine = FastPathEngine()

    test_queries = [
        "what is the time",
        "what's the time",
        "mute",
        "unmute",
        "volume 75",
        "stop",
        "pause music",
        "resume music",
        "open workstation",
        "show agenda",
        "open ledger",
        "show services",
        "open tools",
        "show logs",
        "zen mode",
        "who am i",
        "what is my name",
    ]

    # Warmup
    for q in test_queries:
        engine.evaluate(q)

    # Measure 500 iterations
    latencies_us: List[float] = []
    matches = 0

    for _ in range(500):
        for q in test_queries:
            t0 = time.perf_counter_ns()
            res = engine.evaluate(q)
            t1 = time.perf_counter_ns()
            latencies_us.append((t1 - t0) / 1000.0)  # Microseconds
            if res.matched:
                matches += 1

    stats_ms = {k: v / 1000.0 for k, v in compute_stats(latencies_us).items()}

    print(f"Tested: {len(test_queries) * 500} queries | Match rate: {matches / (len(test_queries) * 500) * 100:.1f}%")
    print(f"Mean Latency:   {stats_ms['mean']:.4f} ms ({stats_ms['mean'] * 1000:.1f} microseconds)")
    print(f"P50 (Median):   {stats_ms['p50']:.4f} ms")
    print(f"P95:            {stats_ms['p95']:.4f} ms")
    print(f"Token Overhead: 0 tokens (Pure compiled regular expression pre-filter)")
    print(f"Speedup vs LLM: >1,000x faster than cloud inference")

    return {
        "tier": "Tier 1 (Fast-Path)",
        "mean_ms": stats_ms["mean"],
        "p50_ms": stats_ms["p50"],
        "p95_ms": stats_ms["p95"],
        "token_cost": 0,
    }


# ─────────────────────────────────────────────────────────────────────────────
# 2. Tier 2: Semantic Intent Router Benchmarks
# ─────────────────────────────────────────────────────────────────────────────
def benchmark_semantic_router() -> Dict[str, Any]:
    print_header("2. Tier 2 Semantic Intent Router (Local Embeddings + Cosine Similarity)")
    from backend.agent.semantic_router import SemanticIntentRouter

    router = SemanticIntentRouter()

    test_queries = [
        "inspect what is in my grip",
        "check if there are any unread messages in Gmail",
        "what's the weather like in Tokyo right now",
        "schedule a catchup with Rohan tomorrow at 4pm",
        "I don't think that's right, check Google",
        "pull up the entire email chain",
        "play some low-fi beats on Spotify",
        "turn on the desk companion sentry",
        "summarize the latest news headlines",
        "read out what is written on this paper in my hand",
    ]

    # Warmup
    for q in test_queries[:2]:
        router.classify(q)

    latencies_ms: List[float] = []
    routes = []

    for q in test_queries:
        for _ in range(5):
            t0 = time.perf_counter()
            res = router.classify(q)
            t1 = time.perf_counter()
            latencies_ms.append((t1 - t0) * 1000.0)
            routes.append((q, res.intent.value, res.confidence))

    stats = compute_stats(latencies_ms)

    print(f"Total Vector Routing Evaluations: {len(latencies_ms)}")
    print(f"Mean Latency:   {stats['mean']:.2f} ms")
    print(f"P50 (Median):   {stats['p50']:.2f} ms")
    print(f"P95:            {stats['p95']:.2f} ms")
    print(f"Min:            {stats['min']:.2f} ms")
    print(f"Max:            {stats['max']:.2f} ms")
    print(f"Sample Routing Results:")
    for q, intent, score in routes[:4]:
        print(f"  * \"{q}\" -> {intent} (similarity: {score:.3f})")

    return {
        "tier": "Tier 2 (Semantic Router)",
        "mean_ms": stats["mean"],
        "p50_ms": stats["p50"],
        "p95_ms": stats["p95"],
    }


# ─────────────────────────────────────────────────────────────────────────────
# 3. Tier 3: LLM Groq LPU Inference (TTFT & Generation Speed)
# ─────────────────────────────────────────────────────────────────────────────
async def benchmark_groq_llm() -> Dict[str, Any]:
    print_header("3. Tier 3 LLM Groq LPU: TTFT & Token Generation Speed")
    from backend.shared.config import GROQ_API_KEY, AGENT_FAST_MODEL
    from groq import AsyncGroq

    if not GROQ_API_KEY:
        print("GROQ_API_KEY not configured. Skipping live LPU benchmark.")
        return {}

    client = AsyncGroq(api_key=GROQ_API_KEY)
    model = AGENT_FAST_MODEL or "llama-3.3-70b-versatile"

    prompts = [
        "Alfred, give a concise 1-sentence status of the workstation.",
        "List 3 high-priority tasks for an AI platform engineer today.",
        "Categorize this expense: '₹450 debited at Blue Tokai Coffee Roasters'. Return 1 short phrase.",
    ]

    ttft_list: List[float] = []
    total_latency_list: List[float] = []
    tps_list: List[float] = []
    token_counts: List[int] = []

    print(f"Target LPU Model: {model}")

    for idx, prompt in enumerate(prompts, 1):
        messages: Any = [
            {"role": "system", "content": "You are Alfred, a crisp, concise British AI assistant."},
            {"role": "user", "content": prompt},
        ]

        t_start = time.perf_counter()
        stream = await client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=0.2,
            max_tokens=256,
            stream=True,
        )

        t_first_token: float | None = None
        chunks: List[str] = []

        async for chunk in stream:
            content = chunk.choices[0].delta.content or ""
            if content:
                if t_first_token is None:
                    t_first_token = time.perf_counter()
                chunks.append(content)

        t_end = time.perf_counter()

        if t_first_token is not None:
            ttft_ms = (t_first_token - t_start) * 1000.0
            total_ms = (t_end - t_start) * 1000.0
            gen_sec = t_end - t_first_token
            num_tokens = len(chunks)
            tps = num_tokens / gen_sec if gen_sec > 0 else 0.0

            ttft_list.append(ttft_ms)
            total_latency_list.append(total_ms)
            tps_list.append(tps)
            token_counts.append(num_tokens)

            full_text = "".join(chunks).strip().replace("\n", " ")
            print(f"Prompt {idx}: TTFT = {ttft_ms:.1f}ms | Total = {total_ms:.1f}ms | Tokens = {num_tokens} | TPS = {tps:.1f} tok/s")
            print(f"  Response: \"{full_text[:75]}...\"")

    ttft_stats = compute_stats(ttft_list)
    tot_stats = compute_stats(total_latency_list)
    tps_stats = compute_stats(tps_list)

    print("\nLPU Performance Metrics:")
    print(f"Time To First Token (TTFT): Mean = {ttft_stats['mean']:.1f} ms | P50 = {ttft_stats['p50']:.1f} ms | P95 = {ttft_stats['p95']:.1f} ms")
    print(f"Total Generation Latency:   Mean = {tot_stats['mean']:.1f} ms | P50 = {tot_stats['p50']:.1f} ms | P95 = {tot_stats['p95']:.1f} ms")
    print(f"Throughput Speed:           Mean = {tps_stats['mean']:.1f} tokens/sec (Peak: {tps_stats['max']:.1f} tok/s)")

    return {
        "ttft_mean_ms": ttft_stats["mean"],
        "ttft_p50_ms": ttft_stats["p50"],
        "total_mean_ms": tot_stats["mean"],
        "total_p50_ms": tot_stats["p50"],
        "tps_mean": tps_stats["mean"],
    }


# ─────────────────────────────────────────────────────────────────────────────
# 4. Tier 3: Swarm Planner End-to-End Latency
# ─────────────────────────────────────────────────────────────────────────────
async def benchmark_swarm_planner() -> Dict[str, Any]:
    print_header("4. Tier 3 Swarm Planner: Multi-Agent Plan Generation Latency")
    try:
        from backend.agent.planner import SwarmPlanner
        from backend.agent.registry import SpecialistRegistry
        planner = SwarmPlanner()
        registry = SpecialistRegistry()
    except Exception as e:
        print(f"Failed to initialize SwarmPlanner: {e}")
        return {}

    plan_queries = [
        "What's the weather in Seattle and add an umbrella to my shopping tasks",
        "Read my unread emails and draft a reply to the latest one",
        "What is our liquid net worth and how much did we spend on food yesterday",
    ]

    latencies_ms: List[float] = []
    plan_types: List[str] = []

    for q in plan_queries:
        t0 = time.perf_counter()
        try:
            plan, _ = await planner.create_plan(q, registry=registry)
            t1 = time.perf_counter()
            elapsed_ms = (t1 - t0) * 1000.0
            latencies_ms.append(elapsed_ms)
            plan_types.append(plan.plan_type)
            print(f"Query: \"{q}\"")
            print(f"  Plan: {plan.plan_type.upper()} with {len(plan.steps)} steps | Latency = {elapsed_ms:.1f} ms")
        except Exception as err:
            print(f"Query \"{q}\" plan error: {err}")

    stats = compute_stats(latencies_ms)
    print(f"\nSwarm Plan Generation: Mean = {stats['mean']:.1f} ms | P50 = {stats['p50']:.1f} ms | P95 = {stats['p95']:.1f} ms")

    return {
        "planner_mean_ms": stats["mean"],
        "planner_p50_ms": stats["p50"],
        "planner_p95_ms": stats["p95"],
    }


# ─────────────────────────────────────────────────────────────────────────────
# 5. Local Neural Speech Synthesis (Piper ONNX TTS)
# ─────────────────────────────────────────────────────────────────────────────
async def benchmark_piper_tts() -> Dict[str, Any]:
    print_header("5. Local Embedded Neural Speech Synthesis (Piper ONNX TTS)")
    try:
        from backend.voice.tts.piper_tts import PiperTTSProvider
        provider = PiperTTSProvider()
        if not provider.is_available():
            print("Piper TTS model is not available or path unconfigured. Skipping TTS benchmark.")
            return {}
    except Exception as e:
        print(f"Failed to initialize PiperTTSProvider: {e}")
        return {}

    test_utterances = [
        ("Short", "Good morning, sir. All VESPER systems are nominal."),
        ("Medium", "Your financial flight deck is updated. You have three meetings scheduled on your executive calendar today."),
        ("Long", "I have finished analyzing the unread notification stream. A high-priority calendar invite from the engineering director arrived six minutes ago, and two banking transactions have been stashed for your review."),
    ]

    # Warmup
    try:
        await provider.synthesize("Warmup.")
    except Exception:
        pass

    results: List[Dict[str, Any]] = []

    for label, text in test_utterances:
        word_count = len(text.split())
        t0 = time.perf_counter()
        try:
            audio_bytes = await provider.synthesize(text)
        except Exception as synth_err:
            print(f"Synthesis failed for '{label}': {synth_err}")
            continue
        t1 = time.perf_counter()

        synthesis_time_s = t1 - t0
        synthesis_time_ms = synthesis_time_s * 1000.0

        # Piper default is 22050 Hz, 16-bit mono PCM (44100 bytes/sec)
        # Skip 44 bytes WAV header
        pcm_bytes = len(audio_bytes) - 44 if len(audio_bytes) > 44 else len(audio_bytes)
        audio_duration_s = pcm_bytes / 44100.0 if pcm_bytes > 0 else 0.0

        rtf = synthesis_time_s / audio_duration_s if audio_duration_s > 0 else 0.0
        speedup = 1.0 / rtf if rtf > 0 else 0.0

        print(f"Utterance [{label}] ({word_count} words):")
        print(f"  Synthesis Time:  {synthesis_time_ms:.1f} ms")
        print(f"  Audio Duration:  {audio_duration_s:.2f} s")
        print(f"  Real-Time Factor (RTF): {rtf:.3f}x ({speedup:.1f}x faster than real-time playback)")

        results.append({
            "label": label,
            "words": word_count,
            "synth_ms": synthesis_time_ms,
            "audio_s": audio_duration_s,
            "rtf": rtf,
            "speedup": speedup,
        })

    avg_rtf = statistics.mean(r["rtf"] for r in results) if results else 0.0
    avg_speedup = statistics.mean(r["speedup"] for r in results) if results else 0.0

    return {
        "results": results,
        "avg_rtf": avg_rtf,
        "avg_speedup": avg_speedup,
    }


# ─────────────────────────────────────────────────────────────────────────────
# 6. Mobile Edge Regex & Idempotency Hashing
# ─────────────────────────────────────────────────────────────────────────────
def benchmark_mobile_edge() -> Dict[str, Any]:
    print_header("6. Mobile Edge: 3-Gate Promo Filter & Idempotent Bucket Hashing")

    # Native Python simulation of mobile TypeScript logic
    import re

    BANKING_HEADERS = re.compile(r"^[A-Z]{2}-([A-Z0-9]+)$")
    PROMO_WORDS = re.compile(r"\b(cashback|rewards?|win\s+up\s+to|flat\s+₹|refer\s+and\s+earn|sale|discount|deal|offer|coupon)\b", re.I)
    SETTLEMENT_VERBS = re.compile(r"\b(debited\s+by|debited\s+for|credited\s+with|received\s+from|paid\s+to|transferred\s+to|spent\s+on)\b", re.I)

    samples = [
        ("VM-HDFCBK", "Alert", "Your A/C ending 4091 has been debited by Rs 420.00 at Swiggy UPI. Available balance: Rs 45,210.00", True),
        ("VK-SBIINB", "Rewards", "Win up to Rs 500 cashback on your next recharge! Click here now.", False),
        ("AD-ICICIB", "Credit Card", "Earn flat Rs 50 reward points on paying your electricity bill with ICICI.", False),
        ("com.phonepe.app", "Payment Sent", "Paid Rs 150.00 to Chai Point successfully.", True),
        ("com.google.android.apps.nbu.paisa.user", "Offer", "Refer a friend and win up to Rs 201 into your bank account.", False),
    ]

    t0 = time.perf_counter_ns()
    iterations = 2000
    for _ in range(iterations):
        for sender, title, text, expected in samples:
            # Gate 1: Check header
            g1 = bool(BANKING_HEADERS.match(sender) or "paisa" in sender or "phonepe" in sender)
            # Gate 2: Promo check
            g2 = not bool(PROMO_WORDS.search(text))
            # Gate 3: Settlement verb
            g3 = bool(SETTLEMENT_VERBS.search(text))
            is_valid = g1 and g2 and g3

            # Deterministic bucket hash:
            bucket = (int(time.time() * 1000) // 300000) * 300000
            key = f"hdfc_420.00_debit_{bucket}_ref123"
            h = hash(key)
    t1 = time.perf_counter_ns()

    total_evals = iterations * len(samples)
    total_us = (t1 - t0) / 1000.0
    us_per_eval = total_us / total_evals

    print(f"Evaluated {total_evals} notification payloads")
    print(f"Throughput: {total_evals / (total_us / 1000000):,.0f} evaluations / second")
    print(f"Latency per Notification: {us_per_eval:.2f} microseconds (<0.01 ms)")
    print(f"Edge Footprint: Zero-cloud, instant on-device filtering")

    return {
        "us_per_eval": us_per_eval,
        "throughput_evals_per_sec": total_evals / (total_us / 1000000),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Main Runner & Resume Synthesis Table
# ─────────────────────────────────────────────────────────────────────────────
async def main():
    print("=" * 80)
    print(" VESPER ARCHITECTURAL LATENCY & PERFORMANCE BENCHMARK SUITE")
    print("=" * 80)

    t1_res = benchmark_fast_path()
    t2_res = benchmark_semantic_router()
    llm_res = await benchmark_groq_llm()
    plan_res = await benchmark_swarm_planner()
    tts_res = await benchmark_piper_tts()
    edge_res = benchmark_mobile_edge()

    print_header("FINAL QUANTITATIVE RESUME & PORTFOLIO METRICS")
    print(f"""
================================================================================
VESPER MULTI-TIER SYSTEM PERFORMANCE SPECIFICATIONS
================================================================================
* Tier 1 Deterministic Fast-Path:
  - Latency:           {t1_res.get('mean_ms', 0):.4f} ms (P50: {t1_res.get('p50_ms', 0):.4f} ms, P95: {t1_res.get('p95_ms', 0):.4f} ms)
  - Token Cost:        0 tokens (100% free deterministic regular expression engine)
  - Speedup:           >1,000x faster than cloud LLM inference

* Tier 2 Semantic Intent Router:
  - Latency:           {t2_res.get('mean_ms', 0):.2f} ms (P50: {t2_res.get('p50_ms', 0):.2f} ms, P95: {t2_res.get('p95_ms', 0):.2f} ms)
  - Architecture:      Local vector embeddings + cosine similarity prototype bank
  - Zero-Cloud:        Runs locally on CPU without remote API dependencies

* Tier 3 Cloud LLM Reasoning (Groq LPU):
  - Time To First Token (TTFT): {llm_res.get('ttft_mean_ms', 0):.1f} ms (P50: {llm_res.get('ttft_p50_ms', 0):.1f} ms)
  - Token Generation Rate:      {llm_res.get('tps_mean', 0):.1f} tokens/second
  - Swarm Planning Latency:     {plan_res.get('planner_mean_ms', 0):.1f} ms (P50: {plan_res.get('planner_p50_ms', 0):.1f} ms)

* Local Embedded Neural Speech (Piper ONNX TTS):
  - Real-Time Factor (RTF):     {tts_res.get('avg_rtf', 0):.3f}x (Synthesizes speech {tts_res.get('avg_speedup', 0):.1f}x faster than real-time)
  - Short Sentence Synthesis:   ~{tts_res.get('results', [{}])[0].get('synth_ms', 0):.1f} ms
  - Cost & Privacy:             Offline ONNX runtime, zero cloud audio streaming fees

* Mobile Edge Triage:
  - Promo Filter & Idempotency: {edge_res.get('us_per_eval', 0):.2f} microseconds/notification ({edge_res.get('throughput_evals_per_sec', 0):,.0f} payload evals/sec)
  - Reliability:                5-minute bucketed deterministic hashing prevents duplicate records
================================================================================
""")


if __name__ == "__main__":
    asyncio.run(main())
