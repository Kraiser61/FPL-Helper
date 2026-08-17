from typing import List, Dict, Tuple
from dataclasses import dataclass

@dataclass
class SquadPlayer:
    id: int
    element_type: int
    xp: float
    chance_of_playing: float
    is_locked_starter: bool # 'no_bench' lock

@dataclass
class LineupResult:
    starting_11: List[int]
    bench_order: List[int] # index 0 is GK (slot 12), then 1-3 (slots 13-15)
    formation: str
    total_xp: float

class LineupSelector:
    """
    Selects the optimal starting 11 and bench order from a 15-player squad.
    Based on constraints in Section 3.4.
    """
    
    VALID_FORMATIONS = [
        (3, 4, 3), (3, 5, 2), (4, 3, 3), (4, 4, 2), 
        (4, 5, 1), (5, 3, 2), (5, 4, 1), (5, 2, 3)
    ]

    def __init__(self, squad: List[SquadPlayer]):
        self.squad = squad or []
        
    def select_optimal_lineup(self) -> LineupResult:
        if not self.squad:
            return LineupResult(starting_11=[], bench_order=[], formation="0-0-0", total_xp=0.0)

        # Separate GKs and outfield players
        gks = [p for p in self.squad if p.element_type == 1]
        defs = [p for p in self.squad if p.element_type == 2]
        mids = [p for p in self.squad if p.element_type == 3]
        fwds = [p for p in self.squad if p.element_type == 4]
        
        # Sort by XP descending
        gks.sort(key=lambda p: p.xp, reverse=True)
        defs.sort(key=lambda p: p.xp, reverse=True)
        mids.sort(key=lambda p: p.xp, reverse=True)
        fwds.sort(key=lambda p: p.xp, reverse=True)
        
        best_xp = -1.0
        best_lineup = []
        best_formation = ""
        best_bench = []
        
        # Determine Starting & Bench GK
        starting_gk = next((gk for gk in gks if gk.is_locked_starter), gks[0]) if gks else None
        bench_gk = (gks[1] if len(gks) > 1 and starting_gk == gks[0] else gks[0]) if len(gks) > 1 else None
        
        # Pre-select locked outfield players
        locked_defs = [p for p in defs if p.is_locked_starter]
        locked_mids = [p for p in mids if p.is_locked_starter]
        locked_fwds = [p for p in fwds if p.is_locked_starter]
        
        for def_req, mid_req, fwd_req in self.VALID_FORMATIONS:
            # Check if lock constraints violate formation
            if len(locked_defs) > def_req or len(locked_mids) > mid_req or len(locked_fwds) > fwd_req:
                continue
                
            # Select players for this formation
            selected_defs = self._select_top_n(defs, def_req, locked_defs)
            selected_mids = self._select_top_n(mids, mid_req, locked_mids)
            selected_fwds = self._select_top_n(fwds, fwd_req, locked_fwds)
            
            current_11 = ([starting_gk] if starting_gk else []) + selected_defs + selected_mids + selected_fwds
            current_xp = sum(p.xp for p in current_11)
            
            if current_xp > best_xp:
                best_xp = current_xp
                best_lineup = current_11
                best_formation = f"{len(selected_defs)}-{len(selected_mids)}-{len(selected_fwds)}"
                
                # Determine Bench Order: Bench GK MUST ALWAYS BE FIRST (Index 0 / Slot 12)
                benched_outfield = [p for p in self.squad if p.element_type != 1 and p not in current_11]
                # Sort bench outfield players by XP descending
                benched_outfield.sort(key=lambda p: p.xp, reverse=True)
                best_bench = ([bench_gk] if bench_gk else []) + benched_outfield

        return LineupResult(
            starting_11=[p.id for p in best_lineup],
            bench_order=[p.id for p in best_bench],
            formation=best_formation or "3-4-3",
            total_xp=round(best_xp, 2)
        )
        
    def _select_top_n(self, players: List[SquadPlayer], n: int, locked: List[SquadPlayer]) -> List[SquadPlayer]:
        selected = list(locked)
        needed = n - len(selected)
        
        for p in players:
            if needed == 0:
                break
            if p not in selected:
                selected.append(p)
                needed -= 1
        return selected
