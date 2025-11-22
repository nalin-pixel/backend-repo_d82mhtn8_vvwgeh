import os
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Dict, Any

from fastapi import FastAPI, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from database import db, create_document, get_documents
from schemas import UserProfile, ChatMessage, RewardLedger, PremiumPass, VaultDocument

app = FastAPI(title="AI Travel Assistant API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------- Utility ----------
COLLECTION_USER = "userprofile"
COLLECTION_CHAT = "chatmessage"
COLLECTION_REWARD = "rewardledger"
COLLECTION_PASS = "premiumpass"
COLLECTION_VAULT = "vaultdocument"

WELCOME_COINS = 10


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def ensure_user(user_id: str) -> Dict[str, Any]:
    existing = db[COLLECTION_USER].find_one({"user_id": user_id}) if db else None
    if existing:
        return existing
    profile = UserProfile(user_id=user_id, coins=WELCOME_COINS)
    create_document(COLLECTION_USER, profile)
    return db[COLLECTION_USER].find_one({"user_id": user_id})


# ---------- Models ----------
class InitRequest(BaseModel):
    user_id: str


class ChatRequest(BaseModel):
    user_id: str
    message: str
    image_url: Optional[str] = None
    locale: str = Field("en", description="en or hi")


class ChatResponse(BaseModel):
    reply: str
    followups: List[str] = []
    tips: List[str] = []
    locale: str = "en"


class BudgetInput(BaseModel):
    user_id: str
    days: int
    travelers: int
    destination_type: str = Field("city", description="city/beach/mountains/rural")
    accommodation: str = Field("budget", description="budget/mid/premium")
    daily_style: str = Field("thrifty", description="thrifty/standard/comfort")


class BudgetOutput(BaseModel):
    total_estimate: float
    per_day: float
    breakdown: Dict[str, float]
    suggestions: List[str]


class RewardRequest(BaseModel):
    user_id: str
    action: str
    coins: int
    notes: Optional[str] = None


class RedeemRequest(BaseModel):
    user_id: str
    feature: str
    duration: str = Field("1d", description="1d/7d/30d")


class TranslateRequest(BaseModel):
    text: str
    target: str = Field("en", description="en or hi")


# ---------- Simple Rule-based AI ----------
PROBLEM_KB = {
    "budget_low": "Try hostels, public buses/metros, cook sometimes, pick free walking tours, travel off-peak.",
    "eat_safe": "Choose busy places with recent reviews, bottled water, avoid raw salads if unsure, prefer hot cooked food.",
    "transport_best": "Short city hops: metro/bus. Intercity: train or budget coach. Late night: licensed cabs only.",
    "girls_safety": "Stick to well-lit areas, share live location, avoid isolated spots late night, verify cabs, trust your instinct.",
    "packing": "Layered clothes, power bank, universal adapter, basic meds, copies of IDs, padlock, quick-dry towel.",
    "cost_reduce": "Travel off-season, fly mid-week, use passes, city cards, shared rides, cook breakfasts, compare across apps.",
    "confusing_plan": "Group by region, reduce hotel hops, add buffer time, keep max 2-3 key activities per day.",
    "hidden_places": "Ask locals, explore neighborhoods beyond the center, check community maps and Reddit threads.",
    "lost_item": "Note location/time, contact venue/transport lost-and-found, file a police diary entry if needed, block cards.",
    "scared": "Find a lit public place, call a trusted contact, share live location, approach staff/security, use emergency numbers.",
    "adventures": "Look for guided hikes, cycling tours, river rafting (seasonal), zip-lines, local cooking or art workshops.",
}


def detect_intent(text: str) -> str:
    t = text.lower()
    if any(k in t for k in ["where should i travel", "go where", "destination"]):
        return "where_travel"
    if any(k in t for k in ["budget", "low money", "cheap"]):
        return "budget_low"
    if any(k in t for k in ["eat", "food", "restaurant", "safe to eat"]):
        return "eat_safe"
    if any(k in t for k in ["transport", "bus", "train", "cab"]):
        return "transport_best"
    if "safe" in t and any(k in t for k in ["girl", "women", "female"]):
        return "girls_safety"
    if any(k in t for k in ["pack", "packing", "luggage"]):
        return "packing"
    if any(k in t for k in ["reduce cost", "save money", "cost down"]):
        return "cost_reduce"
    if any(k in t for k in ["confusing", "fix plan", "improve itinerary"]):
        return "confusing_plan"
    if any(k in t for k in ["hidden", "offbeat", "secret"]):
        return "hidden_places"
    if any(k in t for k in ["lost", "missing", "misplaced"]):
        return "lost_item"
    if any(k in t for k in ["scared", "unsafe", "help me"]):
        return "scared"
    if any(k in t for k in ["adventure", "activities"]):
        return "adventures"
    return "general"


def ai_reply(message: str, locale: str = "en") -> ChatResponse:
    intent = detect_intent(message)
    followups = [
        "What’s your budget range?",
        "When are you traveling?",
        "Solo or with friends/family?",
    ]

    if intent == "where_travel":
        txt = (
            "Tell me your month, budget and vibe (beach/mountains/city). I’ll shortlist 3 destinations with pros/cons."
        )
    elif intent in PROBLEM_KB:
        txt = PROBLEM_KB[intent]
    else:
        txt = (
            "I’ve got you. Share your city, dates and budget. I’ll suggest options, safety notes and a simple plan."
        )

    tips = [
        "Keep digital + paper copies of IDs.",
        "Share your live location when traveling late.",
        "Avoid exchanging cash at airports; use ATMs or cards.",
    ]

    # Basic bilingual support
    if locale.startswith("hi"):
        txt = (
            "Bilkul! Apna budget, tareekh aur vibe batayein. Main aapko behtareen options, safety tips aur simple plan dunga/dungi."
            if intent == "general"
            else txt
        )
        tips = [
            "ID ki digital aur paper copies rakhein.",
            "Late travel pe live location share karein.",
            "Airport par currency exchange mehenga ho sakta hai.",
        ]

    return ChatResponse(reply=txt, followups=followups, tips=tips, locale=locale)


# ---------- Routes ----------
@app.get("/")
def root():
    return {"message": "AI Travel Assistant Backend running"}


@app.get("/test")
def test_database():
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set",
        "database_name": "✅ Set" if os.getenv("DATABASE_NAME") else "❌ Not Set",
        "connection_status": "Not Connected",
        "collections": [],
    }
    try:
        if db is not None:
            response["database"] = "✅ Available"
            response["connection_status"] = "Connected"
            response["collections"] = db.list_collection_names()[:10]
            response["database"] = "✅ Connected & Working"
    except Exception as e:
        response["database"] = f"⚠️ Connected but error: {str(e)[:80]}"
    return response


@app.post("/api/init")
def init_user(req: InitRequest):
    profile = ensure_user(req.user_id)
    return {"ok": True, "user": {"user_id": profile["user_id"], "coins": profile.get("coins", 0)}}


@app.get("/api/profile/{user_id}")
def get_profile(user_id: str):
    profile = ensure_user(user_id)
    return {"ok": True, "user": {"user_id": profile["user_id"], "coins": profile.get("coins", 0), "language": profile.get("language", "auto")}}


@app.get("/api/history/{user_id}")
def get_history(user_id: str):
    messages = get_documents(COLLECTION_CHAT, {"user_id": user_id}, limit=100)
    # sanitize ObjectId
    for m in messages:
        m["_id"] = str(m["_id"])
    return {"ok": True, "messages": messages}


@app.post("/api/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    ensure_user(req.user_id)
    create_document(COLLECTION_CHAT, ChatMessage(user_id=req.user_id, role="user", content=req.message))
    response = ai_reply(req.message, req.locale)
    create_document(COLLECTION_CHAT, ChatMessage(user_id=req.user_id, role="assistant", content=response.reply, meta={"tips": response.tips}))
    return response


@app.post("/api/budget", response_model=BudgetOutput)
def budget_calc(inp: BudgetInput):
    # Base rates per day per person
    base = {
        "thrifty": 18,
        "standard": 35,
        "comfort": 60,
    }[inp.daily_style]
    accom_map = {"budget": 15, "mid": 35, "premium": 80}
    dest_adj = {"city": 1.0, "beach": 1.1, "mountains": 0.9, "rural": 0.8}

    daily_food = base * dest_adj.get(inp.destination_type, 1.0)
    daily_transport = 8 * dest_adj.get(inp.destination_type, 1.0)
    daily_misc = 5
    per_person_daily = daily_food + daily_transport + daily_misc

    accom_daily = accom_map.get(inp.accommodation, 15)
    total = (per_person_daily * inp.travelers + accom_daily) * inp.days

    breakdown = {
        "food": round(daily_food * inp.travelers * inp.days, 2),
        "transport": round(daily_transport * inp.travelers * inp.days, 2),
        "misc": round(daily_misc * inp.travelers * inp.days, 2),
        "stay": round(accom_daily * inp.days, 2),
    }

    suggestions = [
        "Book stays with kitchens to save on breakfasts.",
        "Use day passes for public transport.",
        "Travel mid-week to reduce fares.",
    ]

    return BudgetOutput(
        total_estimate=round(total, 2),
        per_day=round(total / max(inp.days, 1), 2),
        breakdown=breakdown,
        suggestions=suggestions,
    )


@app.get("/api/tips")
def tips(locale: str = "en"):
    items = [
        {"title": "Scan documents", "body": "Keep passport/IDs in cloud + local copy."},
        {"title": "Local SIM", "body": "Buy at airport/train hubs for instant connectivity."},
        {"title": "Hydration", "body": "Carry a refillable bottle and purification tabs."},
    ]
    if locale.startswith("hi"):
        items = [
            {"title": "Docs ka backup", "body": "Passport/ID ki copies cloud me rakhein."},
            {"title": "Local SIM", "body": "Airport ya station par lena aasaan hota hai."},
            {"title": "Paani", "body": "Refillable bottle saath rakhein."},
        ]
    return {"ok": True, "tips": items}


@app.post("/api/translate")
def translate(req: TranslateRequest):
    # Minimal demo translator for en<->hi (not production quality)
    text = req.text.strip()
    if req.target.startswith("hi"):
        return {"ok": True, "text": f"[HI] {text}"}
    return {"ok": True, "text": text.replace(" hai ", " is ")}


@app.get("/api/coins/{user_id}")
def coins(user_id: str):
    profile = ensure_user(user_id)
    return {"ok": True, "coins": profile.get("coins", 0)}


@app.post("/api/reward")
def reward(req: RewardRequest):
    profile = ensure_user(req.user_id)
    new_balance = profile.get("coins", 0) + max(0, req.coins)
    db[COLLECTION_USER].update_one({"user_id": req.user_id}, {"$set": {"coins": new_balance, "updated_at": now_utc()}})
    create_document(COLLECTION_REWARD, RewardLedger(**req.model_dump()))
    return {"ok": True, "coins": new_balance}


@app.post("/api/redeem")
def redeem(req: RedeemRequest):
    costs = {"1d": 10, "7d": 50, "30d": 150}
    days = {"1d": 1, "7d": 7, "30d": 30}[req.duration]
    profile = ensure_user(req.user_id)
    bal = profile.get("coins", 0)
    price = costs[req.duration]
    if bal < price:
        return {"ok": False, "error": "Not enough coins"}
    db[COLLECTION_USER].update_one({"user_id": req.user_id}, {"$set": {"coins": bal - price, "updated_at": now_utc()}})
    pass_doc = PremiumPass(user_id=req.user_id, feature=req.feature, expires_at=now_utc() + timedelta(days=days))
    create_document(COLLECTION_PASS, pass_doc)
    return {"ok": True, "feature": req.feature, "expires_at": pass_doc.expires_at}


@app.get("/api/passes/{user_id}")
def passes(user_id: str):
    docs = get_documents(COLLECTION_PASS, {"user_id": user_id})
    for d in docs:
        d["_id"] = str(d["_id"])
    return {"ok": True, "passes": docs}


@app.post("/api/image")
async def upload_image(user_id: str = Form(...), file: UploadFile = File(...)):
    ensure_user(user_id)
    # store file to tmp path
    folder = "/tmp/travel_vault"
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, f"{now_utc().timestamp()}_{file.filename}")
    content = await file.read()
    with open(path, "wb") as f:
        f.write(content)
    # save record
    create_document(
        COLLECTION_VAULT,
        VaultDocument(
            user_id=user_id,
            filename=file.filename,
            filetype=file.content_type or "unknown",
            size=len(content),
            storage_path=path,
        ),
    )
    # naive recognition placeholder
    note = "Looks like a travel document or ticket. Check names, dates, and QR validity." if any(k in file.filename.lower() for k in ["ticket", "visa", "pass", "boarding"]) else "Image saved. If this is a place/food, I can guide on safety, hygiene and directions."
    return {"ok": True, "message": note}


@app.post("/api/voice")
async def upload_voice(user_id: str = Form(...), file: UploadFile = File(...)):
    ensure_user(user_id)
    # Demo-only: store file and return mocked transcript
    folder = "/tmp/travel_voice"
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, f"{now_utc().timestamp()}_{file.filename}")
    content = await file.read()
    with open(path, "wb") as f:
        f.write(content)
    transcript = "Voice received. For now I converted it to: 'Help me plan cheap local transport.'"
    # Also log to history
    create_document(COLLECTION_CHAT, ChatMessage(user_id=user_id, role="user", content=transcript, meta={"source": "voice"}))
    response = ai_reply(transcript)
    create_document(COLLECTION_CHAT, ChatMessage(user_id=user_id, role="assistant", content=response.reply))
    return {"ok": True, "transcript": transcript, "reply": response.reply}


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
