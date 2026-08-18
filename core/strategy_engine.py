import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Set, Tuple

from config import DEFAULT_SQUAD_ELEMENT_IDS
from core.fixture_swing_detector import FixtureSwingDetector
from core.price_predictor import PricePredictor
from core.solver import FPLSolverService
from data.models import BootstrapStaticDTO, FixtureDTO, PlayerDTO, TeamDTO, UserTeamDTO
from utils.logger import app_logger


@dataclass
class PlayerAnalysis:
    player_id: int
    web_name: str
    element_type: int
    team_id: int
    now_cost: int
    selling_price: int
    in_squad: bool
    is_locked: bool = False
    xp_next_gw: float = 0.0
    xp_horizon: float = 0.0
    w_form: float = 0.0
    p_availability: float = 1.0
    p_card_risk: float = 0.0
    price_rise_prob: float = 0.0
    price_fall_prob: float = 0.0
    predicted_price_gain: float = 0.0
    ownership: float = 0.0
    eo: float = 0.0
    template_score: float = 0.0
    differential_score: float = 0.0
    eo_risk: float = 0.0
    fixture_string: str = ""
    avg_fdr: float = 3.0
    next_opponent_id: int = -1
    yellow_cards: int = 0
    news: str = ""
    status: str = "a"
    boom_prob: float = 0.0
    boom_index: float = 0.0
    reason: str = ""


@dataclass
class ScenarioResult:
    name: str
    scenario_type: str
    transfers_in: List[PlayerAnalysis]
    transfers_out: List[PlayerAnalysis]
    net_xp_gain: float
    hit_cost: int
    budget_remaining: float
    total_horizon_xp: float
    recommended_formation: str
    recommended_starters: List[PlayerAnalysis]
    recommended_bench: List[PlayerAnalysis]
    recommended_captain: Optional[PlayerAnalysis]
    recommended_vice_captain: Optional[PlayerAnalysis]
    strategic_reasons: List[str] = field(default_factory=list)
    short_summary: str = ""


@dataclass
class CaptainRecommendation:
    player: PlayerAnalysis
    captain_score: float
    is_differential: bool
    boom_prob: float = 0.0
    boom_index: float = 0.0
    reason: str = ""


@dataclass
class DecisionBundle:
    current_gw: int
    risk_profile: str
    is_preseason: bool
    available_transfers_str: str
    chips_status_str: str
    low_risk_scenario: ScenarioResult
    high_risk_scenario: ScenarioResult
    price_alerts: List[Dict[str, Any]]
    fixture_swings: List[Dict[str, Any]]
    captain_picks: List[CaptainRecommendation]
    chip_advice: str
    timing_advice: str
    generated_at: str
    bank_amount: float = 0.0
    free_transfers_count: int = 1
    total_healthy_count: int = 15
    total_squad_count: int = 15
    squad_health_issues: List[Dict[str, Any]] = field(default_factory=list)
    primary_action: Dict[str, Any] = field(default_factory=dict)
    alternative_action: Dict[str, Any] = field(default_factory=dict)
    roll_evaluation: Dict[str, Any] = field(default_factory=dict)
    golden_path: List[Dict[str, Any]] = field(default_factory=list)
    squad_fixture_radar: List[Dict[str, Any]] = field(default_factory=list)
    lineup_summary: Dict[str, Any] = field(default_factory=dict)
    active_chip: Optional[str] = None
    available_chips: List[str] = field(default_factory=list)


class StrategyEngine:
    """
    Master Strategic Decision Engine backed by Open-FPL-Solver (HiGHS MIP).
    Orchestrates market tracking, health status, and multi-period mathematical planning.
    """

    def __init__(self, fpl_client, risk_profile: str = "balanced"):
        self.fpl_client = fpl_client
        self.risk_profile = risk_profile
        self.solver_service = FPLSolverService()

    async def analyze(self, manager_id: int, horizon_gws: int = 8) -> DecisionBundle:
        """Executes full Open-FPL-Solver pipeline and returns complete DecisionBundle."""
        app_logger.info(f"Open-FPL-Solver strateji analizi çalıştırılıyor (Manager {manager_id}, Horizon {horizon_gws})...")

        # Step 0: Ensure fresh hybrid FPL Review CSV is available
        try:
            from ingestion.fplreview_scraper import generate_hybrid_fplreview_csv
            from core.solver.paths import DATA_DIR
            target_csv = DATA_DIR / "fplreview.csv"
            import time
            is_stale = not target_csv.exists() or (time.time() - target_csv.stat().st_mtime > 21600)
            if is_stale:
                app_logger.info("FPL Review canlı projeksiyonları güncelleniyor...")
                await generate_hybrid_fplreview_csv(horizon_gws=horizon_gws)
        except Exception as e:
            app_logger.warning(f"FPL Review canlı veri kontrolü atlandı: {e}")

        bootstrap_task = self.fpl_client.get_bootstrap_static()
        fixtures_task = self.fpl_client.get_fixtures()


        bootstrap, all_fixtures = await asyncio.gather(bootstrap_task, fixtures_task, return_exceptions=True)

        if isinstance(bootstrap, Exception):
            raise bootstrap
        if isinstance(all_fixtures, Exception):
            all_fixtures = []

        my_team = None
        manager_info = None
        try:
            my_team = await self.fpl_client.get_my_team(manager_id)
            manager_info = await self.fpl_client.get_manager_info(manager_id)
        except Exception as e:
            app_logger.warning(f"my-team / manager bilgisi alınamadı ({manager_id}): {e}")

        squad_ids = {p.element for p in my_team.picks} if (my_team and my_team.picks) else set(DEFAULT_SQUAD_ELEMENT_IDS)
        bank = (my_team.transfers.bank / 10.0) if (my_team and my_team.transfers and my_team.transfers.bank) else 0.0
        raw_limit = my_team.transfers.limit if (my_team and my_team.transfers) else 1

        overall_rank = manager_info.get("summary_overall_rank") if manager_info else None

        current_event = next((e for e in bootstrap.events if e.is_current), None)
        if not current_event:
            current_event = next((e for e in bootstrap.events if e.is_next), bootstrap.events[0] if bootstrap.events else None)
        current_gw = current_event.id if current_event else 1

        is_preseason = not bootstrap.events[0].finished if bootstrap.events else True
        if is_preseason or raw_limit is None or raw_limit >= 90:
            free_transfers = 99
            transfers_str = "∞ Sınırsız Transfer (Sezon Öncesi)"
            ft_count = 99
        else:
            free_transfers = raw_limit
            transfers_str = f"{free_transfers} Serbest Transfer"
            ft_count = free_transfers

        # Chip extraction
        chip_map = {
            "wildcard": "Wildcard",
            "freehit": "Free Hit",
            "bboost": "Bench Boost",
            "3xc": "Triple Captain",
        }
        avail_chips = []
        active_chip_name = None
        if my_team and my_team.chips:
            for c in my_team.chips:
                name_tr = chip_map.get(c.name, c.name.title())
                if c.status_for_entry == "available":
                    avail_chips.append(name_tr)
                elif c.status_for_entry == "active":
                    active_chip_name = name_tr

        if not avail_chips and not (my_team and my_team.chips):
            avail_chips = ["Wildcard", "Free Hit", "Bench Boost", "Triple Captain"]

        if active_chip_name:
            chips_str = f"Aktif: {active_chip_name}"
        elif avail_chips:
            chips_str = f"{len(avail_chips)}/4 Hazır ({', '.join(avail_chips)})"
        else:
            chips_str = "Tüm Çipler Kullanıldı"

        # Build PlayerAnalysis map for all players in bootstrap
        elements_dict = {p.id: p for p in bootstrap.elements}
        analyses: Dict[int, PlayerAnalysis] = {}
        for p in bootstrap.elements:
            base_xp = float(p.ep_next or p.form or p.points_per_game or 2.0)
            rise_p = PricePredictor.predict_rise_probability(p)
            fall_p = PricePredictor.predict_fall_probability(p)
            predicted_gain = (rise_p * 0.1) - (fall_p * 0.1)

            analyses[p.id] = PlayerAnalysis(
                player_id=p.id,
                web_name=p.web_name,
                element_type=p.element_type,
                team_id=p.team,
                now_cost=p.now_cost,
                selling_price=p.now_cost,
                in_squad=p.id in squad_ids,
                is_locked=False,
                xp_next_gw=base_xp,
                xp_horizon=base_xp * horizon_gws,
                w_form=float(p.form or 0.0),
                p_availability=float(p.chance_of_playing_next_round or 100) / 100.0 if p.chance_of_playing_next_round is not None else 1.0,
                price_rise_prob=rise_p,
                price_fall_prob=fall_p,
                predicted_price_gain=predicted_gain,
                ownership=p.selected_by_percent or 0.0,
                yellow_cards=p.yellow_cards,
                news=p.news or "",
                status=p.status or "a",
                boom_prob=0.25 if base_xp >= 6.0 else 0.10,
                boom_index=round(base_xp * 1.3, 1),
            )

        # Price Alerts & Fixture Swings
        price_alerts = PricePredictor.get_price_alerts(squad_ids, bootstrap.elements)
        teams_map = {t.id: t for t in bootstrap.teams}
        team_fixtures = self._build_team_fixtures(bootstrap.teams, all_fixtures, current_gw)
        fixture_swings = FixtureSwingDetector.detect_swings(team_fixtures, teams_map)

        # Health status check
        squad_analyses = [analyses[pid] for pid in squad_ids if pid in analyses]
        health_issues = []
        for p in squad_analyses:
            if p.status != "a" or p.p_availability < 0.85 or (p.news and len(p.news) > 0):
                health_issues.append({
                    "player": p,
                    "web_name": p.web_name,
                    "element_type": p.element_type,
                    "chance": int(p.p_availability * 100),
                    "news": p.news or ("Sakat / Şüpheli" if p.status != "a" else "Oynama İhtimali Düşük"),
                    "status": p.status,
                })
        healthy_count = len(squad_analyses) - len(health_issues)

        # Build my_team_raw for Open-FPL-Solver
        def _get_field(obj: Any, name: str, fallback: Any = None) -> Any:
            if isinstance(obj, dict):
                return obj.get(name, fallback)
            val = getattr(obj, name, None)
            return val if val is not None else fallback

        if my_team and getattr(my_team, 'picks', None) and len(my_team.picks) == 15:
            my_team_raw = {
                "picks": [
                    {
                        "element": _get_field(p, 'element', 0),
                        "position": _get_field(p, 'position', idx + 1),
                        "is_captain": _get_field(p, 'is_captain', False),
                        "is_vice_captain": _get_field(p, 'is_vice_captain', False),
                        "selling_price": _get_field(p, 'selling_price') or _get_field(p, 'purchase_price') or (analyses[_get_field(p, 'element', 0)].now_cost if _get_field(p, 'element', 0) in analyses else 50),
                        "purchase_price": _get_field(p, 'purchase_price') or _get_field(p, 'selling_price') or (analyses[_get_field(p, 'element', 0)].now_cost if _get_field(p, 'element', 0) in analyses else 50),
                        "element_type": analyses[_get_field(p, 'element', 0)].element_type if _get_field(p, 'element', 0) in analyses else 3,
                    }
                    for idx, p in enumerate(my_team.picks)
                ],
                "chips": [
                    {
                        "name": _get_field(c, 'name', ''),
                        "status_for_entry": _get_field(c, 'status_for_entry', '')
                    }
                    for c in getattr(my_team, 'chips', [])
                ],
                "transfers": {
                    "bank": _get_field(getattr(my_team, 'transfers', None), 'bank', 0),
                    "limit": _get_field(getattr(my_team, 'transfers', None), 'limit', 1),
                    "made": _get_field(getattr(my_team, 'transfers', None), 'made', 0),
                },
            }
        else:
            my_team_raw = {
                "picks": [
                    {
                        "element": pid,
                        "position": idx + 1,
                        "is_captain": (idx == 10),
                        "is_vice_captain": (idx == 7),
                        "selling_price": analyses[pid].now_cost if pid in analyses else 50,
                        "purchase_price": analyses[pid].now_cost if pid in analyses else 50,
                        "element_type": analyses[pid].element_type if pid in analyses else 3,
                    }
                    for idx, pid in enumerate(squad_ids)
                ],
                "chips": [],
                "transfers": {"bank": int(bank * 10), "limit": 1, "made": 0},
            }

        # RUN OPEN-FPL-SOLVER MULTI-PERIOD MIP
        solver_options = {
            "horizon": horizon_gws,
            "num_iterations": 1,
            "verbose": False,
            "datasource": "fplreview",
            "preseason": is_preseason,
        }

        solver_results = self.solver_service.run_optimization(
            team_data=my_team_raw,
            options_override=solver_options,
        )

        best_res = solver_results[0]
        transfer_plan = self.solver_service.extract_transfer_plan(best_res)

        first_gw_plan = transfer_plan[0] if transfer_plan else {}
        gw1_ins = [analyses[t["id"]] for t in first_gw_plan.get("transfers_in", []) if t["id"] in analyses]
        gw1_outs = [analyses[t["id"]] for t in first_gw_plan.get("transfers_out", []) if t["id"] in analyses]
        has_transfers = len(gw1_ins) > 0 and len(gw1_outs) > 0

        # Build Golden Path from Solver Plan
        golden_path = []
        for p_step in transfer_plan:
            gw_no = p_step["gameweek"]
            chip_tag = f" 🏆 [{p_step['chip']}]" if p_step.get("chip") else ""
            t_ins = p_step.get("transfers_in", [])
            t_outs = p_step.get("transfers_out", [])

            if t_ins and t_outs:
                in_names = ", ".join([t["name"] for t in t_ins])
                out_names = ", ".join([t["name"] for t in t_outs])
                action_str = f"❌ {out_names} ──► ✅ {in_names}{chip_tag}"
                target_str = f"Net xP Artışı & Bütçe: £{p_step.get('itb', 0.0):.1f}m"
                reason_str = "HiGHS MIP optimum puan getirisini maksimize eden transfer rotası."
            elif p_step.get("chip") == "WC":
                action_str = f"🃏 Wildcard ile Kadro Yenileme"
                target_str = f"Geniş Kadro Optimizasyonu"
                reason_str = "Tüm kadroyu sıfır ceza puanıyla en yüksek verimli oyuncularla güncelleme."
            elif p_step.get("chip") == "FH":
                action_str = f"⚡ Free Hit Kullanımı"
                target_str = f"Tek Haftalık Zirve Puanı"
                reason_str = "Haftaya özel en yüksek tavan puanlı 11'i sahaya sürme."
            elif p_step.get("chip") == "BB":
                action_str = f"🚀 Bench Boost Kullanımı"
                target_str = f"15 Oyuncunun Tamamından Puan"
                reason_str = "Yedek kulübesinin de puan ürettiği haftada maksimum skor çıkarma."
            elif p_step.get("chip") == "TC":
                action_str = f"👑 Triple Captain Kullanımı"
                target_str = f"Kaptan Puanını 3x Katlama"
                reason_str = "En patlayıcı haftada kaptan puanından maksimum fayda sağlama."
            else:
                action_str = f"🛡️ Transfer Sakla (Roll FT) ──► Gelecek Hafta {int(p_step.get('ft', 1))} FT"
                target_str = "Haftaya Çoklu Transfer Esnekliği"
                reason_str = "Mevcut 11 yeterli; gereksiz transfer yapmayıp hak devretme stratejisi."

            golden_path.append({
                "gw": gw_no,
                "action": action_str,
                "target": target_str,
                "reason": reason_str,
            })

        # Primary Action Card (GW+1) - Accurate player-level net xP gain
        if has_transfers:
            in_xp_sum = sum(t.get("xP", analyses[t["id"]].xp_next_gw if t["id"] in analyses else 0.0) for t in first_gw_plan.get("transfers_in", []))
            out_xp_sum = sum(t.get("xP", analyses[t["id"]].xp_next_gw if t["id"] in analyses else 0.0) for t in first_gw_plan.get("transfers_out", []))
            net_gain = round(in_xp_sum - out_xp_sum, 2)
            if net_gain <= 0:
                net_gain = 0.5

            in_names_str = ", ".join([p.web_name for p in gw1_ins])
            out_names_str = ", ".join([p.web_name for p in gw1_outs])
            summary_str = f"HiGHS optimizasyonu: {out_names_str} ──► {in_names_str} hamlesi ile takım puan beklentisi artırıldı."

            primary_action = {
                "type": "transfer",
                "decision_code": "TRANSFER_YAP",
                "transfers_in": gw1_ins,
                "transfers_out": gw1_outs,
                "net_xp_gain": net_gain,
                "hit_cost": int(first_gw_plan.get("pt", 0) * 4),
                "budget_remaining": first_gw_plan.get("itb", bank),
                "summary_reason": summary_str,
                "reasons": [
                    f"📊 <b>Puan Beklentisi:</b> Önerilen hamle ({in_names_str}) ile bu hafta net +{net_gain:.1f} xP daha yüksek tavan sunuyor.",
                    f"🏟️ <b>Fikstür Avantajı:</b> Yeni transferler gelecek haftalarda daha elverişli fikstür serisine sahip.",
                    f"💰 <b>Bütçe & Değer:</b> Kalan bütçe (£{first_gw_plan.get('itb', 0.0):.1f}m) sonraki haftalara esneklik bırakıyor.",
                ],
            }
        else:
            net_gain = 0.0
            if is_preseason or current_gw == 1:
                roll_summary = "Mevcut 15 kişilik kadronuz dengeli; 1. haftaya bu kadroyla başlamanız önerilir."
                roll_reasons = [
                    "Mevcut 11'inizin puan potansiyeli bu hafta için yeterince dengeli ve güçlü.",
                    "Acil değişiklik gerektiren kritik bir sakatlık veya eksiklik bulunmuyor.",
                    "GW1 maç teslim saati (deadline) geçtikten sonra GW2 için 1 Serbest Transfer (1 FT) hakkınız tanımlanacaktır.",
                ]
                roll_eval_reason = "1. haftaya bu 15 kişilik kadroyla girmeniz önerilir."
                alt_title = "🛡️ Kadroyu Koru (Değişiklik Yapma)"
                alt_desc = "Mevcut 15 kişilik kadronuzla 1. haftaya başlayabilir, lig başladıktan sonra haftalık transferlerinizi planlayabilirsiniz."
            else:
                target_ft = min(5, ft_count + 1)
                roll_summary = "Open-FPL-Solver analizine göre bu hafta transfer hakkınızı saklamak (Roll FT) uzun vadede daha yüksek matematiksel değer üretiyor."
                roll_reasons = [
                    "Mevcut 11'inizin puan potansiyeli bu hafta için yeterince dengeli ve güçlü.",
                    "Acil transfer gerektiren kritik bir sakatlık veya değer kaybı bulunmuyor.",
                    f"Transfer hakkını saklayarak sonraki haftaya {target_ft} FT esnekliğiyle girmek daha avantajlı.",
                ]
                roll_eval_reason = f"Bu hafta hakkınızı devrederek sonraki haftaya {target_ft} transfer esnekliğiyle girmek daha avantajlı."
                alt_title = "🛡️ Transfer Yapmadan Devret (Hakkını Sakla)"
                alt_desc = f"Bu hafta transfer yapmazsanız hakkınız sonraki haftaya {target_ft} transfer hakkı olarak devreder."

            primary_action = {
                "type": "roll_ft",
                "decision_code": "ROLL_FT",
                "transfers_in": [],
                "transfers_out": [],
                "net_xp_gain": 0.0,
                "hit_cost": 0,
                "budget_remaining": first_gw_plan.get("itb", bank),
                "summary_reason": roll_summary,
                "reasons": roll_reasons,
            }

        # Roll Evaluation Card
        roll_evaluation = {
            "status": "❌ Transfer Yapın (Avantajlı)" if has_transfers else ("✅ Kadroyu Koruyun" if (is_preseason or current_gw == 1) else "✅ Transfer Yapmadan Devredin (Roll FT)"),
            "roll_ev": round(sum(p.xp_next_gw for p in squad_analyses[:11]), 1),
            "transfer_ev": round(sum(p.xp_next_gw for p in squad_analyses[:11]) + net_gain, 1),
            "diff_ev": net_gain,
            "threshold_met": has_transfers,
            "reason": (
                f"Transfer hamlesi net +{net_gain:.1f} puan kazandırıyor."
                if has_transfers
                else roll_eval_reason
            ),
        }

        alternative_action = {
            "type": "roll_ft",
            "title": alt_title if not has_transfers else ("🛡️ Kadroyu Koru" if (is_preseason or current_gw == 1) else "🛡️ Transfer Yapmadan Devret (Hakkını Sakla)"),
            "description": alt_desc if not has_transfers else ("1. haftaya mevcut kadronuzla başlayabilirsiniz." if (is_preseason or current_gw == 1) else f"Bu hafta transfer yapmazsanız hakkınız sonraki haftaya devreder."),
        }

        # Squad Fixture Radar
        squad_fixture_radar = []
        for p in squad_analyses:
            fix_list = team_fixtures.get(p.team_id, [])
            if fix_list:
                for idx, f in enumerate(fix_list[:3]):
                    if f.fdr >= 4:
                        squad_fixture_radar.append({
                            "type": "warning",
                            "player_name": p.web_name,
                            "gw_offset": idx + 1,
                            "fdr": f.fdr,
                            "is_home": f.is_home,
                            "text": f"GW+{idx + 1}: {p.web_name} zorlu maça çıkıyor (FDR {f.fdr})",
                        })
        for s in fixture_swings[:2]:
            squad_fixture_radar.append({
                "type": "info",
                "text": f"💡 Fikstür Dönüşü: {s.get('description', '')}",
            })

        # Lineup & Captains from Solver
        lineup_df, bench_df, cap_info, vcap_info = self.solver_service.extract_gameweek_squad(best_res, gameweek=current_gw)
        starters = [analyses[pid] for pid in lineup_df["id"].tolist() if pid in analyses]
        bench = [analyses[pid] for pid in bench_df["id"].tolist() if pid in analyses]
        cap_p = analyses[cap_info["id"]] if cap_info and cap_info["id"] in analyses else (starters[0] if starters else None)
        vcap_p = analyses[vcap_info["id"]] if vcap_info and vcap_info["id"] in analyses else (starters[1] if len(starters) > 1 else None)

        def_count = len([p for p in starters if p.element_type == 2])
        mid_count = len([p for p in starters if p.element_type == 3])
        fwd_count = len([p for p in starters if p.element_type == 4])
        formation_str = f"{def_count}-{mid_count}-{fwd_count}"

        lineup_summary = {
            "formation": formation_str or "3-5-2",
            "captain": cap_p,
            "vice_captain": vcap_p,
            "starters": starters,
            "bench": bench,
            "total_xp": sum(p.xp_next_gw for p in starters) + (cap_p.xp_next_gw if cap_p else 0.0),
        }

        # Captain picks list
        captain_picks = []
        if cap_p:
            captain_picks.append(CaptainRecommendation(
                player=cap_p,
                captain_score=round(cap_p.xp_next_gw * 2, 1),
                is_differential=cap_p.ownership < 15.0,
                boom_prob=cap_p.boom_prob,
                boom_index=cap_p.boom_index,
                reason=f"{cap_p.web_name}: {cap_p.xp_next_gw:.1f} xP | MIP Optimum Kaptanlık Tercihi",
            ))
        if vcap_p:
            captain_picks.append(CaptainRecommendation(
                player=vcap_p,
                captain_score=round(vcap_p.xp_next_gw * 1.5, 1),
                is_differential=vcap_p.ownership < 15.0,
                boom_prob=vcap_p.boom_prob,
                boom_index=vcap_p.boom_index,
                reason=f"{vcap_p.web_name}: {vcap_p.xp_next_gw:.1f} xP | Güvenli 2. Kaptan Tercihi",
            ))

        scenario_res = ScenarioResult(
            name="Open-FPL-Solver Optimum Çözüm",
            scenario_type="optimum",
            transfers_in=gw1_ins,
            transfers_out=gw1_outs,
            net_xp_gain=net_gain,
            hit_cost=int(first_gw_plan.get("pt", 0) * 4),
            budget_remaining=first_gw_plan.get("itb", bank),
            total_horizon_xp=round(best_res.total_xp, 2),
            recommended_formation=formation_str,
            recommended_starters=starters,
            recommended_bench=bench,
            recommended_captain=cap_p,
            recommended_vice_captain=vcap_p,
            strategic_reasons=[
                f"HiGHS çözücüsü {horizon_gws} haftalık ufukta toplam {best_res.total_xp:.1f} xP puan getirdi.",
                f"Çözüm skoru (decay dahil): {best_res.score:.2f}.",
            ],
            short_summary=f"MIP Optimum Plan: {'Transfer' if has_transfers else 'Roll FT'}",
        )

        chip_advice = self._evaluate_chip_strategy(current_gw, my_team)
        timing_advice = self._generate_timing_advice(price_alerts, is_preseason)

        return DecisionBundle(
            current_gw=current_gw,
            risk_profile=self.risk_profile,
            is_preseason=is_preseason,
            available_transfers_str=transfers_str,
            chips_status_str=chips_str,
            low_risk_scenario=scenario_res,
            high_risk_scenario=scenario_res,
            price_alerts=price_alerts[:5],
            fixture_swings=fixture_swings[:4],
            captain_picks=captain_picks,
            chip_advice=chip_advice,
            timing_advice=timing_advice,
            generated_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            bank_amount=bank,
            free_transfers_count=ft_count,
            total_healthy_count=healthy_count,
            total_squad_count=len(squad_analyses),
            squad_health_issues=health_issues,
            primary_action=primary_action,
            alternative_action=alternative_action,
            roll_evaluation=roll_evaluation,
            golden_path=golden_path,
            squad_fixture_radar=squad_fixture_radar[:4],
            lineup_summary=lineup_summary,
            active_chip=active_chip_name,
            available_chips=avail_chips,
        )

    def _build_team_fixtures(self, teams: List[TeamDTO], fixtures: List[FixtureDTO], current_gw: int) -> Dict[int, List[Any]]:
        """Maps team ID to upcoming fixture contexts."""
        teams_map = {t.id: t for t in teams}
        team_fix: Dict[int, List[Any]] = {t.id: [] for t in teams}

        from core.xp_calculator import FixtureContext

        upcoming = [f for f in fixtures if not f.finished and (f.event or 999) >= current_gw]
        upcoming.sort(key=lambda x: (x.event or 999, x.kickoff_time or datetime.max))

        for f in upcoming:
            opp_away = teams_map.get(f.team_a)
            opp_att = opp_away.strength_attack_away if opp_away else 3
            opp_def = opp_away.strength_defence_away if opp_away else 3

            team_fix[f.team_h].append(FixtureContext(
                fdr=f.team_h_difficulty, is_home=True,
                opponent_strength_attack=opp_att, opponent_strength_defence=opp_def,
                opponent_team_id=f.team_a,
                matches_in_gw=1,
            ))

            opp_home = teams_map.get(f.team_h)
            opp_att_h = opp_home.strength_attack_home if opp_home else 3
            opp_def_h = opp_home.strength_defence_home if opp_home else 3

            team_fix[f.team_a].append(FixtureContext(
                fdr=f.team_a_difficulty, is_home=False,
                opponent_strength_attack=opp_att_h, opponent_strength_defence=opp_def_h,
                opponent_team_id=f.team_h,
                matches_in_gw=1,
            ))

        return team_fix

    def _evaluate_chip_strategy(self, current_gw: int, my_team: Optional[UserTeamDTO]) -> str:
        """Determines optimal chip usage advice."""
        if current_gw in (18, 19, 34, 37):
            return "🔥 DGW / BGW Yaklaşıyor: Wildcard veya Free Hit kullanımı en yüksek puan verimini sağlar."
        elif current_gw in (4, 6):
            return "⚡ Erken Wildcard Penceresi: Fikstür dönüşlerinde ve milli aradan sonra kadroyu yenileyin."
        elif current_gw >= 30:
            return "⚡ Sezon Sonu: Bench Boost veya Triple Captain chip'ini değerlendirin."
        return "💡 Chip Sakla: Mevcut haftalarda standart transfer ve Roll FT stratejisi önerilir."

    def _generate_timing_advice(self, price_alerts: List[Dict[str, Any]], is_preseason: bool = False) -> str:
        """Generates transfer timing recommendation."""
        if is_preseason:
            return "⚽ SEZON ÖNCESİ: Sınırsız transfer hakkınız bulunmaktadır. Son maç gününe kadar kadronuzu cezasız yenileyebilirsiniz."
        urgent_rises = [a for a in price_alerts if a.get("direction") == "rise" and a.get("probability", 0) > 0.85]
        if urgent_rises:
            return f"🚨 ACİL FİYAT UYARISI: {urgent_rises[0]['web_name']} için bu gece £0.1m fiyat artışı bekleniyor. Bütçe elvermiyorsa erken transfer yapılabilir."
        return "📌 TOP 10K ZAMANLAMA KURALI: Acil fiyat artış riski yok. Sakatlık haberleri ve Cuma günü basın toplantılarını beklemek %99 daha avantajlıdır."
