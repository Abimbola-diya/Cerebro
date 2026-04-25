"""Enums and constants for research planning contracts."""

from __future__ import annotations

from enum import Enum


class DimensionKey(str, Enum):
    REGULATORY = "dimension_1_regulatory"
    FINANCIAL = "dimension_2_financial_institutions"
    MARKET = "dimension_3_market_listing"
    EXPERT = "dimension_4_expert_opinion"
    NEWS = "dimension_5_news"
    INTERNATIONAL = "dimension_6_international_orgs"
    ASSOCIATIONS = "dimension_7_industry_associations"


ALL_DIMENSIONS: tuple[DimensionKey, ...] = (
    DimensionKey.REGULATORY,
    DimensionKey.FINANCIAL,
    DimensionKey.MARKET,
    DimensionKey.EXPERT,
    DimensionKey.NEWS,
    DimensionKey.INTERNATIONAL,
    DimensionKey.ASSOCIATIONS,
)


class DimensionStatus(str, Enum):
    ACTIVE = "ACTIVE"
    SKIP = "SKIP"


class Priority(str, Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class NigeriaRelevance(str, Enum):
    DIRECT = "DIRECT"
    STRONG = "STRONG"
    MODERATE = "MODERATE"
    LOW = "LOW"


class SourceTier(str, Enum):
    CORE = "core"
    EXTENDED = "extended"
    DOMAIN_PACK = "domain_pack"


class SourceType(str, Enum):
    REGULATOR = "regulator"
    GOVERNMENT = "government"
    EXCHANGE = "exchange"
    FINANCIAL_INSTITUTION = "financial_institution"
    RESEARCH_FIRM = "research_firm"
    THINK_TANK = "think_tank"
    ASSOCIATION = "association"
    NEWS = "news"
    PUBLICATION = "publication"
    COMPANY_IR = "company_ir"
    DATA_PLATFORM = "data_platform"
