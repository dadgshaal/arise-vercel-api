"""
ARISE - Backend API (FastAPI) + PostgreSQL optional fallback
=============================================================
Endpoint tetap sama untuk Unity. Backend akan mencoba menyimpan data ke
PostgreSQL. Jika database tidak tersedia, backend tetap berjalan memakai
SESSIONS in-memory agar demo tidak rusak.
"""

import uuid
from typing import List

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from arise_ai_engine import (
    SCENARIOS,
    PROFILE_DESCRIPTIONS,
    CognitiveProfiler,
    next_level,
    pick_scenario,
)

try:
    import db_utils
except Exception as exc:
    db_utils = None
    print("[DB] db_utils tidak dapat dimuat:", exc)

app = FastAPI(
    title="ARISE API",
    description="AI Simulator Ancaman Adaptif untuk Edukasi Keamanan Siber Inklusif",
    version="0.2.0-db-fallback",
)

profiler = CognitiveProfiler()
SESSIONS: dict = {}
TOTAL_ROUNDS = 6


@app.get("/")
def root():
    return {
        "name": "ARISE API",
        "status": "online",
        "health": "/health",
        "docs": "/docs",
    }




# ============================================================
# Models
# ============================================================
class AssessmentAnswer(BaseModel):
    response_time_seconds: float
    correct: bool


class AssessmentRequest(BaseModel):
    user_id: str
    answers: List[AssessmentAnswer]


class AssessmentResponse(BaseModel):
    session_id: str
    cognitive_profile: str
    profile_label: str
    profile_description: str
    initial_level: int
    reduced_motion_recommended: bool


class ScenarioOption(BaseModel):
    id: str
    label: str


class NextScenarioResponse(BaseModel):
    scenario_id: int
    category: str
    sender: str
    message: str
    options: List[ScenarioOption]
    level: int
    round_number: int


class ScenarioAnswer(BaseModel):
    session_id: str
    option_id: str
    response_time_seconds: float


class ScenarioResult(BaseModel):
    correct: bool
    feedback: str
    ar_mode: str
    new_level: int
    rounds_completed: int
    session_finished: bool


class DashboardResponse(BaseModel):
    cognitive_profile: str
    rounds_completed: int
    correct_total: int
    current_level: int
    history: list
    recommendation: str


# ============================================================
# Helpers
# ============================================================
def _db_available() -> bool:
    if db_utils is None:
        return False
    status = db_utils.database_status()
    return bool(status.get("connected"))


def _save_session_memory(session_id: str, user_id: str, profile: str, initial_level: int):
    SESSIONS[session_id] = {
        "user_id": user_id,
        "profile": profile,
        "level": initial_level,
        "used_scenario_ids": [],
        "current_scenario_id": None,
        "history": [],
    }


def _get_session(session_id: str) -> dict:
    """
    Ambil session dengan PostgreSQL sebagai sumber utama.

    Penting untuk deployment serverless seperti Vercel:
    proses/function bisa berganti antar request. Kalau kita mengutamakan
    SESSIONS in-memory, data session bisa stale, misalnya current_scenario_id
    masih None padahal /scenario/next sudah menyimpan skenario aktif ke database.

    Karena itu saat db_utils tersedia, coba load dari database lebih dulu.
    Kalau database gagal/tidak ada, baru fallback ke memory.
    """
    if db_utils is not None:
        loaded = db_utils.load_session(session_id)
        if loaded:
            SESSIONS[session_id] = loaded
            return loaded

    session = SESSIONS.get(session_id)
    if session:
        return session

    raise HTTPException(status_code=404, detail="Sesi tidak ditemukan")


def _make_recommendation(history: list) -> str:
    wrong_categories: dict = {}
    for h in history:
        if not h["correct"]:
            wrong_categories[h["category"]] = wrong_categories.get(h["category"], 0) + 1

    if not history:
        return "Belum ada data. Mulai latihan untuk melihat rekomendasi."
    if not wrong_categories:
        return "Tidak ada catatan kesalahan. Pertahankan dengan latihan rutin."

    top_category = max(wrong_categories, key=wrong_categories.get)
    return f'Disarankan mengulang materi tentang "{top_category}" dengan pendampingan tambahan.'


# ============================================================
# 1. ASESMEN KOGNITIF AWAL
# ============================================================
@app.post("/assessment/submit", response_model=AssessmentResponse)
def submit_assessment(payload: AssessmentRequest):
    if not payload.answers:
        raise HTTPException(status_code=400, detail="Jawaban asesmen tidak boleh kosong")

    times = [a.response_time_seconds for a in payload.answers]
    corrects = [a.correct for a in payload.answers]

    avg_time = sum(times) / len(times)
    accuracy = sum(1 for c in corrects if c) / len(corrects)
    variability = (max(times) - min(times)) if len(times) > 1 else 0.5

    profile, _ = profiler.predict(avg_time, accuracy, variability)
    info = PROFILE_DESCRIPTIONS[profile]
    initial_level = 2 if accuracy >= 0.66 else 1
    session_id = str(uuid.uuid4())

    _save_session_memory(session_id, payload.user_id, profile, initial_level)

    if db_utils is not None:
        saved = db_utils.create_session_record(
            session_id=session_id,
            external_user_id=payload.user_id,
            profile=profile,
            avg_time=avg_time,
            accuracy=accuracy,
            variability=variability,
            reduced_motion=info["reduced_motion"],
            initial_level=initial_level,
        )
        print("[DB] session saved:" if saved else "[DB] session fallback-memory:", session_id)

    return AssessmentResponse(
        session_id=session_id,
        cognitive_profile=profile,
        profile_label=info["label"],
        profile_description=info["description"],
        initial_level=initial_level,
        reduced_motion_recommended=info["reduced_motion"],
    )


# ============================================================
# 2. SKENARIO BERIKUTNYA
# ============================================================
@app.get("/scenario/next/{session_id}", response_model=NextScenarioResponse)
def get_next_scenario(session_id: str):
    session = _get_session(session_id)

    scenario = pick_scenario(session["level"], session["used_scenario_ids"])
    session["used_scenario_ids"].append(scenario["id"])
    session["current_scenario_id"] = scenario["id"]

    if db_utils is not None:
        db_utils.update_next_scenario(session_id, session["used_scenario_ids"], scenario["id"])

    return NextScenarioResponse(
        scenario_id=scenario["id"],
        category=scenario["category"],
        sender=scenario["sender"],
        message=scenario["message"],
        options=[ScenarioOption(id=o["id"], label=o["label"]) for o in scenario["options"]],
        level=session["level"],
        round_number=len(session["history"]) + 1,
    )


# ============================================================
# 3. JAWABAN PENGGUNA
# ============================================================
@app.post("/scenario/respond", response_model=ScenarioResult)
def respond_scenario(payload: ScenarioAnswer):
    session = _get_session(payload.session_id)

    if session["current_scenario_id"] is None:
        raise HTTPException(status_code=400, detail="Belum ada skenario aktif untuk sesi ini")

    scenario = next(s for s in SCENARIOS if s["id"] == session["current_scenario_id"])
    option = next((o for o in scenario["options"] if o["id"] == payload.option_id), None)
    if option is None:
        raise HTTPException(status_code=400, detail="option_id tidak dikenali")

    level_before = session["level"]
    new_level = next_level(level_before, option["correct"])
    round_number = len(session["history"]) + 1
    session_finished = round_number >= TOTAL_ROUNDS

    session["history"].append({
        "round": round_number,
        "scenario_id": scenario["id"],
        "category": scenario["category"],
        "correct": option["correct"],
        "level_before": level_before,
        "level_after": new_level,
        "response_time_seconds": payload.response_time_seconds,
        "ar_mode": option["arMode"],
    })
    session["level"] = new_level
    session["current_scenario_id"] = None

    if db_utils is not None:
        db_utils.save_response_record(
            session_id=payload.session_id,
            round_number=round_number,
            scenario_id=scenario["id"],
            option_code=option["id"],
            is_correct=option["correct"],
            level_before=level_before,
            level_after=new_level,
            response_time_seconds=payload.response_time_seconds,
            ar_mode=option["arMode"],
            session_finished=session_finished,
        )

    return ScenarioResult(
        correct=option["correct"],
        feedback=option["feedback"],
        ar_mode=option["arMode"],
        new_level=new_level,
        rounds_completed=len(session["history"]),
        session_finished=session_finished,
    )


# ============================================================
# 4. DASHBOARD PENDAMPING
# ============================================================
@app.get("/dashboard/{session_id}", response_model=DashboardResponse)
def get_dashboard(session_id: str):
    session = _get_session(session_id)
    history = session["history"]
    correct_total = sum(1 for h in history if h["correct"])

    return DashboardResponse(
        cognitive_profile=session["profile"],
        rounds_completed=len(history),
        correct_total=correct_total,
        current_level=session["level"],
        history=history,
        recommendation=_make_recommendation(history),
    )


@app.get("/health")
def health_check():
    db_status = db_utils.database_status() if db_utils is not None else {"connected": False, "reason": "db_utils tidak tersedia"}
    return {
        "status": "ok",
        "scenarios_loaded": len(SCENARIOS),
        "db": db_status,
        "memory_sessions": len(SESSIONS),
    }
