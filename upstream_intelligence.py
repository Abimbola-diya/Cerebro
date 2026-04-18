"""Upstream intelligence dashboard generation service.

Builds a contract-stable dashboard payload for the frontend upstream view:
- Accepts lens-weighted request settings
- Performs focused web retrieval for latest upstream context
- Synthesizes structured metrics and nuanced analysis
- Returns a complete dashboard schema with safe fallbacks
"""

from __future__ import annotations

import copy
import json
import logging
import re
import time
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

from web_search import HybridSearcher, synthesize_web_results

logger = logging.getLogger(__name__)

LENS_KEYS = ["finance", "volume", "economics", "risk", "geopolitics", "operations"]
ALLOWED_LENSES = set(LENS_KEYS)
ALLOWED_INCLUDE = {"global", "nigeria", "cost_curves", "yield_breakdown", "nuances"}
ALLOWED_SEVERITY = {"watch", "elevated", "critical"}


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clamp_float(value: Any, minimum: float, maximum: float, default: float) -> float:
    try:
        parsed = float(value)
    except Exception:
        return default
    return max(minimum, min(maximum, parsed))


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        if isinstance(value, str):
            cleaned = value.replace(",", "").replace("$", "").strip()
            return float(cleaned)
        return float(value)
    except Exception:
        return default


def _normalize_lens_weights(raw_weights: Dict[str, Any]) -> Dict[str, float]:
    baseline = {key: max(0.0, _to_float(raw_weights.get(key), 0.0)) for key in LENS_KEYS}
    total = sum(baseline.values())
    if total <= 0:
        even = round(100.0 / len(LENS_KEYS), 4)
        return {key: even for key in LENS_KEYS}
    return {key: round((value / total) * 100.0, 4) for key, value in baseline.items()}


def _dominant_lens(weights: Dict[str, float]) -> str:
    return max(weights.items(), key=lambda item: item[1])[0]


def _focus_label(focus_strength: float) -> str:
    if focus_strength >= 75:
        return "high"
    if focus_strength >= 40:
        return "medium"
    return "broad"


def _default_dashboard(dominant_lens: str) -> Dict[str, Any]:
    return {
        "dashboardTitle": "Nigeria Upstream Petrochemical Intelligence Overview",
        "generatedAt": _iso_now(),
        "summary": (
            "Nigeria's upstream petroleum environment is currently balancing strong production ambitions, "
            "cost pressure, infrastructure constraints, and geopolitical sensitivity."
        ),
        "dominantLens": dominant_lens,
        "metrics": {
            "globalProduction": {
                "value": 102.8,
                "unit": "million barrels/day",
                "context": "Global upstream output remains resilient, though concentrated among a few major producers.",
                "trendText": "Output trend is stable with periodic volatility.",
                "topProducers": [
                    {"name": "United States", "code": "US", "value": 13.2, "share": 12.8},
                    {"name": "Saudi Arabia", "code": "SA", "value": 10.1, "share": 9.8},
                    {"name": "Russia", "code": "RU", "value": 9.8, "share": 9.5},
                ],
                "series": [97.8, 98.6, 99.4, 100.1, 100.8, 101.6, 102.1, 102.8],
            },
            "brentSpotPrice": {
                "value": 88.5,
                "unit": "$/barrel",
                "context": "Brent remains sensitive to supply risk, shipping routes, and OPEC+ policy direction.",
                "trendText": "Market is elevated versus long-run comfort band.",
                "rangeLow": 72.0,
                "rangeHigh": 99.0,
                "alert": "Risk premium can expand quickly during disruption headlines.",
                "series": [76.0, 79.5, 81.8, 84.0, 86.2, 87.1, 88.0, 88.5],
            },
            "barrelYields": [
                {
                    "name": "Gasoline",
                    "value": 19.4,
                    "unit": "gal",
                    "sharePct": 46.0,
                    "note": "Largest refined share; retail pricing highly visible to households.",
                },
                {
                    "name": "Diesel",
                    "value": 12.1,
                    "unit": "gal",
                    "sharePct": 29.0,
                    "note": "Key freight and industry input that feeds inflation pressure.",
                },
                {
                    "name": "Jet Fuel",
                    "value": 4.1,
                    "unit": "gal",
                    "sharePct": 10.0,
                    "note": "Travel demand changes influence this yield's margin sensitivity.",
                },
                {
                    "name": "LPG/Other",
                    "value": 6.4,
                    "unit": "gal",
                    "sharePct": 15.0,
                    "note": "By-products and specialty streams shape secondary margin capture.",
                },
            ],
            "reserves": {
                "value": 1.55,
                "unit": "trillion barrels",
                "yearsOfSupply": 49,
                "context": "Reserve replacement remains uneven globally, with capital discipline shaping exploration pace.",
                "topHolders": ["Venezuela", "Saudi Arabia", "Iran", "Canada", "Iraq"],
                "series": [1.46, 1.47, 1.48, 1.5, 1.51, 1.52, 1.54, 1.55],
            },
            "breakEvenByRegion": [
                {"region": "Middle East Onshore", "min": 3.0, "max": 10.0},
                {"region": "US Shale", "min": 40.0, "max": 58.0},
                {"region": "Offshore Deepwater", "min": 45.0, "max": 72.0},
                {"region": "Oil Sands", "min": 58.0, "max": 86.0},
            ],
            "nigeriaPulse": {
                "productionBpd": 1420000,
                "upstreamCapacityBpd": 2200000,
                "refineryThroughputBpd": 420000,
                "pmsDemandBpd": 510000,
                "context": "Nigeria's upstream economics are improving but conversion bottlenecks and supply reliability remain uneven.",
                "bottleneck": "Crude evacuation constraints and feedstock-routing inefficiencies still suppress full capacity capture.",
                "series": [1260000, 1290000, 1310000, 1340000, 1360000, 1390000, 1410000, 1420000],
            },
        },
        "nuances": [
            {
                "title": "Margin vs. Infrastructure Mismatch",
                "detail": "Price strength can improve upstream cash flow while logistics and processing limits delay realized gains.",
                "severity": "elevated",
            },
            {
                "title": "Risk Premium Sensitivity",
                "detail": "Small geopolitical shocks can move benchmark prices disproportionately when spare capacity is tightly perceived.",
                "severity": "watch",
            },
            {
                "title": "Capital Allocation Discipline",
                "detail": "Operators prioritize high-certainty projects, which can support short-term returns but delay long-cycle reserve replacement.",
                "severity": "watch",
            },
        ],
    }


def _extract_first_json_object(text: str) -> Optional[Dict[str, Any]]:
    if not text:
        return None

    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned)

    try:
        parsed = json.loads(cleaned)
        return parsed if isinstance(parsed, dict) else None
    except Exception:
        pass

    match = re.search(r"\{[\s\S]*\}", cleaned)
    if not match:
        return None

    try:
        parsed = json.loads(match.group(0))
        return parsed if isinstance(parsed, dict) else None
    except Exception:
        return None


def _compact_evidence_payload(evidence: Dict[str, Any]) -> Dict[str, Any]:
    compact: Dict[str, Any] = {}
    for key, payload in evidence.items():
        source_briefs = payload.get("source_briefs", [])
        data_points = payload.get("data_points", [])
        compact_points = []
        for point in data_points[:8]:
            if not isinstance(point, dict):
                continue
            compact_points.append(
                {
                    "metric": str(point.get("metric", ""))[:40],
                    "value": _to_float(point.get("value"), 0.0),
                    "unit": str(point.get("unit", ""))[:24],
                    "source": str(point.get("source", ""))[:80],
                }
            )

        compact[key] = {
            "topic": payload.get("topic", key),
            "provider_counts": payload.get("provider_counts", {}),
            "summary": str(payload.get("summary", ""))[:380],
            "data_points": compact_points,
            "source_briefs": [
                {
                    "title": str(item.get("title", "Unknown"))[:120],
                    "provider": str(item.get("provider", "unknown"))[:24],
                    "url": str(item.get("url", ""))[:100],
                    "text": str(item.get("text", ""))[:220],
                }
                for item in source_briefs[:3]
            ],
        }
    return compact


def _extract_price_candidates(texts: Iterable[str]) -> List[float]:
    candidates: List[float] = []
    pattern = re.compile(r"\$\s?(\d{2,3}(?:\.\d+)?)")
    for text in texts:
        lowered = (text or "").lower()
        if "brent" not in lowered and "crude" not in lowered and "oil" not in lowered:
            continue
        for raw in pattern.findall(text or ""):
            value = _to_float(raw, 0.0)
            if 20.0 <= value <= 220.0:
                candidates.append(value)
    return candidates


def _coerce_dashboard_shape(raw: Dict[str, Any], fallback: Dict[str, Any]) -> Dict[str, Any]:
    payload = copy.deepcopy(fallback)

    def _series(values: Any, default: List[float]) -> List[float]:
        if not isinstance(values, list):
            return default
        out: List[float] = []
        for item in values:
            parsed = _to_float(item, -1.0)
            if parsed >= 0:
                out.append(round(parsed, 4))
        return out if len(out) >= 6 else default

    if isinstance(raw.get("dashboardTitle"), str) and raw["dashboardTitle"].strip():
        payload["dashboardTitle"] = raw["dashboardTitle"].strip()
    if isinstance(raw.get("summary"), str) and raw["summary"].strip():
        payload["summary"] = raw["summary"].strip()
    if isinstance(raw.get("generatedAt"), str) and raw["generatedAt"].strip():
        payload["generatedAt"] = raw["generatedAt"].strip()

    dominant_lens = str(raw.get("dominantLens", "")).strip().lower()
    if dominant_lens in ALLOWED_LENSES:
        payload["dominantLens"] = dominant_lens

    metrics_raw = raw.get("metrics")
    if not isinstance(metrics_raw, dict):
        return payload

    gp = metrics_raw.get("globalProduction")
    if isinstance(gp, dict):
        target = payload["metrics"]["globalProduction"]
        candidate_value = _to_float(gp.get("value"), target["value"])
        if 20.0 <= candidate_value <= 200.0:
            target["value"] = candidate_value
        target["unit"] = str(gp.get("unit", target["unit"]))
        target["context"] = str(gp.get("context", target["context"]))
        target["trendText"] = str(gp.get("trendText", target["trendText"]))
        candidate_series = _series(gp.get("series"), target["series"])
        if all(20.0 <= value <= 200.0 for value in candidate_series):
            target["series"] = candidate_series

        top_producers = gp.get("topProducers")
        if isinstance(top_producers, list) and top_producers:
            coerced = []
            for item in top_producers[:5]:
                if not isinstance(item, dict):
                    continue
                name = str(item.get("name", "")).strip()
                code = str(item.get("code", "")).strip()[:8]
                if not name:
                    continue
                value = _to_float(item.get("value"), 0.0)
                share = _to_float(item.get("share"), 0.0)
                if not (0.0 <= value <= 30.0 and 0.0 <= share <= 100.0):
                    continue
                coerced.append(
                    {
                        "name": name,
                        "code": code or name[:3].upper(),
                        "value": value,
                        "share": share,
                    }
                )
            if coerced:
                target["topProducers"] = coerced

    brent = metrics_raw.get("brentSpotPrice")
    if isinstance(brent, dict):
        target = payload["metrics"]["brentSpotPrice"]
        brent_value = _to_float(brent.get("value"), target["value"])
        if 20.0 <= brent_value <= 220.0:
            target["value"] = brent_value
        target["unit"] = str(brent.get("unit", target["unit"]))
        target["context"] = str(brent.get("context", target["context"]))
        target["trendText"] = str(brent.get("trendText", target["trendText"]))
        range_low = _to_float(brent.get("rangeLow"), target["rangeLow"])
        range_high = _to_float(brent.get("rangeHigh"), target["rangeHigh"])
        if 10.0 <= range_low <= 220.0 and 10.0 <= range_high <= 240.0:
            target["rangeLow"] = range_low
            target["rangeHigh"] = max(range_low, range_high)
        target["alert"] = str(brent.get("alert", target["alert"]))
        brent_series = _series(brent.get("series"), target["series"])
        if all(20.0 <= value <= 220.0 for value in brent_series):
            target["series"] = brent_series

    yields = metrics_raw.get("barrelYields")
    if isinstance(yields, list) and yields:
        parsed_yields = []
        for item in yields[:6]:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name", "")).strip()
            if not name:
                continue
            parsed_yields.append(
                {
                    "name": name,
                    "value": _to_float(item.get("value"), 0.0),
                    "unit": str(item.get("unit", "")) or "unit",
                    "sharePct": _clamp_float(item.get("sharePct"), 0.0, 100.0, 0.0),
                    "note": str(item.get("note", "")).strip() or "No additional note provided.",
                }
            )
        if parsed_yields:
            payload["metrics"]["barrelYields"] = parsed_yields

    reserves = metrics_raw.get("reserves")
    if isinstance(reserves, dict):
        target = payload["metrics"]["reserves"]
        reserves_value = _to_float(reserves.get("value"), target["value"])
        if 0.1 <= reserves_value <= 10.0:
            target["value"] = reserves_value
        target["unit"] = str(reserves.get("unit", target["unit"]))
        years_supply = int(_to_float(reserves.get("yearsOfSupply"), target["yearsOfSupply"]))
        if 1 <= years_supply <= 200:
            target["yearsOfSupply"] = years_supply
        target["context"] = str(reserves.get("context", target["context"]))
        reserves_series = _series(reserves.get("series"), target["series"])
        if all(0.1 <= value <= 10.0 for value in reserves_series):
            target["series"] = reserves_series
        holders = reserves.get("topHolders")
        if isinstance(holders, list):
            cleaned_holders = [str(holder).strip() for holder in holders if str(holder).strip()]
            if cleaned_holders:
                target["topHolders"] = cleaned_holders[:8]

    curves = metrics_raw.get("breakEvenByRegion")
    if isinstance(curves, list) and curves:
        parsed_rows = []
        for row in curves[:8]:
            if not isinstance(row, dict):
                continue
            region = str(row.get("region", "")).strip()
            if not region:
                continue
            minimum = _to_float(row.get("min"), 0.0)
            maximum = max(minimum, _to_float(row.get("max"), minimum))
            if not (0.0 <= minimum <= 200.0 and 0.0 <= maximum <= 250.0):
                continue
            parsed_rows.append({"region": region, "min": minimum, "max": maximum})
        if parsed_rows:
            payload["metrics"]["breakEvenByRegion"] = parsed_rows

    nigeria = metrics_raw.get("nigeriaPulse")
    if isinstance(nigeria, dict):
        target = payload["metrics"]["nigeriaPulse"]
        target["productionBpd"] = int(_to_float(nigeria.get("productionBpd"), target["productionBpd"]))
        target["upstreamCapacityBpd"] = int(
            _to_float(nigeria.get("upstreamCapacityBpd"), target["upstreamCapacityBpd"])
        )
        target["refineryThroughputBpd"] = int(
            _to_float(nigeria.get("refineryThroughputBpd"), target["refineryThroughputBpd"])
        )
        target["pmsDemandBpd"] = int(_to_float(nigeria.get("pmsDemandBpd"), target["pmsDemandBpd"]))
        target["context"] = str(nigeria.get("context", target["context"]))
        target["bottleneck"] = str(nigeria.get("bottleneck", target["bottleneck"]))
        target["series"] = _series(nigeria.get("series"), target["series"])

    nuances = raw.get("nuances")
    if isinstance(nuances, list) and nuances:
        parsed_nuances = []
        for nuance in nuances[:8]:
            if not isinstance(nuance, dict):
                continue
            title = str(nuance.get("title", "")).strip()
            detail = str(nuance.get("detail", "")).strip()
            severity = str(nuance.get("severity", "watch")).strip().lower()
            if not title or not detail:
                continue
            if severity not in ALLOWED_SEVERITY:
                severity = "watch"
            parsed_nuances.append({"title": title, "detail": detail, "severity": severity})
        if parsed_nuances:
            payload["nuances"] = parsed_nuances

    return payload


def _gather_evidence(
    scope: str,
    include: List[str],
    dominant_lens: str,
    deadline_ts: Optional[float] = None,
) -> Dict[str, Dict[str, Any]]:
    evidence: Dict[str, Dict[str, Any]] = {}
    searcher = HybridSearcher()
    searcher.query_variants = min(searcher.query_variants, 2)
    searcher.max_discovered_sources = min(searcher.max_discovered_sources, 10)
    searcher.max_sources_to_scrape = min(searcher.max_sources_to_scrape, 4)
    searcher.extensive_mode = True

    subject_map = {
        "global": "Global upstream oil and gas market",
        "nigeria": "Nigeria upstream petroleum sector",
        "cost_curves": "Global upstream break-even cost curves",
        "yield_breakdown": "Crude barrel product yield structure",
        "nuances": "Nigeria upstream petroleum strategic outlook",
    }

    topic_map = {
        "global": (
            "latest global daily oil production mb/d, brent crude spot levels, "
            "major producer concentration, and proven reserve trend"
        ),
        "nigeria": (
            "latest nigeria upstream crude production bopd, upstream capacity, refinery throughput, "
            "and pms demand"
        ),
        "cost_curves": "latest upstream break-even oil cost by region including middle east, shale, and offshore",
        "yield_breakdown": "latest crude barrel yield breakdown gasoline diesel jet fuel and other outputs",
        "nuances": "current nigeria upstream nuances, geopolitics, financing, operational risk, and infrastructure constraints",
    }

    for key in include:
        if deadline_ts and time.time() >= deadline_ts:
            logger.warning("Upstream evidence gathering stopped early due to time budget")
            break

        subject = subject_map.get(key, "Nigeria upstream petroleum industry")
        topic = topic_map.get(key, "latest upstream petroleum outlook")
        focus_hint = f"Focus on {dominant_lens} implications under scope={scope}."

        try:
            web_results = searcher.search_and_scrape(subject, f"{topic}. {focus_hint}")
            synthesis = synthesize_web_results(subject, {}, web_results, key)
            evidence[key] = {
                "topic": topic,
                "provider_counts": web_results.get("provider_counts", {}),
                "summary": web_results.get("tavily_summary", ""),
                "data_points": synthesis.get("data_points", []),
                "source_briefs": synthesis.get("source_briefs", []),
                "raw_web": web_results,
            }
        except Exception as exc:
            logger.warning("Upstream intelligence evidence retrieval failed for '%s': %s", key, exc)
            evidence[key] = {
                "topic": topic,
                "provider_counts": {},
                "summary": "",
                "data_points": [],
                "source_briefs": [],
                "raw_web": {},
            }

        if deadline_ts and time.time() >= deadline_ts:
            logger.warning("Upstream evidence gathering reached time budget after '%s'", key)
            break

    return evidence


def _lightweight_metric_refresh(dashboard: Dict[str, Any], evidence: Dict[str, Dict[str, Any]]) -> None:
    global_evidence = evidence.get("global", {})
    nigeria_evidence = evidence.get("nigeria", {})

    global_points = global_evidence.get("data_points", []) if isinstance(global_evidence, dict) else []
    nigeria_points = nigeria_evidence.get("data_points", []) if isinstance(nigeria_evidence, dict) else []

    production_values = [
        _to_float(item.get("value"), -1.0)
        for item in global_points
        if isinstance(item, dict) and str(item.get("metric", "")).lower() == "production"
    ]
    production_values = [value for value in production_values if value > 0]

    if production_values:
        refreshed = max(production_values)
        if 20.0 <= refreshed <= 160.0:
            dashboard["metrics"]["globalProduction"]["value"] = round(refreshed, 2)

    candidate_texts = [str(global_evidence.get("summary", ""))]
    for brief in global_evidence.get("source_briefs", [])[:10] if isinstance(global_evidence, dict) else []:
        if isinstance(brief, dict):
            candidate_texts.append(str(brief.get("text", "")))

    price_candidates = _extract_price_candidates(candidate_texts)
    if price_candidates:
        dashboard["metrics"]["brentSpotPrice"]["value"] = round(price_candidates[0], 2)

    nigeria_prod_values = [
        _to_float(item.get("value"), -1.0)
        for item in nigeria_points
        if isinstance(item, dict) and str(item.get("metric", "")).lower() == "production"
    ]
    nigeria_prod_values = [value for value in nigeria_prod_values if value > 0]
    if nigeria_prod_values:
        refreshed_nigeria = max(nigeria_prod_values)
        if 10000 <= refreshed_nigeria <= 5000000:
            dashboard["metrics"]["nigeriaPulse"]["productionBpd"] = int(refreshed_nigeria)

    summaries: List[str] = []
    for key in ["global", "nigeria", "cost_curves", "nuances"]:
        summary = str(evidence.get(key, {}).get("summary", ""))
        if summary:
            summaries.append(summary)
    if summaries:
        dashboard["summary"] = " ".join(summaries)[:1200]


def _llm_dashboard_generation(
    fallback_dashboard: Dict[str, Any],
    scope: str,
    normalized_weights: Dict[str, float],
    focus_strength: float,
    include: List[str],
    evidence: Dict[str, Dict[str, Any]],
    llm_pipeline: Any,
) -> Dict[str, Any]:
    if not llm_pipeline:
        return fallback_dashboard

    evidence_payload = _compact_evidence_payload(evidence)
    focus_label = _focus_label(focus_strength)

    system_prompt = """You are generating a strict JSON dashboard for an upstream petroleum intelligence UI.

Return JSON only. No markdown.
Use this exact schema and key names:
{
  "dashboardTitle": string,
  "generatedAt": string,
  "summary": string,
  "dominantLens": "finance" | "volume" | "economics" | "risk" | "geopolitics" | "operations",
  "metrics": {
    "globalProduction": {
      "value": number,
      "unit": string,
      "context": string,
      "trendText": string,
      "topProducers": [{"name": string, "code": string, "value": number, "share": number}],
      "series": number[]
    },
    "brentSpotPrice": {
      "value": number,
      "unit": string,
      "context": string,
      "trendText": string,
      "rangeLow": number,
      "rangeHigh": number,
      "alert": string,
      "series": number[]
    },
    "barrelYields": [{"name": string, "value": number, "unit": string, "sharePct": number, "note": string}],
    "reserves": {
      "value": number,
      "unit": string,
      "yearsOfSupply": number,
      "context": string,
      "topHolders": string[],
      "series": number[]
    },
    "breakEvenByRegion": [{"region": string, "min": number, "max": number}],
    "nigeriaPulse": {
      "productionBpd": number,
      "upstreamCapacityBpd": number,
      "refineryThroughputBpd": number,
      "pmsDemandBpd": number,
      "context": string,
      "bottleneck": string,
      "series": number[]
    }
  },
  "nuances": [{"title": string, "detail": string, "severity": "watch" | "elevated" | "critical"}]
}

Hard constraints:
1. Keep all numeric fields as numbers (never strings).
2. Keep series arrays with at least 6 points each.
3. Ensure breakEvenByRegion rows satisfy max >= min.
4. Keep severity strictly in allowed enum.
5. Tailor the narrative to Nigeria upstream + petrochemical context with strategic nuance.
"""

    user_prompt = (
        f"Request scope: {scope}\n"
        f"Lens weights (normalized): {json.dumps(normalized_weights, indent=2)}\n"
        f"Focus strength: {focus_strength} ({focus_label})\n"
        f"Included sections: {include}\n\n"
        f"Fallback title: {fallback_dashboard.get('dashboardTitle', '')}\n"
        f"Fallback dominant lens: {fallback_dashboard.get('dominantLens', '')}\n\n"
        f"Evidence payload:\n{json.dumps(evidence_payload, indent=2)}\n\n"
        "Generate the final dashboard JSON now."
    )

    preferred_provider = None
    try:
        provider_value = str(getattr(llm_pipeline, "web_final_synthesis_provider", "auto") or "auto")
        preferred_provider = provider_value if provider_value not in {"", "auto", "default"} else None
    except Exception:
        preferred_provider = None

    try:
        if hasattr(llm_pipeline, "_call_llm_with_preference"):
            output = llm_pipeline._call_llm_with_preference(
                system_prompt,
                user_prompt,
                preferred_provider=preferred_provider,
            )
        elif hasattr(llm_pipeline, "_call_llm"):
            output = llm_pipeline._call_llm(system_prompt, user_prompt)
        else:
            logger.warning("LLM pipeline lacks callable interface for upstream intelligence generation")
            return fallback_dashboard

        parsed = _extract_first_json_object(output)
        if not parsed:
            logger.warning("LLM upstream dashboard generation returned non-JSON output")
            return fallback_dashboard

        return _coerce_dashboard_shape(parsed, fallback_dashboard)
    except Exception as exc:
        logger.warning("LLM upstream dashboard synthesis failed: %s", exc)
        return fallback_dashboard


def generate_upstream_dashboard(
    scope: str,
    lens_weights: Dict[str, Any],
    focus_strength: float,
    include: List[str],
    llm_pipeline: Any,
    skip_research: bool = False,
    time_budget_seconds: Optional[int] = None,
) -> Dict[str, Any]:
    """Generate upstream intelligence dashboard payload for frontend rendering."""
    normalized_weights = _normalize_lens_weights(lens_weights)
    dominant = _dominant_lens(normalized_weights)

    dashboard = _default_dashboard(dominant)
    dashboard["generatedAt"] = _iso_now()

    if skip_research:
        dashboard["summary"] = (
            "Upstream intelligence is temporarily using baseline analytics due to request timing limits. "
            "Retry for refreshed web-sourced insights."
        )
        dashboard["dominantLens"] = dominant
        return dashboard

    include_sanitized = [item for item in include if item in ALLOWED_INCLUDE]
    if not include_sanitized:
        include_sanitized = ["global", "nigeria", "cost_curves", "yield_breakdown", "nuances"]

    deadline_ts: Optional[float] = None
    if time_budget_seconds and time_budget_seconds > 0:
        deadline_ts = time.time() + float(time_budget_seconds)

    evidence = _gather_evidence(scope, include_sanitized, dominant, deadline_ts=deadline_ts)
    _lightweight_metric_refresh(dashboard, evidence)

    dashboard = _llm_dashboard_generation(
        fallback_dashboard=dashboard,
        scope=scope,
        normalized_weights=normalized_weights,
        focus_strength=focus_strength,
        include=include_sanitized,
        evidence=evidence,
        llm_pipeline=llm_pipeline,
    )

    dashboard["generatedAt"] = _iso_now()
    dashboard["dominantLens"] = _dominant_lens(normalized_weights)
    return dashboard
