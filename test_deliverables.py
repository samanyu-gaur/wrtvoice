"""
Quick test script for Deliverable 2 & 3 components that do NOT require
Ollama or a GPU.  Run with:  python test_deliverables.py
"""

import asyncio
import sys
import os
import importlib

# Ensure project root is on the path
sys.path.insert(0, os.path.dirname(__file__))

# ------------------------------------------------------------------
# The modules/__init__.py imports pdf_parser which needs PyPDF2.
# PyPDF2 is not installed, so we bypass __init__.py entirely and
# import each module file directly.
# ------------------------------------------------------------------
def _import_module(name):
    """Import a single .py from modules/ without triggering __init__.py."""
    spec = importlib.util.spec_from_file_location(
        f"modules.{name}",
        os.path.join(os.path.dirname(__file__), "modules", f"{name}.py"),
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules[f"modules.{name}"] = mod
    spec.loader.exec_module(mod)
    return mod

# Load the modules we need (order matters -- dependencies first)
_cm = _import_module("conversation_manager")
ConversationManager = _cm.ConversationManager

_sm = _import_module("deliv2_session_manager")
SessionManager = _sm.SessionManager

_re = _import_module("deliv2_resource_estimation")
generate_full_report = _re.generate_full_report

_ca = _import_module("deliv3_compute_assessment")
full_assessment = _ca.full_assessment


# ==================================================================
# TESTS
# ==================================================================

async def test_session_manager():
    print("=" * 60)
    print("TEST: SessionManager")
    print("=" * 60)

    mgr = SessionManager(max_concurrent_inferences=3)

    # Create sessions
    s1 = await mgr.create_session(pdf_context="Test essay 1")
    s2 = await mgr.create_session(pdf_context="Test essay 2")
    s3 = await mgr.create_session(pdf_context="Test essay 3")
    print(f"  Created 3 sessions: {s1[:8]}..., {s2[:8]}..., {s3[:8]}...")

    # Check stats
    stats = await mgr.get_stats()
    assert stats["active_sessions"] == 3, f"Expected 3, got {stats['active_sessions']}"
    print(f"  Stats: {stats}")

    # Test inference slot (acquire and release)
    async with mgr.inference_slot(s1):
        stats_during = await mgr.get_stats()
        assert stats_during["active_inferences"] == 1
        print(f"  During inference: {stats_during['active_inferences']} active")

    stats_after = await mgr.get_stats()
    assert stats_after["active_inferences"] == 0
    print(f"  After inference: {stats_after['active_inferences']} active")

    # Test queue position
    pos = await mgr.get_queue_position(s1)
    print(f"  Queue position for {s1[:8]}...: {pos}")

    # Remove sessions
    await mgr.remove_session(s1)
    await mgr.remove_session(s2)
    await mgr.remove_session(s3)
    stats_final = await mgr.get_stats()
    assert stats_final["active_sessions"] == 0
    print(f"  After cleanup: {stats_final['active_sessions']} sessions")
    print("  PASSED\n")


async def test_concurrency_queue():
    print("=" * 60)
    print("TEST: Concurrency queue (cap=2, 4 tasks)")
    print("=" * 60)

    mgr = SessionManager(max_concurrent_inferences=2)
    sid = await mgr.create_session()

    async def fake_inference(task_id, delay):
        async with mgr.inference_slot(sid):
            stats = await mgr.get_stats()
            print(f"  Task {task_id}: running "
                  f"(active={stats['active_inferences']}, "
                  f"queued={stats['queue_depth']})")
            await asyncio.sleep(delay)

    # Launch 4 tasks with a cap of 2
    tasks = [asyncio.create_task(fake_inference(i, 0.3)) for i in range(4)]
    await asyncio.gather(*tasks)

    print(f"  All 4 tasks completed")
    await mgr.remove_session(sid)
    print("  PASSED\n")


def test_conversation_schema_with_image():
    print("=" * 60)
    print("TEST: Conversation schema with optional image field")
    print("=" * 60)

    mgr = ConversationManager(storage_dir="conversations")
    mgr.start_session(pdf_context="Test context")

    # Message WITHOUT image (should work exactly like before)
    msg1 = mgr.add_message("student", "Here is my argument.")
    assert "image" not in msg1, "image field should be absent for text-only"
    print(f"  Text-only message: OK (no image field)")

    # Message WITH image (Deliverable 3 extension)
    msg2 = mgr.add_message(
        "student",
        "Here is my floor plan.",
        image={
            "filename": "plan_v2.png",
            "mime_type": "image/png",
            "stored_path": "uploads/sessions/test/plan_v2.png",
        },
    )
    assert msg2["image"]["filename"] == "plan_v2.png"
    print(f"  Image message: OK (image.filename = {msg2['image']['filename']})")

    # Bot response (no image)
    msg3 = mgr.add_message("bot", "Tell me about the circulation path.")
    assert "image" not in msg3
    print(f"  Bot message: OK (no image field)")

    print(f"  Total messages: {len(mgr.conversation)}")
    print("  PASSED\n")


def test_resource_estimation():
    print("=" * 60)
    print("TEST: Resource estimation report")
    print("=" * 60)

    report = generate_full_report()

    assert report["usage_projection"]["total_students"] == 250
    assert report["usage_projection"]["peak_concurrent_users"] == 20
    print(f"  Peak concurrent users: "
          f"{report['usage_projection']['peak_concurrent_users']}")

    for scenario in report["hardware_scenarios"]:
        status = "OK" if scenario["can_serve_peak"] else "INSUFFICIENT"
        print(f"  {scenario['scenario']}: {status} "
              f"(slots={scenario['max_concurrent_slots']}, "
              f"headroom={scenario['headroom_slots']})")
    print("  PASSED\n")


def test_compute_assessment():
    print("=" * 60)
    print("TEST: Compute assessment (VLM impact)")
    print("=" * 60)

    report = full_assessment()

    a100 = report["assessment_a100_80gb"]
    text_slots = a100["text_only"]["max_concurrent_slots"]
    vision_slots = a100["text_plus_vision"]["max_concurrent_slots"]
    reduction = a100["impact_summary"]["concurrent_slot_reduction"]
    print(f"  A100 80GB text-only: {text_slots} slots")
    print(f"  A100 80GB text+vision: {vision_slots} slots")
    print(f"  Slot reduction: {reduction}")
    assert reduction == text_slots - vision_slots

    print(f"  Key takeaways: {len(report['key_takeaways'])} items")
    print("  PASSED\n")


async def main():
    print("\nRunning Deliverable 2 & 3 tests (no Ollama required)\n")

    test_conversation_schema_with_image()
    test_resource_estimation()
    test_compute_assessment()
    await test_session_manager()
    await test_concurrency_queue()

    print("=" * 60)
    print("ALL TESTS PASSED")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
