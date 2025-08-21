#nennnn
##nnn
from flask import Flask, request, jsonify, make_response, send_from_directory
import os, uuid, logging, sys
import random
from pathlib import Path
import json
import hashlib
import ast
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional

# Fix Python path to import from game24
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.append(str(PROJECT_ROOT))

from game24.picker import QuestionPicker 
from game24.card_utils import get_values, get_ranks_for_display, _rng_for
from game24.card_assets import pick_card_images
from game24.complexity import preprocess_ranks
from game24.safety_eval import safe_eval_bounded, UnsafeExpression

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Load puzzles
DATA_ROOT = PROJECT_ROOT / 'web' / 'static' / 'answers.json'
with open(DATA_ROOT, encoding="utf-8") as f:
    PUZZLES = json.load(f)
logger.debug(f"I loaded total {len(PUZZLES)} puzzles from {DATA_ROOT}")

# Configuration
PICTURES_ROOT = PROJECT_ROOT / 'web' / 'static' / 'assets' / 'images'
SESSION_STORE = {}
logger.debug(f"picutures are here: {PICTURES_ROOT}")

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'dev-secret-key')
app.permanent_session_lifetime = timedelta(minutes=30)  # Session expires after 30 minutes

def cleanup_sessions():
    """Remove expired sessions"""
    now = datetime.now()
    expired = [sid for sid, session in SESSION_STORE.items() 
              if now - session['last_activity'] > app.permanent_session_lifetime]
    for sid in expired:
        del SESSION_STORE[sid]

def get_or_create_session_id(request):
    """Gets the session ID from the cookie or creates a new one."""
    session_id = request.cookies.get('session_id')
    if not session_id:
        session_id = str(uuid.uuid4())
    return session_id

def get_session_state(session_id, expected_seq=None):
    """Retrieves the session state, optionally validating the sequence number."""
    cleanup_sessions()  # Clean up expired sessions first

    # Get or create the session state
    if session_id not in SESSION_STORE:
        # Initialize a brand new session
        SESSION_STORE[session_id] = {
            'seq': expected_seq if expected_seq is not None else 0,
            'picker': QuestionPicker(PUZZLES),
            'current': None,
            'last_activity': datetime.now(),
            'stats': {
                'played': 0,
                'solved': 0,
                'revealed': 0,
                'skipped': 0,
                'difficulty': {
                    'easy': {'played': 0, 'solved': 0},
                    'medium': {'played': 0, 'solved': 0},
                    'hard': {'played': 0, 'solved': 0},
                    'challenge': {'played': 0, 'solved': 0}
                }
            }
        }
        app.logger.debug(f"Created NEW session: {session_id[:8]}...")
    else:
        # This is an existing session
        session_data = SESSION_STORE[session_id]

        # CRITICAL: Check for sequence mismatch.
        # If the frontend provides an expected_seq, it must match our stored seq.
        if expected_seq is not None and session_data['seq'] != expected_seq:
            app.logger.warning(f"Session {session_id[:8]}... seq mismatch! Frontend:{expected_seq}, Backend:{session_data['seq']}. Resetting session.")
            # Handle the mismatch. One option is to reset the session to the frontend's expected_seq.
            # This is often the safest bet to recover from a de-sync.
            session_data['seq'] = expected_seq
            # You might also want to reset other state, but it's complex.
            # For simplicity, we just update the seq to what the frontend expects.

        # Update the activity time
        session_data['last_activity'] = datetime.now()

    return SESSION_STORE[session_id]

# Helper function to find a puzzle by case_id
def find_puzzle_by_case_id(case_id):
    """Search all puzzles for a specific case_id. Returns the puzzle dict or None."""
    for puzzle in PUZZLES:
        if puzzle.get('case_id') == case_id:
            return puzzle
    return None  # Not found

@app.route('/api/next')
def api_next():
    # Get session ID and the expected sequence number from the frontend
    session_id = get_or_create_session_id(request)
    logger.debug(f"in next :session_id = {session_id}")
    current_seq = request.args.get('seq', type=int, default=0)  # Default to 0 if not provided

    # Retrieve the session state, checking for seq mismatch
    state = get_session_state(session_id, expected_seq=current_seq)

    # Now, INCREMENT the sequence number for the NEW state we are about to send
    new_seq = state['seq'] + 1
    state['seq'] = new_seq  # Update the state with the new sequence number

    # Update stats and pick a new question
    theme = request.args.get('theme', 'classic')
    level = request.args.get('level', 'easy')
    requested_case_id = request.args.get('case_id', type=int)

    state['stats']['played'] += 1
    state['stats']['difficulty'][level]['played'] += 1 # This line now works

    #new
    if requested_case_id is not None:
        # Try to find the specific puzzle by ID
        p = find_puzzle_by_case_id(requested_case_id)
        if p is None:
            # If not found, decrement the counters we just added and return an error
            state['seq'] -= 1
            state['stats']['played'] -= 1
            return jsonify({"error": f"Case ID {requested_case_id} not found."}), 404
        print(f"DEBUG: Loading specific case_id: {requested_case_id}")
    else:
        # Otherwise, get a random puzzle the normal way
        p = state['picker'].pick(level)
        if not p:
            # If no puzzles available, decrement the counters and return an error
            state['seq'] -= 1
            state['stats']['played'] -= 1
            return jsonify({"error": "No puzzles available"}), 404

    state['current'] = p

    values = get_values(p)
    ranks = get_ranks_for_display(p)
    rng = _rng_for(values, salt=theme)
    cards = pick_card_images(values, theme=theme, pictures_root=str(PICTURES_ROOT), rng=rng)

    # Build the response
    response_data = {
        "seq": new_seq, # Send the NEW sequence number to the frontend
        "ranks": ranks,
        "values": values,
        "images": [{"code": c["code"], "url": f"/static/assets/images/{theme}/{c['code']}.png"} for c in cards],
        "question": f"[{', '.join(ranks)}] (values: {', '.join(str(v) for v in values)})",
        "case_id": p.get('case_id'),
        "difficulty": p.get("difficulty", "unknown"),
        "stats": state['stats']
    }

    # Create the response and set the session cookie if it's a new session
    resp = make_response(jsonify(response_data))
    if not request.cookies.get('session_id'):
        resp.set_cookie('session_id', session_id, max_age=1800) # 30 minutes
    return resp


def _find_puzzle_by_values(values_needed: List[int]) -> Optional[Dict[str, Any]]:
    tgt = sorted(int(x) for x in values_needed)
    for p in PUZZLES:
        if sorted(get_values(p)) == tgt:
            return p
    return None

def extract_constants(expr: str) -> List[int]:
    expr2 = preprocess_ranks(expr).replace("^", "**")
    tree = ast.parse(expr2, mode="eval")
    consts: List[int] = []
    class V(ast.NodeVisitor):
        def visit_Constant(self, node: ast.Constant):
            if isinstance(node.value, (int, float)):
                v = int(round(float(node.value)))
                consts.append(v)
    V().visit(tree)
    return consts

@app.route('/')
def home():
    return send_from_directory('static', 'index.html')

@app.route('/api/check', methods=['POST'])
def api_check():
    session_id = get_or_create_session_id(request)
    state = get_session_state(session_id)
    
    logger.debug(f"in check :session_id = {session_id}")
    data = request.get_json()
    values_needed = sorted(int(x) for x in data.get('values', []))
    ans = (data.get('answer', '') or "").strip()

    if ans.lower() in {"no sol", "nosol", "no solution", "0", "-1"}:
        puzzle = _find_puzzle_by_values(values_needed)
        sols_exist = bool(puzzle and puzzle.get("solutions"))
        if not sols_exist:
            return jsonify({"ok": True, "value": None, "kind": "no-solution"})
        else:
            return jsonify({
                "ok": False,
                "reason": "Try 'help' to see a solution example, 'help all' to see all solutions.",
                "kind": "help-available",
            })

    try:
        used_consts = sorted(extract_constants(ans))
    except Exception as e:
        return jsonify({"ok": False, "reason": f"Invalid expression: {e}"}), 400

    if used_consts != values_needed:
        return jsonify({"ok": False, "reason": f"You must use exactly these numbers {values_needed}. Found {used_consts}."}), 400

    try:
        val = safe_eval_bounded(preprocess_ranks(ans))
    except UnsafeExpression as e:
        return jsonify({"ok": False, "reason": str(e)}), 400
    except ZeroDivisionError:
        return jsonify({"ok": False, "reason": "Division by zero."}), 400
    except Exception as e:
        return jsonify({"ok": False, "reason": f"Invalid expression: {e}"}), 400

    if abs(val - 24.0) < 1e-9:
        state['stats']['solved'] += 1
        state['stats']['difficulty'][state['current'].get('level', 'easy')]['solved'] += 1
        return jsonify({"ok": True, "value": val, "kind": "formula"})
    else:
        return jsonify({"ok": False, "value": val, "reason": f"Not 24 "})

@app.route('/api/help', methods=['POST'])
def api_help():
    session_id = get_or_create_session_id(request)
    logger.debug(f"in help :session_id = {session_id}")
    state = get_session_state(session_id)
    state['stats']['revealed'] += 1
    
    data = request.get_json()
    try:
        p = _find_puzzle_by_values(data.get('values', []))
        if not p:
            return jsonify({"solutions": [], "has_solution": False})

        sols = list(p.get("solutions", []))
        if not sols:
            return jsonify({"solutions": [], "has_solution": False})

        if data.get('all', False):
            return jsonify({"solutions": sols, "has_solution": True})
        return jsonify({"solutions": [random.choice(sols)], "has_solution": True})
    except Exception as e:
        return jsonify({"solutions": [], "has_solution": False}), 400

@app.route('/api/skip', methods=['POST'])
def api_skip():
    session_id = get_or_create_session_id(request)
    logger.debug(f"in skip :session_id = {session_id}")
    state = get_session_state(session_id)
    state['stats']['skipped'] += 1
    return api_next()

@app.route('/api/restart', methods=['POST'])
def api_restart():
    session_id = get_or_create_session_id(request)
    logger.debug(f"in restart :session_id = {session_id}")
    if session_id in SESSION_STORE:
        level = SESSION_STORE[session_id]['current'].get('level', 'easy') if SESSION_STORE[session_id]['current'] else 'easy'
        SESSION_STORE[session_id] = {
            'seq': 0,
            'picker': QuestionPicker(PUZZLES, recent_window=60, medium_no_sol_target=0.10),
            'current': None,
            'last_activity': datetime.now(),
            'stats': {
                'played': 0,
                'solved': 0,
                'revealed': 0,
                'skipped': 0,
                'difficulty': {
                    'easy': {'played': 0, 'solved': 0},
                    'medium': {'played': 0, 'solved': 0},
                    'hard': {'played': 0, 'solved': 0},
                    'challenge': {'played': 0, 'solved': 0}
                }
            }
        }
    return jsonify({"ok": True, "msg": "Session reset"})

@app.route('/api/exit', methods=['POST'])
def api_exit():
    session_id = get_or_create_session_id(request)
    logger.debug(f"in exit :session_id = {session_id}")
    if session_id in SESSION_STORE:
        del SESSION_STORE[session_id]
    return jsonify({"ok": True, "msg": "Session ended"})

@app.route('/api/stats')
def api_stats():
    session_id = get_or_create_session_id(request)
    state = get_session_state(session_id)
    return jsonify(state['stats'])

@app.route('/static/<path:filename>')
def static_files(filename):
    return send_from_directory('static', filename)

if __name__ == '__main__':
    print("using version stats error")
    app.run(debug=True)
