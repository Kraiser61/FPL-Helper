from typing import List, Optional, Any
from pydantic import BaseModel, Field, field_validator
from datetime import datetime

class PlayerDTO(BaseModel):
    id: int
    web_name: str
    team: int
    element_type: int
    now_cost: int
    form: float = 0.0
    total_points: int = 0
    selected_by_percent: float = 0.0
    status: str = "a"
    news: str = ""
    chance_of_playing_next_round: Optional[int] = None
    chance_of_playing_this_round: Optional[int] = None
    minutes: int = 0
    goals_scored: int = 0
    assists: int = 0
    clean_sheets: int = 0
    bonus: int = 0
    bps: int = 0
    expected_goals: float = 0.0
    expected_assists: float = 0.0
    expected_goal_involvements: float = 0.0
    expected_goals_conceded: float = 0.0
    ict_index: float = 0.0
    transfers_in_event: int = 0
    transfers_out_event: int = 0

    # Extended attributes for strategic engine
    yellow_cards: int = 0
    red_cards: int = 0
    points_per_game: float = 0.0
    value_form: float = 0.0
    value_season: float = 0.0
    influence: float = 0.0
    creativity: float = 0.0
    threat: float = 0.0
    ep_next: Optional[float] = None
    ep_this: Optional[float] = None
    clearances_blocks_interceptions: int = 0
    recoveries: int = 0
    tackles: int = 0

    @field_validator(
        'form', 'selected_by_percent', 'expected_goals', 
        'expected_assists', 'expected_goal_involvements', 
        'expected_goals_conceded', 'ict_index', 'points_per_game',
        'value_form', 'value_season', 'influence', 'creativity', 'threat',
        'ep_next', 'ep_this', mode='before'
    )
    def parse_float_from_string(cls, v):
        if v is None or v == "":
            return 0.0
        if isinstance(v, str):
            try:
                return float(v)
            except ValueError:
                return 0.0
        return float(v)

    def get_normalized_chance_next(self) -> float:
        if self.chance_of_playing_next_round is not None:
            return max(0.0, min(1.0, self.chance_of_playing_next_round / 100.0))
        return 1.0 if self.status == "a" else 0.0

    @property
    def team_id(self) -> int:
        return self.team


class TeamDTO(BaseModel):
    id: int
    name: str
    short_name: str
    strength: Optional[int] = 3
    strength_overall_home: Optional[int] = 1000
    strength_overall_away: Optional[int] = 1000
    strength_attack_home: Optional[int] = 1000
    strength_attack_away: Optional[int] = 1000
    strength_defence_home: Optional[int] = 1000
    strength_defence_away: Optional[int] = 1000

    @field_validator(
        'strength', 'strength_overall_home', 'strength_overall_away',
        'strength_attack_home', 'strength_attack_away',
        'strength_defence_home', 'strength_defence_away', mode='before'
    )
    def parse_optional_int(cls, v):
        if v is None:
            return 3
        return int(v)


class EventDTO(BaseModel):
    id: int
    name: str
    deadline_time: datetime
    finished: bool = False
    is_current: bool = False
    is_next: bool = False
    average_entry_score: int = 0
    highest_score: Optional[int] = None


class BootstrapStaticDTO(BaseModel):
    events: List[EventDTO] = Field(default_factory=list)
    teams: List[TeamDTO] = Field(default_factory=list)
    elements: List[PlayerDTO] = Field(default_factory=list)


class FixtureStatItemDTO(BaseModel):
    value: int = 0
    element: int = 0


class FixtureStatDTO(BaseModel):
    identifier: str
    a: List[FixtureStatItemDTO] = Field(default_factory=list)
    h: List[FixtureStatItemDTO] = Field(default_factory=list)


class FixtureDTO(BaseModel):
    id: int
    event: Optional[int] = None
    team_h: int
    team_a: int
    team_h_difficulty: int = 3
    team_a_difficulty: int = 3
    team_h_score: Optional[int] = None
    team_a_score: Optional[int] = None
    finished: bool = False
    finished_provisional: bool = False
    started: bool = False
    minutes: int = 0
    kickoff_time: Optional[datetime] = None
    stats: List[FixtureStatDTO] = Field(default_factory=list)


class PickDTO(BaseModel):
    element: int
    position: int
    multiplier: int = 1
    is_captain: bool = False
    is_vice_captain: bool = False
    selling_price: Optional[int] = None
    purchase_price: Optional[int] = None


class EntryHistoryDTO(BaseModel):
    event: int
    points: int = 0
    total_points: int = 0
    rank: Optional[int] = None
    event_transfers: int = 0
    event_transfers_cost: int = 0
    points_on_bench: int = 0
    value: int = 1000
    bank: int = 0


class UserPickDTO(BaseModel):
    active_chip: Optional[str] = None
    picks: List[PickDTO] = Field(default_factory=list)
    entry_history: Optional[EntryHistoryDTO] = None


class ChipDTO(BaseModel):
    name: str
    number: int
    start_event: int
    stop_event: int
    status_for_entry: str


class TransferDTO(BaseModel):
    cost: int = 0
    status: str = "ok"
    limit: Optional[int] = None
    made: int = 0
    bank: int = 0
    value: int = 0


class UserTeamDTO(BaseModel):
    picks: List[PickDTO] = Field(default_factory=list)
    chips: List[ChipDTO] = Field(default_factory=list)
    transfers: Optional[TransferDTO] = None


class LiveStatsDTO(BaseModel):
    minutes: int = 0
    goals_scored: int = 0
    assists: int = 0
    bonus: int = 0
    bps: int = 0
    total_points: int = 0
    in_dreamteam: bool = False


class LiveElementDTO(BaseModel):
    id: int
    stats: LiveStatsDTO = Field(default_factory=LiveStatsDTO)
    explain: List[Any] = Field(default_factory=list)


class LiveGWDataDTO(BaseModel):
    elements: List[LiveElementDTO] = Field(default_factory=list)
