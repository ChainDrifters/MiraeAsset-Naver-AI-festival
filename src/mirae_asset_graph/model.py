from __future__ import annotations

import hashlib
import math
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote

FIBO = "https://spec.edmcouncil.org/fibo/ontology/"
MA_ONTOLOGY = "urn:miraeasset:ontology:financial-products:"

FINANCIAL_INSTRUMENT = FIBO + "FBC/FinancialInstruments/FinancialInstruments/FinancialInstrument"
DEBT_INSTRUMENT = FIBO + "FBC/FinancialInstruments/FinancialInstruments/DebtInstrument"
BOND = FIBO + "SEC/Debt/Bonds/Bond"
ETF = FIBO + "SEC/Funds/Funds/ExchangeTradedFund"
MUTUAL_FUND = FIBO + "SEC/Funds/Funds/MutualFund"
FUND_UNIT = FIBO + "SEC/Funds/Funds/FundUnit"
TRADABLE_FUND_UNIT = FIBO + "SEC/Funds/Funds/TradableFundUnit"
NON_TRADABLE_FUND_UNIT = FIBO + "SEC/Funds/Funds/NonTradableFundUnit"
LISTED_SECURITY = FIBO + "SEC/Securities/SecuritiesListings/ListedSecurity"
LISTING = FIBO + "SEC/Securities/SecuritiesListings/Listing"
ETN = MA_ONTOLOGY + "ExchangeTradedNote"
KOREAN_BOND = MA_ONTOLOGY + "KoreanBond"
KOREAN_ETF = MA_ONTOLOGY + "KoreanExchangeTradedFund"
KOREAN_ETN = MA_ONTOLOGY + "KoreanExchangeTradedNote"
GLOBAL_ETF = MA_ONTOLOGY + "GlobalExchangeTradedFund"
GLOBAL_ETN = MA_ONTOLOGY + "GlobalExchangeTradedNote"
PUBLIC_FUND = MA_ONTOLOGY + "PublicFund"
PUBLIC_FUND_UNIT = MA_ONTOLOGY + "PublicFundUnit"


CLASS_NAMES = {
    FINANCIAL_INSTRUMENT: "Financial instrument",
    DEBT_INSTRUMENT: "Debt instrument",
    BOND: "Bond",
    ETF: "Exchange-traded fund",
    MUTUAL_FUND: "Mutual fund",
    FUND_UNIT: "Fund unit",
    TRADABLE_FUND_UNIT: "Tradable fund unit",
    NON_TRADABLE_FUND_UNIT: "Non-tradable fund unit",
    LISTED_SECURITY: "Listed security",
    LISTING: "Security listing",
    ETN: "Exchange-traded note",
    KOREAN_BOND: "Korean bond",
    KOREAN_ETF: "Korean exchange-traded fund",
    KOREAN_ETN: "Korean exchange-traded note",
    GLOBAL_ETF: "Global exchange-traded fund",
    GLOBAL_ETN: "Global exchange-traded note",
    PUBLIC_FUND: "Public fund",
    PUBLIC_FUND_UNIT: "Public fund unit",
}


@dataclass(frozen=True)
class DatasetSpec:
    code: str
    name: str
    data_pattern: str
    schema_pattern: str


DATASETS = (
    DatasetSpec(
        "domestic_bonds",
        "Domestic bond master",
        "PRBD01N001_*_datarows.xlsx",
        "PRBD01N001_*_schema.xlsx",
    ),
    DatasetSpec(
        "domestic_etf_etn",
        "Korean ETF and ETN master",
        "PREF01N001_*_datarows.xlsx",
        "PREF01N001_*_schema.xlsx",
    ),
    DatasetSpec(
        "overseas_etf_etn",
        "Overseas ETF and ETN master",
        "PREF02N001_*_datarows.xlsx",
        "PREF02N001_*_schema.xlsx",
    ),
    DatasetSpec(
        "public_funds",
        "Public fund master",
        "PRFD01N001_*_datarows.xlsx",
        "PRFD01N001_*_schema.xlsx",
    ),
)


_ISIN_RE = re.compile(r"^[A-Z]{2}[A-Z0-9]{9}[0-9]$")
_DATE_RE = re.compile(r"^(\d{4})(\d{2})(\d{2})$")
_SNAPSHOT_RE = re.compile(r"_(\d{8})_datarows\.xlsx$")


def clean(value: Any) -> Any:
    if isinstance(value, str):
        value = value.strip()
        return value or None
    if isinstance(value, float) and math.isnan(value):
        return None
    if isinstance(value, datetime):
        return value.replace(tzinfo=None)
    return value


def text(value: Any) -> str | None:
    value = clean(value)
    if value is None:
        return None
    return str(value).strip() or None


def number(value: Any) -> float | None:
    value = clean(value)
    if value is None:
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def integer(value: Any) -> int | None:
    value = number(value)
    return int(value) if value is not None and value.is_integer() else None


def boolean(value: Any) -> bool | None:
    value = text(value)
    if value is None:
        return None
    normalized = value.upper()
    if normalized in {"Y", "YES", "TRUE", "1", "판매중"}:
        return True
    if normalized in {"N", "NO", "FALSE", "0", "판매완료"}:
        return False
    return None


def parsed_date(value: Any) -> date | None:
    value = clean(value)
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    raw = str(value).strip().replace("-", "")
    match = _DATE_RE.match(raw)
    if not match:
        return None
    try:
        return date(*(int(part) for part in match.groups()))
    except ValueError:
        return None


def snapshot_date(path: Path) -> date | None:
    match = _SNAPSHOT_RE.search(path.name)
    return parsed_date(match.group(1)) if match else None


def is_isin(value: Any) -> bool:
    candidate = text(value)
    return bool(candidate and _ISIN_RE.match(candidate.upper()))


def is_korean_source_item(value: Any) -> bool:
    """Validate the vendor's 12-character KR item key, which may end in M."""
    candidate = text(value)
    return bool(
        candidate
        and len(candidate) == 12
        and candidate.upper().startswith("KR")
        and candidate.isalnum()
    )


def is_placeholder(value: Any) -> bool:
    candidate = text(value)
    return candidate is None or set(candidate) <= {"0"}


def component(value: Any) -> str:
    return quote(text(value) or "unknown", safe="")


def hashed_component(value: Any) -> str:
    normalized = (text(value) or "unknown").casefold().encode("utf-8")
    return hashlib.sha256(normalized).hexdigest()[:24]


def source_record_uri(dataset: str, snapshot: date | None, row_number: int) -> str:
    stamp = snapshot.isoformat() if snapshot else "undated"
    return f"urn:miraeasset:source-record:{dataset}:{stamp}:{row_number}"


def security_uri(identifier: Any, fallback: str) -> str:
    if is_isin(identifier):
        return f"urn:miraeasset:security:isin:{component(str(identifier).upper())}"
    return f"urn:miraeasset:security:{fallback}"


def fund_uri(identifier: Any, fallback: str) -> str:
    if is_isin(identifier):
        return f"urn:miraeasset:fund:isin:{component(str(identifier).upper())}"
    return f"urn:miraeasset:fund:{fallback}"


def organization(value: Any, *, scheme: str = "name", source_field: str | None = None) -> dict[str, Any] | None:
    normalized = text(value)
    if not normalized or is_placeholder(normalized):
        return None
    return {
        "uri": f"urn:miraeasset:organization:{scheme}:{hashed_component(normalized)}",
        "name": normalized if scheme == "name" else None,
        "code": normalized if scheme != "name" else None,
        "identityScheme": scheme,
        "sourceField": source_field,
    }


def identifier(scheme: str, value: Any) -> dict[str, Any] | None:
    normalized = text(value)
    if not normalized or is_placeholder(normalized):
        return None
    if scheme == "ISIN":
        normalized = normalized.upper()
    return {
        "uri": f"urn:miraeasset:identifier:{component(scheme.lower())}:{component(normalized)}",
        "scheme": scheme,
        "value": normalized,
    }


def benchmark(name: Any, english_name: Any = None) -> dict[str, Any] | None:
    preferred = text(name) or text(english_name)
    if not preferred:
        return None
    return {
        "uri": f"urn:miraeasset:benchmark:name:{hashed_component(preferred)}",
        "name": text(name) or preferred,
        "englishName": text(english_name),
    }


def classification(scheme: str, value: Any, label: Any = None) -> dict[str, Any] | None:
    normalized = text(value)
    if not normalized:
        return None
    return {
        "uri": f"urn:miraeasset:classification:{component(scheme)}:{component(normalized)}",
        "scheme": scheme,
        "code": normalized,
        "name": text(label) or normalized,
    }


def class_refs(uris: Iterable[str]) -> list[dict[str, str]]:
    return [{"uri": uri, "name": CLASS_NAMES.get(uri, uri.rsplit("/", 1)[-1])} for uri in uris]


def compact(values: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in values.items() if value is not None}


def compact_list(values: Iterable[dict[str, Any] | None]) -> list[dict[str, Any]]:
    return [value for value in values if value is not None]


def raw_properties(row: Mapping[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in row.items():
        value = clean(value)
        if value is not None:
            result[str(key)] = value
    return result


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()
