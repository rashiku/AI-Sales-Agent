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


def test_scenario_3_changed_requirement_recalculates_quantity_and_price():
    session = "scenario3-requirement-change"

    # 4 rooms -> ceil(4/2) = 2 units -> 998
    first = chat(
        session,
        "I need AeroMesh PRO for 4 rooms."
    )

    assert "2 unit(s)" in first["response"]
    assert "$998.0" in first["response"]

    # Change to 7 rooms -> ceil(7/2) = 4 units -> 1996
    second = chat(
        session,
        "Actually, I need 7 rooms."
    )

    assert "4 unit(s)" in second["response"]
    assert "$1996.0" in second["response"]

    # Confirm the UPDATED quote.
    third = chat(session, "Yes, book it.")

    booking_calls = [
        call for call in third["api_calls"]
        if call["api"] == "POST /api/bookings"
    ]

    assert len(booking_calls) == 1

    payload = booking_calls[0]["payload"]

    assert payload["sku_id"] == "SKU_MESH_WIFI6"
    assert payload["plan_code"] == "PRO"
    assert payload["quantity"] == 4
    assert payload["promo_code"] is None
    assert payload["final_price"] == 1996.0


def test_scenario_3_changed_plan_recalculates_price():
    session = "scenario3-plan-change"

    chat(session, "I need AeroMesh for 5 rooms on STD.")

    result = chat(session, "Actually, change the plan to PRO.")

    # 3 units: STD = 1197, PRO = 1497.
    assert "PRO" in result["response"]
    assert "1497.0" in result["response"]

    # Do not book stale STD pricing.
    assert not any(
        call["api"] == "POST /api/bookings"
        for call in result["api_calls"]
    )
