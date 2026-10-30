import asyncio
import requests

BASE_URL = "http://localhost:8000"


def chat(session_id, message):
    response = requests.post(
        f"{BASE_URL}/chat",
        json={"session_id": session_id, "message": message},
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def test_scenario_4_duplicate_confirmation():
    session = "scenario4-duplicate"

    # Establish the quote first.
    chat(
        session,
        "I need AeroMesh PRO for 5 rooms."
    )

    # First confirmation should create the booking.
    first = chat(session, "Yes, book it.")

    first_booking_calls = [
        call for call in first["api_calls"]
        if call["api"] == "POST /api/bookings"
    ]

    assert len(first_booking_calls) == 1

    # Repeated confirmation must NOT create another booking.
    second = chat(session, "Yes, book it again.")

    second_booking_calls = [
        call for call in second["api_calls"]
        if call["api"] == "POST /api/bookings"
    ]

    assert len(second_booking_calls) == 0


def test_scenario_4_two_concurrent_confirmations():
    """
    This test sends two confirmations concurrently.

    NOTE:
    The current app stores sessions in process memory and uses an
    asyncio.Lock per session. This test verifies that both requests
    share the same session and that only one booking is created.
    """

    session = "scenario4-concurrent"

    chat(
        session,
        "I need AeroMesh PRO for 5 rooms."
    )

    async def send_confirmation():
        return await asyncio.to_thread(
            chat,
            session,
            "Yes, book it!"
        )

    results = asyncio.run(
        asyncio.gather(
            send_confirmation(),
            send_confirmation(),
        )
    )

    total_booking_calls = sum(
        1
        for result in results
        for call in result["api_calls"]
        if call["api"] == "POST /api/bookings"
    )

    assert total_booking_calls == 1
