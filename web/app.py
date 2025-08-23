# web/app.py
from flask import Flask, request, jsonify, make_response, send_file
import json, random, time, ast
from pathlib import Path
from typing import List, Dict, Any, Optional

import core  # our helpers/state module

# ---- optional imports from your original logic ----
try:
    from game24.complexity import puzzle_has_simple_solution as _simple_fn  # type: ignore
    from game24.complexity import puzzle_has_hard_solution   as _hard_fn    # type: ignore
except Exception:
    _simple_fn = None
    _hard_fn = None

app = Flask(__name__, static_folder='static', template_folder='templates')

# ---------- load puzzles ----------
def _answers_path():
    here = Path(__file__).parent
    p = here / 'static' / 'answers.json'
    if p.exists(): return p
    raise FileNotFoundError("answers.json not found at web/static/answers.json")

ANSWERS_PATH = _answers_path()
with open(ANSWERS_PATH, encoding='utf-8') as f:
    ALL_PUZZLES: List[Dict[str, Any]] = json.load(f)

def _values_key(cards: List[int]) -> str:
    return "-".join(map(str, sorted(map(int, cards or []))))

# Fast lookups
core.PUZZLES_BY_ID  = {int(p['case_id']): p for p in ALL_PUZZLES}
core.PUZZLES_BY_KEY = {_values_key(p['cards']): p for p in ALL_PUZZLES}

app.logger.debug(f"I loaded total {len(ALL_PUZZLES)} puzzles from {ANSWERS_PATH}")
assets_dir = Path(app.static_folder) / 'assets' / 'images'
app.logger.debug(f"picutures are here: {assets_dir}")

# ---------- helpers for preprocessing into pools ----------
def has_solution(p: Dict[str,Any]) -> bool:
    return bool(p.get('solutions'))

def puzzle_has_simple_solution(p: Dict[str,Any]) -> bool:
    if _simple_fn:
        try:
            return bool(_simple_fn(p))
        except Exception:
            pass
    for s in (p.get('solutions') or []):
        if '^' not in s:
            return True
    return False

def puzzle_has_hard_solution(p: Dict[str,Any]) -> bool:
    if _hard_fn:
        try:
            return bool(_hard_fn(p))
        except Exception:
            pass
    for s in (p.get('solutions') or []):
        if '^' in s:
            return True
    return False

def _build_index(puzzles: List[Dict[str,Any]]):
    idx = []
    for p in puzzles:
        vals = list(map(int, p.get('cards') or []))
        key = _values_key(vals)
        idx.append((p, vals, key))
    return idx

def pre_process_pool(puzzles: List[Dict[str,Any]]):
    app.logger.debug("inside pre_process_pool, sort out pools")

    easy_pool = []
    med_pool_with_simple = []
    med_pool = []
    hard_pool = []
    med_pool_with_hard = []
    nosol_pool = []

    for (p, vals, key) in _build_index(puzzles):
        lvl = str(p.get("level","")).strip().lower()
        _has = has_solution(p)
        if not _has:
            nosol_pool.append((p, vals, key))
        if lvl == "easy" and _has:
            easy_pool.append((p, vals, key))
        if lvl == "medium":
            med_pool.append((p, vals, key))
            if _has and puzzle_has_simple_solution(p):
                med_pool_with_simple.append((p, vals, key))
            if _has and puzzle_has_hard_solution(p):
                med_pool_with_hard.append((p, vals, key))
        if lvl == "hard":
            hard_pool.append((p, vals, key))

    easy_like = easy_pool + med_pool_with_simple
    hard_like = hard_pool + med_pool_with_hard

    app.logger.debug(
        "loaded original games: nosol=%d, easy=%d, medium=%d, hard=%d, total=%d",
        len(nosol_pool), len(easy_pool), len(med_pool), len(hard_pool),
        len(nosol_pool) + len(easy_pool) + len(med_pool) + len(hard_pool)
    )

    return {
        'nosol': nosol_pool,
        'easy_like': easy_like,
        'medium': med_pool,
        'hard_like': hard_like,
    }

# Build once at startup
POOLS_ADV = pre_process_pool(ALL_PUZZLES)

# ---------- image helpers ----------
SUITS = ['D','S','H','C']
def _rank_code(n: int) -> str:
    return {1:'A',10:'T',11:'J',12:'Q',13:'K'}.get(n, str(n))

def _cards_to_images(cards: List[int], theme: str) -> List[Dict[str, str]]:
    out = []
    for i, n in enumerate(cards):
        rank = _rank_code(n)
        suit = SUITS[i % len(SUITS)]
        code = f"{rank}{suit}"
        url = f"/static/assets/images/{theme}/{code}.png"
        out.append({'code': code, 'url': url})
    return out

# ----- safe expression eval for /api/check -----
ALLOWED_NODES = (
    ast.Expression, ast.BinOp, ast.UnaryOp, ast.Num, ast.Constant,
    ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Pow, ast.USub, ast.UAdd,
    ast.Load, ast.Name
)
ALLOWED_NAMES = { 'A':1, 'T':10, 'J':11, 'Q':12, 'K':13 }
def safe_eval(expr: str) -> float:
    tree = ast.parse(expr, mode='eval')
    for node in ast.walk(tree):
        if not isinstance(node, ALLOWED_NODES):
            raise ValueError(f"Illegal expression: {type(node).__name__}")
        if isinstance(node, ast.Name) and node.id not in ALLOWED_NAMES:
            raise ValueError(f"Unknown identifier: {node.id}")
    code = compile(tree, "<expr>", "eval")
    return float(eval(code, {"__builtins__": {}}, ALLOWED_NAMES))

# ---------- level normalization ----------
LEVEL_ALIASES = {
    '0':'easy','easy':'easy',
    '1':'medium','medium':'medium',
    '2':'hard','3':'hard','hard':'hard',
    '4':'challenge','challenge':'challenge',
    'nosol':'nosol',
}
def normalize_level(level: str) -> str:
    if level is None: return 'easy'
    return LEVEL_ALIASES.get(str(level).lower(), str(level).lower())

# ---------- selection using preprocessed pools ----------
def _pick_from_pool_name(pool_name: str, state: Dict[str,Any]) -> Dict[str,Any]:
    pool = POOLS_ADV.get(pool_name, [])
    if not pool:
        pool = POOLS_ADV['medium']

    recent = set(state.get('recent_keys', [])[-50:])
    candidates = [t for t in pool if t[2] not in recent] or pool
    choice = random.choice(candidates)
    state.setdefault('recent_keys', []).append(choice[2])
    if len(state['recent_keys']) > 100:
        state['recent_keys'] = state['recent_keys'][-100:]
    return choice[0]  # puzzle dict

def _random_pick_by_level(level: str, state: Dict[str,Any]) -> Dict[str,Any]:
    lvl = normalize_level(level)
    if lvl in ('challenge','nosol'):
        return _pick_from_pool_name('nosol', state)
    if lvl == 'hard':
        return _pick_from_pool_name('hard_like', state)
    if lvl == 'easy':
        return _pick_from_pool_name('easy_like', state)
    return _pick_from_pool_name('medium', state)

def _counting_level_for_current(state: Dict[str,Any], puzzle: Dict[str,Any], requested_level: str) -> str:
    p = core._pool(state)
    if p.get('mode') in ('custom', 'competition') or state.get('current_case_id'):
        return puzzle.get('level') or normalize_level(requested_level)
    rl = normalize_level(requested_level)
    return 'challenge' if rl in ('challenge','nosol') else rl

def _competition_time_left(state: Dict[str,Any]) -> Optional[int]:
    end = state.get('competition_ends_at')
    if not end: return None
    left = int(round(end - time.time()))
    return max(0, left)

def _stats_payload(state):
    st = state.get('stats', {})
    app.logger.debug(f"""
        'played': {int(st.get('played', 0))},
        'solved': {int(st.get('solved', 0))},
        'revealed': {int(st.get('revealed', 0))},
        'skipped': {int(st.get('skipped', 0))},
        'difficulty': {st.get('by_level', '')},
        'help_single': {int(st.get('help_single', 0))},
        'help_all': {int(st.get('help_all', 0))},
        'answer_attempts': {int(st.get('answer_attempts', 0))},
        'answer_correct': {int(st.get('answer_correct', 0))},
        'answer_wrong': {int(st.get('answer_wrong', 0))},
        'deal_swaps': {int(st.get('deal_swaps', 0))},
        """)
    return {
        'played': int(st.get('played', 0)),
        'solved': int(st.get('solved', 0)),
        'revealed': int(st.get('revealed', 0)),
        'skipped': int(st.get('skipped', 0)),
        'difficulty': st.get('by_level', {}),
        # optional action counters if you want them on every response
        'help_single': int(st.get('help_single', 0)),
        'help_all': int(st.get('help_all', 0)),
        'answer_attempts': int(st.get('answer_attempts', 0)),
        'answer_correct': int(st.get('answer_correct', 0)),
        'answer_wrong': int(st.get('answer_wrong', 0)),
        'deal_swaps': int(st.get('deal_swaps', 0)),
    }


# ---------- routes ----------
@app.get('/')
def index():
    return send_file('static/index.html')

@app.get('/api/next')
def api_next():
    sid = core.get_or_create_session_id(request)
    app.logger.debug(f"in next :session_id = {sid}")
    state = core.SESSIONS.setdefault(sid, core.default_state())
    gid = core.get_guest_id(request)
    if gid: state['guest_id'] = gid

    theme = request.args.get('theme', 'classic')
    level = request.args.get('level', 'easy')
    case_id = request.args.get('case_id', type=int)
    seq = int(request.args.get('seq', 0))

    # If the user is dealing away the current hand without interacting, count a deal_swap
    prev_cid = state.get('current_case_id')
    if prev_cid and not state.get('hand_interacted'):
        core.bump_deal_swap(state)  # NO played increment; purely diagnostic

    left = _competition_time_left(state)
    if left is not None and left <= 0:
        return jsonify({'competition_over': True}), 403

    pstate = core._pool(state)
    puzzle = None

    if case_id:
        puzzle = core.PUZZLES_BY_ID.get(int(case_id))
        if not puzzle:
            return jsonify({'error': f'Case #{case_id} not found'}), 404
        core._mark_case_status(state, case_id, 'shown')

    elif pstate['mode'] in ('custom','competition'):
        if pstate['done'] or pstate['index'] >= len(pstate['ids']):
            pstate['done'] = True
            score_map, unfinished = core._pool_score(state)
            return jsonify({'error': 'Pool complete', 'pool_done': True, 'unfinished': unfinished}), 400
        case_id = pstate['ids'][pstate['index']]
        pstate['index'] += 1
        puzzle = core.PUZZLES_BY_ID.get(int(case_id))
        core._mark_case_status(state, case_id, 'shown')

    else:
        puzzle = _random_pick_by_level(level, state)

    state['current_case_id'] = int(puzzle['case_id'])
    state['hand_interacted'] = False
    count_level = _counting_level_for_current(state, puzzle, level)
    state['current_effective_level'] = count_level

    values = list(map(int, puzzle['cards']))
    images = _cards_to_images(values, theme)
    resp_payload = {
        'seq': seq + 1,
        'case_id': int(puzzle['case_id']),
        'question': ", ".join(map(str, values)),
        'values': values,
        'images': images,
        'help_disabled': bool(state.get('help_disabled')),
        'pool_done': bool(pstate['done'] or (pstate['mode'] in ('custom','competition') and pstate['index'] >= len(pstate['ids']))),
    }

    left = _competition_time_left(state)
    if left is not None and left > 0:
        resp_payload['time_left'] = left

    resp = make_response(jsonify(resp_payload))
    cookie_base = (sid.split(':', 1)[0]) if ':' in sid else sid
    if not request.cookies.get('session_id'):
        resp.set_cookie('session_id', cookie_base, max_age=1800)
    return resp

# web/app.py - Fix the check endpoint
@app.post('/api/check')
def api_check():
    sid = core.get_or_create_session_id(request)
    state = core.SESSIONS.setdefault(sid, core.default_state())
    gid = core.get_guest_id(request)
    if gid: state['guest_id'] = gid

    data = request.get_json(silent=True) or {}
    values = data.get('values') or []
    ans = (data.get('answer') or '').strip()

    cid = state.get('current_case_id')
    puzzle = core.PUZZLES_BY_ID.get(int(cid)) if cid else core.PUZZLES_BY_KEY.get(_values_key(values)) if values else None

    # "no solution" path counts as an attempt
    if ans.lower() in {"no solution","no sol","nosol","0","-1"}:
        sols_exist = bool(puzzle and puzzle.get('solutions'))
        core.bump_played_once(state, state.get('current_effective_level') or (puzzle and puzzle.get('level') or 'unknown'))
        state['hand_interacted'] = True
        if not sols_exist:
            core.bump_attempt(state, True)
            if cid:
                core._mark_case_status(state, cid, 'good')
                core._set_case_solved(state, cid)
            core.bump_solved(state, state.get('current_effective_level') or (puzzle and puzzle.get('level') or 'unknown'))
            return jsonify({'ok': True, 'value': None, 'kind': 'no-solution', 'stats': _stats_payload(state)})
        else:
            core.bump_attempt(state, False)
            in_comp = (core._pool(state).get('mode') == 'competition')
            if cid: core._mark_case_status(state, cid, 'attempt')
            return jsonify({
                'ok': False,
                'reason': "Incorrect — this case is solvable." + (" (Help is disabled in competition.)" if in_comp else " Try Help to see one."),
                'kind': 'solvable' if in_comp else 'help-available',
                'stats': _stats_payload(state)
            })

    try:
        value = safe_eval(ans)
    except Exception:
        core.bump_played_once(state, state.get('current_effective_level') or (puzzle and puzzle.get('level') or 'unknown'))
        core.bump_attempt(state, False)
        state['hand_interacted'] = True
        if cid: core._mark_case_status(state, cid, 'attempt')
        return jsonify({'ok': False, 'reason': 'Invalid expression', 'stats': _stats_payload(state)}), 200

    tol = 1e-6
    ok = abs(value - 24.0) < tol

    level_for_stats = state.get('current_effective_level') or (puzzle and puzzle.get('level') or 'unknown')
    core.bump_played_once(state, level_for_stats)
    core.bump_attempt(state, ok)
    state['hand_interacted'] = True

    if ok:
        if cid:
            core._mark_case_status(state, cid, 'good')
            core._set_case_solved(state, cid)
        core.bump_solved(state, level_for_stats)
        return jsonify({'ok': True, 'value': value, 'stats': _stats_payload(state)})
    else:
        if cid: core._mark_case_status(state, cid, 'attempt')
        return jsonify({'ok': False, 'value': value, 'reason': 'Not 24', 'stats': _stats_payload(state)})

@app.post('/api/help')
def api_help():
    sid = core.get_or_create_session_id(request)
    app.logger.debug(f"in check :session_id = {sid}")
    state = core.SESSIONS.setdefault(sid, core.default_state())
    gid = core.get_guest_id(request)
    if gid: state['guest_id'] = gid

    if state.get('help_disabled'):
        return jsonify({'has_solution': False, 'solutions': []}), 200

    data = request.get_json(silent=True) or {}
    values = data.get('values') or []
    show_all = bool(data.get('all'))
    cid = state.get('current_case_id')
    puzzle = core.PUZZLES_BY_ID.get(int(cid)) if cid else core.PUZZLES_BY_KEY.get(_values_key(values)) if values else None

    sols = list(puzzle.get('solutions') or []) if puzzle else []
    has = len(sols) > 0
    resp = {'has_solution': has, 'solutions': sols if show_all else (sols[:min(50, len(sols))] if has else [])}

    level_for_stats = state.get('current_effective_level') or (puzzle and puzzle.get('level') or 'unknown')
    core.bump_played_once(state, level_for_stats)
    core.bump_revealed(state)
    core.bump_help(state, all=show_all)  # NEW: track help usage
    state['hand_interacted'] = True

    if cid and has:
        core._mark_case_status(state, cid, 'revealed')
    resp['stats'] = _stats_payload(state)
    return jsonify(resp)

@app.post('/api/pool')
def api_pool():
    sid = core.get_or_create_session_id(request)
    app.logger.debug(f"in check :session_id = {sid}")
    state = core.SESSIONS.setdefault(sid, core.default_state())
    gid = core.get_guest_id(request)
    if gid: state['guest_id'] = gid

    data = request.get_json(silent=True) or {}
    mode = data.get('mode')
    ids = data.get('case_ids') or []
    duration = int(data.get('duration_sec') or 0)

    if mode not in ('custom','competition'):
        return jsonify({'error': 'mode must be custom or competition'}), 400
    if not ids:
        return jsonify({'error': f'No {mode} pool set'}), 400

    p = core._pool(state)
    p['mode'] = mode
    p['ids'] = [int(x) for x in ids]
    p['index'] = 0
    p['status'] = {str(cid): {'status':'unseen','attempts':0} for cid in p['ids']}
    p['score']  = {str(cid): 0 for cid in p['ids']}
    p['done'] = False

    if mode == 'competition' and duration > 0:
        state['competition_ends_at'] = time.time() + duration
        state['help_disabled'] = True
    else:
        state.pop('competition_ends_at', None)
        state['help_disabled'] = False

    # Optional: reset session-visible stats when a new pool starts
    state['stats'].update({
        'played': 0, 'solved': 0, 'revealed': 0, 'skipped': 0,
        'by_level': {},
        'help_single': 0, 'help_all': 0,
        'answer_attempts': 0, 'answer_correct': 0, 'answer_wrong': 0,
        'deal_swaps': 0,
    })
    state['recent_keys'] = []
    state['current_case_id'] = None
    state['current_effective_level'] = None
    state['hand_interacted'] = False

    return jsonify({'ok': True, 'pool_len': len(p['ids']), 'stats_reset': True})

@app.get('/api/pool_report')
def api_pool_report():
    sid = core.get_or_create_session_id(request)
    app.logger.debug(f"in check :session_id = {sid}")
    state = core.SESSIONS.setdefault(sid, core.default_state())
    gid = core.get_guest_id(request) or state.get('guest_id')

    st = state.get('stats', {})
    score_map, unfinished = core._pool_score(state)
    payload = {
        # classic
        'played': int(st.get('played', 0)),
        'solved': int(st.get('solved', 0)),
        'revealed': int(st.get('revealed', 0)),
        'skipped': int(st.get('skipped', 0)),
        'difficulty': st.get('by_level', {}),
        # new action counters
        'help_single': int(st.get('help_single',0)),
        'help_all': int(st.get('help_all',0)),
        'answer_attempts': int(st.get('answer_attempts',0)),
        'answer_correct': int(st.get('answer_correct',0)),
        'answer_wrong': int(st.get('answer_wrong',0)),
        'deal_swaps': int(st.get('deal_swaps',0)),

        'guest_id': gid,
        'pool_mode': core._pool(state).get('mode'),
        'pool_len': len(core._pool(state).get('ids') or []),
        'pool_score': score_map,
        'unfinished': unfinished,
        'pool_report': core._pool_report(state),
    }
    return jsonify({'ok': True, 'stats': payload})

@app.post('/api/restart')
def api_restart():
    sid = core.get_or_create_session_id(request)
    app.logger.debug(f"in restart :session_id = {sid}")  # <— add this line
    core.SESSIONS[sid] = core.default_state()
    return jsonify({'ok': True})

@app.post('/api/exit')
def api_exit():
    sid = core.get_or_create_session_id(request)
    app.logger.debug(f"in check :session_id = {sid}")
    state = core.SESSIONS.setdefault(sid, core.default_state())
    gid = core.get_guest_id(request) or state.get('guest_id')

    st = state.get('stats', {})
    score_map, unfinished = core._pool_score(state)
    p = core._pool(state)
    payload = {
        'played': int(st.get('played', 0)),
        'solved': int(st.get('solved', 0)),
        'revealed': int(st.get('revealed', 0)),
        'skipped': int(st.get('skipped', 0)),
        'difficulty': st.get('by_level', {}),

        # NEW: action counters
        'help_single': int(st.get('help_single',0)),
        'help_all': int(st.get('help_all',0)),
        'answer_attempts': int(st.get('answer_attempts',0)),
        'answer_correct': int(st.get('answer_correct',0)),
        'answer_wrong': int(st.get('answer_wrong',0)),
        'deal_swaps': int(st.get('deal_swaps',0)),

        'guest_id': gid,
        'pool_mode': p.get('mode'),
        'pool_len': len(p.get('ids') or []),
        'pool_score': score_map,
        'unfinished': unfinished,
        'pool_report': core._pool_report(state),
    }
    return jsonify({'ok': True, 'stats': payload})

if __name__ == '__main__':
    app.run(debug=True)

