# app.py (final version with session + tracker)
from fastapi import FastAPI, Request, Response, HTTPException, Query
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path
import json
from game24.session import get_or_create_session_id
from game24.tracker import log_round
from game24.picker import QuestionPicker
from game24.card_utils import get_values, get_ranks_for_display, _rng_for
from game24.card_assets import pick_card_images
#from game24.schemas import NextResponse  # Optional if using pydantic validation

app = FastAPI()
app.mount("/assets", StaticFiles(directory="pictures"), name="assets")
app.mount("/", StaticFiles(directory="web", html=True), name="web")

DATA_PATH = Path("data/answers.json")
PICTURES_ROOT = Path("pictures")

with open(DATA_PATH, encoding="utf-8") as f:
    PUZZLES = json.load(f)

SESSIONS = {}  # session_id -> {'picker': QuestionPicker, 'recent': set, 'seq': int, 'current': dict}

# Get or init per-session state
def get_session_state(session_id: str):
    if session_id not in SESSIONS:
        SESSIONS[session_id] = {
            'picker': QuestionPicker(PUZZLES),
            'recent': set(),
            'seq': 0,
            'current': None
        }
    return SESSIONS[session_id]

@app.get("/api/next")
def api_next(request: Request, response: Response, level: str = "easy", theme: str = "classic"):
    session_id = get_or_create_session_id(request, response)
    state = get_session_state(session_id)

    print(f"📥 Session: {session_id} requests next puzzle, level={level}")
    p = state['picker'].pick(level)
    if not p:
        print("❌ No puzzles left for this level")
        raise HTTPException(status_code=404, detail="No puzzles available for this difficulty")

    state['seq'] += 1
    state['current'] = p

    values = get_values(p)
    ranks = get_ranks_for_display(p)
    rng = _rng_for(values, salt=theme)
    cards = pick_card_images(values, theme=theme, pictures_root=str(PICTURES_ROOT), rng=rng)

    return {
        "seq": state['seq'],
        "ranks": ranks,
        "values": values,
        "images": [{"code": c["code"], "url": f"/assets/{theme}/{c['code']}.png"} for c in cards],
        "question": f"[{', '.join(ranks)}] (values: {', '.join(str(v) for v in values)})"
    }

@app.post("/api/check")
async def api_check(request: Request, response: Response):
    payload = await request.json()
    session_id = get_or_create_session_id(request, response)
    state = get_session_state(session_id)

    answer = payload.get("answer")
    values = payload.get("values")
    current = state.get("current")
    if not current:
        return JSONResponse({"ok": False, "reason": "No active puzzle"})

    # TODO: Replace with your formula evaluation
    result = {"ok": True, "kind": "formula", "value": 24}  # placeholder

    log_round(session_id, {
        "level": current.get("level"),
        "cards": current.get("cards"),
        "values": current.get("values"),
        "answer": answer,
        "correct": result["ok"],
        "used_help": False,
        "time_spent_sec": 0
    })

    return result

@app.post("/api/restart")
def api_restart(request: Request, response: Response):
    session_id = get_or_create_session_id(request, response)
    SESSIONS[session_id] = {
        'picker': QuestionPicker(PUZZLES),
        'recent': set(),
        'seq': 0,
        'current': None
    }
    print(f"🔄 Session {session_id} restarted.")
    return {"ok": True}

@app.post("/api/exit")
def api_exit():
    return {"ok": True, "msg": "Session ended."}

