import random
from collections import deque, Counter
from typing import List, Dict, Any, Optional, Tuple

from .card_utils import get_values
from .complexity import score_complexity, SIMPLE_THRESHOLD, HARD_THRESHOLD

def has_solution(p: Dict[str, Any]) -> bool:
    return bool(p.get("solutions"))

def combo_key_numeric(values: List[int]) -> str:
    return "-".join(map(str, sorted(values)))

def puzzle_has_simple_solution(p: Dict[str, Any]) -> bool:
    sols = p.get("solutions") or []
    if not sols: return False
    return min(score_complexity(s) for s in sols) <= SIMPLE_THRESHOLD

def puzzle_has_hard_solution(p: Dict[str, Any]) -> bool:
    sols = p.get("solutions") or []
    if not sols: return False
    return max(score_complexity(s) for s in sols) >= HARD_THRESHOLD

def all_values_unique(values: List[int]) -> bool:
    c = Counter(values)
    return all(v == 1 for v in c.values())

class QuestionPicker:
    def __init__(self, puzzles: List[Dict[str, Any]], recent_window: int = 60,
                 medium_no_sol_target: float = 0.10):
        self.puzzles = puzzles
        self.recent = deque(maxlen=recent_window)
        self.total_served = 0
        self.no_sol_served = 0
        self.medium_no_sol_target = medium_no_sol_target
        self.index = []
        for p in puzzles:
            vals = get_values(p)
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
                print(f"find not recent used cards {str(it)} in _pick_from")
                return self._serve(it)
        print(f"find not recent used cards NONE--0 in _pick_from")
        return None

        #new

    #new
    def pick2(self, level="easy"):
        """Select a puzzle matching the requested difficulty level"""
        print(f"inside pick, Picker request level={level}")
    
        level = level.lower()
        easy_pool = []
        med_pool = []
        hard_pool = []
        no_sol_pool = []
    
        for (p, vals, key) in self.index:
            lvl = str(p.get("level","")).strip().lower()  # Normalize level case
            has_sol = has_solution(p)
    
            if not has_sol:
                no_sol_pool.append((p, vals, key))
            elif lvl == "easy":
                easy_pool.append((p, vals, key))
            elif lvl == "medium":
                med_pool.append((p, vals, key))
            elif lvl == "hard":
                hard_pool.append((p, vals, key))  # Removed unique_vals check
    
        print(f"Hard pool size before filtering: {len(hard_pool)}")
    
        if level in ("easy","1"):
            pool = [it for it in easy_pool if self._not_recent(it[2])]
            return self._pick_from(pool)
    
        if level in ("medium","2"):
                med_pool.append((p, vals, key))
                if has_sol and puzzle_has_simple_solution(p):
                    med_pool_with_simple.append((p, vals, key))
                if has_sol and puzzle_has_hard_solution(p):
                    med_pool_with_hard.append((p, vals, key))
            # ... (keep existing medium logic)
    
        if level in ("hard","3"):
            print(f"Final hard pool size: {len(hard_pool)}")
            return self._pick_from([it for it in hard_pool if self._not_recent(it[2])])
    
        return None
#end

    def pick(self, level="easy"):
        """Select a puzzle matching the requested difficulty level """

        print(f"inside pick, Picker request level={level}")

        level = level.lower()
        easy_pool = []
        med_pool_with_simple = []
        med_pool = []
        hard_pool = []
        med_pool_with_hard = []
        no_sol_pool = []

        for (p, vals, key) in self.index:
            lvl = str(p.get("level","")).strip()
            #lvl = str(p.get("level","")).strip().lower()  # Normalize level case
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
                #if unique_vals:
                hard_pool.append((p, vals, key))

        #print(f"after load, hard pool len={len(easy_pool)}; {len(med_pool)}; {len(hard_pool)}")
        if level in ("easy","1"):
            print("Q picked from easy pool")
            pool = [it for it in (easy_pool + med_pool_with_simple) if self._not_recent(it[2])]
            return self._pick_from(pool)

        if level in ("medium","2"):
            print("Q picked from medium pool")
            need_ratio = self.no_sol_served / self.total_served if self.total_served else 0.0
            allow_no_sol = need_ratio < self.medium_no_sol_target
            med_only = [it for it in med_pool if has_solution(it[0])]
            candidates = med_only + (no_sol_pool if allow_no_sol else [])
            candidates = [it for it in candidates if self._not_recent(it[2])]
            return self._pick_from(candidates)

        if level in ("hard","3"):
            print(f"hard pool len={len(hard_pool)}")
            print("Q picked from hard pool")
            #hard_like = hard_pool + [it for it in med_pool_with_hard if all_values_unique(it[1])]
            hard_like = hard_pool 
            if not hard_like:
                hard_like = med_pool_with_hard
            hard_like = [it for it in hard_like if self._not_recent(it[2])]
            return self._pick_from(hard_like)

        print("Q picked None")
        return None

