import argparse
import ast
import gzip
import hashlib
import logging
import re
import sys
import time
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, BinaryIO, List, Optional, Set

import pandas as pd
import pyshacl
from rdflib import Graph

# Base IRIs
NS_RDF = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"
NS_RDFS = "http://www.w3.org/2000/01/rdf-schema#"
NS_OWL = "http://www.w3.org/2002/07/owl#"
NS_XSD = "http://www.w3.org/2001/XMLSchema#"
NS_DCTERMS = "http://purl.org/dc/terms/"
NS_DCAT = "http://www.w3.org/ns/dcat#"
NS_FOAF = "http://xmlns.com/foaf/0.1/"
NS_MO = "http://purl.org/ontology/mo/"
NS_SPOTIFY = "https://w3id.org/spotify-kg/ontology#"
NS_RES = "https://w3id.org/spotify-kg/resource/"
NS_WD = "http://www.wikidata.org/entity/"

# XSD Datatype IRIs
DT_STRING = f"<{NS_XSD}string>"
DT_INTEGER = f"<{NS_XSD}integer>"
DT_NON_NEG_INT = f"<{NS_XSD}nonNegativeInteger>"
DT_DECIMAL = f"<{NS_XSD}decimal>"
DT_BOOLEAN = f"<{NS_XSD}boolean>"
DT_DATE = f"<{NS_XSD}date>"
DT_GYEAR_MONTH = f"<{NS_XSD}gYearMonth>"
DT_GYEAR = f"<{NS_XSD}gYear>"
DT_DATETIME = f"<{NS_XSD}dateTime>"

# Predicates & Classes
RDF_TYPE = f"<{NS_RDF}type>"
RDFS_LABEL = f"<{NS_RDFS}label>"
OWL_SAME_AS = f"<{NS_OWL}sameAs>"
FOAF_NAME = f"<{NS_FOAF}name>"
DCAT_DATASET = f"<{NS_DCAT}Dataset>"
DCT_TITLE = f"<{NS_DCTERMS}title>"
DCT_IDENTIFIER = f"<{NS_DCTERMS}identifier>"
DCT_ISSUED = f"<{NS_DCTERMS}issued>"
DCT_LICENSE = f"<{NS_DCTERMS}license>"
DCT_SOURCE = f"<{NS_DCTERMS}source>"

MO_TRACK = f"<{NS_MO}Track>"
MO_ARTIST = f"<{NS_MO}MusicArtist>"
MO_RECORD = f"<{NS_MO}Record>"
MO_GENRE = f"<{NS_MO}Genre>"
MO_TRACK_PRED = f"<{NS_MO}track>"
MO_GENRE_PRED = f"<{NS_MO}genre>"
MO_DURATION = f"<{NS_MO}duration>"
MO_TRACK_NUM = f"<{NS_MO}track_number>"
MO_TRACK_COUNT = f"<{NS_MO}track_count>"
MO_RELEASE_TYPE = f"<{NS_MO}release_type>"

SP_CHART_ENTRY = f"<{NS_SPOTIFY}ChartEntry>"
SP_MARKET = f"<{NS_SPOTIFY}Market>"
SP_CREDITED_ARTIST = f"<{NS_SPOTIFY}creditedArtist>"
SP_HAS_CHART_ENTRY = f"<{NS_SPOTIFY}hasChartEntry>"
SP_AVAILABLE_IN = f"<{NS_SPOTIFY}availableIn>"
SP_STREAMS = f"<{NS_SPOTIFY}streams>"
SP_EXPLICIT = f"<{NS_SPOTIFY}explicit>"
SP_ADDED_AT = f"<{NS_SPOTIFY}addedAt>"
SP_POPULARITY = f"<{NS_SPOTIFY}popularity>"
SP_KEY = f"<{NS_SPOTIFY}key>"
SP_MODE = f"<{NS_SPOTIFY}mode>"
SP_TIME_SIG = f"<{NS_SPOTIFY}timeSignature>"
SP_TEMPO = f"<{NS_SPOTIFY}tempo>"
SP_ENERGY = f"<{NS_SPOTIFY}energy>"
SP_SPEECHINESS = f"<{NS_SPOTIFY}speechiness>"
SP_DANCEABILITY = f"<{NS_SPOTIFY}danceability>"
SP_VALENCE = f"<{NS_SPOTIFY}valence>"
SP_ACOUSTICNESS = f"<{NS_SPOTIFY}acousticness>"
SP_LIVENESS = f"<{NS_SPOTIFY}liveness>"
SP_INSTRUMENTALNESS = f"<{NS_SPOTIFY}instrumentalness>"
SP_LOUDNESS = f"<{NS_SPOTIFY}loudness>"
SP_ARTIST_FOLLOWERS = f"<{NS_SPOTIFY}artistFollowers>"
SP_ARTIST_POP = f"<{NS_SPOTIFY}artistPopularity>"
SP_CHART_NAME = f"<{NS_SPOTIFY}chartName>"
SP_RANK = f"<{NS_SPOTIFY}rank>"
SP_CHART_REGION = f"<{NS_SPOTIFY}chartRegion>"
SP_POS_CHANGE = f"<{NS_SPOTIFY}positionChange>"
SP_MARKET_CODE = f"<{NS_SPOTIFY}marketCode>"

MARKET_WIKIDATA = {
    "AR": "Q414", "AU": "Q408", "AT": "Q40",  "BE": "Q31",  "BR": "Q155",
    "CA": "Q16",  "CH": "Q39",  "CL": "Q298", "CO": "Q739", "CZ": "Q213",
    "DE": "Q183", "DK": "Q35",  "ES": "Q29",  "FI": "Q33",  "FR": "Q142",
    "GB": "Q145", "GR": "Q41",  "HK": "Q8646","HU": "Q28",  "ID": "Q252",
    "IE": "Q27",  "IL": "Q801", "IN": "Q668", "IT": "Q38",  "JP": "Q17",
    "KR": "Q884", "MX": "Q96",  "MY": "Q833", "NL": "Q55",  "NO": "Q20",
    "NZ": "Q664", "PE": "Q419", "PH": "Q928", "PL": "Q36",  "PT": "Q45",
    "RO": "Q218", "RU": "Q159", "SA": "Q851", "SE": "Q34",  "SG": "Q334",
    "TH": "Q869", "TR": "Q43",  "TW": "Q865", "UA": "Q212", "US": "Q30",
    "VN": "Q881", "ZA": "Q258",
}

RELEASE_TYPE_MAP = {
    "album": f"<{NS_MO}album>",
    "single": f"<{NS_MO}single>",
    "compilation": f"<{NS_MO}compilation>",
}

CATEGORICAL_TRENDS = {"MOVE_UP", "MOVE_DOWN", "SAME_POSITION", "NEW_ENTRY", "NO_CHANGE"}
SLUG_RE = re.compile(r"[^a-zA-Z0-9_-]+")
DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
GYM_RE = re.compile(r"\d{4}-\d{2}")
GY_RE = re.compile(r"\d{4}")
DT_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}")


def setup_issues_logger(log_path: Path) -> logging.Logger:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("pipeline_issues")
    logger.setLevel(logging.WARNING)
    logger.handlers.clear()
    fh = logging.FileHandler(log_path, mode="w", encoding="utf-8")
    fh.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(message)s"))
    logger.addHandler(fh)
    return logger


def nt_lit(value: str, datatype_iri: str) -> str:
    escaped = (
        value.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", "\\n")
        .replace("\r", "\\r")
        .replace("\t", "\\t")
    )
    return f'"{escaped}"^^{datatype_iri}'


def is_missing(val: Any) -> bool:
    if val is None:
        return True
    if isinstance(val, float) and val != val:  # fast NaN check
        return True
    s = str(val).strip()
    return s == "" or s.lower() in {"nan", "none", "null", "na"}


def stable_slug(text: str) -> str:
    cleaned = SLUG_RE.sub("-", text.strip().lower()).strip("-")
    if cleaned:
        return cleaned[:80]
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:16]


def stable_hash_id(*parts: str) -> str:
    joined = "||".join(p.strip().lower() for p in parts)
    return hashlib.sha1(joined.encode("utf-8")).hexdigest()[:16]


def compact_key(iri: str) -> int:
    return int.from_bytes(hashlib.blake2b(iri.encode("utf-8"), digest_size=8).digest(), "big")


def parse_multi_value(raw: Any) -> List[str]:
    if is_missing(raw):
        return []
    text = str(raw).strip()
    if text.startswith("[") and text.endswith("]"):
        try:
            parsed = ast.literal_eval(text)
            if isinstance(parsed, list):
                return [str(x).strip() for x in parsed if not is_missing(x)]
        except (ValueError, SyntaxError, TypeError):
            inner = text[1:-1].strip()
            if not inner:
                return []
            sep = ";" if ";" in inner else ","
            return [
                item.strip().strip("'\"")
                for item in inner.split(sep)
                if not is_missing(item.strip().strip("'\""))
            ]
    sep = ";" if ";" in text else ","
    return [item.strip() for item in text.split(sep) if not is_missing(item)]


def parse_int(raw: Any, issues: logging.Logger, row_id: str, col: str) -> Optional[int]:
    if is_missing(raw):
        return None
    try:
        return int(float(str(raw).strip()))
    except ValueError:
        issues.warning(f"track={row_id} | col={col} | Invalid integer value: {raw!r}")
        return None


def parse_decimal(raw: Any, issues: logging.Logger, row_id: str, col: str) -> Optional[str]:
    if is_missing(raw):
        return None
    try:
        dec = Decimal(str(raw).strip())
        if not dec.is_finite():
            raise InvalidOperation()
        return str(dec)
    except InvalidOperation:
        issues.warning(f"track={row_id} | col={col} | Invalid decimal value: {raw!r}")
        return None


def parse_bool(raw: Any, issues: logging.Logger, row_id: str, col: str) -> Optional[str]:
    if is_missing(raw):
        return None
    s = str(raw).strip().lower()
    if s in {"true", "1", "yes", "t"}:
        return "true"
    if s in {"false", "0", "no", "f"}:
        return "false"
    issues.warning(f"track={row_id} | col={col} | Invalid boolean value: {raw!r}")
    return None


def parse_release_date(raw: Any, issues: logging.Logger, row_id: str) -> Optional[tuple[str, str]]:
    if is_missing(raw):
        return None
    s = str(raw).strip()
    if DATE_RE.fullmatch(s):
        return (s, DT_DATE)
    if GYM_RE.fullmatch(s):
        return (s, DT_GYEAR_MONTH)
    if GY_RE.fullmatch(s):
        return (s, DT_GYEAR)
    issues.warning(f"track={row_id} | col=album_release_date | Unsupported date format: {s!r}")
    return None


def parse_datetime(raw: Any, issues: logging.Logger, row_id: str) -> Optional[str]:
    if is_missing(raw):
        return None
    s = str(raw).strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    s = s.replace(" ", "T")
    if DT_RE.match(s):
        return s
    issues.warning(f"track={row_id} | col=added_at | Invalid dateTime: {raw!r}")
    return None


def dataset_metadata_lines() -> List[str]:
    ds = f"<{NS_RES}dataset/spotify-tracks-kg>"
    return [
        f"{ds} {RDF_TYPE} {DCAT_DATASET} .\n",
        f"{ds} {DCT_TITLE} {nt_lit('Almost a Million Spotify Tracks — 5-Star Knowledge Graph', DT_STRING)} .\n",
        f"{ds} {DCT_LICENSE} <https://creativecommons.org/licenses/by/4.0/> .\n",
        f"{ds} {DCT_SOURCE} <https://zenodo.org/records/11453410> .\n",
        f"{ds} {DCT_ISSUED} {nt_lit(date.today().isoformat(), DT_DATE)} .\n",
    ]


def process_chunk(
    chunk_df: pd.DataFrame,
    row_offset: int,
    issues: logging.Logger,
    seen_artists: Set[int],
    seen_albums: Set[int],
    seen_genres: Set[int],
    seen_markets: Set[int],
    include_metadata: bool,
    collect_validation_lines: bool,
) -> tuple[List[str], List[str]]:
    out_lines: List[str] = []
    val_lines: List[str] = []

    if include_metadata:
        meta = dataset_metadata_lines()
        out_lines.extend(meta)
        if collect_validation_lines:
            val_lines.extend(meta)

    for i, row in enumerate(chunk_df.to_dict(orient="records")):
        row_num = row_offset + i
        if is_missing(row.get("track_id")):
            issues.warning(f"row={row_num} | Missing required track_id; skipping row.")
            continue

        track_id = str(row["track_id"]).strip()
        t_iri = f"<{NS_RES}track/{stable_slug(track_id)}>"
        row_lines = [
            f"{t_iri} {RDF_TYPE} {MO_TRACK} .\n",
            f"{t_iri} {DCT_IDENTIFIER} {nt_lit(track_id, DT_STRING)} .\n",
        ]

        if not is_missing(row.get("name")):
            row_lines.append(f"{t_iri} {DCT_TITLE} {nt_lit(str(row['name']).strip(), DT_STRING)} .\n")

        for col, pred, min_v, max_v in [
            ("streams", SP_STREAMS, 0, None),
            ("popularity", SP_POPULARITY, 0, 100),
            ("key", SP_KEY, -1, 11),
            ("mode", SP_MODE, 0, 1),
            ("time_signature", SP_TIME_SIG, None, None),
        ]:
            val = parse_int(row.get(col), issues, track_id, col)
            if val is not None:
                if (min_v is not None and val < min_v) or (max_v is not None and val > max_v):
                    issues.warning(f"track={track_id} | col={col} | Out of range: {val}")
                else:
                    row_lines.append(f"{t_iri} {pred} {nt_lit(str(val), DT_INTEGER)} .\n")

        dur = parse_int(row.get("duration_ms"), issues, track_id, "duration_ms")
        if dur is not None and dur >= 0:
            row_lines.append(f"{t_iri} {MO_DURATION} {nt_lit(str(dur), DT_INTEGER)} .\n")

        tnum = parse_int(row.get("track_track_number"), issues, track_id, "track_track_number")
        if tnum is not None and tnum >= 0:
            row_lines.append(f"{t_iri} {MO_TRACK_NUM} {nt_lit(str(tnum), DT_NON_NEG_INT)} .\n")

        exp = parse_bool(row.get("explicit"), issues, track_id, "explicit")
        if exp is not None:
            row_lines.append(f"{t_iri} {SP_EXPLICIT} {nt_lit(exp, DT_BOOLEAN)} .\n")

        added = parse_datetime(row.get("added_at"), issues, track_id)
        if added is not None:
            row_lines.append(f"{t_iri} {SP_ADDED_AT} {nt_lit(added, DT_DATETIME)} .\n")

        for col, pred in [
            ("tempo", SP_TEMPO),
            ("energy", SP_ENERGY),
            ("speechiness", SP_SPEECHINESS),
            ("danceability", SP_DANCEABILITY),
            ("valence", SP_VALENCE),
            ("acousticness", SP_ACOUSTICNESS),
            ("liveness", SP_LIVENESS),
            ("instrumentalness", SP_INSTRUMENTALNESS),
            ("loudness", SP_LOUDNESS),
        ]:
            dec = parse_decimal(row.get(col), issues, track_id, col)
            if dec is not None:
                row_lines.append(f"{t_iri} {pred} {nt_lit(dec, DT_DECIMAL)} .\n")

        # Artists
        artists = parse_multi_value(row.get("track_artists"))
        artist_followers = parse_int(row.get("artist_followers"), issues, track_id, "artist_followers")
        artist_pop = parse_int(row.get("artist_popularity"), issues, track_id, "artist_popularity")

        for idx_a, artist_name in enumerate(artists):
            a_iri = f"<{NS_RES}artist/{stable_hash_id(artist_name)}>"
            row_lines.append(f"{t_iri} {SP_CREDITED_ARTIST} {a_iri} .\n")
            akey = compact_key(a_iri)
            if akey not in seen_artists:
                seen_artists.add(akey)
                row_lines.append(f"{a_iri} {RDF_TYPE} {MO_ARTIST} .\n")
                row_lines.append(f"{a_iri} {FOAF_NAME} {nt_lit(artist_name, DT_STRING)} .\n")
                if idx_a == 0:
                    if artist_followers is not None and artist_followers >= 0:
                        row_lines.append(f"{a_iri} {SP_ARTIST_FOLLOWERS} {nt_lit(str(artist_followers), DT_INTEGER)} .\n")
                    if artist_pop is not None and 0 <= artist_pop <= 100:
                        row_lines.append(f"{a_iri} {SP_ARTIST_POP} {nt_lit(str(artist_pop), DT_INTEGER)} .\n")
            elif collect_validation_lines:
                val_lines.append(f"{a_iri} {RDF_TYPE} {MO_ARTIST} .\n")
                val_lines.append(f"{a_iri} {FOAF_NAME} {nt_lit(artist_name, DT_STRING)} .\n")

        # Album
        if not is_missing(row.get("album_name")):
            album_name = str(row["album_name"]).strip()
            rel_date = parse_release_date(row.get("album_release_date"), issues, track_id)
            rel_key = rel_date[0] if rel_date else ""
            alb_iri = f"<{NS_RES}album/{stable_hash_id(album_name, rel_key)}>"

            row_lines.append(f"{alb_iri} {MO_TRACK_PRED} {t_iri} .\n")
            alb_key = compact_key(alb_iri)
            if alb_key not in seen_albums:
                seen_albums.add(alb_key)
                row_lines.append(f"{alb_iri} {RDF_TYPE} {MO_RECORD} .\n")
                row_lines.append(f"{alb_iri} {DCT_TITLE} {nt_lit(album_name, DT_STRING)} .\n")

                total_tracks = parse_int(row.get("album_total_tracks"), issues, track_id, "album_total_tracks")
                if total_tracks is not None and total_tracks >= 0:
                    row_lines.append(f"{alb_iri} {MO_TRACK_COUNT} {nt_lit(str(total_tracks), DT_INTEGER)} .\n")

                if rel_date is not None:
                    row_lines.append(f"{alb_iri} {DCT_ISSUED} {nt_lit(rel_date[0], rel_date[1])} .\n")

                if not is_missing(row.get("track_album_album")):
                    raw_type = str(row["track_album_album"]).strip().lower()
                    if raw_type in RELEASE_TYPE_MAP:
                        row_lines.append(f"{alb_iri} {MO_RELEASE_TYPE} {RELEASE_TYPE_MAP[raw_type]} .\n")
                    else:
                        issues.warning(f"track={track_id} | col=track_album_album | Unknown release type: {raw_type!r}")
            elif collect_validation_lines:
                val_lines.append(f"{alb_iri} {RDF_TYPE} {MO_RECORD} .\n")

        # Genres
        for genre_name in parse_multi_value(row.get("genres")):
            g_iri = f"<{NS_RES}genre/{stable_slug(genre_name)}>"
            row_lines.append(f"{t_iri} {MO_GENRE_PRED} {g_iri} .\n")
            gkey = compact_key(g_iri)
            if gkey not in seen_genres:
                seen_genres.add(gkey)
                row_lines.append(f"{g_iri} {RDF_TYPE} {MO_GENRE} .\n")
                row_lines.append(f"{g_iri} {RDFS_LABEL} {nt_lit(genre_name, DT_STRING)} .\n")
            elif collect_validation_lines:
                val_lines.append(f"{g_iri} {RDF_TYPE} {MO_GENRE} .\n")
                val_lines.append(f"{g_iri} {RDFS_LABEL} {nt_lit(genre_name, DT_STRING)} .\n")

        # Markets + Wikidata reconciliation
        for code in parse_multi_value(row.get("available_markets")):
            code_clean = code.upper()
            m_iri = f"<{NS_RES}market/{stable_slug(code_clean)}>"
            row_lines.append(f"{t_iri} {SP_AVAILABLE_IN} {m_iri} .\n")
            mkey = compact_key(m_iri)
            if mkey not in seen_markets:
                seen_markets.add(mkey)
                row_lines.append(f"{m_iri} {RDF_TYPE} {SP_MARKET} .\n")
                row_lines.append(f"{m_iri} {SP_MARKET_CODE} {nt_lit(code_clean, DT_STRING)} .\n")
                if code_clean in MARKET_WIKIDATA:
                    row_lines.append(f"{m_iri} {OWL_SAME_AS} <{NS_WD}{MARKET_WIKIDATA[code_clean]}> .\n")
            elif collect_validation_lines:
                val_lines.append(f"{m_iri} {RDF_TYPE} {SP_MARKET} .\n")
                val_lines.append(f"{m_iri} {SP_MARKET_CODE} {nt_lit(code_clean, DT_STRING)} .\n")

        # ChartEntry
        has_chart = any(not is_missing(row.get(c)) for c in ["chart", "rank", "region", "trend"])
        if has_chart:
            chart_name = str(row["chart"]).strip() if not is_missing(row.get("chart")) else ""
            region_name = str(row["region"]).strip() if not is_missing(row.get("region")) else ""
            e_iri = f"<{NS_RES}chart-entry/{stable_hash_id(track_id, chart_name, region_name)}>"

            row_lines.append(f"{t_iri} {SP_HAS_CHART_ENTRY} {e_iri} .\n")
            row_lines.append(f"{e_iri} {RDF_TYPE} {SP_CHART_ENTRY} .\n")

            if chart_name:
                row_lines.append(f"{e_iri} {SP_CHART_NAME} {nt_lit(chart_name, DT_STRING)} .\n")
            if region_name:
                row_lines.append(f"{e_iri} {SP_CHART_REGION} {nt_lit(region_name, DT_STRING)} .\n")

            rank_val = parse_int(row.get("rank"), issues, track_id, "rank")
            if rank_val is not None and rank_val >= 1:
                row_lines.append(f"{e_iri} {SP_RANK} {nt_lit(str(rank_val), DT_INTEGER)} .\n")

            raw_trend = row.get("trend")
            if not is_missing(raw_trend):
                trend_str = str(raw_trend).strip().upper()
                if trend_str not in CATEGORICAL_TRENDS:
                    trend_val = parse_int(raw_trend, issues, track_id, "trend")
                    if trend_val is not None:
                        row_lines.append(f"{e_iri} {SP_POS_CHANGE} {nt_lit(str(trend_val), DT_INTEGER)} .\n")

        out_lines.extend(row_lines)
        if collect_validation_lines:
            val_lines.extend(row_lines)

    return out_lines, val_lines


def open_output(path: Path) -> BinaryIO:
    if path.suffix == ".gz":
        return gzip.open(path, "wb", compresslevel=3)
    return open(path, "wb")


def main() -> None:
    parser = argparse.ArgumentParser(description="Fast conversion of Spotify CSV to SHACL-validated 5-star RDF.")
    parser.add_argument("--input", required=True, type=Path, help="Path to source Spotify CSV file.")
    parser.add_argument("--output", default=Path("data/spotify_kg.nt.gz"), type=Path, help="Output file (.nt or .nt.gz).")
    parser.add_argument("--shapes", default=Path("shacl/shapes.ttl"), type=Path, help="Path to SHACL shapes file.")
    parser.add_argument("--ontology", default=Path("ontology/spotify.ttl"), type=Path, help="Path to custom ontology file.")
    parser.add_argument("--issues-log", default=Path("logs/issues.log"), type=Path, help="Path to data issues log.")
    parser.add_argument("--report-out", default=Path("logs/shacl_report.txt"), type=Path, help="Path to SHACL report.")
    parser.add_argument("--chunk-size", type=int, default=5000, help="Rows processed per chunk (default: 5000).")
    parser.add_argument("--limit", type=int, default=None, help="Optional total row limit.")
    parser.add_argument("--validate-limit", type=int, default=10000, help="Rows to validate with pySHACL (default: 10000).")
    args = parser.parse_args()

    issues = setup_issues_logger(args.issues_log)
    start_time = time.time()

    print(f"Loading SHACL shapes from {args.shapes} and ontology from {args.ontology}...", flush=True)
    shapes_graph = Graph().parse(args.shapes, format="turtle")
    ont_graph = Graph().parse(args.ontology, format="turtle")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.report_out.parent.mkdir(parents=True, exist_ok=True)

    seen_artists: Set[int] = set()
    seen_albums: Set[int] = set()
    seen_genres: Set[int] = set()
    seen_markets: Set[int] = set()

    total_rows = 0
    total_triples = 0
    validated_rows = 0
    last_report = "Conforms: True\n"

    reader = pd.read_csv(args.input, chunksize=args.chunk_size, nrows=args.limit, low_memory=False)

    with open_output(args.output) as out_f:
        for chunk_idx, chunk_df in enumerate(reader):
            should_validate = args.validate_limit < 0 or validated_rows < args.validate_limit

            out_lines, val_lines = process_chunk(
                chunk_df=chunk_df,
                row_offset=total_rows,
                issues=issues,
                seen_artists=seen_artists,
                seen_albums=seen_albums,
                seen_genres=seen_genres,
                seen_markets=seen_markets,
                include_metadata=(chunk_idx == 0),
                collect_validation_lines=should_validate,
            )

            if should_validate:
                val_g = Graph()
                val_g.parse(data="".join(val_lines), format="nt")
                conforms, _, report_text = pyshacl.validate(
                    data_graph=val_g,
                    shacl_graph=shapes_graph,
                    ont_graph=ont_graph,
                    inference="none",
                    abort_on_first=False,
                )
                last_report = report_text
                validated_rows += len(chunk_df)
                if not conforms:
                    args.report_out.write_text(report_text, encoding="utf-8")
                    print(f"SHACL VALIDATION FAILED at chunk {chunk_idx + 1}!", file=sys.stderr, flush=True)
                    print(report_text, file=sys.stderr, flush=True)
                    sys.exit(1)

            out_f.write("".join(out_lines).encode("utf-8"))

            total_rows += len(chunk_df)
            total_triples += len(out_lines)

            if (chunk_idx + 1) % 5 == 0 or should_validate or args.limit is not None:
                elapsed = time.time() - start_time
                print(
                    f"Processed {total_rows:,} rows | {total_triples:,} triples | "
                    f"validated {validated_rows:,} rows | {elapsed:.1f}s",
                    flush=True,
                )

    args.report_out.write_text(
        f"Validated {validated_rows:,} rows ({total_rows:,} total rows converted).\n\n{last_report}",
        encoding="utf-8",
    )
    elapsed = time.time() - start_time
    print(f"Done in {elapsed:.1f}s! Wrote {total_triples:,} triples from {total_rows:,} rows to {args.output}.", flush=True)


if __name__ == "__main__":
    main()
