from typing import Dict, List, Any, Optional, Tuple

def calculate_fixture_swing_score(
    fdr_near3: float, 
    fdr_far3: float, 
    far3_matches: List[int], 
    p_rise: float
) -> Tuple[float, bool]:
    """
    Calculates Fixture Swing Score over near3 (GW1-3) and far3 (GW4-6) horizons
    considering DGW/BGW occurrences and player price rise probabilities.
    
    Formula:
    Swing Score = |FDR_near3 - FDR_far3| * DGW_Bonus
    DGW_Bonus: 2.0 if far3 has DGW, 0.3 if far3 has BGW, 1.0 otherwise.
    Transfer Window Signal: Swing Score >= 2.0 AND P(Rise) < 0.30
    """
    has_dgw = any(m >= 2 for m in far3_matches)
    has_bgw = any(m == 0 for m in far3_matches)
    
    if has_dgw:
        dgw_bonus = 2.0
    elif has_bgw:
        dgw_bonus = 0.3
    else:
        dgw_bonus = 1.0
        
    swing_score = abs(fdr_near3 - fdr_far3) * dgw_bonus
    transfer_signal = bool(swing_score >= 2.0 and p_rise < 0.30)
    
    return round(swing_score, 3), transfer_signal

class FixtureSwingDetector:
    """
    Detects major upcoming fixture difficulty swings (Fixture Swings)
    for Premier League teams over a multi-gameweek horizon.
    Used by Top 10k managers to target players right before easy runs start.
    """
    
    @classmethod
    def detect_swings(
        cls, 
        team_fixtures: Dict[int, List[Any]], 
        teams_map: Dict[int, Any],
        p_rise_map: Optional[Dict[int, float]] = None
    ) -> List[Dict[str, Any]]:
        """
        Analyzes upcoming 6 GWs per team with DGW/BGW radar weighting.
        """
        swings = []
        p_rise_map = p_rise_map or {}
        
        for team_id, fix_list in team_fixtures.items():
            if len(fix_list) < 3:
                continue
                
            team_obj = teams_map.get(team_id)
            team_name = team_obj.name if team_obj and hasattr(team_obj, 'name') else f"Team {team_id}"
            
            near_3_fdr = sum(getattr(f, 'fdr', 3) for f in fix_list[:3]) / 3.0
            
            if len(fix_list) >= 6:
                far_3_fdr = sum(getattr(f, 'fdr', 3) for f in fix_list[3:6]) / 3.0
                # Determine match count per GW for far3
                gw_counts: Dict[int, int] = {}
                for f in fix_list[3:6]:
                    gw = getattr(f, 'event', getattr(f, 'gw', 0))
                    gw_counts[gw] = gw_counts.get(gw, 0) + 1
                far3_matches = list(gw_counts.values()) if gw_counts else [1, 1, 1]
            else:
                far_3_fdr = near_3_fdr
                far3_matches = [1, 1, 1]
                
            p_rise = p_rise_map.get(team_id, 0.0)
            swing_score, signal = calculate_fixture_swing_score(
                fdr_near3=near_3_fdr,
                fdr_far3=far_3_fdr,
                far3_matches=far3_matches,
                p_rise=p_rise
            )
            
            if near_3_fdr <= 2.2:
                swings.append({
                    "team_id": team_id,
                    "team_name": team_name,
                    "near_fdr": round(near_3_fdr, 1),
                    "far_fdr": round(far_3_fdr, 1),
                    "swing_score": swing_score,
                    "transfer_signal": signal,
                    "type": "immediate_easy",
                    "description": f"{team_name}: Önümüzdeki 3 maç son derece kolay fikstür bloğunda (Ort. FDR: {near_3_fdr:.1f}, Swing: {swing_score})."
                })
            elif (near_3_fdr - far_3_fdr) >= 1.0 and far_3_fdr <= 2.3:
                swings.append({
                    "team_id": team_id,
                    "team_name": team_name,
                    "near_fdr": round(near_3_fdr, 1),
                    "far_fdr": round(far_3_fdr, 1),
                    "swing_score": swing_score,
                    "transfer_signal": signal,
                    "type": "upcoming_swing",
                    "description": f"{team_name}: 3 hafta sonra fikstür belirgin şekilde kolaylaşıyor (FDR {near_3_fdr:.1f} -> {far_3_fdr:.1f}, Swing: {swing_score})."
                })
            elif swing_score >= 2.0:
                swings.append({
                    "team_id": team_id,
                    "team_name": team_name,
                    "near_fdr": round(near_3_fdr, 1),
                    "far_fdr": round(far_3_fdr, 1),
                    "swing_score": swing_score,
                    "transfer_signal": signal,
                    "type": "radar_dgw_swing",
                    "description": f"{team_name}: DGW/BGW Radarı önemli bir fikstür dönüşü tespit etti (Swing: {swing_score})."
                })
                
        swings.sort(key=lambda x: x.get("near_fdr", 5.0))
        return swings

if __name__ == "__main__":
    print("--- SANITY CHECK: core/fixture_swing_detector.py ---")
    
    # Test standalone calculate_fixture_swing_score
    score_dgw, sig_dgw = calculate_fixture_swing_score(4.0, 2.0, [1, 2, 1], p_rise=0.10)
    score_bgw, sig_bgw = calculate_fixture_swing_score(4.0, 2.0, [1, 0, 1], p_rise=0.10)
    
    print(f"DGW Swing Score: {score_dgw}, Signal: {sig_dgw}")
    print(f"BGW Swing Score: {score_bgw}, Signal: {sig_bgw}")
    
    assert score_dgw == 4.0
    assert sig_dgw is True
    assert score_bgw == 0.6
    assert sig_bgw is False
    
    # Mock class test
    class MockFixture:
        def __init__(self, fdr, event):
            self.fdr = fdr
            self.event = event
            
    mock_fixtures = {
        1: [MockFixture(4, 1), MockFixture(4, 2), MockFixture(4, 3), MockFixture(2, 4), MockFixture(2, 4), MockFixture(2, 5)]
    }
    class MockTeam:
        name = "Arsenal"
        
    swings = FixtureSwingDetector.detect_swings(mock_fixtures, {1: MockTeam()})
    assert len(swings) > 0
    print(f"Detected Swings: {swings[0]['team_name']} - Swing Score: {swings[0]['swing_score']}")
    print("[SUCCESS] Fixture swing detector sanity checks passed.")
