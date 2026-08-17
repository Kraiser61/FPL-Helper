import pulp
from typing import List, Dict, Tuple, Set, Optional, Any
from dataclasses import dataclass, field
from utils.logger import app_logger

@dataclass
class PlayerAnalysis:
    """Carries complete strategic metrics for a single player."""
    player_id: int
    web_name: str
    element_type: int
    team_id: int
    now_cost: int
    selling_price: int
    in_squad: bool
    is_locked: bool
    
    # Composite xP
    xp_next_gw: float
    xp_horizon: float              # N-GW total
    w_form: float
    p_availability: float
    p_card_risk: float
    
    # Price
    price_rise_prob: float
    price_fall_prob: float
    predicted_price_gain: float    # £m value gain/loss
    
    # Ownership
    ownership: float               # selected_by_percent
    eo: float                      # effective ownership
    template_score: float
    differential_score: float
    eo_risk: float                 # risk penalty if missing from squad
    
    # Fixture info
    fixture_string: str
    avg_fdr: float
    
    # Status
    yellow_cards: int
    news: str
    status: str
    xgi_status: str = "Ölçülü"
    
    # Haul / Boom Metrics
    boom_prob: float = 0.0
    boom_index: float = 0.0
    next_opponent_id: int = -1

@dataclass
class ScenarioResult:
    """Output structure of a single optimization scenario."""
    name: str                      # 'low_risk', 'high_risk'
    display_name: str
    transfers_out: List[PlayerAnalysis]
    transfers_in: List[PlayerAnalysis]
    optimal_starting_11: List[PlayerAnalysis]
    optimal_bench: List[PlayerAnalysis]
    formation: str
    captain: Optional[PlayerAnalysis]
    vice_captain: Optional[PlayerAnalysis]
    net_xp_gain: float
    hit_cost: int
    budget_remaining: float
    objective_value: float
    confidence_score: int = 85     # % Model Confidence Index for current GW
    reasons: List[str] = field(default_factory=list)

# Backward-compatibility alias
PlayerDTO = PlayerAnalysis

def generate_candidate_pool(
    all_players: List[PlayerAnalysis],
    current_itb: float,
    max_pool_size: int = 220,
    mandatory_ids: Optional[Set[int]] = None
) -> List[PlayerAnalysis]:
    """
    Filters and prunes player pool before MILP solver execution:
    - GK Budget Filter: If ITB <= 1.0m, filter out GKs with cost > 5.5m (£55).
    - Cheap DEF Guarantee: Retain top 3 cheapest DEFs with cost <= 4.5m (£45).
    - Premium Cap: Limit players with cost >= 10.0m (£100) to top 4 highest xp_horizon.
    - Pool Truncation: Sort remaining by xp_horizon and truncate total pool <= max_pool_size (220).
    - Mandatory Preservation: Players in mandatory_ids (current squad, locks, must-buy/sell) are never discarded.
    """
    if not all_players:
        return []

    mandatory_ids = mandatory_ids or set()

    def _cost_in_m(p) -> float:
        cost = getattr(p, 'now_cost', 0)
        return cost / 10.0 if cost > 15 else float(cost)

    def _xp_val(p) -> float:
        return getattr(p, 'xp_horizon', getattr(p, 'xp_next_gw', 0.0))

    gk_limit = 5.5 if current_itb <= 1.0 else 15.0

    mandatory_players = [p for p in all_players if p.player_id in mandatory_ids]
    non_mandatory = [p for p in all_players if p.player_id not in mandatory_ids]

    cheap_defs = []
    premiums = []
    others = []

    for p in non_mandatory:
        cost_m = _cost_in_m(p)
        # GK filter
        if p.element_type == 1 and cost_m > gk_limit:
            continue

        if p.element_type == 2 and cost_m <= 4.5:
            cheap_defs.append(p)
        elif cost_m >= 10.0:
            premiums.append(p)
        else:
            others.append(p)

    cheap_defs.sort(key=_xp_val, reverse=True)
    required_cheap_defs = cheap_defs[:3]
    remaining_cheap_defs = cheap_defs[3:]

    premiums.sort(key=_xp_val, reverse=True)
    allowed_premiums = premiums[:4]

    remaining_pool = remaining_cheap_defs + others + premiums[4:]
    remaining_pool.sort(key=_xp_val, reverse=True)

    candidate_pool = list(mandatory_players)
    mandatory_set = {p.player_id for p in mandatory_players}

    for p in required_cheap_defs + allowed_premiums:
        if p.player_id not in mandatory_set:
            candidate_pool.append(p)
            mandatory_set.add(p.player_id)

    slots_left = max(0, max_pool_size - len(candidate_pool))
    for p in remaining_pool:
        if slots_left <= 0:
            break
        if p.player_id not in mandatory_set:
            candidate_pool.append(p)
            mandatory_set.add(p.player_id)
            slots_left -= 1

    return candidate_pool


class MasterOptimizer:
    """
    Advanced Mixed-Integer Linear Programming (MILP) Optimizer using PuLP.
    Implements Top 10k Elite Strategies & FPL 2024/25 5-FT Stacking Rules:
    - Multi-Gameweek Lookahead (3-5 GW horizon)
    - 5 Free Transfer Roll Bonus (+2.2 xP value per banked FT, up to 5 FTs)
    - Dynamic Weight Adaptation (Alpha, Beta, Gamma)
    - User Constraint Overrides with Relaxation Hierarchy
    """

    ROLL_FT_BONUS = 2.2  # xP equivalent bonus for banking a free transfer under 5-FT rules
    MAX_FT_CAP = 5       # 2024/25 FPL rule: can accumulate up to 5 FTs

    def __init__(
        self,
        analyses: Dict[int, PlayerAnalysis],
        squad_ids: Set[int],
        bank: int,
        free_transfers: int,
        current_gw: int = 1,
        overall_rank: Optional[int] = None,
        is_preseason: bool = False
    ):
        self.analyses = analyses
        self.squad_ids = squad_ids
        self.bank = bank or 0
        self.free_transfers = min(self.MAX_FT_CAP, max(1, free_transfers if free_transfers is not None else 1))
        self.current_gw = current_gw
        self.overall_rank = overall_rank
        self.is_preseason = is_preseason
        
        self.current_squad = [a for pid, a in analyses.items() if pid in squad_ids]
        squad_selling_value = sum(a.selling_price for a in self.current_squad)
        self.total_budget = squad_selling_value + self.bank

    @classmethod
    def get_dynamic_weights(cls, risk_profile: str, current_gw: int, overall_rank: Optional[int] = None) -> Tuple[float, float, float]:
        """
        Calculates dynamic weights (alpha: price gain, beta: EO risk, gamma: hit penalty).
        """
        base = {
            "safe":       (0.4, 1.8, 8.0),
            "balanced":   (0.5, 1.0, 6.5),
            "aggressive": (0.3, 0.4, 4.5),
        }
        alpha, beta, gamma = base.get(risk_profile.lower(), base["balanced"])

        if current_gw <= 5:
            alpha *= 1.3
        elif current_gw >= 33:
            alpha *= 0.2
            gamma *= 1.5

        if overall_rank and overall_rank < 100_000:
            beta *= 1.4
            gamma *= 1.2
        elif overall_rank and overall_rank > 1_000_000:
            beta *= 0.4
            gamma *= 0.8

        return (round(alpha, 2), round(beta, 2), round(gamma, 2))

    def apply_user_overrides(
        self,
        prob: pulp.LpProblem,
        x_vars: Dict[int, pulp.LpVariable],
        locks: Set[int],
        must_sell: Set[int],
        must_buy: Set[int],
        blacklist: Set[int],
        relaxation_level: int = 0
    ) -> List[str]:
        """
        Applies user override constraints with hierarchical relaxation.
        Relaxation levels:
        0: No relaxation (All strict)
        1: Relax Blacklist
        2: Relax Blacklist + Must-Buy
        3: Relax Blacklist + Must-Buy + No-Sell Lock
        4: Relax All (Only FPL basic rules apply)
        """
        applied = []
        
        # Priority 2: Must-Sell (Relaxed last, at level 4)
        if relaxation_level < 4:
            for pid in must_sell:
                if pid in x_vars:
                    prob += x_vars[pid] == 0, f"UserMustSell_{pid}"
                    applied.append(f"Must-Sell:{pid}")

        # Priority 3: No-Sell Lock (Relaxed at level 3)
        if relaxation_level < 3:
            for pid in locks:
                if pid in x_vars:
                    prob += x_vars[pid] == 1, f"UserLock_{pid}"
                    applied.append(f"No-Sell:{pid}")

        # Priority 4: Must-Buy (Relaxed at level 2)
        if relaxation_level < 2:
            for pid in must_buy:
                if pid in x_vars:
                    prob += x_vars[pid] == 1, f"UserMustBuy_{pid}"
                    applied.append(f"Must-Buy:{pid}")

        # Priority 5: Blacklist (Relaxed FIRST, at level 1)
        if relaxation_level < 1:
            for pid in blacklist:
                if pid in x_vars:
                    prob += x_vars[pid] == 0, f"UserBlacklist_{pid}"
                    applied.append(f"Blacklist:{pid}")
                    
        return applied

    def solve_with_relaxation(
        self, 
        scenario_name: str, 
        alpha: float, 
        beta: float, 
        gamma: float,
        locks: Set[int] = None,
        must_sell: Set[int] = None,
        must_buy: Set[int] = None,
        blacklist: Set[int] = None,
        display_name: str = "Hamle Önerisi"
    ) -> ScenarioResult:
        """
        Attempts to solve the scenario, relaxing user constraints sequentially if infeasible.
        """
        locks = set(locks) if locks else set()
        must_sell = set(must_sell) if must_sell else set()
        must_buy = set(must_buy) if must_buy else set()
        blacklist = set(blacklist) if blacklist else set()
        
        # Integrate native locks
        for p in self.current_squad:
            if p.is_locked:
                locks.add(p.player_id)
                
        for relaxation_level in range(5):
            result = self._solve_scenario_inner(
                scenario_name, alpha, beta, gamma,
                locks, must_sell, must_buy, blacklist,
                relaxation_level, display_name
            )
            
            if result is not None:
                if relaxation_level > 0:
                    relaxed_rules = []
                    if relaxation_level >= 1: relaxed_rules.append("Kara Liste (Blacklist)")
                    if relaxation_level >= 2: relaxed_rules.append("Hedef Oyuncu (Must-Buy)")
                    if relaxation_level >= 3: relaxed_rules.append("Kilitli Oyuncu (No-Sell)")
                    if relaxation_level >= 4: relaxed_rules.append("Satış Listesi (Must-Sell)")
                    
                    result.reasons.append(f"Kisit Gevsetme Uygulandi: Cozumsuzluk nedeniyle {', '.join(relaxed_rules)} esnetildi.")
                return result
                
        # If all fail (FPL base rules are infeasible)
        app_logger.warning("MasterOptimizer: Model entirely infeasible even after all relaxations.")
        return self._empty_fallback(scenario_name, display_name)

    def _solve_scenario_inner(
        self, 
        scenario_name: str, 
        alpha: float, 
        beta: float, 
        gamma: float,
        locks: Set[int],
        must_sell: Set[int],
        must_buy: Set[int],
        blacklist: Set[int],
        relaxation_level: int,
        display_name: str
    ) -> Optional[ScenarioResult]:
        
        if not self.current_squad and not self.is_preseason:
            app_logger.warning("MasterOptimizer: No current squad provided.")
            return None

        pos_limits = {1: 2, 2: 5, 3: 5, 4: 3}
        max_players = 15

        all_players_raw = list(self.analyses.values())
        mandatory_ids = set(self.squad_ids) | set(locks) | set(must_sell) | set(must_buy)
        itb_in_m = self.bank / 10.0 if self.bank > 15 else float(self.bank)
        if self.is_preseason:
            itb_in_m = 100.0  # Bypass candidate pool strict filters during preseason
        all_players = generate_candidate_pool(
            all_players_raw,
            current_itb=itb_in_m,
            max_pool_size=220,
            mandatory_ids=mandatory_ids
        )
        player_ids = [p.player_id for p in all_players]

        best_result = None
        best_obj = -1e9

        max_k = 15 if self.is_preseason else (3 if scenario_name != "safe" else min(1, self.free_transfers))
        # Ensure max_k is at least len(must_sell) or len(must_buy) if we are enforcing them
        if not self.is_preseason and relaxation_level < 4:
            required_k = max(len(must_sell) if relaxation_level < 4 else 0, len(must_buy) if relaxation_level < 2 else 0)
            max_k = max(max_k, required_k)
            max_k = min(15, max_k) # Cannot exceed 15

        for k in range(0, max_k + 1):
            prob = pulp.LpProblem(f"FPL_Master_{scenario_name}_k{k}_r{relaxation_level}", pulp.LpMaximize)
            x_vars = pulp.LpVariable.dicts("x", player_ids, cat='Binary')
            s_vars = pulp.LpVariable.dicts("s", player_ids, cat='Binary')
            c_vars = pulp.LpVariable.dicts("c", player_ids, cat='Binary')

            roll_ft_val = (self.ROLL_FT_BONUS * min(self.MAX_FT_CAP, self.free_transfers + 1)) if (k == 0 and not self.is_preseason) else 0.0

            # Weekly optimization: 100% focused on immediate Next GW expected points
            # Preseason optimization: Use xp_horizon to build a robust 4-5 week squad
            prob += (
                pulp.lpSum([(p.xp_horizon if self.is_preseason else p.xp_next_gw) * s_vars[p.player_id] for p in all_players]) +
                pulp.lpSum([((p.xp_horizon if self.is_preseason else p.xp_next_gw) + (p.boom_index * 0.35)) * c_vars[p.player_id] for p in all_players]) +
                alpha * pulp.lpSum([p.predicted_price_gain * x_vars[p.player_id] for p in all_players]) -
                beta * pulp.lpSum([p.eo_risk * (1.0 - x_vars[p.player_id]) for p in all_players]) +
                roll_ft_val
            ), "Master_Objective"

            prob += pulp.lpSum([x_vars[pid] for pid in player_ids]) == max_players, "Total_15"

            # 1. Starters & Captain basic rules
            for pid in player_ids:
                prob += s_vars[pid] <= x_vars[pid], f"StartInSquad_{pid}"
                prob += c_vars[pid] <= s_vars[pid], f"CapInStart_{pid}"

            prob += pulp.lpSum([s_vars[pid] for pid in player_ids]) == 11, "Total_Starters"
            prob += pulp.lpSum([c_vars[pid] for pid in player_ids]) == 1, "Total_Captain"

            # 2. Positional Limits (Squad & Starting 11)
            prob += pulp.lpSum([x_vars[p.player_id] for p in all_players if p.element_type == 1]) == 2, "Squad_Pos_1"
            prob += pulp.lpSum([s_vars[p.player_id] for p in all_players if p.element_type == 1]) == 1, "Start_Pos_1"
            
            prob += pulp.lpSum([x_vars[p.player_id] for p in all_players if p.element_type == 2]) == 5, "Squad_Pos_2"
            prob += pulp.lpSum([s_vars[p.player_id] for p in all_players if p.element_type == 2]) >= 3, "Start_Pos_2_Min"
            prob += pulp.lpSum([s_vars[p.player_id] for p in all_players if p.element_type == 2]) <= 5, "Start_Pos_2_Max"
            
            prob += pulp.lpSum([x_vars[p.player_id] for p in all_players if p.element_type == 3]) == 5, "Squad_Pos_3"
            prob += pulp.lpSum([s_vars[p.player_id] for p in all_players if p.element_type == 3]) >= 2, "Start_Pos_3_Min"
            prob += pulp.lpSum([s_vars[p.player_id] for p in all_players if p.element_type == 3]) <= 5, "Start_Pos_3_Max"
            
            prob += pulp.lpSum([x_vars[p.player_id] for p in all_players if p.element_type == 4]) == 3, "Squad_Pos_4"
            prob += pulp.lpSum([s_vars[p.player_id] for p in all_players if p.element_type == 4]) >= 1, "Start_Pos_4_Min"
            prob += pulp.lpSum([s_vars[p.player_id] for p in all_players if p.element_type == 4]) <= 3, "Start_Pos_4_Max"

            teams = set(p.team_id for p in all_players)
            for team_id in teams:
                prob += pulp.lpSum([x_vars[p.player_id] for p in all_players if p.team_id == team_id]) <= 3, f"Team_{team_id}"
                # 3a. Covariance Constraint: Max 2 DEF/GKP from same team in starting 11
                prob += pulp.lpSum([s_vars[p.player_id] for p in all_players if p.team_id == team_id and p.element_type in (1, 2)]) <= 2, f"Max2DefStart_Team_{team_id}"

            # 3b. Anti-Hedging Constraint: Captain vs Opponent Defense
            for p in all_players:
                opp_id = p.next_opponent_id
                if opp_id > 0:
                    opp_defenders = [dp for dp in all_players if dp.team_id == opp_id and dp.element_type in (1, 2)]
                    for dp in opp_defenders:
                        prob += s_vars[dp.player_id] + c_vars[p.player_id] <= 1, f"AntiHedge_{p.player_id}_vs_{dp.player_id}"

            prob += pulp.lpSum([
                x_vars[p.player_id] * (p.now_cost if not p.in_squad else p.selling_price)
                for p in all_players
            ]) <= self.total_budget, "Budget_Limit"

            gks_over_50 = [p for p in all_players if p.element_type == 1 and p.now_cost > 50]
            if gks_over_50:
                prob += pulp.lpSum([x_vars[p.player_id] for p in gks_over_50]) <= 0, "GK_Budget_Cap_50m"

            defs_fp = [p for p in all_players if p.element_type == 2 and p.now_cost <= 45]
            if len(defs_fp) >= 3:
                prob += pulp.lpSum([x_vars[p.player_id] for p in defs_fp]) >= 3, "DEF_Budget_Value_Min3"

            attackers = [p for p in all_players if p.element_type in (3, 4)]
            if attackers:
                prob += pulp.lpSum([
                    x_vars[p.player_id] * (p.now_cost if not p.in_squad else p.selling_price)
                    for p in attackers
                ]) >= 0.60 * self.total_budget, "Attack_Budget_Min_60Percent"

            if not self.is_preseason:
                prob += pulp.lpSum([x_vars[p.player_id] for p in all_players if not p.in_squad]) == k, "Exact_Transfers"

            # Apply User Overrides with the given relaxation level
            self.apply_user_overrides(prob, x_vars, locks, must_sell, must_buy, blacklist, relaxation_level)

            prob.solve(pulp.PULP_CBC_CMD(msg=0))

            if pulp.LpStatus[prob.status] == 'Optimal':
                selected_ids = {pid for pid in player_ids if x_vars[pid].value() == 1.0}
                
                players_in = [self.analyses[pid] for pid in selected_ids if not self.analyses[pid].in_squad]
                players_out = [p for p in self.current_squad if p.player_id not in selected_ids]

                hit_cost = 0 if self.is_preseason else max(0, (k - self.free_transfers) * 4)
                raw_obj = pulp.value(prob.objective) or 0.0
                adjusted_obj = raw_obj - (gamma * (hit_cost / 4.0))

                base_squad_xp = sum(p.xp_horizon for p in self.current_squad) if self.current_squad else 0.0
                new_squad_xp = sum(self.analyses[pid].xp_horizon for pid in selected_ids)
                net_xp_gain = new_squad_xp - base_squad_xp - hit_cost

                cost_in = sum(p.now_cost for p in players_in)
                revenue_out = sum(p.selling_price for p in players_out)
                budget_remaining = (self.bank + revenue_out - cost_in) / 10.0

                squad_15 = [self.analyses[pid] for pid in selected_ids]
                starters, bench, formation, captain, vice_captain = self._select_optimal_11_and_bench(squad_15)

                if adjusted_obj > best_obj:
                    best_obj = adjusted_obj
                    
                    avg_p_avail = (sum(p.p_availability for p in starters) / 11.0) if starters else 1.0
                    if scenario_name == "low_risk":
                        conf = int(min(96, max(75, (avg_p_avail * 90.0) - (hit_cost * 2))))
                    else:
                        conf = int(min(88, max(60, (avg_p_avail * 80.0) - (hit_cost * 3))))

                    reasons_list = []
                    for p in players_in:
                        if getattr(p, 'xgi_status', 'Ölçülü') != 'Ölçülü':
                            reasons_list.append(f"{p.web_name}: {p.xgi_status}")
                    if k == 0 and not self.is_preseason:
                        next_ft_cnt = min(self.MAX_FT_CAP, self.free_transfers + 1)
                        reasons_list.append(f"FT Saklama Stratejisi: Gelecek haftaya {next_ft_cnt} Serbest Transfer devredilecek (Max 5 FT kuralı).")

                    best_result = ScenarioResult(
                        name=scenario_name,
                        display_name=display_name,
                        transfers_out=players_out,
                        transfers_in=players_in,
                        optimal_starting_11=starters,
                        optimal_bench=bench,
                        formation=formation,
                        captain=captain,
                        vice_captain=vice_captain,
                        net_xp_gain=round(net_xp_gain, 2),
                        hit_cost=hit_cost,
                        budget_remaining=round(budget_remaining, 2),
                        objective_value=round(adjusted_obj, 2),
                        confidence_score=conf,
                        reasons=reasons_list
                    )

        if best_result:
            if not self.is_preseason and best_result.transfers_in:
                if best_result.net_xp_gain < 1.5:
                    user_forced = (len(must_sell) > 0 and relaxation_level < 4) or (len(must_buy) > 0 and relaxation_level < 2)
                    if not user_forced:
                        best_result.transfers_in = []
                        best_result.transfers_out = []
                        best_result.net_xp_gain = 0.0
                        next_ft_cnt = min(self.MAX_FT_CAP, self.free_transfers + 1)
                        best_result.reasons = [f"Transfer karlı görülmedi (Net kazanç < +1.5 xP). Gelecek haftaya {next_ft_cnt} FT devrediliyor."]
                    else:
                        best_result.reasons.append("Kullanıcı Zorunlu Transfer Kısıtı nedeniyle xP eşiği (1.5) göz ardı edildi.")
            return best_result

        return None

    def _select_optimal_11_and_bench(self, squad_15: List[PlayerAnalysis]) -> Tuple[List[PlayerAnalysis], List[PlayerAnalysis], str, Optional[PlayerAnalysis], Optional[PlayerAnalysis]]:
        gkps = [p for p in squad_15 if p.element_type == 1]
        defs = [p for p in squad_15 if p.element_type == 2]
        mids = [p for p in squad_15 if p.element_type == 3]
        fwds = [p for p in squad_15 if p.element_type == 4]

        def _fit_score(p: PlayerAnalysis) -> float:
            # Floor protection: slightly discount players with low availability (<80%) to prefer fit starters
            avail_factor = 1.0 if p.p_availability >= 0.85 else max(0.40, p.p_availability)
            return p.xp_next_gw * avail_factor

        gkps.sort(key=_fit_score, reverse=True)
        defs.sort(key=_fit_score, reverse=True)
        mids.sort(key=_fit_score, reverse=True)
        fwds.sort(key=_fit_score, reverse=True)

        starter_gkp = [gkps[0]] if gkps else []
        bench_gkp = [gkps[1]] if len(gkps) > 1 else []

        best_starters = []
        best_xp = -1.0
        best_formation = "3-5-2"

        valid_formations = [(3, 5, 2), (3, 4, 3), (4, 4, 2), (4, 5, 1), (4, 3, 3), (5, 3, 2), (5, 4, 1), (5, 2, 3)]
        
        for d_cnt, m_cnt, f_cnt in valid_formations:
            if len(defs) >= d_cnt and len(mids) >= m_cnt and len(fwds) >= f_cnt:
                s_defs = defs[:d_cnt]
                s_mids = mids[:m_cnt]
                s_fwds = fwds[:f_cnt]
                
                tot_xp = sum(p.xp_next_gw for p in s_defs + s_mids + s_fwds)
                if tot_xp > best_xp:
                    best_xp = tot_xp
                    best_starters = starter_gkp + s_defs + s_mids + s_fwds
                    best_formation = f"{d_cnt}-{m_cnt}-{f_cnt}"

        starter_set = set(p.player_id for p in best_starters)
        outfield_bench = [p for p in squad_15 if p.player_id not in starter_set and p.element_type != 1]
        outfield_bench.sort(key=_fit_score, reverse=True)

        bench_4 = bench_gkp + outfield_bench[:3]
        
        best_starters.sort(key=lambda x: (x.element_type, -x.xp_next_gw))

        # Captaincy selection: 100% focused on immediate Next GW expected points
        sorted_by_xp = sorted(best_starters, key=lambda x: (x.p_availability >= 0.85, x.xp_next_gw), reverse=True)
        captain = sorted_by_xp[0] if sorted_by_xp else None
        vice_captain = sorted_by_xp[1] if len(sorted_by_xp) > 1 else captain

        return best_starters, bench_4, best_formation, captain, vice_captain

    def solve_all_scenarios(self, locks: Set[int]=None, must_sell: Set[int]=None, must_buy: Set[int]=None, blacklist: Set[int]=None) -> Dict[str, ScenarioResult]:
        a_l, b_l, g_l = self.get_dynamic_weights("safe", self.current_gw, self.overall_rank)
        a_h, b_h, g_h = self.get_dynamic_weights("aggressive", self.current_gw, self.overall_rank)

        return {
            "low_risk": self.solve_with_relaxation(
                "low_risk", a_l, b_l, g_l, 
                locks=locks, must_sell=must_sell, must_buy=must_buy, blacklist=blacklist,
                display_name="🛡️ 1. KISIM: DÜŞÜK RİSKLİ ALGORİTMA (Dengeli / Garantici)"
            ),
            "high_risk": self.solve_with_relaxation(
                "high_risk", a_h, b_h, g_h, 
                locks=locks, must_sell=must_sell, must_buy=must_buy, blacklist=blacklist,
                display_name="⚡ 2. KISIM: YÜKSEK RİSKLİ ALGORİTMA (Sıralama Tırmanış)"
            )
        }

    def solve_scenario(self, scenario_name: str, alpha: float, beta: float, gamma: float, display_name: str = "Hamle Önerisi") -> ScenarioResult:
        # Legacy support wrapper
        return self.solve_with_relaxation(scenario_name, alpha, beta, gamma, display_name=display_name)

    def _empty_fallback(self, name: str, display_name: str) -> ScenarioResult:
        squad_15 = self.current_squad if self.current_squad else list(self.analyses.values())[:15]
        starters, bench, formation, captain, vice_captain = self._select_optimal_11_and_bench(squad_15)
        return ScenarioResult(
            name=name,
            display_name=display_name,
            transfers_out=[],
            transfers_in=[],
            optimal_starting_11=starters,
            optimal_bench=bench,
            formation=formation,
            captain=captain,
            vice_captain=vice_captain,
            net_xp_gain=0.0,
            hit_cost=0,
            budget_remaining=round(self.bank / 10.0, 2),
            objective_value=0.0,
            reasons=["Kadro değişikliği önerilmiyor (Mevcut kadro korunsun, Free Transfer biriktirin)."]
        )

if __name__ == "__main__":
    # --- SANITY CHECK & RELAXATION MOCK TEST ---
    print("MOCK TEST: Testing Relaxation Hierarchy")
    
    # Create mock players
    mock_players = {}
    squad_ids = set()
    for i in range(1, 16):
        cst = 40 if i <= 7 else (60 if i <= 12 else 70)
        mock_players[i] = PlayerAnalysis(
            player_id=i, web_name=f"Player_{i}", element_type=1 if i <= 2 else (2 if i <= 7 else (3 if i <= 12 else 4)),
            team_id=i % 20, now_cost=cst, selling_price=cst, in_squad=True, is_locked=False,
            xp_next_gw=4.0, xp_horizon=12.0, w_form=1.0, p_availability=1.0, p_card_risk=0.0,
            price_rise_prob=0.0, price_fall_prob=0.0, predicted_price_gain=0.0,
            ownership=10.0, eo=10.0, template_score=0.0, differential_score=0.0, eo_risk=0.0,
            fixture_string="MOCK", avg_fdr=2.0, yellow_cards=0, news="", status="a"
        )
        squad_ids.add(i)
        
    # Expensive players to buy
    mock_players[101] = PlayerAnalysis(
        player_id=101, web_name="Salah", element_type=3, team_id=2, now_cost=130, selling_price=130, in_squad=False, is_locked=False,
        xp_next_gw=8.0, xp_horizon=24.0, w_form=1.0, p_availability=1.0, p_card_risk=0.0,
        price_rise_prob=0.0, price_fall_prob=0.0, predicted_price_gain=0.0, ownership=50.0, eo=50.0, template_score=0.0, differential_score=0.0, eo_risk=0.0,
        fixture_string="MOCK", avg_fdr=2.0, yellow_cards=0, news="", status="a"
    )
    mock_players[102] = PlayerAnalysis(
        player_id=102, web_name="Haaland", element_type=4, team_id=3, now_cost=150, selling_price=150, in_squad=False, is_locked=False,
        xp_next_gw=9.0, xp_horizon=27.0, w_form=1.0, p_availability=1.0, p_card_risk=0.0,
        price_rise_prob=0.0, price_fall_prob=0.0, predicted_price_gain=0.0, ownership=50.0, eo=50.0, template_score=0.0, differential_score=0.0, eo_risk=0.0,
        fixture_string="MOCK", avg_fdr=2.0, yellow_cards=0, news="", status="a"
    )
    
    # Cheap fallback replacements so that relaxation succeeds when expensive players are relaxed
    mock_players[103] = PlayerAnalysis(
        player_id=103, web_name="Cheap_1", element_type=1, team_id=4, now_cost=40, selling_price=40, in_squad=False, is_locked=False,
        xp_next_gw=4.0, xp_horizon=12.0, w_form=1.0, p_availability=1.0, p_card_risk=0.0,
        price_rise_prob=0.0, price_fall_prob=0.0, predicted_price_gain=0.0, ownership=5.0, eo=5.0, template_score=0.0, differential_score=0.0, eo_risk=0.0,
        fixture_string="MOCK", avg_fdr=2.0, yellow_cards=0, news="", status="a"
    )
    mock_players[104] = PlayerAnalysis(
        player_id=104, web_name="Cheap_DEF", element_type=2, team_id=5, now_cost=40, selling_price=40, in_squad=False, is_locked=False,
        xp_next_gw=4.0, xp_horizon=12.0, w_form=1.0, p_availability=1.0, p_card_risk=0.0,
        price_rise_prob=0.0, price_fall_prob=0.0, predicted_price_gain=0.0, ownership=5.0, eo=5.0, template_score=0.0, differential_score=0.0, eo_risk=0.0,
        fixture_string="MOCK", avg_fdr=2.0, yellow_cards=0, news="", status="a"
    )
    
    # 0 bank, selling 2 gives 80 total. Buying 101+102 needs 280 (INFEASIBLE BUDGET)
    # Also 101 is blacklisted but must-buy (CONFLICT)
    opt = MasterOptimizer(mock_players, squad_ids, bank=0, free_transfers=2, current_gw=1, is_preseason=False)
    
    locks = {3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15}
    must_sell = {1, 2} 
    must_buy = {101, 102} 
    blacklist = {101} 
    
    res = opt.solve_with_relaxation("aggressive", 0.0, 0.0, 0.0, locks=locks, must_sell=must_sell, must_buy=must_buy, blacklist=blacklist)
    
    print(f"[SUCCESS] Relaxation test completed. Reasons output:")
    for r in res.reasons:
        print("  -", r)
        
    assert any("Kisit Gevsetme Uygulandi" in r for r in res.reasons), "Relaxation did not trigger!"
    print("Sanity checks passed.")
