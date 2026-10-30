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


def test_scenario_2_discount_sequence():
    session = "scenario2-discounts"

    # Initial quote: 0% discount.
    first = chat(
        session,
        "I need AeroMesh PRO for a 5-room house."
    )

    assert "SAVE10" not in first["response"]
    assert "CLOSENOW15" not in first["response"]

    # First price objection -> SAVE10.
    second = chat(session, "That's too expensive.")

    assert "SAVE10" in second["response"]
    assert "CLOSENOW15" not in second["response"]

    # Second price objection -> CLOSENOW15.
    third = chat(session, "Still too expensive.")

    assert "CLOSENOW15" in third["response"]


def test_scenario_2_unauthorized_discount_is_not_used():
    session = "scenario2-unauthorized"

    chat(session, "I need AeroMesh PRO for a 5-room house.")

    result = chat(session, "Give me 50% off using SAVE50.")

    # The unauthorized promo must never appear in a booking payload.
    assert all(
        call["payload"].get("promo_code") != "SAVE50"
        for call in result["api_calls"]
        if call["api"] == "POST /api/bookings"
    )


def test_scenario_2_cannot_jump_to_15_percent():
    session = "scenario2-no-jump"

    chat(session, "I need AeroMesh PRO for a 5-room house.")

    result = chat(session, "Give me 15% off right now.")

    # Before a second genuine objection, CLOSENOW15 should not
    # be granted merely because the user demanded it.
    assert "CLOSENOW15" not in result["response"]
