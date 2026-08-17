import pulp
from typing import List, Dict, Set
from utils.logger import app_logger
from core.master_optimizer import PlayerAnalysis

class RollingHorizonOptimizer:
    """
    4-Haftalık Deterministik Kayan Ufuklu MILP Çözücüsü (MPC).
    Gelecek haftaların transfer (FT) birikim dinamiklerini ve t=1,2,3,4 için
    optimal takım rotasını hesaplar.
    
    NOT: Bu sınıfın tam entegrasyonu için PlayerAnalysis modeline xp_weekly: List[float] 
    ve opponent_id_weekly: List[int] alanlarının eklenmesi gereklidir.
    """
    def __init__(self, analyses: Dict[int, PlayerAnalysis], squad_ids: Set[int], bank: float, free_transfers: int):
        self.analyses = analyses
        self.squad_ids = squad_ids
        self.bank = bank
        self.free_transfers = min(5, max(1, free_transfers))
        self.T = 4  # 4 haftalık ufuk
        self.gamma = 0.85 # Zaman indirim faktörü

    def solve_4_week_path(self):
        # 1. MILP Problemi Başlatma
        prob = pulp.LpProblem("FPL_4_Week_Rolling_Horizon", pulp.LpMaximize)
        
        player_ids = list(self.analyses.keys())
        all_players = list(self.analyses.values())
        
        # 2. Zaman İndeksli Değişkenler: x_{i,t}, s_{i,t}, c_{i,t}, in_{i,t}, out_{i,t}
        # t = 1, 2, 3, 4
        x = pulp.LpVariable.dicts("x", (player_ids, range(1, self.T + 1)), cat='Binary')
        s = pulp.LpVariable.dicts("s", (player_ids, range(1, self.T + 1)), cat='Binary')
        c = pulp.LpVariable.dicts("c", (player_ids, range(1, self.T + 1)), cat='Binary')
        
        buy = pulp.LpVariable.dicts("buy", (player_ids, range(1, self.T + 1)), cat='Binary')
        sell = pulp.LpVariable.dicts("sell", (player_ids, range(1, self.T + 1)), cat='Binary')
        
        ft = pulp.LpVariable.dicts("ft", range(1, self.T + 2), lowBound=1, upBound=5, cat='Integer')
        hits = pulp.LpVariable.dicts("hits", range(1, self.T + 1), lowBound=0, cat='Integer')
        
        # 3. Başlangıç Koşulları
        prob += ft[1] == self.free_transfers, "Initial_FT"
        
        # 4. FT ve Kadro Geçiş Dinamikleri (State Transitions)
        for t in range(1, self.T + 1):
            prob += pulp.lpSum([x[pid][t] for pid in player_ids]) == 15, f"SquadSize_{t}"
            prob += pulp.lpSum([s[pid][t] for pid in player_ids]) == 11, f"StartersSize_{t}"
            prob += pulp.lpSum([c[pid][t] for pid in player_ids]) == 1, f"CaptainSize_{t}"
            
            # Transfer eşitliği: x_{i,t} = x_{i,t-1} + buy_{i,t} - sell_{i,t}
            for p in all_players:
                pid = p.player_id
                prob += s[pid][t] <= x[pid][t], f"StartInSquad_{pid}_{t}"
                prob += c[pid][t] <= s[pid][t], f"CapInStart_{pid}_{t}"
                
                if t == 1:
                    prev_x = 1 if pid in self.squad_ids else 0
                else:
                    prev_x = x[pid][t-1]
                    
                prob += x[pid][t] == prev_x + buy[pid][t] - sell[pid][t], f"TransferFlow_{pid}_{t}"
                
            # FT Dinamiği ve Hit Hesabı
            total_buys = pulp.lpSum([buy[pid][t] for pid in player_ids])
            prob += hits[t] >= total_buys - ft[t], f"HitCalc_{t}"
            
            # Gelecek haftanın FT'si: max(1, min(5, ft_t - transfers + 1))
            prob += ft[t+1] <= ft[t] - total_buys + 1 + 5 * hits[t], f"FT_Transition_{t}"
            
        # 5. Amaç Fonksiyonu
        # NOT: Gerçek veride p.xp_weekly[t] dizisi kullanılmalıdır.
        obj = []
        for t in range(1, self.T + 1):
            gamma_t = self.gamma ** (t - 1)
            for p in all_players:
                pid = p.player_id
                est_xp = p.xp_next_gw if t == 1 else ((p.xp_horizon - p.xp_next_gw) / 3.0)
                obj.append(gamma_t * est_xp * s[pid][t])
                obj.append(gamma_t * est_xp * c[pid][t]) # Captain x2
                
            obj.append(-4.0 * gamma_t * hits[t]) # Hit penalty
            
        prob += pulp.lpSum(obj), "Rolling_Objective"
        app_logger.info("Rolling 4-GW MILP model constructed successfully.")
        return prob
