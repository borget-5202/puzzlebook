# picker.py
import random
from collections import deque, Counter
from typing import List, Dict, Any, Optional, Tuple
from card_utils import get_values
from card_utils import rank_to_value, value_to_rank, get_values, get_ranks_for_display
from complexity import score_complexity, SIMPLE_THRESHOLD, HARD_THRESHOLD



def values_from_puzzle(p):
    # values field preferred, fallback to rank mapping you already have
    #from your_module import rank_to_value  # or adjust import path
    if "values" in p and p["values"]:
        return [int(x) for x in p["values"]]
    return [rank_to_value(r) for r in p.get("cards", [])]

def has_solution(p):
    return bool(p.get("solutions"))

def combo_key_numeric(values: List[int]) -> str:
    # ignore suits; stable key for de-dup
    return "-".join(map(str, sorted(values)))

def puzzle_has_simple_solution(p) -> bool:
    sols = p.get("solutions") or []
    if not sols:
        return False
    best = min(score_complexity(s) for s in sols)
    return best <= SIMPLE_THRESHOLD

def puzzle_has_hard_solution(p) -> bool:
    sols = p.get("solutions") or []
    if not sols:
        return False
    worst = max(score_complexity(s) for s in sols)
    return worst >= HARD_THRESHOLD

def all_values_unique(values: List[int]) -> bool:
    c = Counter(values)
    return all(v == 1 for v in c.values())

class QuestionPicker:
    """
    Maintains session state:
      - target no-solution ratio for medium
      - “recent N” memory to avoid repeats
      - hard level unique-values rule
      - easy: only solved; plus medium-with-simple-solution
      - hard: hard + medium-with-hard-solution
    """
    def __init__(self, puzzles: List[Dict[str, Any]], recent_window: int = 60,
                 medium_no_sol_target: float = 0.10):
        self.puzzles = puzzles
        self.recent = deque(maxlen=recent_window)
        self.total_served = 0
        self.no_sol_served = 0
        self.medium_no_sol_target = medium_no_sol_target
        # Pre-index
        self.index = []
        for p in puzzles:
            vals = values_from_puzzle(p)
            self.index.append((p, vals, combo_key_numeric(vals)))

    def _not_recent(self, key: str) -> bool:
        return key not in self.recent

    def _serve(self, item) -> Dict[str, Any]:
        p, vals, key = item
        self.recent.append(key)
        self.total_served += 1
        if not has_solution(p):
            self.no_sol_served += 1
        return p

    def _pick_from(self, pool: List[Tuple[Dict[str,Any], List[int], str]]) -> Optional[Dict[str,Any]]:
        random.shuffle(pool)
        for it in pool:
            if self._not_recent(it[2]):
                return self._serve(it)
        return None

    def pick(self, level: str) -> Optional[Dict[str, Any]]:
        level = level.lower()
        # Build candidate pools based on rules
        easy_pool = []
        med_pool_with_simple = []
        med_pool = []
        hard_pool = []
        med_pool_with_hard = []
        no_sol_pool = []

        for (p, vals, key) in self.index:
            lvl = str(p.get("level","")).strip()
            has_sol = has_solution(p)
            unique_vals = all_values_unique(vals)

            if not has_sol:
                no_sol_pool.append((p, vals, key))
            if lvl == "Easy" and has_sol:
                easy_pool.append((p, vals, key))
            if lvl == "Medium":
                med_pool.append((p, vals, key))
                if has_sol and puzzle_has_simple_solution(p):
                    med_pool_with_simple.append((p, vals, key))
                if has_sol and puzzle_has_hard_solution(p):
                    med_pool_with_hard.append((p, vals, key))
            if lvl == "Hard":
                # enforce unique numbers for hard; if your dataset already ensures this, keep anyway
                if unique_vals:
                    hard_pool.append((p, vals, key))

        if level in ("easy","1"):
            # easy = all solved + (medium with simple solution)
            pool = easy_pool + med_pool_with_simple
            pool = [it for it in pool if self._not_recent(it[2])]
            return self._pick_from(pool)

        if level in ("medium","2"):
            # medium = medium + controlled no-solution <= 10% overall session
            # decide whether to allow a no-solution now
            need_ratio = self.no_sol_served / self.total_served if self.total_served else 0.0
            allow_no_sol = need_ratio < self.medium_no_sol_target
            med_only = [it for it in med_pool if has_solution(it[0])]
            candidates = med_only
            if allow_no_sol:
                candidates = candidates + no_sol_pool
            candidates = [it for it in candidates if self._not_recent(it[2])]
            return self._pick_from(candidates)

        if level in ("hard","3"):
            # hard = hard (unique values) + medium with hard solution (unique preferred)
            hard_like = hard_pool + [it for it in med_pool_with_hard if all_values_unique(it[1])]
            if not hard_like:
                # fallback: allow med with hard solution even if duplicates exist
                hard_like = med_pool_with_hard
            hard_like = [it for it in hard_like if self._not_recent(it[2])]
            return self._pick_from(hard_like)

        return None

