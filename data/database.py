import sqlite3
import contextlib
from config import DB_PATH
from utils.logger import app_logger

class DatabaseManager:
    """
    Thread-safe SQLite Database Connection Manager featuring WAL mode, 30s busy timeout, and normal sync.
    Includes full Strategic Engine tables, Set-Piece Hierarchy, and Time-Series Compound Indexes.
    """
    
    def __init__(self, db_path=DB_PATH):
        self.db_path = db_path
        
    @contextlib.contextmanager
    def get_connection(self):
        """Context manager for SQLite database connection."""
        conn = None
        try:
            conn = sqlite3.connect(self.db_path, timeout=30.0, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            
            conn.execute("PRAGMA busy_timeout=30000;")
            conn.execute("PRAGMA foreign_keys=ON;")
            
            yield conn
        except sqlite3.Error as e:
            app_logger.error(f"Database connection error: {e}")
            raise
        finally:
            if conn:
                conn.close()

    def init_db(self):
        """Initializes the database schema with WAL mode, Strategic Engine tables, and Set-Piece hierarchy."""
        app_logger.info(f"Initializing database at {self.db_path}")
        
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute("PRAGMA journal_mode=WAL;")
            cursor.execute("PRAGMA synchronous=NORMAL;")
            
            # 1. Seasons
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS seasons (
                id              INTEGER PRIMARY KEY,
                label           TEXT NOT NULL,
                is_current      BOOLEAN DEFAULT 0
            );
            """)
            cursor.execute("INSERT OR IGNORE INTO seasons (id, label, is_current) VALUES (1, '2026/27', 1);")
            
            # 2. Teams
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS teams (
                id                      INTEGER PRIMARY KEY,
                season_id               INTEGER NOT NULL,
                name                    TEXT NOT NULL,
                short_name              TEXT NOT NULL,
                strength                INTEGER,
                strength_overall_home   INTEGER,
                strength_overall_away   INTEGER,
                strength_attack_home    INTEGER,
                strength_attack_away    INTEGER,
                strength_defence_home   INTEGER,
                strength_defence_away   INTEGER,
                updated_at              TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (season_id) REFERENCES seasons(id)
            );
            """)
            
            # 3. Players
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS players (
                id                          INTEGER PRIMARY KEY,
                season_id                   INTEGER NOT NULL,
                team_id                     INTEGER NOT NULL,
                first_name                  TEXT,
                second_name                 TEXT,
                web_name                    TEXT NOT NULL,
                element_type                INTEGER NOT NULL,
                now_cost                    INTEGER NOT NULL,
                original_cost               INTEGER,
                total_points                INTEGER DEFAULT 0,
                form                        REAL DEFAULT 0.0,
                points_per_game             REAL DEFAULT 0.0,
                selected_by_percent         REAL DEFAULT 0.0,
                minutes                     INTEGER DEFAULT 0,
                goals_scored                INTEGER DEFAULT 0,
                assists                     INTEGER DEFAULT 0,
                clean_sheets                INTEGER DEFAULT 0,
                goals_conceded              INTEGER DEFAULT 0,
                own_goals                   INTEGER DEFAULT 0,
                penalties_saved             INTEGER DEFAULT 0,
                penalties_missed            INTEGER DEFAULT 0,
                yellow_cards                INTEGER DEFAULT 0,
                red_cards                   INTEGER DEFAULT 0,
                saves                       INTEGER DEFAULT 0,
                bonus                       INTEGER DEFAULT 0,
                bps                         INTEGER DEFAULT 0,
                influence                   REAL DEFAULT 0.0,
                creativity                  REAL DEFAULT 0.0,
                threat                      REAL DEFAULT 0.0,
                ict_index                   REAL DEFAULT 0.0,
                expected_goals              REAL DEFAULT 0.0,
                expected_assists            REAL DEFAULT 0.0,
                expected_goal_involvements  REAL DEFAULT 0.0,
                expected_goals_conceded     REAL DEFAULT 0.0,
                value_form                  REAL DEFAULT 0.0,
                value_season                REAL DEFAULT 0.0,
                ep_next                     REAL,
                ep_this                     REAL,
                status                      TEXT DEFAULT 'a',
                news                        TEXT DEFAULT '',
                news_added                  TIMESTAMP,
                chance_of_playing_next      INTEGER,
                chance_of_playing_this      INTEGER,
                transfers_in_event          INTEGER DEFAULT 0,
                transfers_out_event         INTEGER DEFAULT 0,
                photo                       TEXT,
                updated_at                  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (season_id) REFERENCES seasons(id),
                FOREIGN KEY (team_id) REFERENCES teams(id)
            );
            """)
            
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_players_team ON players(team_id);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_players_element_type ON players(element_type);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_players_now_cost ON players(now_cost);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_players_perf ON players(element_type, now_cost, selected_by_percent);")
            
            # 4. Gameweeks
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS gameweeks (
                id              INTEGER PRIMARY KEY,
                season_id       INTEGER NOT NULL,
                name            TEXT,
                deadline_time   TIMESTAMP NOT NULL,
                finished        BOOLEAN DEFAULT 0,
                is_current      BOOLEAN DEFAULT 0,
                is_next         BOOLEAN DEFAULT 0,
                average_score   REAL,
                highest_score   INTEGER,
                updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (season_id) REFERENCES seasons(id)
            );
            """)
            
            # 5. Fixtures
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS fixtures (
                id                  INTEGER PRIMARY KEY,
                season_id           INTEGER NOT NULL,
                gameweek_id         INTEGER,
                team_home_id        INTEGER NOT NULL,
                team_away_id        INTEGER NOT NULL,
                team_h_difficulty   INTEGER,
                team_a_difficulty   INTEGER,
                team_h_score        INTEGER,
                team_a_score        INTEGER,
                kickoff_time        TIMESTAMP,
                started             BOOLEAN DEFAULT 0,
                finished            BOOLEAN DEFAULT 0,
                finished_provisional BOOLEAN DEFAULT 0,
                updated_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (season_id) REFERENCES seasons(id),
                FOREIGN KEY (gameweek_id) REFERENCES gameweeks(id),
                FOREIGN KEY (team_home_id) REFERENCES teams(id),
                FOREIGN KEY (team_away_id) REFERENCES teams(id)
            );
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_fixtures_gameweek ON fixtures(gameweek_id);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_fixtures_teams ON fixtures(team_home_id, team_away_id);")
            
            # 6. Player GW Stats
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS player_gw_stats (
                id                          INTEGER PRIMARY KEY AUTOINCREMENT,
                player_id                   INTEGER NOT NULL,
                gameweek_id                 INTEGER NOT NULL,
                season_id                   INTEGER NOT NULL,
                minutes                     INTEGER DEFAULT 0,
                goals_scored                INTEGER DEFAULT 0,
                assists                     INTEGER DEFAULT 0,
                clean_sheets                INTEGER DEFAULT 0,
                goals_conceded              INTEGER DEFAULT 0,
                own_goals                   INTEGER DEFAULT 0,
                penalties_saved             INTEGER DEFAULT 0,
                penalties_missed            INTEGER DEFAULT 0,
                yellow_cards                INTEGER DEFAULT 0,
                red_cards                   INTEGER DEFAULT 0,
                saves                       INTEGER DEFAULT 0,
                bonus                       INTEGER DEFAULT 0,
                bps                         INTEGER DEFAULT 0,
                total_points                INTEGER DEFAULT 0,
                expected_goals              REAL DEFAULT 0.0,
                expected_assists            REAL DEFAULT 0.0,
                expected_goal_involvements  REAL DEFAULT 0.0,
                expected_goals_conceded     REAL DEFAULT 0.0,
                influence                   REAL DEFAULT 0.0,
                creativity                  REAL DEFAULT 0.0,
                threat                      REAL DEFAULT 0.0,
                ict_index                   REAL DEFAULT 0.0,
                value                       INTEGER,
                selected                    INTEGER,
                transfers_balance           INTEGER,
                opponent_team_id            INTEGER,
                was_home                    BOOLEAN,
                fixture_difficulty          INTEGER,
                UNIQUE(player_id, gameweek_id, season_id),
                FOREIGN KEY (player_id) REFERENCES players(id),
                FOREIGN KEY (gameweek_id) REFERENCES gameweeks(id),
                FOREIGN KEY (opponent_team_id) REFERENCES teams(id)
            );
            """)
            
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_pgw_player ON player_gw_stats(player_id);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_pgw_gameweek ON player_gw_stats(gameweek_id);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_pgw_player_season ON player_gw_stats(player_id, season_id);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_pgw_xgi ON player_gw_stats(player_id, gameweek_id, expected_goals, expected_assists);")

            # 7. User Profile
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_profile (
                id                  INTEGER PRIMARY KEY,
                email               TEXT,
                player_name         TEXT,
                team_name           TEXT,
                overall_points      INTEGER,
                overall_rank        INTEGER,
                season_id           INTEGER,
                updated_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (season_id) REFERENCES seasons(id)
            );
            """)
            
            # 8. User GW Picks
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_gw_picks (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                gameweek_id     INTEGER NOT NULL,
                player_id       INTEGER NOT NULL,
                position        INTEGER NOT NULL,
                multiplier      INTEGER DEFAULT 1,
                is_captain      BOOLEAN DEFAULT 0,
                is_vice_captain BOOLEAN DEFAULT 0,
                gw_points       INTEGER,
                gw_total_points INTEGER,
                gw_rank         INTEGER,
                gw_overall_rank INTEGER,
                gw_value        INTEGER,
                gw_bank         INTEGER,
                gw_transfers    INTEGER,
                gw_transfer_cost INTEGER DEFAULT 0,
                gw_points_on_bench INTEGER,
                active_chip     TEXT,
                UNIQUE(gameweek_id, player_id),
                FOREIGN KEY (gameweek_id) REFERENCES gameweeks(id),
                FOREIGN KEY (player_id) REFERENCES players(id)
            );
            """)
            
            # 9. User Transfers
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_transfers (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                gameweek_id     INTEGER NOT NULL,
                player_in_id    INTEGER NOT NULL,
                player_out_id   INTEGER NOT NULL,
                player_in_cost  INTEGER NOT NULL,
                player_out_cost INTEGER NOT NULL,
                transfer_time   TIMESTAMP,
                FOREIGN KEY (gameweek_id) REFERENCES gameweeks(id),
                FOREIGN KEY (player_in_id) REFERENCES players(id),
                FOREIGN KEY (player_out_id) REFERENCES players(id)
            );
            """)
            
            # 10. Chip Usage
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS chip_usage (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                season_id       INTEGER NOT NULL,
                chip_name       TEXT NOT NULL,
                gameweek_id     INTEGER,
                half            INTEGER,
                status          TEXT DEFAULT 'available',
                FOREIGN KEY (season_id) REFERENCES seasons(id),
                FOREIGN KEY (gameweek_id) REFERENCES gameweeks(id)
            );
            """)
            
            # 11. Price Changes
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS price_changes (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                player_id       INTEGER NOT NULL,
                old_price       INTEGER NOT NULL,
                new_price       INTEGER NOT NULL,
                change_date     DATE NOT NULL,
                FOREIGN KEY (player_id) REFERENCES players(id)
            );
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_price_player ON price_changes(player_id);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_price_date ON price_changes(change_date);")
            
            # 12. Player ID Mapping
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS player_id_mapping (
                fpl_id          INTEGER PRIMARY KEY,
                understat_id    INTEGER,
                fbref_id        TEXT,
                matched_name    TEXT,
                confidence      REAL DEFAULT 1.0,
                FOREIGN KEY (fpl_id) REFERENCES players(id)
            );
            """)
            
            # 13. Player Locks
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS player_locks (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                player_id       INTEGER NOT NULL UNIQUE,
                lock_type       TEXT NOT NULL,
                reason          TEXT,
                created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expires_gw      INTEGER,
                FOREIGN KEY (player_id) REFERENCES players(id)
            );
            """)
            
            # 14. Recommendation History
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS recommendation_history (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                gameweek_id     INTEGER NOT NULL,
                recommendation_type TEXT NOT NULL,
                recommendation_json TEXT NOT NULL,
                xp_score        REAL,
                was_accepted    BOOLEAN,
                actual_outcome  REAL,
                created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (gameweek_id) REFERENCES gameweeks(id)
            );
            """)
            
            # 15. API Cache Meta
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS api_cache_meta (
                endpoint        TEXT PRIMARY KEY,
                last_fetched    TIMESTAMP NOT NULL,
                ttl_seconds     INTEGER NOT NULL,
                response_hash   TEXT,
                status          TEXT DEFAULT 'ok'
            );
            """)

            # 16. API Cache Data
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS api_cache_data (
                endpoint        TEXT PRIMARY KEY,
                json_data       TEXT NOT NULL,
                FOREIGN KEY (endpoint) REFERENCES api_cache_meta(endpoint)
            );
            """)

            # 17. Transfer Velocity Log
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS transfer_velocity_log (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                player_id       INTEGER NOT NULL,
                timestamp       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                transfers_in    INTEGER NOT NULL,
                transfers_out   INTEGER NOT NULL,
                net_velocity    REAL NOT NULL,
                price_at_time   INTEGER NOT NULL,
                rise_prob       REAL,
                fall_prob       REAL,
                FOREIGN KEY (player_id) REFERENCES players(id)
            );
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_velocity_player ON transfer_velocity_log(player_id);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_velocity_time ON transfer_velocity_log(timestamp);")

            # 18. Strategic Decision History
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS decision_history (
                id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                gameweek_id         INTEGER NOT NULL,
                scenario_name       TEXT NOT NULL,
                transfers_json      TEXT NOT NULL,
                objective_value     REAL,
                net_xp_predicted    REAL,
                net_xp_actual       REAL,
                was_accepted        BOOLEAN DEFAULT 0,
                created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (gameweek_id) REFERENCES gameweeks(id)
            );
            """)

            # 19. Set-Piece Takers Hierarchy Registry (20 PL Clubs)
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS set_piece_takers (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                team_id         INTEGER NOT NULL,
                category        TEXT NOT NULL, -- 'penalty', 'corner', 'freekick'
                rank_order      INTEGER NOT NULL, -- 1 = Primary, 2 = Secondary, 3 = Tertiary
                player_name     TEXT NOT NULL,
                fpl_player_id   INTEGER,
                updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(team_id, category, rank_order)
            );
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_set_piece_team ON set_piece_takers(team_id, category);")

            conn.commit()
            app_logger.info("Database schema initialized with Set-Piece Hierarchy & Compound Time-Series Indexes.")

db_manager = DatabaseManager()
