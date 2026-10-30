import os
import math
import asyncio
from typing import Dict, Any, Optional
from difflib import SequenceMatcher
from dotenv import load_dotenv
from pydantic import BaseModel, Field
from google import genai
from google.genai import types
from fastapi import FastAPI, HTTPException

# Load environment variables
load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    raise ValueError("GEMINI_API_KEY environment variable is missing. Check your .env file.")

# Initialize Google GenAI client
client = genai.Client(api_key=GEMINI_API_KEY)

# -------------------------------------------------------------------
# Mock External Catalog & Booking APIs
# -------------------------------------------------------------------
MOCK_CATALOG = {
    "SKU_AIRPODS_PRO2": {
        "name": "AirPods Pro 2nd Gen",
        "max_capacity_per_unit": 1,
        "plans": {"STD": 249.0, "CARE": 279.0}
    },
    "SKU_MESH_WIFI6": {
        "name": "AeroMesh Wi-Fi 6E Home Pack",
        "max_capacity_per_unit": 2,
        "plans": {"STD": 399.0, "PRO": 499.0}
    },
    "SKU_TEAM_HUB": {
        "name": "SyncHub Conference Bar",
        "max_capacity_per_unit": 3,
        "plans": {"STD": 899.0, "PRO": 1150.0}
    }
}

def get_catalog_info() -> Dict[str, Any]:
    """GET /api/catalog"""
    return MOCK_CATALOG

def create_booking(sku_id: str, plan_code: str, quantity: int, promo_code: Optional[str], final_price: float) -> Dict[str, Any]:
    """POST /api/bookings"""
    return {
        "status": "SUCCESS",
        "booking_id": f"BK-{abs(hash((sku_id, plan_code, quantity, final_price)))}",
        "details": {
            "sku_id": sku_id,
            "plan_code": plan_code,
            "quantity": quantity,
            "promo_code": promo_code,
            "final_price": final_price
        }
    }

# -------------------------------------------------------------------
# Pydantic Schema for Structured Intent Extraction
# -------------------------------------------------------------------
class UserIntentSchema(BaseModel):
    requested_item: Optional[str] = Field(
        default=None, 
        description="Product or hardware item mentioned by user (e.g., 'arrow mesh wifi', 'sink hub', 'AirPods')."
    )
    plan_code: Optional[str] = Field(
        default=None, 
        description="Plan code mentioned by user: 'STD', 'PRO', or 'CARE'. Upper case only."
    )
    capacity_requirement: Optional[int] = Field(
        default=None, 
        description="Total rooms, people, or units required as an integer (e.g., 5 for '5-room house')."
    )
    is_price_objection: bool = Field(
        default=False, 
        description="True ONLY if user objects to price (e.g. 'too expensive', 'cheaper', 'discount'). False if user demands specific codes or promo codes."
    )
    is_explicit_confirmation: bool = Field(
        default=False, 
        description="True if user explicitly confirms booking (e.g., 'book it', 'yes', 'confirm', 'proceed')."
    )

# -------------------------------------------------------------------
# Deterministic State Machine Class
# -------------------------------------------------------------------
class SalesAgentSession:
    def __init__(self, session_id: str):
        self.session_id = session_id
        self.lock = asyncio.Lock()
        
        # State Tracking
        self.sku_id: Optional[str] = None
        self.plan_code: Optional[str] = None
        self.requirement_capacity: Optional[int] = None
        self.discount_level: int = 0  # 0: Standard, 1: SAVE10 (10%), 2: CLOSENOW15 (15%)
        self.user_confirmed_quote: bool = False
        self.is_booked: bool = False
        self.booking_record: Optional[Dict[str, Any]] = None

    def match_sku_fuzzy(self, query_item: Optional[str]) -> Optional[str]:
        """Scenario 1: Fuzzy & keyword lookup against catalog."""
        if not query_item:
            return None
        
        query = query_item.lower().strip()
        catalog = get_catalog_info()

        aliases = {
            "SKU_MESH_WIFI6": ["aeromesh", "arrow mesh", "wifi 6e", "mesh wifi", "aero mesh"],
            "SKU_TEAM_HUB": ["synchub", "sink hub", "conference bar", "sync hub"],
            "SKU_AIRPODS_PRO2": ["airpods", "air pods", "airpods pro"]
        }

        for sku, keywords in aliases.items():
            if any(kw in query for kw in keywords):
                return sku

        best_sku, best_score = None, 0.6
        for sku, details in catalog.items():
            score = SequenceMatcher(None, query, details["name"].lower()).ratio()
            if score > best_score:
                best_score = score
                best_sku = sku

        return best_sku

    def calculate_order(self) -> Dict[str, Any]:
        """Scenario 1 & 2: Deterministic capacity math & discount ceiling."""
        if not self.sku_id or not self.plan_code or not self.requirement_capacity:
            return {}

        catalog_item = MOCK_CATALOG[self.sku_id]
        unit_capacity = catalog_item["max_capacity_per_unit"]
        unit_price = catalog_item["plans"][self.plan_code]

        # Exact ceiling calculation
        quantity = math.ceil(self.requirement_capacity / unit_capacity)
        base_total = quantity * unit_price

        # Enforce exact promo codes
        promo_code = None
        discount_rate = 0.0
        if self.discount_level == 1:
            promo_code = "SAVE10"
            discount_rate = 0.10
        elif self.discount_level >= 2:
            promo_code = "CLOSENOW15"
            discount_rate = 0.15

        final_price = round(base_total * (1.0 - discount_rate), 2)

        return {
            "sku_id": self.sku_id,
            "product_name": catalog_item["name"],
            "plan_code": self.plan_code,
            "quantity": quantity,
            "promo_code": promo_code,
            "final_price": final_price
        }

    async def process_turn(self, user_message: str) -> Dict[str, Any]:
        """Scenario 4: Lock protection against concurrent duplicate triggers."""
        async with self.lock:
            if self.is_booked:
                return {
                    "response": f"Your order is already confirmed! Booking ID: {self.booking_record['booking_id']}",
                    "api_calls": []
                }

            # 1. Structured output extraction using Gemini API
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=f"Extract structured intent from user message: '{user_message}'",
                config=types.GenerateContentConfig(
                    system_instruction="Extract structured entities and user intent for sales order processing.",
                    response_mime_type="application/json",
                    response_schema=UserIntentSchema,
                ),
            )

            # Parse structured output from Gemini response
            intent = UserIntentSchema.model_validate_json(response.text)

            api_calls = [{"api": "GET /api/catalog", "payload": {}}]
            state_modified = False

            # 2. Match SKU (Scenario 1)
            if intent.requested_item:
                matched_sku = self.match_sku_fuzzy(intent.requested_item)
                if not matched_sku:
                    return {
                        "response": f"I'm sorry, but '{intent.requested_item}' is not in our catalog.",
                        "api_calls": api_calls
                    }
                if matched_sku != self.sku_id:
                    self.sku_id = matched_sku
                    state_modified = True

            # Extract plan
            if intent.plan_code and intent.plan_code in ["STD", "PRO", "CARE"]:
                if intent.plan_code != self.plan_code:
                    self.plan_code = intent.plan_code
                    state_modified = True
            elif not self.plan_code:
                self.plan_code = "STD"

            # Extract requirements
            if intent.capacity_requirement and intent.capacity_requirement > 0:
                if intent.capacity_requirement != self.requirement_capacity:
                    self.requirement_capacity = intent.capacity_requirement
                    state_modified = True

            # Scenario 3: If requirements changed mid-conversation, invalidate explicit confirmation
            if state_modified:
                self.user_confirmed_quote = False

            # Scenario 2: Price objection handling
            if intent.is_price_objection:
                if self.discount_level < 2:
                    self.discount_level += 1
                self.user_confirmed_quote = False

            order = self.calculate_order()

            # Scenario 3: Execute create_booking ONLY after explicit user confirmation
            if intent.is_explicit_confirmation:
                if not order:
                    return {
                        "response": "Please specify the item, plan, and quantity/capacity before booking.",
                        "api_calls": api_calls
                    }
                
                if self.user_confirmed_quote:
                    booking_payload = {
                        "sku_id": order["sku_id"],
                        "plan_code": order["plan_code"],
                        "quantity": order["quantity"],
                        "promo_code": order["promo_code"],
                        "final_price": order["final_price"]
                    }
                    res = create_booking(**booking_payload)
                    api_calls.append({"api": "POST /api/bookings", "payload": booking_payload})

                    self.is_booked = True
                    self.booking_record = res

                    return {
                        "response": f"Booking successful! Confirmation ID: {res['booking_id']}. Total: ${order['final_price']}.",
                        "api_calls": api_calls
                    }

            self.user_confirmed_quote = True
            discount_text = f" (Discount Applied: {order['promo_code']})" if order.get("promo_code") else ""

            return {
                "response": (
                    f"For a requirement of {self.requirement_capacity}, you will need {order['quantity']} unit(s) "
                    f"of {order['product_name']} ({order['plan_code']} plan). Total price: ${order['final_price']}{discount_text}. "
                    f"Would you like to proceed with the booking?"
                ),
                "api_calls": api_calls
            }

# -------------------------------------------------------------------
# FastAPI Web App Interface
# -------------------------------------------------------------------
app = FastAPI(title="AI Voice Sales Engine")
SESSIONS: Dict[str, SalesAgentSession] = {}

class ChatRequest(BaseModel):
    session_id: str
    message: str

@app.post("/chat")
async def chat_endpoint(req: ChatRequest):
    if req.session_id not in SESSIONS:
        SESSIONS[req.session_id] = SalesAgentSession(session_id=req.session_id)
    
    session = SESSIONS[req.session_id]
    result = await session.process_turn(req.message)
    return result

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)