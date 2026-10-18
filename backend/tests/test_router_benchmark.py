"""Held-out evaluation benchmark for VESPER Tier 2 Semantic Router.

Evaluates generalization across unseen paraphrases (not in prototype bank)
and adversarial near-misses (holding meetings, screen time, horoscopes,
multi-intent queries, negations, and entity-parameterized requests).

Computes Precision, Recall, and F1 score per intent, plus latency percentiles.
"""

import time
from typing import Any, Dict, List, Tuple
import pytest
from backend.agent.semantic_router import SemanticIntent, SemanticIntentRouter


# Held-out evaluation dataset: 260 distinct examples NOT in INTENT_PROTOTYPES or CONTRAST_PROTOTYPES
HELD_OUT_DATASET: List[Tuple[str, SemanticIntent]] = [
    # ── 1. HANDHELD_OBJECT_RESEARCH (25 unseen paraphrases) ──────────────────
    ("inspect what is in my grip", SemanticIntent.HANDHELD_OBJECT_RESEARCH),
    ("look at what I'm showing the lens", SemanticIntent.HANDHELD_OBJECT_RESEARCH),
    ("can you read this snippet of text from the paper I'm holding", SemanticIntent.HANDHELD_OBJECT_RESEARCH),
    ("what does this document in front of me say", SemanticIntent.HANDHELD_OBJECT_RESEARCH),
    ("take a look at the bottle in my hand", SemanticIntent.HANDHELD_OBJECT_RESEARCH),
    ("read the nutritional facts on this can I am holding", SemanticIntent.HANDHELD_OBJECT_RESEARCH),
    ("tell me the price on this grocery receipt I am holding", SemanticIntent.HANDHELD_OBJECT_RESEARCH),
    ("can you scan this card in my hand", SemanticIntent.HANDHELD_OBJECT_RESEARCH),
    ("what is written on this invoice in my palm", SemanticIntent.HANDHELD_OBJECT_RESEARCH),
    ("inspect this book cover in my hand", SemanticIntent.HANDHELD_OBJECT_RESEARCH),
    ("what product am I holding up right now", SemanticIntent.HANDHELD_OBJECT_RESEARCH),
    ("check the label on this package in my hand", SemanticIntent.HANDHELD_OBJECT_RESEARCH),
    ("read the instructions on this box I am holding", SemanticIntent.HANDHELD_OBJECT_RESEARCH),
    ("can you see the serial number on this device in my hand", SemanticIntent.HANDHELD_OBJECT_RESEARCH),
    ("describe the item I am presenting to the camera", SemanticIntent.HANDHELD_OBJECT_RESEARCH),
    ("what is this object I'm holding up to you", SemanticIntent.HANDHELD_OBJECT_RESEARCH),
    ("read out the medicine prescription in my hand", SemanticIntent.HANDHELD_OBJECT_RESEARCH),
    ("check this business card I'm holding", SemanticIntent.HANDHELD_OBJECT_RESEARCH),
    ("tell me what is printed on this flyer I'm holding", SemanticIntent.HANDHELD_OBJECT_RESEARCH),
    ("look at this handwritten note in my hand", SemanticIntent.HANDHELD_OBJECT_RESEARCH),
    ("what are the line items on this restaurant slip I am holding", SemanticIntent.HANDHELD_OBJECT_RESEARCH),
    ("analyze the document I'm holding up", SemanticIntent.HANDHELD_OBJECT_RESEARCH),
    ("can you inspect this warranty card in my hands", SemanticIntent.HANDHELD_OBJECT_RESEARCH),
    ("read the total amount on this store slip in my hand", SemanticIntent.HANDHELD_OBJECT_RESEARCH),
    ("what book am I holding in front of the lens", SemanticIntent.HANDHELD_OBJECT_RESEARCH),

    # ── 2. VERIFY_RESEARCH (25 unseen paraphrases) ───────────────────────────
    ("I don't think that's right, check Google", SemanticIntent.VERIFY_RESEARCH),
    ("are you certain about that? please verify", SemanticIntent.VERIFY_RESEARCH),
    ("that sounds completely made up, search online", SemanticIntent.VERIFY_RESEARCH),
    ("wrong answer, look it up properly", SemanticIntent.VERIFY_RESEARCH),
    ("nope that is incorrect, do a web search", SemanticIntent.VERIFY_RESEARCH),
    ("double-check that fact on the web", SemanticIntent.VERIFY_RESEARCH),
    ("that doesn't sound correct, please research", SemanticIntent.VERIFY_RESEARCH),
    ("can you look that up to be sure", SemanticIntent.VERIFY_RESEARCH),
    ("are you sure? do some research on this", SemanticIntent.VERIFY_RESEARCH),
    ("that's false, look up the actual numbers", SemanticIntent.VERIFY_RESEARCH),
    ("search again, you got it wrong", SemanticIntent.VERIFY_RESEARCH),
    ("please verify that information on the internet", SemanticIntent.VERIFY_RESEARCH),
    ("I doubt that, go search for it", SemanticIntent.VERIFY_RESEARCH),
    ("that's inaccurate, please search again", SemanticIntent.VERIFY_RESEARCH),
    ("look it up online to confirm", SemanticIntent.VERIFY_RESEARCH),
    ("nope, try searching again", SemanticIntent.VERIFY_RESEARCH),
    ("you're mistaken, check the web", SemanticIntent.VERIFY_RESEARCH),
    ("are you sure? please double check", SemanticIntent.VERIFY_RESEARCH),
    ("check your facts with a search engine", SemanticIntent.VERIFY_RESEARCH),
    ("that's not true, search the internet", SemanticIntent.VERIFY_RESEARCH),
    ("wrong data, please look it up", SemanticIntent.VERIFY_RESEARCH),
    ("are you certain? search for the source", SemanticIntent.VERIFY_RESEARCH),
    ("re-check that online right now", SemanticIntent.VERIFY_RESEARCH),
    ("that can't be right, look it up", SemanticIntent.VERIFY_RESEARCH),
    ("try searching again to verify", SemanticIntent.VERIFY_RESEARCH),

    # ── 3. EMAIL_THREAD (20 unseen paraphrases) ──────────────────────────────
    ("pull up the entire email chain", SemanticIntent.EMAIL_THREAD),
    ("show me all messages in this email thread", SemanticIntent.EMAIL_THREAD),
    ("display the full thread history", SemanticIntent.EMAIL_THREAD),
    ("can I see the complete email conversation", SemanticIntent.EMAIL_THREAD),
    ("read back the earlier replies in this thread", SemanticIntent.EMAIL_THREAD),
    ("open the full email correspondence", SemanticIntent.EMAIL_THREAD),
    ("show the back-and-forth email chain", SemanticIntent.EMAIL_THREAD),
    ("bring up the complete conversation for this thread", SemanticIntent.EMAIL_THREAD),
    ("retrieve the full message thread", SemanticIntent.EMAIL_THREAD),
    ("let me see the previous emails in this chain", SemanticIntent.EMAIL_THREAD),
    ("show me the ongoing thread", SemanticIntent.EMAIL_THREAD),
    ("read the whole email discussion", SemanticIntent.EMAIL_THREAD),
    ("pull the entire email history for this topic", SemanticIntent.EMAIL_THREAD),
    ("what did everyone say in this email chain", SemanticIntent.EMAIL_THREAD),
    ("show the full email exchange", SemanticIntent.EMAIL_THREAD),
    ("fetch the complete thread history", SemanticIntent.EMAIL_THREAD),
    ("expand the whole email chain", SemanticIntent.EMAIL_THREAD),
    ("give me the complete thread from that email", SemanticIntent.EMAIL_THREAD),
    ("show me what was said earlier in this email thread", SemanticIntent.EMAIL_THREAD),
    ("load the entire email conversation", SemanticIntent.EMAIL_THREAD),

    # ── 4. UNREAD_EMAILS (25 unseen paraphrases) ─────────────────────────────
    ("any unread mail in my inbox", SemanticIntent.UNREAD_EMAILS),
    ("have I received any new emails today", SemanticIntent.UNREAD_EMAILS),
    ("show me what emails haven't been opened yet", SemanticIntent.UNREAD_EMAILS),
    ("check if there are any unread messages in Gmail", SemanticIntent.UNREAD_EMAILS),
    ("do I have unopened emails", SemanticIntent.UNREAD_EMAILS),
    ("fetch my unread mail", SemanticIntent.UNREAD_EMAILS),
    ("give me a rundown of unread emails", SemanticIntent.UNREAD_EMAILS),
    ("see if any new mail came in", SemanticIntent.UNREAD_EMAILS),
    ("are there any unread emails waiting", SemanticIntent.UNREAD_EMAILS),
    ("check my inbox for new items", SemanticIntent.UNREAD_EMAILS),
    ("how many unread emails do I have", SemanticIntent.UNREAD_EMAILS),
    ("tell me about my unopened mail", SemanticIntent.UNREAD_EMAILS),
    ("list all unread messages in my inbox", SemanticIntent.UNREAD_EMAILS),
    ("any recent unread emails", SemanticIntent.UNREAD_EMAILS),
    ("show unread emails from today", SemanticIntent.UNREAD_EMAILS),
    ("check for any fresh emails", SemanticIntent.UNREAD_EMAILS),
    ("what new messages came into my inbox", SemanticIntent.UNREAD_EMAILS),
    ("pull up unread emails", SemanticIntent.UNREAD_EMAILS),
    ("summarize unread mail in my inbox", SemanticIntent.UNREAD_EMAILS),
    ("did any emails arrive recently", SemanticIntent.UNREAD_EMAILS),
    ("check my inbox right now", SemanticIntent.UNREAD_EMAILS),
    ("look for new messages in my email", SemanticIntent.UNREAD_EMAILS),
    ("any unread messages in my inbox", SemanticIntent.UNREAD_EMAILS),
    ("see what emails I missed", SemanticIntent.UNREAD_EMAILS),
    ("check incoming mail", SemanticIntent.UNREAD_EMAILS),

    # ── 5. SONG_ORIGIN (20 unseen paraphrases) ───────────────────────────────
    ("which movie does this tune belong to", SemanticIntent.SONG_ORIGIN),
    ("what picture features this soundtrack", SemanticIntent.SONG_ORIGIN),
    ("who is the singer of this track", SemanticIntent.SONG_ORIGIN),
    ("what movie has this song in it", SemanticIntent.SONG_ORIGIN),
    ("name the artist singing this track right now", SemanticIntent.SONG_ORIGIN),
    ("which film's soundtrack is this track on", SemanticIntent.SONG_ORIGIN),
    ("who sang this song", SemanticIntent.SONG_ORIGIN),
    ("what cinema release used this song", SemanticIntent.SONG_ORIGIN),
    ("who performed the song that is currently playing", SemanticIntent.SONG_ORIGIN),
    ("which movie is playing this background music", SemanticIntent.SONG_ORIGIN),
    ("what album or film does this song come from", SemanticIntent.SONG_ORIGIN),
    ("who is the vocalist on this track", SemanticIntent.SONG_ORIGIN),
    ("which movie soundtrack contains this tune", SemanticIntent.SONG_ORIGIN),
    ("who composed this song that is playing", SemanticIntent.SONG_ORIGIN),
    ("what film featured this theme music", SemanticIntent.SONG_ORIGIN),
    ("who is singing this song right now", SemanticIntent.SONG_ORIGIN),
    ("which Bollywood movie is this song from", SemanticIntent.SONG_ORIGIN),
    ("what movie is this music from", SemanticIntent.SONG_ORIGIN),
    ("identify the movie for this song", SemanticIntent.SONG_ORIGIN),
    ("who originally sang this track", SemanticIntent.SONG_ORIGIN),

    # ── 6. DAILY_AGENDA (25 unseen paraphrases) ──────────────────────────────
    ("what does my day look like", SemanticIntent.DAILY_AGENDA),
    ("what do I have on my plate today", SemanticIntent.DAILY_AGENDA),
    ("run down my schedule for today", SemanticIntent.DAILY_AGENDA),
    ("what are my commitments today", SemanticIntent.DAILY_AGENDA),
    ("give me an overview of today's schedule", SemanticIntent.DAILY_AGENDA),
    ("what events are lined up for me today", SemanticIntent.DAILY_AGENDA),
    ("what should I be working on today", SemanticIntent.DAILY_AGENDA),
    ("check my schedule for today", SemanticIntent.DAILY_AGENDA),
    ("any appointments on my calendar today", SemanticIntent.DAILY_AGENDA),
    ("walk me through my agenda for today", SemanticIntent.DAILY_AGENDA),
    ("what are my to-dos today", SemanticIntent.DAILY_AGENDA),
    ("show me what I need to accomplish today", SemanticIntent.DAILY_AGENDA),
    ("tell me my schedule today", SemanticIntent.DAILY_AGENDA),
    ("brief me on my day today", SemanticIntent.DAILY_AGENDA),
    ("what is scheduled for today", SemanticIntent.DAILY_AGENDA),
    ("review my daily agenda", SemanticIntent.DAILY_AGENDA),
    ("give me my morning rundown", SemanticIntent.DAILY_AGENDA),
    ("do I have any calendar events today", SemanticIntent.DAILY_AGENDA),
    ("what are my main tasks for today", SemanticIntent.DAILY_AGENDA),
    ("what is on my calendar today", SemanticIntent.DAILY_AGENDA),
    ("list my daily tasks and appointments", SemanticIntent.DAILY_AGENDA),
    ("what does my agenda hold for today", SemanticIntent.DAILY_AGENDA),
    ("tell me my itinerary for today", SemanticIntent.DAILY_AGENDA),
    ("check my daily schedule", SemanticIntent.DAILY_AGENDA),
    ("what's on tap for today", SemanticIntent.DAILY_AGENDA),

    # ── 7. FINANCE_BALANCE (20 unseen paraphrases) ───────────────────────────
    ("how much is in my checking account", SemanticIntent.FINANCE_BALANCE),
    ("what's my current financial standing", SemanticIntent.FINANCE_BALANCE),
    ("check my total funds", SemanticIntent.FINANCE_BALANCE),
    ("how much money is left in my bank", SemanticIntent.FINANCE_BALANCE),
    ("show my total account balances", SemanticIntent.FINANCE_BALANCE),
    ("what is my available cash balance", SemanticIntent.FINANCE_BALANCE),
    ("how much liquid cash do I possess", SemanticIntent.FINANCE_BALANCE),
    ("check my current net worth and balances", SemanticIntent.FINANCE_BALANCE),
    ("tell me my bank balance", SemanticIntent.FINANCE_BALANCE),
    ("how much money do I have across all accounts", SemanticIntent.FINANCE_BALANCE),
    ("what is my overall bank balance", SemanticIntent.FINANCE_BALANCE),
    ("view my financial balance", SemanticIntent.FINANCE_BALANCE),
    ("how many rupees do I have left", SemanticIntent.FINANCE_BALANCE),
    ("check how much funds are in my account", SemanticIntent.FINANCE_BALANCE),
    ("give me my account balance total", SemanticIntent.FINANCE_BALANCE),
    ("what's my wallet balance", SemanticIntent.FINANCE_BALANCE),
    ("how much total money is in my accounts", SemanticIntent.FINANCE_BALANCE),
    ("show me my savings balance", SemanticIntent.FINANCE_BALANCE),
    ("what is my remaining bank balance", SemanticIntent.FINANCE_BALANCE),
    ("check my current cash reserves", SemanticIntent.FINANCE_BALANCE),

    # ── 8. SYSTEM_STATUS (20 unseen paraphrases) ─────────────────────────────
    ("how are my workstation resources looking", SemanticIntent.SYSTEM_STATUS),
    ("give me CPU and memory telemetry", SemanticIntent.SYSTEM_STATUS),
    ("is the workstation running hot", SemanticIntent.SYSTEM_STATUS),
    ("check RAM and processor usage", SemanticIntent.SYSTEM_STATUS),
    ("how is system load right now", SemanticIntent.SYSTEM_STATUS),
    ("show processor and memory metrics", SemanticIntent.SYSTEM_STATUS),
    ("what is the current CPU utilization", SemanticIntent.SYSTEM_STATUS),
    ("how much free RAM is available", SemanticIntent.SYSTEM_STATUS),
    ("give me machine health stats", SemanticIntent.SYSTEM_STATUS),
    ("is the server under heavy load", SemanticIntent.SYSTEM_STATUS),
    ("check workstation health", SemanticIntent.SYSTEM_STATUS),
    ("show hardware vital signs", SemanticIntent.SYSTEM_STATUS),
    ("what is the system resource consumption", SemanticIntent.SYSTEM_STATUS),
    ("how are the CPU cores performing", SemanticIntent.SYSTEM_STATUS),
    ("check memory and CPU levels", SemanticIntent.SYSTEM_STATUS),
    ("inspect machine diagnostics", SemanticIntent.SYSTEM_STATUS),
    ("give me a status update on the computer", SemanticIntent.SYSTEM_STATUS),
    ("show system performance metrics", SemanticIntent.SYSTEM_STATUS),
    ("how heavily loaded is my computer", SemanticIntent.SYSTEM_STATUS),
    ("report on current workstation resources", SemanticIntent.SYSTEM_STATUS),

    # ── 9. MOBILE_NOTIFICATIONS (20 unseen paraphrases) ──────────────────────
    ("what pings came to my phone", SemanticIntent.MOBILE_NOTIFICATIONS),
    ("read out recent notifications from my phone", SemanticIntent.MOBILE_NOTIFICATIONS),
    ("any missed alerts on my mobile device", SemanticIntent.MOBILE_NOTIFICATIONS),
    ("did anyone ping me on my smartphone", SemanticIntent.MOBILE_NOTIFICATIONS),
    ("show unread phone notifications", SemanticIntent.MOBILE_NOTIFICATIONS),
    ("check my phone for any push notifications", SemanticIntent.MOBILE_NOTIFICATIONS),
    ("what notifications are waiting on my phone", SemanticIntent.MOBILE_NOTIFICATIONS),
    ("any Slack or WhatsApp pings on my phone", SemanticIntent.MOBILE_NOTIFICATIONS),
    ("list my recent mobile notifications", SemanticIntent.MOBILE_NOTIFICATIONS),
    ("did my phone get any new alerts", SemanticIntent.MOBILE_NOTIFICATIONS),
    ("check what popped up on my phone screen", SemanticIntent.MOBILE_NOTIFICATIONS),
    ("give me the notifications from my phone", SemanticIntent.MOBILE_NOTIFICATIONS),
    ("any new push alerts on my phone", SemanticIntent.MOBILE_NOTIFICATIONS),
    ("what alerts are on my mobile", SemanticIntent.MOBILE_NOTIFICATIONS),
    ("check incoming notifications on my phone", SemanticIntent.MOBILE_NOTIFICATIONS),
    ("have there been any notifications on my phone", SemanticIntent.MOBILE_NOTIFICATIONS),
    ("show alerts received on my phone", SemanticIntent.MOBILE_NOTIFICATIONS),
    ("summarize incoming phone alerts", SemanticIntent.MOBILE_NOTIFICATIONS),
    ("did I miss any phone pings", SemanticIntent.MOBILE_NOTIFICATIONS),
    ("check my smartphone alerts", SemanticIntent.MOBILE_NOTIFICATIONS),

    # ── 10. BATTERY_STATUS (20 unseen paraphrases) ───────────────────────────
    ("how much juice is left in my phone", SemanticIntent.BATTERY_STATUS),
    ("what is the charge level on my mobile", SemanticIntent.BATTERY_STATUS),
    ("check battery percentage of my phone", SemanticIntent.BATTERY_STATUS),
    ("is my laptop battery dying", SemanticIntent.BATTERY_STATUS),
    ("how much battery life remains", SemanticIntent.BATTERY_STATUS),
    ("what percentage is my phone battery at", SemanticIntent.BATTERY_STATUS),
    ("check power level of my phone", SemanticIntent.BATTERY_STATUS),
    ("is my phone battery low", SemanticIntent.BATTERY_STATUS),
    ("how full is my phone battery", SemanticIntent.BATTERY_STATUS),
    ("check device battery percentages", SemanticIntent.BATTERY_STATUS),
    ("is my smartphone currently charging", SemanticIntent.BATTERY_STATUS),
    ("what is my laptop's battery status", SemanticIntent.BATTERY_STATUS),
    ("how many percent battery do I have", SemanticIntent.BATTERY_STATUS),
    ("battery check on all my devices", SemanticIntent.BATTERY_STATUS),
    ("tell me my phone battery percentage", SemanticIntent.BATTERY_STATUS),
    ("do I need to plug in my phone", SemanticIntent.BATTERY_STATUS),
    ("what is my battery level", SemanticIntent.BATTERY_STATUS),
    ("check how much battery is remaining", SemanticIntent.BATTERY_STATUS),
    ("is my laptop plugged into power", SemanticIntent.BATTERY_STATUS),
    ("what's the charge on my phone", SemanticIntent.BATTERY_STATUS),

    # ── 11. NONE (40 Adversarials, Multi-Intent, Negations, Slots) ───────────
    ("who is holding the record for the highest mountain climb", SemanticIntent.NONE),
    ("we are holding a team sync at 3pm", SemanticIntent.NONE),
    ("holding an emergency board meeting", SemanticIntent.NONE),
    ("holding a press briefing tomorrow", SemanticIntent.NONE),
    ("the company is holding its annual shareholder gala", SemanticIntent.NONE),
    ("holding down the shift key", SemanticIntent.NONE),
    ("what is holding back the release", SemanticIntent.NONE),
    ("check my daily screen time stats", SemanticIntent.NONE),
    ("how many hours of screen time did I log", SemanticIntent.NONE),
    ("screen time usage report for iOS", SemanticIntent.NONE),
    ("read my daily horoscope for Virgo", SemanticIntent.NONE),
    ("what does my horoscope say for this week", SemanticIntent.NONE),
    ("daily astrological prediction", SemanticIntent.NONE),
    ("don't check my email", SemanticIntent.NONE),
    ("do not read my inbox", SemanticIntent.NONE),
    ("never check my bank balance", SemanticIntent.NONE),
    ("stop checking my notifications", SemanticIntent.NONE),
    ("cancel reading my schedule", SemanticIntent.NONE),
    ("what's my balance and read my unread emails", SemanticIntent.NONE),
    ("check my unread emails and show my agenda", SemanticIntent.NONE),
    ("what is my bank balance and check the weather in Tokyo", SemanticIntent.NONE),
    ("check system vitals and also look up who won the game", SemanticIntent.NONE),
    ("email thread with Sarah Jenkins about the merger", SemanticIntent.NONE),
    ("show the email chain from Dr. Rao", SemanticIntent.NONE),
    ("check the thread with Alex regarding the contract", SemanticIntent.NONE),
    ("who sang the national anthem at the 1991 Super Bowl", SemanticIntent.NONE),
    ("what is the battery chemistry of lithium iron phosphate", SemanticIntent.NONE),
    ("system architecture of Linux kernel vfs", SemanticIntent.NONE),
    ("write a python function to invert a binary tree", SemanticIntent.NONE),
    ("how do I cook paneer butter masala", SemanticIntent.NONE),
    ("what is the distance from Earth to Mars", SemanticIntent.NONE),
    ("who won the 2024 ICC T20 World Cup", SemanticIntent.NONE),
    ("send an email to boss saying I will be late", SemanticIntent.NONE),
    ("transfer 500 dollars to John", SemanticIntent.NONE),
    ("add a task to buy groceries tomorrow at 5pm", SemanticIntent.NONE),
    ("schedule a meeting with marketing team on Friday", SemanticIntent.NONE),
    ("turn off the living room lights", SemanticIntent.NONE),
    ("summarize the email from Harvard University", SemanticIntent.NONE),
    ("what is the weather like in Seattle right now", SemanticIntent.NONE),
    ("explain quantum computing in simple terms", SemanticIntent.NONE),
]


def run_held_out_benchmark() -> Dict[str, Any]:
    """Runs classification on held-out evaluation dataset and calculates metrics."""
    router = SemanticIntentRouter.get_instance()
    
    # Warmup
    router.classify("warmup query")
    
    # Metrics tracking per intent
    intents = list(SemanticIntent)
    tp: Dict[SemanticIntent, int] = {i: 0 for i in intents}
    fp: Dict[SemanticIntent, int] = {i: 0 for i in intents}
    fn: Dict[SemanticIntent, int] = {i: 0 for i in intents}
    total_samples: Dict[SemanticIntent, int] = {i: 0 for i in intents}
    
    latencies_ms: List[float] = []
    confusion_rows: List[Tuple[str, SemanticIntent, SemanticIntent, float]] = []

    for query, expected in HELD_OUT_DATASET:
        total_samples[expected] += 1
        t0 = time.perf_counter()
        result = router.classify(query)
        t_el = (time.perf_counter() - t0) * 1000.0
        latencies_ms.append(t_el)

        actual = result.intent
        confusion_rows.append((query, expected, actual, result.confidence))

        if actual == expected:
            tp[expected] += 1
        else:
            fn[expected] += 1
            fp[actual] += 1

    # Calculate per-intent Precision, Recall, F1
    report = {}
    sum_p, sum_r, sum_f1 = 0.0, 0.0, 0.0
    active_intents = [i for i in intents if total_samples[i] > 0]

    for i in active_intents:
        p = tp[i] / (tp[i] + fp[i]) if (tp[i] + fp[i]) > 0 else 0.0
        r = tp[i] / (tp[i] + fn[i]) if (tp[i] + fn[i]) > 0 else 0.0
        f1 = (2 * p * r) / (p + r) if (p + r) > 0 else 0.0
        sum_p += p
        sum_r += r
        sum_f1 += f1
        report[i.value] = {
            "samples": total_samples[i],
            "tp": tp[i],
            "fp": fp[i],
            "fn": fn[i],
            "precision": round(p, 4),
            "recall": round(r, 4),
            "f1": round(f1, 4),
        }

    n_active = len(active_intents)
    macro_avg = {
        "precision": round(sum_p / n_active, 4),
        "recall": round(sum_r / n_active, 4),
        "f1": round(sum_f1 / n_active, 4),
    }

    latencies_ms.sort()
    latency_stats = {
        "count": len(latencies_ms),
        "mean_ms": round(sum(latencies_ms) / len(latencies_ms), 2),
        "p50_ms": round(latencies_ms[int(len(latencies_ms) * 0.50)], 2),
        "p95_ms": round(latencies_ms[int(len(latencies_ms) * 0.95)], 2),
        "p99_ms": round(latencies_ms[int(len(latencies_ms) * 0.99)], 2),
    }

    return {
        "per_intent": report,
        "macro_avg": macro_avg,
        "latency_stats": latency_stats,
        "confusion_rows": confusion_rows,
    }


def test_held_out_benchmark():
    """Validates that router maintains high precision and recall on unseen queries."""
    results = run_held_out_benchmark()
    macro = results["macro_avg"]
    per_intent = results["per_intent"]

    print("\n" + "=" * 80)
    print(f"{'Intent':<28} | {'Samples':<7} | {'Prec':<7} | {'Recall':<7} | {'F1':<7}")
    print("-" * 80)
    for intent_name, metrics in per_intent.items():
        print(
            f"{intent_name:<28} | "
            f"{metrics['samples']:<7} | "
            f"{metrics['precision']:<7.3f} | "
            f"{metrics['recall']:<7.3f} | "
            f"{metrics['f1']:<7.3f}"
        )
    print("-" * 80)
    print(
        f"{'MACRO AVERAGE':<28} | "
        f"{sum(m['samples'] for m in per_intent.values()):<7} | "
        f"{macro['precision']:<7.3f} | "
        f"{macro['recall']:<7.3f} | "
        f"{macro['f1']:<7.3f}"
    )
    print("=" * 80)
    print(f"Latency: Mean={results['latency_stats']['mean_ms']}ms, "
          f"P50={results['latency_stats']['p50_ms']}ms, "
          f"P95={results['latency_stats']['p95_ms']}ms")
    print("=" * 80)

    # Check for any mismatches
    mismatches = [row for row in results["confusion_rows"] if row[1] != row[2]]
    if mismatches:
        print(f"\nMismatches ({len(mismatches)} total):")
        for q, expected, actual, score in mismatches:
            print(f"  [MISMATCH] '{q}' -> expected={expected.value}, got={actual.value} (score={score:.3f})")

    # Strict architectural performance assertions:
    # 1. Macro precision >= 0.85
    assert macro["precision"] >= 0.85, f"Macro precision too low: {macro['precision']}"
    # 2. Macro recall >= 0.80
    assert macro["recall"] >= 0.80, f"Macro recall too low: {macro['recall']}"
    # 3. NONE class recall >= 0.95 (Ensures 95%+ of adversarial/compound/negated queries route to Tier 3)
    assert per_intent["none"]["recall"] >= 0.95, f"Adversarial recall too low: {per_intent['none']}"
    # 4. Positive intent precision >= 0.90 (Ensures Tier 2 fast path does not execute false positive actions)
    positive_prec = [m["precision"] for k, m in per_intent.items() if k != "none"]
    assert min(positive_prec) >= 0.90, f"Positive intent precision too low: {positive_prec}"
    # 5. Latency p95 under 50ms on host CPU
    assert results["latency_stats"]["p95_ms"] < 50.0, f"Latency p95 too high: {results['latency_stats']['p95_ms']}ms"


if __name__ == "__main__":
    test_held_out_benchmark()
