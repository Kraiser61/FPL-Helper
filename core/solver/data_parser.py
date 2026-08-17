import csv
import json
import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from unicodedata import combining, normalize

import numpy as np
import pandas as pd
from fuzzywuzzy import fuzz
from loguru import logger

from core.solver.paths import DATA_DIR
from core.solver.utils import cached_request


def read_data(options: Dict[str, Any], source: Optional[str] = None) -> pd.DataFrame:
    """
    Reads and prepares projection data from single or mixed CSV files.
    Supports Solio, FPLReview, Mikkel, and custom formats.
    """
    # Check if a direct file path was provided
    direct_path = options.get("data_path") or options.get("csv_file_path")
    if direct_path:
        file_path = Path(direct_path)
        if not file_path.exists():
            raise FileNotFoundError(f"Projeksiyon CSV dosyası bulunamadı: {file_path}")
        return _read_single_file(file_path, options)

    source = source or options.get("datasource", "projections")
    weights = options.get("data_weights", {})

    if source == "mixed":
        return read_mixed(options, weights)

    # Search in DATA_DIR for the matching CSV or the latest CSV
    list_of_files = [x for x in os.listdir(DATA_DIR) if x.endswith(".csv")]

    target_filename = f"{source}.csv" if not source.endswith(".csv") else source
    target_path = DATA_DIR / target_filename

    if target_path.exists() and target_path.stat().st_size > 500:
        return _read_single_file(target_path, options)

    if list_of_files:
        valid_files = [DATA_DIR / x for x in list_of_files if (DATA_DIR / x).stat().st_size > 500]
        if valid_files:
            latest_file = max(valid_files, key=os.path.getctime)
            logger.info(f"Belirtilen kaynak ({source}) bulunamadı, en son CSV kullanılıyor: {latest_file}")
            return _read_single_file(latest_file, options)

    # Automatically generate live built-in projections
    from core.solver.projection_generator import generate_builtin_projections
    generated_path = generate_builtin_projections(horizon_gws=int(options.get("horizon", 8)))
    return _read_single_file(generated_path, options)


def validate_and_import_projection_csv(
    source_path: str | Path,
    target_name: str = "projections.csv",
) -> Dict[str, Any]:
    """
    Validates an external projection CSV file and imports it to the application data directory.

    Args:
        source_path: Path to the selected CSV file.
        target_name: Destination filename in DATA_DIR.

    Returns:
        Dictionary containing validation status, player count, detected gameweeks, and metadata.
    """
    path = Path(source_path)
    if not path.exists():
        raise FileNotFoundError(f"Seçilen dosya bulunamadı: {path}")

    if not path.name.lower().endswith(".csv"):
        raise ValueError("Seçilen dosya bir .csv dosyası olmalıdır.")

    DATA_DIR.mkdir(parents=True, exist_ok=True)

    # Attempt parsing with options
    options: Dict[str, Any] = {"datasource": path.stem}
    df = _read_single_file(path, options)

    if df.empty:
        raise ValueError("Yüklenen CSV dosyası boş veya hiçbir geçerli oyuncu satırı içermiyor.")

    # Detect gameweeks
    pts_cols = [c for c in df.columns if "_Pts" in c]
    detected_gws: List[int] = []
    for col in pts_cols:
        gw_prefix = col.split("_")[0]
        if gw_prefix.isdigit():
            detected_gws.append(int(gw_prefix))
    detected_gws = sorted(list(set(detected_gws)))

    if not detected_gws:
        raise ValueError(
            "CSV dosyasında geçerli hafta puan sütunları (örn: 1_Pts, 2_Pts veya sayısal hafta başlıkları) tespit edilemedi."
        )

    # Copy to DATA_DIR
    target_file = DATA_DIR / target_name
    shutil.copyfile(path, target_file)

    meta = {
        "is_valid": True,
        "filename": target_name,
        "original_name": path.name,
        "file_path": str(target_file),
        "player_count": len(df),
        "gameweeks": detected_gws,
        "gw_range_str": f"GW{min(detected_gws)} - GW{max(detected_gws)}" if detected_gws else "Bilinmiyor",
        "updated_at": datetime.now().strftime("%d.%m.%Y %H:%M:%S"),
        "size_kb": round(target_file.stat().st_size / 1024, 1),
    }

    # Save metadata JSON
    meta_path = DATA_DIR / "projection_meta.json"
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2, ensure_ascii=False)

    logger.success(f"Projeksiyon CSV dosyası başarıyla içe aktarıldı: {meta}")
    return meta


def get_active_projection_metadata() -> Dict[str, Any]:
    """
    Returns metadata for the currently active projection file in DATA_DIR, or None state.
    """
    meta_path = DATA_DIR / "projection_meta.json"
    target_file = DATA_DIR / "projections.csv"

    if meta_path.exists():
        try:
            with open(meta_path, "r", encoding="utf-8") as f:
                meta = json.load(f)
                if Path(meta.get("file_path", "")).exists():
                    return meta
        except Exception as e:
            logger.warning(f"Meta dosyası okunamadı: {e}")

    if target_file.exists():
        try:
            df = pd.read_csv(target_file)
            pts_cols = [c for c in df.columns if "_Pts" in c]
            detected_gws = sorted([int(c.split("_")[0]) for c in pts_cols if c.split("_")[0].isdigit()])
            return {
                "is_valid": True,
                "filename": target_file.name,
                "original_name": target_file.name,
                "file_path": str(target_file),
                "player_count": len(df),
                "gameweeks": detected_gws,
                "gw_range_str": f"GW{min(detected_gws)} - GW{max(detected_gws)}" if detected_gws else "Bilinmiyor",
                "updated_at": datetime.fromtimestamp(target_file.stat().st_mtime).strftime("%d.%m.%Y %H:%M:%S"),
                "size_kb": round(target_file.stat().st_size / 1024, 1),
            }
        except Exception:
            pass

    return {
        "is_valid": False,
        "filename": None,
        "original_name": None,
        "file_path": None,
        "player_count": 0,
        "gameweeks": [],
        "gw_range_str": "Yok",
        "updated_at": None,
        "size_kb": 0,
    }


def _read_single_file(filepath: Path, options: Dict[str, Any]) -> pd.DataFrame:
    """Attempts to read a single CSV file with various parser strategies."""
    readers = [read_solio_or_review, read_mikkel]
    errors: List[str] = []

    for reader in readers:
        try:
            df = reader(filepath, options)
            if df is not None and not df.empty:
                # Normalize position codes
                if "Pos" in df.columns:
                    df["Pos"] = df["Pos"].replace({
                        "GKP": "G", "GK": "G", "DEF": "D", "MID": "M", "FWD": "F"
                    })
                elif "Position" in df.columns:
                    df["Pos"] = df["Position"].replace({
                        "GKP": "G", "GK": "G", "DEF": "D", "MID": "M", "FWD": "F"
                    })
                return df
        except Exception as e:
            errors.append(f"{reader.__name__}: {e}")

    raise RuntimeError(
        f"CSV dosyası okunamadı ({filepath.name}). Karşılaşılan hatalar:\n" + "\n".join(errors)
    )


def read_solio_or_review(filepath: Path, options: Dict[str, Any]) -> pd.DataFrame:
    """Reads Solio or FPLReview formatted CSV file."""
    for enc in ["utf-8", "utf-8-sig", "latin-1"]:
        try:
            df = pd.read_csv(filepath, encoding=enc)
            df.columns = [col.strip() for col in df.columns]
            return df
        except Exception:
            continue
    raise ValueError("CSV dosyası UTF-8 veya Latin-1 kodlamasıyla okunamadı.")


def read_mikkel(filepath: Path, options: Dict[str, Any]) -> pd.DataFrame:
    """Reads Mikkel formatted CSV file and transforms it to Review standard."""
    output_file = DATA_DIR / "mikkel_cleaned.csv"
    convert_mikkel_to_review(filepath, output_file=output_file)
    return pd.read_csv(output_file, encoding="utf-8")


def read_mixed(options: Dict[str, Any], weights: Dict[str, float]) -> pd.DataFrame:
    """Merges projection data from multiple sources according to provided weights."""
    all_data: List[pd.DataFrame] = []
    for name, weight in weights.items():
        if weight <= 0:
            continue
        sub_opts = dict(options)
        sub_opts["datasource"] = name
        df = read_data(sub_opts)

        first_gw_col = next((col for col in df.columns if "_Pts" in col), None)
        if first_gw_col:
            df = df[~df[first_gw_col].isnull()].copy()

        for col in df.columns:
            if "_Pts" in col:
                df[col.split("_")[0] + "_weight"] = weight

        all_data.append(df)

    if not all_data:
        raise ValueError("Ağırlıklandırılacak hiçbir geçerli veri kaynağı bulunamadı.")

    for i, d in enumerate(all_data):
        for col in d.columns:
            if "_xMins" in col:
                d[col] = pd.to_numeric(d[col], errors="coerce").fillna(0).astype(int)
        all_data[i] = d

    new_data: List[pd.DataFrame] = []
    for d in all_data:
        pts_columns = [i for i in d.columns if "_Pts" in i]
        min_columns = [i for i in d.columns if "_xMins" in i]
        weights_cols = [i.split("_")[0] + "_weight" for i in pts_columns]

        d[pts_columns] = pd.DataFrame(
            d[pts_columns].values * d[weights_cols].values,
            columns=d[pts_columns].columns,
            index=d[pts_columns].index,
        )
        min_weights_cols = [i.split("_")[0] + "_weight" for i in min_columns]
        d[min_columns] = pd.DataFrame(
            d[min_columns].values * d[min_weights_cols].values,
            columns=d[min_columns].columns,
            index=d[min_columns].index,
        )
        new_data.append(d.copy())

    combined_data = pd.concat(new_data, ignore_index=True)
    combined_data["real_id"] = combined_data["ID"]
    combined_data = combined_data.reset_index(drop=True)

    key_dict: Dict[str, str] = {}
    for i in combined_data.columns.to_list():
        if "_weight" in i or "_xMins" in i or "_Pts" in i:
            key_dict[i] = "sum"
        else:
            key_dict[i] = "first"

    grouped_data = combined_data.groupby("real_id").agg(key_dict)
    final_data = grouped_data[grouped_data["ID"] != 0].copy()

    for c in final_data.columns:
        if "_Pts" in c or "_xMins" in c:
            gw = c.split("_")[0]
            final_data[c] = final_data[c] / final_data[gw + "_weight"]

    try:
        fpl_data = cached_request("https://fantasy.premierleague.com/api/bootstrap-static/")
        players = fpl_data.get("elements", [])
        existing_ids = final_data["ID"].tolist()
        element_type_dict = {1: "G", 2: "D", 3: "M", 4: "F"}
        teams = fpl_data.get("teams", [])
        team_code_dict = {i["code"]: i for i in teams}

        missing_players = []
        for p in players:
            if p["id"] in existing_ids:
                continue
            missing_players.append(
                {
                    "fpl_id": p["id"],
                    "ID": p["id"],
                    "real_id": p["id"],
                    "team": "",
                    "Name": p["web_name"],
                    "Pos": element_type_dict.get(p["element_type"], "M"),
                    "Value": p["now_cost"] / 10,
                    "Team": team_code_dict.get(p["team_code"], {}).get("name", ""),
                    "Missing": 1,
                }
            )

        if missing_players:
            final_data = pd.concat([final_data, pd.DataFrame(missing_players)]).fillna(0)
    except Exception as e:
        logger.warning(f"FPL API üzerinden eksik oyuncu senkronizasyonu yapılamadı: {e}")

    export_path = DATA_DIR / options.get("export_data", "mixed.csv")
    final_data.to_csv(export_path, index=False, encoding="utf-8", float_format="%.2f")

    return final_data


def fix_name_dialect(name: str) -> str:
    """Removes accents and special characters from player names."""
    if not isinstance(name, str):
        return ""
    new_name = "".join([c for c in normalize("NFKD", name) if not combining(c)])
    return (
        new_name.replace("Ø", "O")
        .replace("ø", "o")
        .replace("ã", "a")
        .replace("é", "e")
        .replace("á", "a")
        .replace("í", "i")
        .replace("ó", "o")
        .replace("ú", "u")
        .replace("ñ", "n")
    )


def fix_mikkel(file_address: Path) -> pd.DataFrame:
    """Parses Mikkel's format with CSV Sniffer and fuzzy name matching."""
    df = None
    for enc in ["utf-8", "latin-1"]:
        try:
            with open(file_address, "r", encoding=enc, errors="replace") as f:
                first_line = f.readline()
                delimiter = "," if "," in first_line else ";"
                df = pd.read_csv(file_address, encoding=enc, sep=delimiter)
            break
        except Exception:
            continue

    if df is None:
        raise ValueError(f"Mikkel CSV dosyası okunamadı: {file_address}")

    fpl_data = cached_request("https://fantasy.premierleague.com/api/bootstrap-static/")
    players = fpl_data["elements"]
    mikkel_team_dict = {
        "BHA": "BRI",
        "CRY": "CPL",
        "NFO": "NOT",
        "WHU": "WHM",
    }
    teams = fpl_data["teams"]
    for t in teams:
        t["mikkel_short"] = mikkel_team_dict.get(t["short_name"], t["short_name"])

    df = df.rename(columns={x: str(x).strip() for x in df.columns})
    if "BCV" in df.columns:
        df["BCV_clean"] = df["BCV"].astype(str).str.replace(r"\((.*)\)", "-\\1", regex=True).astype(str).str.strip()
        df["BCV_numeric"] = pd.to_numeric(df["BCV_clean"], errors="coerce")
        df = df.loc[df["BCV_numeric"] != -1]
        df_cleaned = df.loc[~((df["Player"] == "0") | (df["No."].isnull()) | (df["BCV_numeric"].isnull()))].copy()
    else:
        df_cleaned = df.copy()

    df_cleaned["Clean_Name"] = df_cleaned["Player"].apply(fix_name_dialect)
    df_cleaned["Position"] = df_cleaned["Position"].replace({"GK": "G", "GKP": "G"})
    df_cleaned = df_cleaned.dropna(subset=["Team"])

    element_type_dict = {1: "G", 2: "D", 3: "M", 4: "F"}
    team_code_dict = {i["code"]: i for i in teams}
    player_names = [
        {
            "id": e["id"],
            "web_name": e["web_name"],
            "combined": e["first_name"] + " " + e["second_name"],
            "team": team_code_dict[e["team_code"]]["mikkel_short"],
            "position": element_type_dict[e["element_type"]],
        }
        for e in players
    ]
    for target in player_names:
        target["wn"] = fix_name_dialect(target["web_name"])
        target["cn"] = fix_name_dialect(target["combined"])

    entries: List[Dict[str, Any]] = []
    for player in df_cleaned.iloc:
        possible_matches = [
            i for i in player_names
            if i["team"] == player["Team"] and i["position"] == player["Position"]
        ]
        if not possible_matches:
            possible_matches = [i for i in player_names if i["position"] == player["Position"]]

        for target in possible_matches:
            p = player["Clean_Name"]
            target["wn_score"] = fuzz.token_set_ratio(p, target["wn"])
            target["cn_score"] = fuzz.token_set_ratio(p, target["cn"])

        best_match = max(possible_matches, key=lambda r: max(r.get("wn_score", 0), r.get("cn_score", 0)))
        entries.append({
            "player_input": player["Player"],
            "team_input": player["Team"],
            "position_input": player["Position"],
            **best_match,
        })

    entries_df = pd.DataFrame(entries)
    entries_df["score"] = entries_df[["wn_score", "cn_score"]].max(axis=1)
    entries_df["name_team"] = entries_df["player_input"] + " @ " + entries_df["team_input"]
    entry_dict = entries_df.set_index("name_team")["id"].to_dict()
    fpl_name_dict = entries_df.set_index("id")["web_name"].to_dict()
    score_dict = entries_df.set_index("name_team")["score"].to_dict()

    df_cleaned["name_team"] = df_cleaned["Player"] + " @ " + df_cleaned["Team"]
    df_cleaned["FPL ID"] = df_cleaned["name_team"].map(entry_dict)
    df_cleaned["fpl_name"] = df_cleaned["FPL ID"].map(fpl_name_dict)
    df_cleaned["score"] = df_cleaned["name_team"].map(score_dict)

    df_cleaned = df_cleaned.sort_values(by=["score"], ascending=False)
    df_cleaned = df_cleaned.loc[~df_cleaned["FPL ID"].duplicated(keep="first")].sort_index()

    return df_cleaned


def convert_mikkel_to_review(target: Path, output_file: Path) -> None:
    """Converts Mikkel's raw CSV to unified review structure."""
    df = fix_mikkel(target)
    fpl_data = cached_request("https://fantasy.premierleague.com/api/bootstrap-static/")
    teams = fpl_data["teams"]

    new_names = {i: str(i).strip() for i in df.columns}
    df = df.rename(columns=new_names)
    df["Price"] = pd.to_numeric(df.get("Price", 5.0), errors="coerce").fillna(5.0)
    df["Weighted minutes"] = df.get("Weighted minutes", 90).fillna(90)
    df["ID"] = df["FPL ID"].fillna(0).astype(int)

    df["Pos"] = df["Position"].replace({"GK": "G", "GKP": "G"})
    df.loc[df["Pos"].isin(["G", "D"]), "Weighted minutes"] = 90

    gws: List[str] = []
    for i in df.columns:
        try:
            int(i)
            df[f"{i}_Pts"] = df[i].astype(str).str.strip().replace({"-": "0"}).astype(float)
            df[f"{i}_xMins"] = (
                df["Weighted minutes"]
                .astype(str)
                .str.strip()
                .replace({"-": "0"})
                .astype(float)
                .fillna(0)
            )
            gws.append(str(i))
        except Exception:
            continue

    df["Name"] = df["Player"]
    df["Value"] = df["Price"]

    df_final = df[["ID", "Name", "Pos", "Value"] + [f"{gw}_{tag}" for gw in gws for tag in ["Pts", "xMins"]]].copy()
    elements_data = fpl_data["elements"]
    team_dict = {i["code"]: i["name"] for i in teams}
    player_teams = {i["id"]: team_dict.get(i["team_code"], "") for i in elements_data}
    player_names = {i["id"]: i["web_name"] for i in elements_data}

    df_final["Team"] = df_final["ID"].map(player_teams)
    df_final["fpl_id"] = df_final["ID"]
    df_final["Name"] = df_final["ID"].map(player_names).fillna(df_final["Name"])

    output_file.parent.mkdir(parents=True, exist_ok=True)
    df_final.to_csv(output_file, index=False, encoding="utf-8", float_format="%.2f")
