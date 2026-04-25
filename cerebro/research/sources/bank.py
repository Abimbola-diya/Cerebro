"""Large, classified source bank across all 7 dimensions.

The source bank is split into core and extended tiers and is intended to be
loaded through SourceRegistry. Credibility is soft-ranked (1-5) and not used
as a hard-reject threshold at planner stage.
"""

from __future__ import annotations

from collections.abc import Iterable

from cerebro.research.contracts.enums import DimensionKey, NigeriaRelevance, SourceTier, SourceType

from .models import SourceRecord


def _src(
    *,
    id: str,
    name: str,
    url: str,
    dimension: DimensionKey,
    source_type: SourceType,
    tier: SourceTier,
    relevance: NigeriaRelevance,
    rank: int,
    update: str,
    paths: Iterable[str] = (),
    op: str | None = None,
    notes: str | None = None,
) -> SourceRecord:
    return SourceRecord(
        id=id,
        name=name,
        url=url,
        dimension=dimension,
        source_type=source_type,
        tier=tier,
        nigeria_relevance=relevance,
        credibility_rank=rank,
        update_frequency=update,
        crawl_paths=tuple(paths),
        search_operator=op,
        notes=notes,
    )


REGULATORY_SOURCES: list[SourceRecord] = [
    _src(id="nuprc", name="NUPRC", url="https://www.nuprc.gov.ng", dimension=DimensionKey.REGULATORY, source_type=SourceType.REGULATOR, tier=SourceTier.CORE, relevance=NigeriaRelevance.DIRECT, rank=5, update="monthly", paths=["/", "/resources", "/publications", "/news"], op="site:nuprc.gov.ng"),
    _src(id="nmdpra", name="NMDPRA", url="https://www.nmdpra.gov.ng", dimension=DimensionKey.REGULATORY, source_type=SourceType.REGULATOR, tier=SourceTier.CORE, relevance=NigeriaRelevance.DIRECT, rank=5, update="monthly", paths=["/", "/news", "/regulations"], op="site:nmdpra.gov.ng"),
    _src(id="neiti", name="NEITI", url="https://www.neiti.gov.ng", dimension=DimensionKey.REGULATORY, source_type=SourceType.REGULATOR, tier=SourceTier.CORE, relevance=NigeriaRelevance.DIRECT, rank=5, update="quarterly", paths=["/", "/publications", "/reports", "/news"], op="site:neiti.gov.ng"),
    _src(id="sec-ng", name="SEC Nigeria", url="https://www.sec.gov.ng", dimension=DimensionKey.REGULATORY, source_type=SourceType.REGULATOR, tier=SourceTier.CORE, relevance=NigeriaRelevance.DIRECT, rank=5, update="weekly", paths=["/", "/media", "/rules-regulations"], op="site:sec.gov.ng"),
    _src(id="cbn", name="Central Bank of Nigeria", url="https://www.cbn.gov.ng", dimension=DimensionKey.REGULATORY, source_type=SourceType.REGULATOR, tier=SourceTier.CORE, relevance=NigeriaRelevance.DIRECT, rank=5, update="weekly", paths=["/", "/out", "/documents"], op="site:cbn.gov.ng"),
    _src(id="firs", name="FIRS", url="https://www.firs.gov.ng", dimension=DimensionKey.REGULATORY, source_type=SourceType.REGULATOR, tier=SourceTier.CORE, relevance=NigeriaRelevance.DIRECT, rank=4, update="monthly", paths=["/", "/news"], op="site:firs.gov.ng"),
    _src(id="nnpc-group", name="NNPC Limited", url="https://www.nnpcgroup.com", dimension=DimensionKey.REGULATORY, source_type=SourceType.GOVERNMENT, tier=SourceTier.CORE, relevance=NigeriaRelevance.DIRECT, rank=4, update="weekly", paths=["/", "/news", "/investors"], op="site:nnpcgroup.com"),
    _src(id="ncdmb", name="NCDMB", url="https://www.ncdmb.gov.ng", dimension=DimensionKey.REGULATORY, source_type=SourceType.GOVERNMENT, tier=SourceTier.CORE, relevance=NigeriaRelevance.DIRECT, rank=4, update="monthly", paths=["/", "/news-and-events", "/reports"], op="site:ncdmb.gov.ng"),
    _src(id="fmpr", name="Federal Ministry of Petroleum Resources", url="https://www.petroleumresources.gov.ng", dimension=DimensionKey.REGULATORY, source_type=SourceType.GOVERNMENT, tier=SourceTier.CORE, relevance=NigeriaRelevance.DIRECT, rank=4, update="monthly", paths=["/", "/news"], op="site:petroleumresources.gov.ng"),
    _src(id="national-assembly", name="National Assembly Nigeria", url="https://www.nass.gov.ng", dimension=DimensionKey.REGULATORY, source_type=SourceType.GOVERNMENT, tier=SourceTier.EXTENDED, relevance=NigeriaRelevance.STRONG, rank=3, update="weekly", paths=["/", "/news", "/documents"], op="site:nass.gov.ng petroleum"),
    _src(id="nigeria-gazette", name="Federal Republic of Nigeria Official Gazette", url="https://gazettes.africa/akn/ng", dimension=DimensionKey.REGULATORY, source_type=SourceType.GOVERNMENT, tier=SourceTier.EXTENDED, relevance=NigeriaRelevance.STRONG, rank=4, update="monthly", paths=["/"], op="site:gazettes.africa Nigeria petroleum"),
    _src(id="bureau-public-procurement", name="Bureau of Public Procurement", url="https://www.bpp.gov.ng", dimension=DimensionKey.REGULATORY, source_type=SourceType.GOVERNMENT, tier=SourceTier.EXTENDED, relevance=NigeriaRelevance.MODERATE, rank=3, update="monthly", paths=["/", "/news"], op="site:bpp.gov.ng oil"),
    _src(id="nigerian-courts", name="National Judicial Council", url="https://www.njc.gov.ng", dimension=DimensionKey.REGULATORY, source_type=SourceType.GOVERNMENT, tier=SourceTier.EXTENDED, relevance=NigeriaRelevance.MODERATE, rank=3, update="monthly", paths=["/"], op="site:njc.gov.ng petroleum"),
    _src(id="fmf-budget", name="Federal Ministry of Finance", url="https://www.fmf.gov.ng", dimension=DimensionKey.REGULATORY, source_type=SourceType.GOVERNMENT, tier=SourceTier.EXTENDED, relevance=NigeriaRelevance.STRONG, rank=3, update="monthly", paths=["/", "/media-center"], op="site:fmf.gov.ng oil"),
    _src(id="nigerian-upstream-awards", name="Nigeria Upstream Awards and Licensing", url="https://www.nuprc.gov.ng/category/licensing", dimension=DimensionKey.REGULATORY, source_type=SourceType.REGULATOR, tier=SourceTier.EXTENDED, relevance=NigeriaRelevance.DIRECT, rank=4, update="quarterly", paths=["/category/licensing"], op="site:nuprc.gov.ng licensing"),
    _src(id="ecowas-energy", name="ECOWAS Energy", url="https://www.ecowas.int", dimension=DimensionKey.REGULATORY, source_type=SourceType.GOVERNMENT, tier=SourceTier.EXTENDED, relevance=NigeriaRelevance.MODERATE, rank=3, update="quarterly", paths=["/special-post/energy"], op="site:ecowas.int Nigeria oil"),
    _src(id="ogfza", name="Oil and Gas Free Zones Authority", url="https://www.ogfza.gov.ng", dimension=DimensionKey.REGULATORY, source_type=SourceType.REGULATOR, tier=SourceTier.EXTENDED, relevance=NigeriaRelevance.STRONG, rank=3, update="monthly", paths=["/", "/news"], op="site:ogfza.gov.ng"),
    _src(id="nupeng-labour-regulatory", name="NUPENG Regulatory Statements", url="https://www.nupeng.org", dimension=DimensionKey.REGULATORY, source_type=SourceType.ASSOCIATION, tier=SourceTier.EXTENDED, relevance=NigeriaRelevance.STRONG, rank=3, update="monthly", paths=["/news"], op="site:nupeng.org policy"),
]


FINANCIAL_SOURCES: list[SourceRecord] = [
    _src(id="world-bank-ng", name="World Bank Nigeria", url="https://www.worldbank.org/en/country/nigeria", dimension=DimensionKey.FINANCIAL, source_type=SourceType.FINANCIAL_INSTITUTION, tier=SourceTier.CORE, relevance=NigeriaRelevance.DIRECT, rank=5, update="quarterly", paths=["/en/country/nigeria", "/en/country/nigeria/publication/nigeria-development-update"], op="site:worldbank.org Nigeria petroleum"),
    _src(id="imf-ng", name="IMF Nigeria", url="https://www.imf.org/en/Countries/NGA", dimension=DimensionKey.FINANCIAL, source_type=SourceType.FINANCIAL_INSTITUTION, tier=SourceTier.CORE, relevance=NigeriaRelevance.DIRECT, rank=5, update="annual", paths=["/en/Countries/NGA", "/en/Publications/CR"], op="site:imf.org Nigeria Article IV oil"),
    _src(id="afdb-ng", name="AfDB Nigeria", url="https://www.afdb.org/en/countries-west-africa-nigeria", dimension=DimensionKey.FINANCIAL, source_type=SourceType.FINANCIAL_INSTITUTION, tier=SourceTier.CORE, relevance=NigeriaRelevance.DIRECT, rank=5, update="quarterly", paths=["/en/countries-west-africa-nigeria", "/en/news-and-events"], op="site:afdb.org Nigeria energy"),
    _src(id="afreximbank-research", name="Afreximbank Research", url="https://www.afreximbank.com/research", dimension=DimensionKey.FINANCIAL, source_type=SourceType.FINANCIAL_INSTITUTION, tier=SourceTier.CORE, relevance=NigeriaRelevance.STRONG, rank=4, update="quarterly", paths=["/research", "/news-and-events"], op="site:afreximbank.com Nigeria oil"),
    _src(id="cbn-mpr", name="CBN Monetary Policy Releases", url="https://www.cbn.gov.ng/monetarypolicy", dimension=DimensionKey.FINANCIAL, source_type=SourceType.FINANCIAL_INSTITUTION, tier=SourceTier.CORE, relevance=NigeriaRelevance.STRONG, rank=4, update="monthly", paths=["/monetarypolicy"], op="site:cbn.gov.ng monetary policy oil"),
    _src(id="fitch-ratings", name="Fitch Ratings", url="https://www.fitchratings.com", dimension=DimensionKey.FINANCIAL, source_type=SourceType.FINANCIAL_INSTITUTION, tier=SourceTier.EXTENDED, relevance=NigeriaRelevance.STRONG, rank=4, update="weekly", paths=["/research"], op="site:fitchratings.com Nigeria oil"),
    _src(id="moodys", name="Moody's", url="https://www.moodys.com", dimension=DimensionKey.FINANCIAL, source_type=SourceType.FINANCIAL_INSTITUTION, tier=SourceTier.EXTENDED, relevance=NigeriaRelevance.STRONG, rank=4, update="weekly", paths=["/web/en/us/insights"], op="site:moodys.com Nigeria oil"),
    _src(id="sp-global-ratings", name="S&P Global Ratings", url="https://www.spglobal.com/ratings", dimension=DimensionKey.FINANCIAL, source_type=SourceType.FINANCIAL_INSTITUTION, tier=SourceTier.EXTENDED, relevance=NigeriaRelevance.STRONG, rank=4, update="weekly", paths=["/en/research-insights"], op="site:spglobal.com ratings Nigeria energy"),
    _src(id="eiu", name="Economist Intelligence Unit", url="https://www.eiu.com", dimension=DimensionKey.FINANCIAL, source_type=SourceType.RESEARCH_FIRM, tier=SourceTier.EXTENDED, relevance=NigeriaRelevance.MODERATE, rank=3, update="weekly", paths=["/n"], op="site:eiu.com Nigeria oil"),
    _src(id="ifc", name="International Finance Corporation", url="https://www.ifc.org", dimension=DimensionKey.FINANCIAL, source_type=SourceType.FINANCIAL_INSTITUTION, tier=SourceTier.EXTENDED, relevance=NigeriaRelevance.MODERATE, rank=3, update="monthly", paths=["/en/where-we-work/sub-saharan-africa/countries/nigeria"], op="site:ifc.org Nigeria energy"),
    _src(id="isdb", name="Islamic Development Bank", url="https://www.isdb.org", dimension=DimensionKey.FINANCIAL, source_type=SourceType.FINANCIAL_INSTITUTION, tier=SourceTier.EXTENDED, relevance=NigeriaRelevance.MODERATE, rank=3, update="monthly", paths=["/country/nigeria"], op="site:isdb.org Nigeria energy"),
    _src(id="trade-economics-ng", name="Trading Economics Nigeria", url="https://tradingeconomics.com/nigeria", dimension=DimensionKey.FINANCIAL, source_type=SourceType.DATA_PLATFORM, tier=SourceTier.EXTENDED, relevance=NigeriaRelevance.MODERATE, rank=2, update="daily", paths=["/nigeria"], op="site:tradingeconomics.com nigeria oil"),
    _src(id="dmo", name="Debt Management Office Nigeria", url="https://www.dmo.gov.ng", dimension=DimensionKey.FINANCIAL, source_type=SourceType.GOVERNMENT, tier=SourceTier.EXTENDED, relevance=NigeriaRelevance.STRONG, rank=3, update="monthly", paths=["/", "/media"], op="site:dmo.gov.ng oil revenue"),
    _src(id="budget-office", name="Budget Office of the Federation", url="https://www.budgetoffice.gov.ng", dimension=DimensionKey.FINANCIAL, source_type=SourceType.GOVERNMENT, tier=SourceTier.EXTENDED, relevance=NigeriaRelevance.STRONG, rank=3, update="annual", paths=["/", "/reports"], op="site:budgetoffice.gov.ng oil"),
    _src(id="nbs", name="National Bureau of Statistics", url="https://nigerianstat.gov.ng", dimension=DimensionKey.FINANCIAL, source_type=SourceType.GOVERNMENT, tier=SourceTier.EXTENDED, relevance=NigeriaRelevance.STRONG, rank=3, update="monthly", paths=["/elibrary", "/downloads"], op="site:nigerianstat.gov.ng oil"),
    _src(id="unctad", name="UNCTAD", url="https://unctad.org", dimension=DimensionKey.FINANCIAL, source_type=SourceType.FINANCIAL_INSTITUTION, tier=SourceTier.EXTENDED, relevance=NigeriaRelevance.MODERATE, rank=3, update="annual", paths=["/topic/commodities"], op="site:unctad.org Nigeria oil"),
    _src(id="oecd-ecd", name="OECD Economics", url="https://www.oecd.org", dimension=DimensionKey.FINANCIAL, source_type=SourceType.FINANCIAL_INSTITUTION, tier=SourceTier.EXTENDED, relevance=NigeriaRelevance.LOW, rank=2, update="annual", paths=["/economy"], op="site:oecd.org Nigeria commodities"),
    _src(id="kpmg-ng-energy", name="KPMG Nigeria Energy Insights", url="https://kpmg.com/ng", dimension=DimensionKey.FINANCIAL, source_type=SourceType.RESEARCH_FIRM, tier=SourceTier.EXTENDED, relevance=NigeriaRelevance.STRONG, rank=3, update="quarterly", paths=["/en/home/insights.html"], op="site:kpmg.com/ng oil gas"),
]


MARKET_SOURCES: list[SourceRecord] = [
    _src(id="ngx", name="Nigerian Exchange Group", url="https://ngxgroup.com", dimension=DimensionKey.MARKET, source_type=SourceType.EXCHANGE, tier=SourceTier.CORE, relevance=NigeriaRelevance.DIRECT, rank=5, update="daily", paths=["/exchange", "/market-data"], op="site:ngxgroup.com"),
    _src(id="ngx-investor-relations", name="NGX Investors Portal", url="https://investors.ngxgroup.com", dimension=DimensionKey.MARKET, source_type=SourceType.EXCHANGE, tier=SourceTier.CORE, relevance=NigeriaRelevance.DIRECT, rank=4, update="daily", paths=["/"], op="site:investors.ngxgroup.com"),
    _src(id="sec-ng-filings", name="SEC Nigeria Filings", url="https://sec.gov.ng/category/filings", dimension=DimensionKey.MARKET, source_type=SourceType.REGULATOR, tier=SourceTier.CORE, relevance=NigeriaRelevance.DIRECT, rank=5, update="weekly", paths=["/category/filings"], op="site:sec.gov.ng filing"),
    _src(id="nairametrics-markets", name="Nairametrics Markets", url="https://nairametrics.com/category/market", dimension=DimensionKey.MARKET, source_type=SourceType.NEWS, tier=SourceTier.CORE, relevance=NigeriaRelevance.DIRECT, rank=4, update="daily", paths=["/category/market", "/category/energy"], op="site:nairametrics.com market NGX"),
    _src(id="businessday-markets", name="Businessday Markets", url="https://businessday.ng/markets", dimension=DimensionKey.MARKET, source_type=SourceType.NEWS, tier=SourceTier.CORE, relevance=NigeriaRelevance.DIRECT, rank=4, update="daily", paths=["/markets"], op="site:businessday.ng markets"),
    _src(id="lse", name="London Stock Exchange", url="https://www.londonstockexchange.com", dimension=DimensionKey.MARKET, source_type=SourceType.EXCHANGE, tier=SourceTier.EXTENDED, relevance=NigeriaRelevance.MODERATE, rank=4, update="daily", paths=["/"], op="site:londonstockexchange.com SHEL"),
    _src(id="nyse", name="NYSE", url="https://www.nyse.com", dimension=DimensionKey.MARKET, source_type=SourceType.EXCHANGE, tier=SourceTier.EXTENDED, relevance=NigeriaRelevance.MODERATE, rank=4, update="daily", paths=["/quote/XNYS:SHEL"], op="site:nyse.com SHEL"),
    _src(id="seplat-ir", name="Seplat Energy Investor Relations", url="https://www.seplatenergy.com", dimension=DimensionKey.MARKET, source_type=SourceType.COMPANY_IR, tier=SourceTier.CORE, relevance=NigeriaRelevance.DIRECT, rank=4, update="quarterly", paths=["/investors"], op="site:seplatenergy.com investors"),
    _src(id="oando-ir", name="Oando Investor Relations", url="https://oandoplc.com", dimension=DimensionKey.MARKET, source_type=SourceType.COMPANY_IR, tier=SourceTier.CORE, relevance=NigeriaRelevance.DIRECT, rank=4, update="quarterly", paths=["/investor-relations"], op="site:oandoplc.com investor"),
    _src(id="ardova-ir", name="Ardova Investor Relations", url="https://ardovaplc.com", dimension=DimensionKey.MARKET, source_type=SourceType.COMPANY_IR, tier=SourceTier.EXTENDED, relevance=NigeriaRelevance.DIRECT, rank=3, update="quarterly", paths=["/investors"], op="site:ardovaplc.com investor"),
    _src(id="conoil-ir", name="Conoil Investor Relations", url="https://www.conoilplc.com", dimension=DimensionKey.MARKET, source_type=SourceType.COMPANY_IR, tier=SourceTier.EXTENDED, relevance=NigeriaRelevance.DIRECT, rank=3, update="quarterly", paths=["/investor-relations"], op="site:conoilplc.com investor"),
    _src(id="shell-plc-ir", name="Shell plc Investor Relations", url="https://www.shell.com/investors", dimension=DimensionKey.MARKET, source_type=SourceType.COMPANY_IR, tier=SourceTier.EXTENDED, relevance=NigeriaRelevance.MODERATE, rank=4, update="quarterly", paths=["/investors"], op="site:shell.com investors"),
    _src(id="totalenergies-ir", name="TotalEnergies Investors", url="https://totalenergies.com/investors", dimension=DimensionKey.MARKET, source_type=SourceType.COMPANY_IR, tier=SourceTier.EXTENDED, relevance=NigeriaRelevance.MODERATE, rank=4, update="quarterly", paths=["/investors"], op="site:totalenergies.com investors"),
    _src(id="eni-investors", name="Eni Investors", url="https://www.eni.com/en-IT/investors.html", dimension=DimensionKey.MARKET, source_type=SourceType.COMPANY_IR, tier=SourceTier.EXTENDED, relevance=NigeriaRelevance.MODERATE, rank=4, update="quarterly", paths=["/en-IT/investors.html"], op="site:eni.com investors"),
    _src(id="exxon-ir", name="ExxonMobil Investors", url="https://corporate.exxonmobil.com/investors", dimension=DimensionKey.MARKET, source_type=SourceType.COMPANY_IR, tier=SourceTier.EXTENDED, relevance=NigeriaRelevance.MODERATE, rank=4, update="quarterly", paths=["/investors"], op="site:exxonmobil.com investors"),
    _src(id="chevron-ir", name="Chevron Investors", url="https://www.chevron.com/investors", dimension=DimensionKey.MARKET, source_type=SourceType.COMPANY_IR, tier=SourceTier.EXTENDED, relevance=NigeriaRelevance.MODERATE, rank=4, update="quarterly", paths=["/investors"], op="site:chevron.com investors"),
    _src(id="marketscreener", name="MarketScreener", url="https://www.marketscreener.com", dimension=DimensionKey.MARKET, source_type=SourceType.DATA_PLATFORM, tier=SourceTier.EXTENDED, relevance=NigeriaRelevance.MODERATE, rank=2, update="daily", paths=["/"], op="site:marketscreener.com seplat"),
    _src(id="investing", name="Investing.com", url="https://www.investing.com", dimension=DimensionKey.MARKET, source_type=SourceType.DATA_PLATFORM, tier=SourceTier.EXTENDED, relevance=NigeriaRelevance.LOW, rank=2, update="daily", paths=["/"], op="site:investing.com nigeria stocks"),
]


EXPERT_SOURCES: list[SourceRecord] = [
    _src(id="africa-oil-gas-report", name="Africa Oil and Gas Report", url="https://africaoilgasreport.com", dimension=DimensionKey.EXPERT, source_type=SourceType.PUBLICATION, tier=SourceTier.CORE, relevance=NigeriaRelevance.DIRECT, rank=5, update="weekly", paths=["/", "/upstream", "/nigeria"], op="site:africaoilgasreport.com"),
    _src(id="spglobal-ci", name="S&P Global Commodity Insights", url="https://www.spglobal.com/commodityinsights", dimension=DimensionKey.EXPERT, source_type=SourceType.RESEARCH_FIRM, tier=SourceTier.CORE, relevance=NigeriaRelevance.STRONG, rank=5, update="daily", paths=["/en/market-insights/latest-news/oil"], op="site:spglobal.com commodity insights nigeria"),
    _src(id="argus", name="Argus Media", url="https://www.argusmedia.com", dimension=DimensionKey.EXPERT, source_type=SourceType.PUBLICATION, tier=SourceTier.CORE, relevance=NigeriaRelevance.STRONG, rank=5, update="daily", paths=["/en/news-and-insights"], op="site:argusmedia.com nigeria crude"),
    _src(id="platts", name="Platts", url="https://www.spglobal.com/platts", dimension=DimensionKey.EXPERT, source_type=SourceType.PUBLICATION, tier=SourceTier.CORE, relevance=NigeriaRelevance.STRONG, rank=5, update="daily", paths=["/en/market-insights/latest-news"], op="site:spglobal.com/platts nigeria"),
    _src(id="woodmac", name="Wood Mackenzie", url="https://www.woodmac.com", dimension=DimensionKey.EXPERT, source_type=SourceType.RESEARCH_FIRM, tier=SourceTier.CORE, relevance=NigeriaRelevance.STRONG, rank=5, update="weekly", paths=["/news", "/research"], op="site:woodmac.com nigeria"),
    _src(id="rystad", name="Rystad Energy", url="https://www.rystadenergy.com", dimension=DimensionKey.EXPERT, source_type=SourceType.RESEARCH_FIRM, tier=SourceTier.CORE, relevance=NigeriaRelevance.STRONG, rank=4, update="weekly", paths=["/news"], op="site:rystadenergy.com nigeria"),
    _src(id="energy-intelligence", name="Energy Intelligence", url="https://www.energyintel.com", dimension=DimensionKey.EXPERT, source_type=SourceType.PUBLICATION, tier=SourceTier.CORE, relevance=NigeriaRelevance.STRONG, rank=4, update="daily", paths=["/"], op="site:energyintel.com nigeria"),
    _src(id="reuters-energy", name="Reuters Energy", url="https://www.reuters.com/business/energy", dimension=DimensionKey.EXPERT, source_type=SourceType.PUBLICATION, tier=SourceTier.CORE, relevance=NigeriaRelevance.STRONG, rank=4, update="daily", paths=["/business/energy"], op="site:reuters.com nigeria energy analysis"),
    _src(id="bloomberg-energy", name="Bloomberg Energy", url="https://www.bloomberg.com/energy", dimension=DimensionKey.EXPERT, source_type=SourceType.PUBLICATION, tier=SourceTier.CORE, relevance=NigeriaRelevance.STRONG, rank=4, update="daily", paths=["/energy"], op="site:bloomberg.com nigeria oil"),
    _src(id="chatham-house", name="Chatham House", url="https://www.chathamhouse.org", dimension=DimensionKey.EXPERT, source_type=SourceType.THINK_TANK, tier=SourceTier.CORE, relevance=NigeriaRelevance.STRONG, rank=4, update="monthly", paths=["/topics/energy", "/regions/africa"], op="site:chathamhouse.org nigeria energy"),
    _src(id="nrgi", name="NRGI", url="https://resourcegovernance.org", dimension=DimensionKey.EXPERT, source_type=SourceType.THINK_TANK, tier=SourceTier.CORE, relevance=NigeriaRelevance.DIRECT, rank=5, update="monthly", paths=["/countries/nigeria"], op="site:resourcegovernance.org nigeria"),
    _src(id="ieefa", name="IEEFA", url="https://ieefa.org", dimension=DimensionKey.EXPERT, source_type=SourceType.THINK_TANK, tier=SourceTier.CORE, relevance=NigeriaRelevance.MODERATE, rank=3, update="weekly", paths=["/"], op="site:ieefa.org nigeria"),
    _src(id="oxford-energy", name="Oxford Institute for Energy Studies", url="https://www.oxfordenergy.org", dimension=DimensionKey.EXPERT, source_type=SourceType.THINK_TANK, tier=SourceTier.EXTENDED, relevance=NigeriaRelevance.MODERATE, rank=4, update="monthly", paths=["/publications"], op="site:oxfordenergy.org nigeria"),
    _src(id="carnegie-africa", name="Carnegie Africa Program", url="https://carnegieendowment.org", dimension=DimensionKey.EXPERT, source_type=SourceType.THINK_TANK, tier=SourceTier.EXTENDED, relevance=NigeriaRelevance.MODERATE, rank=3, update="monthly", paths=["/regions/africa"], op="site:carnegieendowment.org nigeria energy"),
    _src(id="brookings-africa", name="Brookings Africa", url="https://www.brookings.edu", dimension=DimensionKey.EXPERT, source_type=SourceType.THINK_TANK, tier=SourceTier.EXTENDED, relevance=NigeriaRelevance.MODERATE, rank=3, update="monthly", paths=["/topic/africa"], op="site:brookings.edu nigeria oil"),
    _src(id="csis-energy", name="CSIS Energy Security", url="https://www.csis.org", dimension=DimensionKey.EXPERT, source_type=SourceType.THINK_TANK, tier=SourceTier.EXTENDED, relevance=NigeriaRelevance.LOW, rank=3, update="monthly", paths=["/programs/energy-security"], op="site:csis.org nigeria energy"),
    _src(id="energy-connects", name="Energy Connects", url="https://www.energyconnects.com", dimension=DimensionKey.EXPERT, source_type=SourceType.PUBLICATION, tier=SourceTier.EXTENDED, relevance=NigeriaRelevance.STRONG, rank=3, update="weekly", paths=["/news"], op="site:energyconnects.com nigeria"),
    _src(id="offshore-technology", name="Offshore Technology", url="https://www.offshore-technology.com", dimension=DimensionKey.EXPERT, source_type=SourceType.PUBLICATION, tier=SourceTier.EXTENDED, relevance=NigeriaRelevance.MODERATE, rank=2, update="daily", paths=["/"], op="site:offshore-technology.com nigeria"),
    _src(id="upstream-online", name="Upstream Online", url="https://www.upstreamonline.com", dimension=DimensionKey.EXPERT, source_type=SourceType.PUBLICATION, tier=SourceTier.EXTENDED, relevance=NigeriaRelevance.MODERATE, rank=3, update="daily", paths=["/"], op="site:upstreamonline.com nigeria"),
    _src(id="energy-voice", name="Energy Voice", url="https://www.energyvoice.com", dimension=DimensionKey.EXPERT, source_type=SourceType.PUBLICATION, tier=SourceTier.EXTENDED, relevance=NigeriaRelevance.MODERATE, rank=2, update="daily", paths=["/"], op="site:energyvoice.com nigeria"),
    _src(id="ogj", name="Oil and Gas Journal", url="https://www.ogj.com", dimension=DimensionKey.EXPERT, source_type=SourceType.PUBLICATION, tier=SourceTier.EXTENDED, relevance=NigeriaRelevance.MODERATE, rank=3, update="weekly", paths=["/"], op="site:ogj.com nigeria"),
    _src(id="spe", name="Society of Petroleum Engineers", url="https://www.spe.org", dimension=DimensionKey.EXPERT, source_type=SourceType.ASSOCIATION, tier=SourceTier.EXTENDED, relevance=NigeriaRelevance.MODERATE, rank=3, update="monthly", paths=["/"], op="site:spe.org nigeria"),
]


NEWS_SOURCES: list[SourceRecord] = [
    _src(id="businessday", name="Businessday Nigeria", url="https://businessday.ng", dimension=DimensionKey.NEWS, source_type=SourceType.NEWS, tier=SourceTier.CORE, relevance=NigeriaRelevance.DIRECT, rank=5, update="daily", paths=["/energy", "/markets"], op="site:businessday.ng energy"),
    _src(id="nairametrics", name="Nairametrics", url="https://nairametrics.com", dimension=DimensionKey.NEWS, source_type=SourceType.NEWS, tier=SourceTier.CORE, relevance=NigeriaRelevance.DIRECT, rank=5, update="daily", paths=["/category/energy", "/category/oil-gas"], op="site:nairametrics.com energy"),
    _src(id="thisday", name="ThisDay", url="https://www.thisdaylive.com", dimension=DimensionKey.NEWS, source_type=SourceType.NEWS, tier=SourceTier.CORE, relevance=NigeriaRelevance.DIRECT, rank=4, update="daily", paths=["/index.php/category/business"], op="site:thisdaylive.com oil"),
    _src(id="punch", name="The Punch", url="https://punchng.com", dimension=DimensionKey.NEWS, source_type=SourceType.NEWS, tier=SourceTier.CORE, relevance=NigeriaRelevance.DIRECT, rank=4, update="daily", paths=["/topics/business"], op="site:punchng.com oil"),
    _src(id="guardian-ng", name="The Guardian Nigeria", url="https://guardian.ng", dimension=DimensionKey.NEWS, source_type=SourceType.NEWS, tier=SourceTier.CORE, relevance=NigeriaRelevance.DIRECT, rank=4, update="daily", paths=["/business-services"], op="site:guardian.ng oil"),
    _src(id="reuters", name="Reuters", url="https://www.reuters.com", dimension=DimensionKey.NEWS, source_type=SourceType.NEWS, tier=SourceTier.CORE, relevance=NigeriaRelevance.STRONG, rank=5, update="daily", paths=["/world/africa", "/business/energy"], op="site:reuters.com nigeria oil"),
    _src(id="bloomberg", name="Bloomberg", url="https://www.bloomberg.com", dimension=DimensionKey.NEWS, source_type=SourceType.NEWS, tier=SourceTier.CORE, relevance=NigeriaRelevance.STRONG, rank=5, update="daily", paths=["/africa", "/energy"], op="site:bloomberg.com nigeria oil"),
    _src(id="ft", name="Financial Times", url="https://www.ft.com", dimension=DimensionKey.NEWS, source_type=SourceType.NEWS, tier=SourceTier.EXTENDED, relevance=NigeriaRelevance.STRONG, rank=4, update="daily", paths=["/world/africa"], op="site:ft.com nigeria oil"),
    _src(id="wsj", name="Wall Street Journal", url="https://www.wsj.com", dimension=DimensionKey.NEWS, source_type=SourceType.NEWS, tier=SourceTier.EXTENDED, relevance=NigeriaRelevance.MODERATE, rank=3, update="daily", paths=["/news/business"], op="site:wsj.com nigeria oil"),
    _src(id="premium-times", name="Premium Times", url="https://www.premiumtimesng.com", dimension=DimensionKey.NEWS, source_type=SourceType.NEWS, tier=SourceTier.EXTENDED, relevance=NigeriaRelevance.DIRECT, rank=4, update="daily", paths=["/business"], op="site:premiumtimesng.com oil"),
    _src(id="the-cable", name="TheCable", url="https://www.thecable.ng", dimension=DimensionKey.NEWS, source_type=SourceType.NEWS, tier=SourceTier.EXTENDED, relevance=NigeriaRelevance.DIRECT, rank=3, update="daily", paths=["/category/business"], op="site:thecable.ng oil"),
    _src(id="channels", name="Channels TV", url="https://www.channelstv.com", dimension=DimensionKey.NEWS, source_type=SourceType.NEWS, tier=SourceTier.EXTENDED, relevance=NigeriaRelevance.DIRECT, rank=3, update="daily", paths=["/category/business"], op="site:channelstv.com oil"),
    _src(id="arise", name="Arise News", url="https://www.arise.tv", dimension=DimensionKey.NEWS, source_type=SourceType.NEWS, tier=SourceTier.EXTENDED, relevance=NigeriaRelevance.DIRECT, rank=3, update="daily", paths=["/category/business"], op="site:arise.tv nigeria oil"),
    _src(id="vanguard", name="Vanguard", url="https://www.vanguardngr.com", dimension=DimensionKey.NEWS, source_type=SourceType.NEWS, tier=SourceTier.EXTENDED, relevance=NigeriaRelevance.DIRECT, rank=3, update="daily", paths=["/category/business"], op="site:vanguardngr.com oil"),
    _src(id="daily-trust", name="Daily Trust", url="https://dailytrust.com", dimension=DimensionKey.NEWS, source_type=SourceType.NEWS, tier=SourceTier.EXTENDED, relevance=NigeriaRelevance.DIRECT, rank=3, update="daily", paths=["/business"], op="site:dailytrust.com oil"),
    _src(id="leadership", name="Leadership", url="https://leadership.ng", dimension=DimensionKey.NEWS, source_type=SourceType.NEWS, tier=SourceTier.EXTENDED, relevance=NigeriaRelevance.DIRECT, rank=3, update="daily", paths=["/business"], op="site:leadership.ng oil"),
    _src(id="tribune", name="Nigerian Tribune", url="https://tribuneonlineng.com", dimension=DimensionKey.NEWS, source_type=SourceType.NEWS, tier=SourceTier.EXTENDED, relevance=NigeriaRelevance.DIRECT, rank=2, update="daily", paths=["/category/business"], op="site:tribuneonlineng.com oil"),
    _src(id="sun-news", name="The Sun", url="https://sunnewsonline.com", dimension=DimensionKey.NEWS, source_type=SourceType.NEWS, tier=SourceTier.EXTENDED, relevance=NigeriaRelevance.DIRECT, rank=2, update="daily", paths=["/category/business"], op="site:sunnewsonline.com oil"),
    _src(id="bbc-africa", name="BBC Africa", url="https://www.bbc.com/news/world/africa", dimension=DimensionKey.NEWS, source_type=SourceType.NEWS, tier=SourceTier.EXTENDED, relevance=NigeriaRelevance.STRONG, rank=4, update="daily", paths=["/news/world/africa"], op="site:bbc.com nigeria oil"),
    _src(id="cnn-africa", name="CNN Africa", url="https://edition.cnn.com/africa", dimension=DimensionKey.NEWS, source_type=SourceType.NEWS, tier=SourceTier.EXTENDED, relevance=NigeriaRelevance.MODERATE, rank=3, update="daily", paths=["/africa"], op="site:cnn.com nigeria oil"),
    _src(id="aljazeera-africa", name="Al Jazeera Africa", url="https://www.aljazeera.com/africa", dimension=DimensionKey.NEWS, source_type=SourceType.NEWS, tier=SourceTier.EXTENDED, relevance=NigeriaRelevance.MODERATE, rank=3, update="daily", paths=["/africa"], op="site:aljazeera.com nigeria oil"),
    _src(id="ap-news", name="Associated Press", url="https://apnews.com", dimension=DimensionKey.NEWS, source_type=SourceType.NEWS, tier=SourceTier.EXTENDED, relevance=NigeriaRelevance.MODERATE, rank=3, update="daily", paths=["/hub/africa"], op="site:apnews.com nigeria oil"),
    _src(id="sahara-reporters", name="Sahara Reporters", url="https://saharareporters.com", dimension=DimensionKey.NEWS, source_type=SourceType.NEWS, tier=SourceTier.EXTENDED, relevance=NigeriaRelevance.MODERATE, rank=2, update="daily", paths=["/"], op="site:saharareporters.com oil"),
    _src(id="ripples", name="Ripples Nigeria", url="https://www.ripplesnigeria.com", dimension=DimensionKey.NEWS, source_type=SourceType.NEWS, tier=SourceTier.EXTENDED, relevance=NigeriaRelevance.MODERATE, rank=2, update="daily", paths=["/category/business"], op="site:ripplesnigeria.com oil"),
]


INTERNATIONAL_SOURCES: list[SourceRecord] = [
    _src(id="iea", name="International Energy Agency", url="https://www.iea.org", dimension=DimensionKey.INTERNATIONAL, source_type=SourceType.FINANCIAL_INSTITUTION, tier=SourceTier.CORE, relevance=NigeriaRelevance.DIRECT, rank=5, update="annual", paths=["/countries/nigeria", "/reports"], op="site:iea.org nigeria"),
    _src(id="opec", name="OPEC", url="https://www.opec.org", dimension=DimensionKey.INTERNATIONAL, source_type=SourceType.FINANCIAL_INSTITUTION, tier=SourceTier.CORE, relevance=NigeriaRelevance.DIRECT, rank=5, update="monthly", paths=["/opec_web/en"], op="site:opec.org nigeria"),
    _src(id="eia", name="US EIA", url="https://www.eia.gov", dimension=DimensionKey.INTERNATIONAL, source_type=SourceType.FINANCIAL_INSTITUTION, tier=SourceTier.CORE, relevance=NigeriaRelevance.DIRECT, rank=5, update="annual", paths=["/international/analysis/country/NGA"], op="site:eia.gov nigeria"),
    _src(id="world-bank-intl", name="World Bank Energy", url="https://www.worldbank.org/en/topic/energy", dimension=DimensionKey.INTERNATIONAL, source_type=SourceType.FINANCIAL_INSTITUTION, tier=SourceTier.CORE, relevance=NigeriaRelevance.STRONG, rank=5, update="quarterly", paths=["/en/topic/energy"], op="site:worldbank.org nigeria energy"),
    _src(id="imf-intl", name="IMF Publications", url="https://www.imf.org/en/Publications", dimension=DimensionKey.INTERNATIONAL, source_type=SourceType.FINANCIAL_INSTITUTION, tier=SourceTier.CORE, relevance=NigeriaRelevance.STRONG, rank=5, update="annual", paths=["/en/Publications"], op="site:imf.org nigeria oil"),
    _src(id="afdb-energy", name="AfDB Energy", url="https://www.afdb.org/en/topics-and-sectors/sectors/energy", dimension=DimensionKey.INTERNATIONAL, source_type=SourceType.FINANCIAL_INSTITUTION, tier=SourceTier.CORE, relevance=NigeriaRelevance.STRONG, rank=4, update="quarterly", paths=["/en/topics-and-sectors/sectors/energy"], op="site:afdb.org nigeria energy"),
    _src(id="unep", name="UNEP", url="https://www.unep.org", dimension=DimensionKey.INTERNATIONAL, source_type=SourceType.GOVERNMENT, tier=SourceTier.CORE, relevance=NigeriaRelevance.MODERATE, rank=4, update="annual", paths=["/regions/africa"], op="site:unep.org nigeria oil"),
    _src(id="undp", name="UNDP", url="https://www.undp.org", dimension=DimensionKey.INTERNATIONAL, source_type=SourceType.GOVERNMENT, tier=SourceTier.EXTENDED, relevance=NigeriaRelevance.MODERATE, rank=3, update="annual", paths=["/africa"], op="site:undp.org nigeria energy"),
    _src(id="irena", name="IRENA", url="https://www.irena.org", dimension=DimensionKey.INTERNATIONAL, source_type=SourceType.FINANCIAL_INSTITUTION, tier=SourceTier.EXTENDED, relevance=NigeriaRelevance.MODERATE, rank=3, update="annual", paths=["/publications"], op="site:irena.org nigeria"),
    _src(id="unido", name="UNIDO", url="https://www.unido.org", dimension=DimensionKey.INTERNATIONAL, source_type=SourceType.GOVERNMENT, tier=SourceTier.EXTENDED, relevance=NigeriaRelevance.MODERATE, rank=3, update="annual", paths=["/where-we-work/africa/nigeria"], op="site:unido.org nigeria energy"),
    _src(id="wto", name="WTO", url="https://www.wto.org", dimension=DimensionKey.INTERNATIONAL, source_type=SourceType.GOVERNMENT, tier=SourceTier.EXTENDED, relevance=NigeriaRelevance.LOW, rank=2, update="annual", paths=["/"], op="site:wto.org nigeria fuel"),
    _src(id="unctad-intl", name="UNCTAD Commodities", url="https://unctad.org/topic/commodities", dimension=DimensionKey.INTERNATIONAL, source_type=SourceType.FINANCIAL_INSTITUTION, tier=SourceTier.EXTENDED, relevance=NigeriaRelevance.MODERATE, rank=3, update="annual", paths=["/topic/commodities"], op="site:unctad.org nigeria commodities"),
    _src(id="ecowas-energy-intl", name="ECOWAS Energy Directorate", url="https://www.ecowas.int/special-post/energy", dimension=DimensionKey.INTERNATIONAL, source_type=SourceType.GOVERNMENT, tier=SourceTier.EXTENDED, relevance=NigeriaRelevance.STRONG, rank=3, update="quarterly", paths=["/special-post/energy"], op="site:ecowas.int nigeria energy"),
    _src(id="au-energy", name="African Union Energy", url="https://au.int", dimension=DimensionKey.INTERNATIONAL, source_type=SourceType.GOVERNMENT, tier=SourceTier.EXTENDED, relevance=NigeriaRelevance.MODERATE, rank=2, update="quarterly", paths=["/"], op="site:au.int nigeria energy"),
    _src(id="g20-energy", name="G20 Energy Track", url="https://www.g20.org", dimension=DimensionKey.INTERNATIONAL, source_type=SourceType.GOVERNMENT, tier=SourceTier.EXTENDED, relevance=NigeriaRelevance.LOW, rank=2, update="annual", paths=["/"], op="site:g20.org energy nigeria"),
    _src(id="iaee", name="International Association for Energy Economics", url="https://www.iaee.org", dimension=DimensionKey.INTERNATIONAL, source_type=SourceType.ASSOCIATION, tier=SourceTier.EXTENDED, relevance=NigeriaRelevance.LOW, rank=2, update="monthly", paths=["/"], op="site:iaee.org nigeria oil"),
    _src(id="opec-fund", name="OPEC Fund", url="https://opecfund.org", dimension=DimensionKey.INTERNATIONAL, source_type=SourceType.FINANCIAL_INSTITUTION, tier=SourceTier.EXTENDED, relevance=NigeriaRelevance.MODERATE, rank=3, update="quarterly", paths=["/"], op="site:opecfund.org nigeria"),
    _src(id="commonwealth-energy", name="Commonwealth Energy", url="https://thecommonwealth.org", dimension=DimensionKey.INTERNATIONAL, source_type=SourceType.GOVERNMENT, tier=SourceTier.EXTENDED, relevance=NigeriaRelevance.LOW, rank=2, update="annual", paths=["/"], op="site:thecommonwealth.org nigeria energy"),
]


ASSOCIATION_SOURCES: list[SourceRecord] = [
    _src(id="opts", name="OPTS", url="https://lcci.com.ng/opts", dimension=DimensionKey.ASSOCIATIONS, source_type=SourceType.ASSOCIATION, tier=SourceTier.CORE, relevance=NigeriaRelevance.DIRECT, rank=5, update="quarterly", paths=["/opts", "/publication"], op="site:lcci.com.ng OPTS"),
    _src(id="petan", name="PETAN", url="https://petan.org", dimension=DimensionKey.ASSOCIATIONS, source_type=SourceType.ASSOCIATION, tier=SourceTier.CORE, relevance=NigeriaRelevance.DIRECT, rank=4, update="monthly", paths=["/", "/news"], op="site:petan.org"),
    _src(id="pengassan", name="PENGASSAN", url="https://pengassan.org", dimension=DimensionKey.ASSOCIATIONS, source_type=SourceType.ASSOCIATION, tier=SourceTier.CORE, relevance=NigeriaRelevance.DIRECT, rank=4, update="monthly", paths=["/", "/press-statements"], op="site:pengassan.org"),
    _src(id="nupeng", name="NUPENG", url="https://www.nupeng.org", dimension=DimensionKey.ASSOCIATIONS, source_type=SourceType.ASSOCIATION, tier=SourceTier.CORE, relevance=NigeriaRelevance.DIRECT, rank=4, update="monthly", paths=["/", "/news"], op="site:nupeng.org"),
    _src(id="nies", name="NIES", url="https://www.nigeriaenergysummit.org", dimension=DimensionKey.ASSOCIATIONS, source_type=SourceType.ASSOCIATION, tier=SourceTier.CORE, relevance=NigeriaRelevance.DIRECT, rank=4, update="annual", paths=["/", "/news", "/publications"], op="site:nigeriaenergysummit.org"),
    _src(id="iogp", name="IOGP", url="https://www.iogp.org", dimension=DimensionKey.ASSOCIATIONS, source_type=SourceType.ASSOCIATION, tier=SourceTier.CORE, relevance=NigeriaRelevance.MODERATE, rank=4, update="quarterly", paths=["/reports", "/news"], op="site:iogp.org nigeria"),
    _src(id="appo", name="APPO", url="https://appo-oil.org", dimension=DimensionKey.ASSOCIATIONS, source_type=SourceType.ASSOCIATION, tier=SourceTier.CORE, relevance=NigeriaRelevance.STRONG, rank=4, update="quarterly", paths=["/", "/news"], op="site:appo-oil.org nigeria"),
    _src(id="ipman", name="IPMAN", url="https://ipman-ng.com", dimension=DimensionKey.ASSOCIATIONS, source_type=SourceType.ASSOCIATION, tier=SourceTier.EXTENDED, relevance=NigeriaRelevance.STRONG, rank=3, update="monthly", paths=["/"], op="site:ipman-ng.com"),
    _src(id="dapman", name="DAPPMAN", url="https://dapman.org", dimension=DimensionKey.ASSOCIATIONS, source_type=SourceType.ASSOCIATION, tier=SourceTier.EXTENDED, relevance=NigeriaRelevance.STRONG, rank=3, update="monthly", paths=["/"], op="site:dapman.org"),
    _src(id="momang", name="MOMAN", url="https://moman.org", dimension=DimensionKey.ASSOCIATIONS, source_type=SourceType.ASSOCIATION, tier=SourceTier.EXTENDED, relevance=NigeriaRelevance.STRONG, rank=3, update="monthly", paths=["/"], op="site:moman.org"),
    _src(id="nman", name="NMAN", url="https://www.nigerianmaritimemedia.com", dimension=DimensionKey.ASSOCIATIONS, source_type=SourceType.ASSOCIATION, tier=SourceTier.EXTENDED, relevance=NigeriaRelevance.MODERATE, rank=2, update="monthly", paths=["/"], op="NMAN Nigeria maritime oil"),
    _src(id="spe-nigeria", name="SPE Nigeria Council", url="https://connect.spe.org/nigeriacouncil", dimension=DimensionKey.ASSOCIATIONS, source_type=SourceType.ASSOCIATION, tier=SourceTier.EXTENDED, relevance=NigeriaRelevance.MODERATE, rank=3, update="monthly", paths=["/nigeriacouncil/home"], op="site:connect.spe.org nigeria"),
    _src(id="nape", name="NAPE", url="https://www.nape.org.ng", dimension=DimensionKey.ASSOCIATIONS, source_type=SourceType.ASSOCIATION, tier=SourceTier.EXTENDED, relevance=NigeriaRelevance.STRONG, rank=3, update="monthly", paths=["/", "/publications"], op="site:nape.org.ng"),
    _src(id="nigerian-gas-association", name="Nigerian Gas Association", url="https://www.nigeriangas.org", dimension=DimensionKey.ASSOCIATIONS, source_type=SourceType.ASSOCIATION, tier=SourceTier.EXTENDED, relevance=NigeriaRelevance.STRONG, rank=3, update="monthly", paths=["/", "/news"], op="site:nigeriangas.org"),
    _src(id="lcci-energy", name="LCCI Energy Group", url="https://lcci.com.ng", dimension=DimensionKey.ASSOCIATIONS, source_type=SourceType.ASSOCIATION, tier=SourceTier.EXTENDED, relevance=NigeriaRelevance.STRONG, rank=3, update="monthly", paths=["/"], op="site:lcci.com.ng energy"),
    _src(id="african-energy-chamber", name="African Energy Chamber", url="https://energychamber.org", dimension=DimensionKey.ASSOCIATIONS, source_type=SourceType.ASSOCIATION, tier=SourceTier.EXTENDED, relevance=NigeriaRelevance.MODERATE, rank=3, update="weekly", paths=["/", "/news"], op="site:energychamber.org nigeria"),
    _src(id="nipc", name="NIPC", url="https://www.nipc.gov.ng", dimension=DimensionKey.ASSOCIATIONS, source_type=SourceType.GOVERNMENT, tier=SourceTier.EXTENDED, relevance=NigeriaRelevance.MODERATE, rank=3, update="monthly", paths=["/", "/news"], op="site:nipc.gov.ng oil"),
    _src(id="icc-nigeria", name="ICC Nigeria", url="https://www.iccnigeria.org", dimension=DimensionKey.ASSOCIATIONS, source_type=SourceType.ASSOCIATION, tier=SourceTier.EXTENDED, relevance=NigeriaRelevance.LOW, rank=2, update="monthly", paths=["/"], op="site:iccnigeria.org oil"),
]


ALL_SOURCE_BANK: list[SourceRecord] = (
    REGULATORY_SOURCES
    + FINANCIAL_SOURCES
    + MARKET_SOURCES
    + EXPERT_SOURCES
    + NEWS_SOURCES
    + INTERNATIONAL_SOURCES
    + ASSOCIATION_SOURCES
)


def source_bank_stats() -> dict[str, int]:
    by_dimension = {
        "dimension_1_regulatory": len(REGULATORY_SOURCES),
        "dimension_2_financial_institutions": len(FINANCIAL_SOURCES),
        "dimension_3_market_listing": len(MARKET_SOURCES),
        "dimension_4_expert_opinion": len(EXPERT_SOURCES),
        "dimension_5_news": len(NEWS_SOURCES),
        "dimension_6_international_orgs": len(INTERNATIONAL_SOURCES),
        "dimension_7_industry_associations": len(ASSOCIATION_SOURCES),
    }
    return {
        "total": len(ALL_SOURCE_BANK),
        "core": len([s for s in ALL_SOURCE_BANK if s.tier.value == "core"]),
        "extended": len([s for s in ALL_SOURCE_BANK if s.tier.value == "extended"]),
        **by_dimension,
    }
