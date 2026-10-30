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


def test_scenario_1_correct_quantity_and_booking():
    session = "scenario1-correct-quantity"

    # 5 rooms / 2 rooms per unit = 3 units
    first = chat(
        session,
        "I need AeroMesh Wi-Fi on the PRO plan for a 5-room house."
    )

    assert "api_calls" in first

    # No booking before confirmation.
    assert not any(
        call["api"] == "POST /api/bookings"
        for call in first["api_calls"]
    )

    second = chat(session, "Yes, book it.")

    booking_calls = [
        call for call in second["api_calls"]
        if call["api"] == "POST /api/bookings"
    ]

    assert len(booking_calls) == 1

    payload = booking_calls[0]["payload"]
    assert payload["sku_id"] == "SKU_MESH_WIFI6"
    assert payload["plan_code"] == "PRO"
    assert payload["quantity"] == 3
    assert payload["promo_code"] is None
    assert payload["final_price"] == 1497.0


def test_scenario_1_unknown_product_is_not_booked():
    session = "scenario1-unknown-product"

    result = chat(
        session,
        "I need a Netgear Orbi router for a 5-room house."
    )

    assert not any(
        call["api"] == "POST /api/bookings"
        for call in result["api_calls"]
    )

    assert (
        "not in our catalog" in result["response"].lower()
        or "couldn't find" in result["response"].lower()
        or "not available" in result["response"].lower()
    )
