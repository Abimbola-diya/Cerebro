# Cerebro Oil & Gas Upstream Producer Database — Complete Schema Context Document

**Version:** 2.0 (Comprehensive)  
**Generated:** April 15, 2026  
**Target User:** Large Language Model (Claude, Groq Llama, or equivalent) generating Cypher queries  
**Purpose:** Provide exhaustive schema definition to ensure defensible, type-safe Cypher generation

---

## Table of Contents

1. [Core Database Structure](#core-database-structure)
2. [Node Types & Properties](#node-types--properties)
3. [Relationship Types](#relationship-types)
4. [All 54 Entities (Complete Roster)](#all-54-entities-complete-roster)
5. [Data Type Handling & Defensive Patterns](#data-type-handling--defensive-patterns)
6. [Property Categories & Enum Values](#property-categories--enum-values)
7. [Critical Rules & Constraints](#critical-rules--constraints)
8. [Query Patterns & Examples](#query-patterns--examples)

---

## Core Database Structure

### Nodes in the Graph

The database contains **6 primary node types**:

| Node Type | Purpose | Quantity (Est.) | Key Identifiers |
|-----------|---------|-----------------|-----------------|
| **Entity** | Base node for any upstream actor | 54 | `id` (unique string) |
| **UpstreamProducer** | Companies that hold oil/gas licenses | 54 | `id`, inherits Entity properties |
| **Operator** | UpstreamProducer subtype: operational control | ~40 | `id`, `operator_equity_percentage` |
| **Partner** | UpstreamProducer subtype: JV/PSC partner | ~10 | `id`, no operator_equity_percentage |
| **FPSOOperator** | Infrastructure layer; NOT UpstreamProducer | 3 | `id`, infrastructure-focused |
| **ClassNode** | Classification/categorization node | ~12 | `id`, `name`, `description` |
| **PropertyIndexNode** | Indexed queryable attributes | 26 | `id`, `name`, `property_indexed` |
| **BaselinePropertyIndexNode** | Core schema contract for UpstreamProducer | 25 | `id`, `property_name`, `required` |

---

## Node Types & Properties

### 1. Entity (Base)

**Definition:** Root node for any upstream actor. All UpstreamProducers and FPSOOperators inherit from Entity.

**Core Properties:**

| Property | Type | Required | Notes | Example |
|----------|------|----------|-------|---------|
| `id` | String (lowercase, kebab-case) | YES | Unique identifier. Format: `{first-word}-{descriptor}` | `shell-spdc`, `heirs-energies`, `neconde-energy` |
| `name` | String | YES | Full legal name | `Shell Petroleum Development Company of Nigeria Limited` |
| `short_name` | String | NO | Marketing/abbreviated name | `Shell SPDC`, `CNL`, `NEPL` |
| `parent_company` | String | NO | Holding company or corporate parent | `Shell plc`, `Chevron Corporation`, `NNPC Limited` |
| `incorporation_country` | String | NO | Country of registration | `Nigeria`, `United Kingdom`, `France`, `China` |
| `headquarters_country` | String | NO | Primary HQ location country | `Nigeria`, `United States`, `France` |

---

### 2. UpstreamProducer (Primary Node Type)

**Definition:** Companies holding licenses to explore and produce crude oil and natural gas. Subtypes: `:Operator` or `:Partner`.

**All Properties (Exhaustive List):**

#### 2A. Identity & Organizational Properties

| Property | Type | Required | NOT_AVAILABLE Handling | Notes & Examples |
|----------|------|----------|------------------------|------------------|
| `id` | String | YES | Never | Unique identifier (inherits from Entity) |
| `name` | String | YES | Never | Full legal name (inherits from Entity) |
| `short_name` | String | NO | Absent property | Abbreviated form |
| `parent_company` | String | NO | Absent property | Corporate parent or holding company |
| `headquarters_country` | String | NO | String `"NOT_AVAILABLE"` | Primary HQ country |
| `incorporation_country` | String | NO | String `"NOT_AVAILABLE"` | Country of registration: `"Nigeria"`, `"United Kingdom"`, `"United States"`, `"France"`, `"China"` |
| `sub_type` | String | NO | Absent property | Classification: `"IOC"` (International Oil Company), `"NOC"` (National Oil Company), `"LargeIndigenous"`, `"MarginalFieldOperator"`, `"IndigenousAggregate"` |
| `former_name` | String | NO | Absent property | For rebranded entities (e.g., `"Nigerian Agip Oil Company Limited"` → Oando) |
| `entity_status` | String | NO | Absent property | `"active"`, `"transitioned"`, `"disputed"`, `"divesting"` |

#### 2B. Ownership & Equity Structure

| Property | Type | Required | NOT_AVAILABLE Handling | Notes & Examples |
|----------|------|----------|------------------------|------------------|
| `nnpc_equity_percentage` | Float | NO | Float `0.0` or String `"N/A"` or `"NOT_AVAILABLE"` | NNPC stake (0–100%). Ex: `55.0`, `60.0`, `100.0`, `0.0` |
| `ioc_equity_percentage` | Float | NO | Float `0.0` or String `"NOT_AVAILABLE"` | IOC/foreign stake (0–100%). For entities with NNPC only, this is `0.0` |
| `operator_equity_percentage` | Float | NO | Absent property; NA for Partners | Operating interest (0–100%). Only present on `:Operator` nodes. Example: `40.0`, `45.0`, `30.0` |
| `other_partners` | Array[String] | NO | Empty `[]` or Absent property | List of partner names: `["TotalEnergies EP Nigeria - 10%", "SPDC - 10%"]` |
| `other_partners_note` | String | NO | Absent property | Descriptive note for complex equity structures (FTSA, cost-recovery, JVs) |
| `equity_structure` | String | NO | Absent property | Narrative description of entire ownership structure |
| `equity_note` | String | NO | Absent property | Clarification for ambiguous structures (PSC vs equity, etc.) |
| `jv_structure_note` | String | NO | Absent property | For Joint Venture operators explaining consortium composition |

#### 2C. Production & Entitlements

| Property | Type | Required | NOT_AVAILABLE Handling | Defensive Cypher Pattern |
|----------|------|----------|------------------------|-------------------------|
| `current_production_bopd` | Float | NO | Float `0.0` or String `"NOT_AVAILABLE"` | "Current daily oil production (barrels per day)" |
| `peak_production_bopd` | Float | NO | Float `0.0` or String `"NOT_AVAILABLE"` | Historical maximum achieved production |
| `peak_production_year` | Integer | NO | Integer `0` or String `"NOT_AVAILABLE"` | Year peak was achieved |
| `nnpc_entitlement_bopd` | Float | NO | Float `0.0` or String `"NOT_AVAILABLE"` | NNPC's daily share (JV equity or PSC allocation) |
| `ioc_entitlement_bopd` | Float | NO | Float `0.0` or String `"NOT_AVAILABLE"` | IOC/foreign contractor's daily share |
| `operator_entitlement_bopd` | Float | NO | Absent property; NA for Partners | Operator's own entitlement (often = operator_equity_percentage × total_production) |
| `current_production_note` | String | NO | Absent property | Qualitative note explaining current production status |
| `production_target_bopd` | Float | NO | Absent property | Forward-looking production target |
| `production_rank` | String | NO | Absent property | Comparative ranking (e.g., "Highest single producer in Nigeria") |

**Defensive Cypher Example:**
```cypher
WHERE (n.current_production_bopd IS NOT NULL 
  AND n.current_production_bopd <> "NOT_AVAILABLE" 
  AND apoc.number.toFloat(toString(n.current_production_bopd)) > 10000)
```

#### 2D. Reserves & Life of Field

| Property | Type | Required | NOT_AVAILABLE Handling | Notes |
|----------|------|----------|------------------------|-------|
| `proven_reserves_mmbbls` | Float | NO | Float `0.0` or String `"NOT_AVAILABLE"` | Proven (2P) reserves in million barrels of oil |
| `proven_reserves_mmboe` | Float | NO | Absent property | Proven reserves in million barrels of oil equivalent (oil + gas) |
| `proven_reserves_note` | String | NO | Absent property | Narrative description of reserve confidence |
| `reserve_life_years` | Float | NO | Float String `"NOT_AVAILABLE"` | Years of production remaining at current rate |
| `reserve_life_note` | String | NO | Absent property | Clarification on reserve status or extension plans |
| `proven_reserves_status` | String | NO | Absent property | `"Mature asset"`, `"Declining"`, `"Stable"`, `"Growth"` |
| `cumulative_production_mmbbls` | Float | NO | Absent property | Total produced to date |

#### 2E. Crude Oil & Products

| Property | Type | Required | NOT_AVAILABLE Handling | Notes & Examples |
|----------|------|----------|------------------------|------------------|
| `crude_types_produced` | Array[String] | NO | Empty `[]` or Absent property | Types of crude: `["light", "medium"]`, `["light", "condensate"]`, `["heavy"]` |
| `crude_grade_name` | String | NO | String `"NOT_AVAILABLE"` or Absent property | Commercial name: `"Bonny Light"`, `"Forcados"`, `"Escravos"`, `"Akpo Condensate"` |
| `avg_cargo_size_bbls` | Float | NO | Float `0.0` or String `"NOT_AVAILABLE"` | Average lift volume in barrels (e.g., `950000`, `1000000`) |

#### 2F. Geographic & Infrastructure

| Property | Type | Required | NOT_AVAILABLE Handling | Notes |
|----------|------|----------|------------------------|-------|
| `operational_area` | Array[String] | NO | Empty `[]` or Absent property | Operational zones: `["onshore"]`, `["shallow offshore"]`, `["deepwater"]`, `["onshore", "swamp", "shallow offshore"]` |
| `latitude` | Float | NO | Absent property or `0.0` | Geographic coordinates (e.g., `4.8156`) |
| `longitude` | Float | NO | Absent property or `0.0` | Geographic coordinates (e.g., `7.0498`) |
| `google_maps_url` | String | NO | Absent property or `"NOT_AVAILABLE"` | Full Google Maps URL for HQ/operational area |
| `nigeria_office_location` | String | NO | Absent property or `"NOT_AVAILABLE"` | Office address: `"Lagos"`, `"Port Harcourt"`, `"Abuja"`, or full address |
| `oml_blocks_held` | Array[String] | NO | Empty `[]` or Absent property | Petroleum mining blocks: `["OML 11", "OML 18"]`, `["PML 23"]` |
| `opl_blocks_held` | Array[String] | NO | Empty `[]` or Absent property | Petroleum prospecting licenses held: `["OPL 283"]` |
| `primary_evacuation_route` | String | NO | String `"NOT_AVAILABLE"` or Absent property | Pipeline/shipping route: `"Trans Niger Pipeline (TNP)"`, `"Bonny Terminal via NCTL"`, `"Direct FPSO offloading"` |
| `primary_export_terminal` | String | NO | String `"NOT_AVAILABLE"` or Absent property | Export hub: `"Bonny Export Terminal"`, `"Forcados Oil Terminal"`, `"Qua Iboe Terminal"` |

#### 2G. Operational Status & Risk

| Property | Type | Required | NOT_AVAILABLE Handling | Valid Values & Notes |
|----------|------|----------|------------------------|---------------------|
| `operational_status` | String | NO | String `"NOT_AVAILABLE"` | `"active"`, `"suspended"`, `"divesting"`, `"pre-production"`, `"field redevelopment"`, `"under court-appointed administration"` |
| `community_relations_risk` | String | NO | Absent property | `"low"`, `"medium"`, `"high"` |
| `security_risk_level` | String | NO | Absent property | `"low"`, `"medium"`, `"high"` (based on theft/sabotage exposure) |
| `production_disruption_history` | String | NO | Absent property | Narrative text describing historical disruptions, force majeure events, or recovery milestones |
| `operational_status_note` | String | NO | Absent property | Additional context (e.g., "transitioning from NAOC to Oando operatorship") |
| `operational_control_note` | String | NO | Absent property | Note on who currently has operational control (disputes, NNPC takeovers, etc.) |

#### 2H. Market & Trading

| Property | Type | Required | NOT_AVAILABLE Handling | Notes & Examples |
|----------|------|----------|------------------------|------------------|
| `offtake_agreement_type` | String | NO | String `"NOT_AVAILABLE"` or Absent property | `"Term contract"`, `"Spot market"`, `"JV marketing"`, `"Sole risk marketing"`, `"FTSA"`, `"Government allocation"` |
| `primary_crude_buyers` | Array[String] | NO | Empty `[]` or Absent property | List of primary customer companies: `["Shell International Trading", "NNPC Trading", "Vitol", "Trafigura"]` |
| `primary_destination_refineries` | Array[String] | NO | Empty `[]` or String `"NOT_AVAILABLE"` | Refinery names: `["Reliance Jamnagar (India)", "Shell Pernis Rotterdam"]`, `"NOT_AVAILABLE"` |
| `primary_export_destinations` | Array[String] | NO | Empty `[]` or Absent property | Country destinations: `["India", "Netherlands", "France"]` |
| `avg_liftings_per_month` | Float | NO | Float `0.0` or String `"NOT_AVAILABLE"` | Number of crude oil lifts/exports per month (e.g., `4`, `0.5`, `0.1`) |

#### 2I. Financial & Compliance

| Property | Type | Required | NOT_AVAILABLE Handling | Notes & Examples |
|----------|------|----------|------------------------|------------------|
| `outstanding_fg_debt_usd` | Float | NO | Float `0.0` or String `"NOT_AVAILABLE"` | Federal Government royalty/penalty arrears in USD |
| `outstanding_fg_debt_ngn` | Float | NO | Float `0.0` or Absent property | FG debt in Nigerian Naira |
| `outstanding_royalties_note` | String | NO | Absent property | Narrative explanation of debt status/reconciliation |
| `annual_report_url` | String | NO | String `"NOT_AVAILABLE"` or Absent property | URL to latest financial disclosures |
| `neiti_audit_reference` | String | NO | String `"NOT_AVAILABLE"` or Absent property | Citation from NEITI OGA reports or official government audits |
| `pac_2025_appearance` | Boolean | NO | Absent property | Whether entity was flagged in House PAC investigations (April 2025) |
| `last_updated` | String | NO | Absent property | ISO 8601 date of last data verification (e.g., `"2026-04-12"`) |

#### 2J. Special Fields (Marginal Fields, Gas, Divestment)

| Property | Type | Required | NOT_AVAILABLE Handling | Notes |
|----------|------|----------|------------------------|-------|
| `marginal_field_round` | Integer | NO | Absent property | `2003`, `2020`, etc. Indicates marginal field awardee |
| `marginal_field_name` | Array[String] | NO | Absent property | Carve-out field names: `["Ajapa"]`, `["Egbonom"]` |
| `is_marginal_field_operator` | Boolean | NO | Absent property | `true` if entity operates marginal field(s) |
| `asset_divestment_status` | String | NO | Absent property | `"not divesting"`, `"actively divesting"`, `"actively acquiring"`, `"disputed"` |
| `known_divested_assets` | Array[String] | NO | Empty `[]` or Absent property | Past divestitures: `["OML 29 (sold to Aiteo, 2015)"]` |
| `associated_gas_production_mmscf` | Float | NO | Float `0.0` or String `"NOT_AVAILABLE"` | Associated gas output (million standard cubic feet) |
| `gas_production_note` | String | NO | Absent property | Narrative on gas utilization, flaring rates, or development plans |
| `gas_reserves_tcf` | Float | NO | Absent property | Gas reserves in trillion cubic feet |
| `project_gazelle_volume_bopd` | Float | NO | Absent property | Specific to NNPC: forward-sale commitment volume |

---

### 3. Operator (Subtype of UpstreamProducer)

**Definition:** UpstreamProducer with operational control and management responsibility.

**Additional/Override Properties:**

| Property | Type | Required | Notes |
|----------|------|----------|-------|
| `operator_equity_percentage` | Float | YES | Operating interest (0–100%). MUST be present; MUST be numeric |
| All inherited UpstreamProducer properties | (inherited) | Per parent definition | Same handling rules apply |

**Key Constraint:** If `operator_equity_percentage` is present and numeric (not `"NOT_AVAILABLE"`), the node is typically labeled `:Operator`. Partners do NOT have this property.

---

### 4. Partner (Subtype of UpstreamProducer)

**Definition:** UpstreamProducer without operational control. Participates via JV or PSC partnership.

**Distinguishing Feature:**

| Property | Type | Presence | Notes |
|----------|------|----------|-------|
| `operator_equity_percentage` | — | ABSENT | Partners never have this property |
| All other UpstreamProducer properties | (inherited) | Per parent definition | Same handling rules apply |

**Common Partner Types:**
- **JV Partner**: Holds equity stake (e.g., `nnpc_equity_percentage`, `ioc_equity_percentage`) in a block operated by another company
- **PSC Partner**: Non-equity contractor in a Production Sharing Contract; has cost-recovery entitlements instead of equity
- **FTSA Partner**: Provides financing and technical services; entitled to cost-recovery + profit-oil share (NOT equity)

---

### 5. FPSOOperator (Infrastructure Layer)

**Definition:** Floating Production Storage Offloading vessel operator. NOT an UpstreamProducer. Separate infrastructure layer.

**Properties:**

| Property | Type | Required | Notes |
|----------|------|----------|-------|
| `id` | String | YES | Kebab-case identifier: `stac-marine-abo`, `abigail-joseph-fpso` |
| `name` | String | YES | Full name: `"STAC Marine Limited"`, `"Abigail-Joseph FPSO Operator"` |
| `short_name` | String | NO | Business name: `"STAC Marine"` |
| `fpso_vessel_name` | String | NO | Vessel name: `"FPSO Abo"`, `"Abigail-Joseph"`, `"Tamara Tokoni"` |
| `throughput_capacity_bopd` | Float | NO | Processing capacity: `15000`, `60000`, `47000` |
| `storage_capacity_bbls` | Float | NO | Storage volume: `930000`, `870000` |
| `location_oml` | String | NO | OML assignment: `"OML 123"` (Adoon FPSO), `"OML 83"` (Abigail-Joseph), `"OML 111"` (Tamara Tokoni) |
| `acquisition_date` | String | NO | When acquired/deployed: `"2023-09-01"` (BW Offshore → STAC Marine, Abo) |
| `operational_status` | String | NO | `"active"`, `"maintenance"`, `"scheduled downtime"` |
| `primary_operator` | String | NO | Parent company: `"STAC Marine Limited"`, `"First E&P"`, `"Century Group"` |

**Key Rule:** FPSOOperators are related to UpstreamProducers via implicit ownership or operational relationships, but are NOT themselves classified as `:UpstreamProducer`. Do NOT expect `current_production_bopd`, `proven_reserves_mmbbls`, or `nnpc_equity_percentage` on FPSO nodes.

---

### 6. ClassNode (Classification)

**Definition:** Organizational node defining categories and classifications for UpstreamProducers.

**Properties:**

| Property | Type | Required | Notes & Examples |
|----------|------|----------|------------------|
| `id` | String | YES | Unique identifier: `"class-upstream-producer"`, `"class-psc-operators-offshore"`, `"class-jv-operators-onshore"` |
| `name` | String | YES | Display name: `"Upstream Producer"`, `"PSC Operators (Offshore)"`, `"JV Operators (Onshore)"` |
| `description` | String | NO | Detailed explanation: `"Companies that hold licenses to explore and produce crude oil"` |
| `created` | String | NO | ISO 8601 timestamp of creation |

**Current ClassNodes in Database:**

| ClassNode ID | Name | Description |
|--------------|------|-------------|
| `class-upstream-producer` | Upstream Producer | Companies that hold licenses to explore and produce crude oil |
| `class-indigenous-operators-2003` | Indigenous Operators (2003 Round) | Domestic Nigerian companies awarded licenses in 2003 inaugural round |
| `class-psc-operators-deepwater` | PSC Operators (Deepwater) | Production Sharing Contract operators in deepwater blocks |
| `class-psc-partners-onshore` | PSC Partners (Onshore) | PSC partners providing capital/services on onshore blocks |
| `class-jv-operators-onshore` | JV Operators (Onshore) | Joint Venture operators with NNPC on onshore blocks |
| `class-fpso-operators` | FPSO Operators | Floating Production Storage Offloading infrastructure operators |
| `class-marginal-operators` | Marginal Field Operators | 2003 and 2020 Marginal Field Round awardees |
| `class-large-indigenous` | Large Indigenous Operators | High-volume indigenous producers |
| `class-noc-entities` | National Oil Company | State-owned oil companies (NNPC Group entities) |
| `class-ioc-deepwater` | International Oil Company (Deepwater) | Foreign operators in deepwater blocks |
| `class-ioc-partner-deepwater` | IOC Partners (Deepwater) | Foreign JV partners in deepwater |

**Relationship:** UpstreamProducers linked to ClassNodes via `:BELONGS_TO` relationship.

---

### 7. PropertyIndexNode (26 Total)

**Definition:** Indexed queryable attributes used to optimize graph queries and enable property-based searches.

**All 26 PropertyIndexNodes:**

| PropertyIndexNode ID | Property Indexed | Node Type(s) | Example Values |
|----------------------|------------------|--------------|-----------------|
| `pidx-production-tier-major` | Production tier (Major ≥100k bopd) | UpstreamProducer | SPDC, CNL, TotalEnergies |
| `pidx-production-tier-mid` | Production tier (Mid 50–99k bopd) | UpstreamProducer | Seplat, Aradel |
| `pidx-production-tier-minor` | Production tier (Minor <50k bopd) | UpstreamProducer | Most marginal operators |
| `pidx-location-onshore` | Location (Onshore) | UpstreamProducer | OML 17, OML 34, OML 56 operators |
| `pidx-location-shallow-offshore` | Location (Shallow Offshore) | UpstreamProducer | OML 83, OML 85 (First E&P) |
| `pidx-location-deepwater` | Location (Deepwater) | UpstreamProducer | OML 128, OML 130 (CNOOC, Chappal) |
| `pidx-crude-light-sweet` | Crude type (Light/Sweet) | UpstreamProducer | Bonny Light producers |
| `pidx-crude-medium` | Crude type (Medium) | UpstreamProducer | Escravos, Forcados producers |
| `pidx-risk-community-high` | Community relations risk (High) | UpstreamProducer | Aiteo, Continental Oil |
| `pidx-risk-community-medium` | Community relations risk (Medium) | UpstreamProducer | Most onshore operators |
| `pidx-risk-security-high` | Security risk (High — pipeline vulnerable) | UpstreamProducer | SPDC, Neconde, Shoreline |
| `pidx-risk-security-medium` | Security risk (Medium) | UpstreamProducer | Seplat, Aradel, most onshore |
| `pidx-ownership-nnpc-100pct` | Ownership (NNPC 100%) | UpstreamProducer | NEPL, Antan Producing |
| `pidx-ownership-nnpc-majority` | Ownership (NNPC >50%) | UpstreamProducer | Most JV operators |
| `pidx-ownership-ioc-100pct` | Ownership (IOC 100%) | UpstreamProducer | SOL Risk Sole operators, Marginal ops |
| `pidx-infrastructure-fpso` | Infrastructure (FPSO Export) | UpstreamProducer | OML 83, OML 128, OML 130 operators |
| `pidx-infrastructure-pipeline` | Infrastructure (Pipeline Export) | UpstreamProducer | Most onshore/shallow water ops |
| `pidx-reserves-high` | Reserves (>400 MMbbls) | UpstreamProducer | Shoreline (1,000 MMbbls), Neconde (600 MMbbls) |
| `pidx-reserves-medium` | Reserves (100–400 MMbbls) | UpstreamProducer | Seplat (886 MMbbls) |
| `pidx-reserves-low` | Reserves (<100 MMbbls) | UpstreamProducer | Marginal field operators |
| `pidx-reserve-life-long` | Reserve Life (>25 years) | UpstreamProducer | Shoreline (15 yrs est), CNOOC/TotalEnergies (25+ yrs) |
| `pidx-reserve-life-medium` | Reserve Life (10–25 years) | UpstreamProducer | Most indigenous mid-size operators |
| `pidx-reserve-life-short` | Reserve Life (<10 years) | UpstreamProducer | Declining onshore assets |
| `pidx-classification-marginal` | Classification (Marginal Operator) | UpstreamProducer | Folstaj, Omofejo, Ekpat, Egbolom SPVs |
| `pidx-classification-indigenous` | Classification (Indigenous Operator) | UpstreamProducer | All sub_type="LargeIndigenous" |
| `pidx-classification-ioc-foreign` | Classification (IOC/Foreign) | UpstreamProducer | Shell, Chevron, TotalEnergies, CNOOC |

---

### 8. BaselinePropertyIndexNode (25 Total)

**Definition:** Core properties that EVERY UpstreamProducer should have (or explicitly NOT_AVAILABLE). Defines the schema contract.

| BaselinePropertyIndexNode ID | Property Name | Presence | Type | Required | Notes |
|------------------------------|---------------|----------|------|----------|-------|
| `bpin-entity-id` | `id` | MUST | String | YES | Unique identifier |
| `bpin-entity-name` | `name` | MUST | String | YES | Full legal name |
| `bpin-entity-short-name` | `short_name` | SHOULD | String | NO | Abbreviated name |
| `bpin-ownership-nnpc-pct` | `nnpc_equity_percentage` | SHOULD | Float \| String | NO | 0.0–100.0 or `"NOT_AVAILABLE"` |
| `bpin-ownership-ioc-pct` | `ioc_equity_percentage` | SHOULD | Float \| String | NO | 0.0–100.0 or `"NOT_AVAILABLE"` |
| `bpin-geo-country-hq` | `headquarters_country` | SHOULD | String | NO | Country code or name |
| `bpin-geo-country-inc` | `incorporation_country` | SHOULD | String | NO | Country of registration |
| `bpin-geo-operational-area` | `operational_area` | SHOULD | Array[String] | NO | `["onshore"]`, `["deepwater"]`, etc. |
| `bpin-production-current-bopd` | `current_production_bopd` | SHOULD | Float \| String | NO | Current daily output or `"NOT_AVAILABLE"` |
| `bpin-production-peak-bopd` | `peak_production_bopd` | SHOULD | Float \| String | NO | Historical peak or `"NOT_AVAILABLE"` |
| `bpin-production-peak-year` | `peak_production_year` | SHOULD | Integer | NO | Year achieved |
| `bpin-entitlement-nnpc-bopd` | `nnpc_entitlement_bopd` | SHOULD | Float \| String | NO | NNPC daily allocation |
| `bpin-entitlement-ioc-bopd` | `ioc_entitlement_bopd` | SHOULD | Float \| String | NO | IOC/contractor daily share |
| `bpin-reserves-proven-mmbbls` | `proven_reserves_mmbbls` | SHOULD | Float \| String | NO | 2P reserves in MMbbls or `"NOT_AVAILABLE"` |
| `bpin-reserves-life-years` | `reserve_life_years` | SHOULD | Float \| String | NO | Years remaining or `"NOT_AVAILABLE"` |
| `bpin-crude-types` | `crude_types_produced` | SHOULD | Array[String] | NO | `["light"]`, `["medium", "heavy"]`, etc. |
| `bpin-crude-grade-name` | `crude_grade_name` | SHOULD | String | NO | Commercial name (Bonny Light, etc.) |
| `bpin-status-operational` | `operational_status` | SHOULD | String | NO | `"active"`, `"suspended"`, etc. |
| `bpin-assets-oml-blocks` | `oml_blocks_held` | SHOULD | Array[String] | NO | `["OML 11"]`, `["OML 18"]`, etc. |
| `bpin-assets-opl-blocks` | `opl_blocks_held` | SHOULD | Array[String] | NO | Prospecting licenses held |
| `bpin-risk-community` | `community_relations_risk` | SHOULD | String | NO | `"low"`, `"medium"`, `"high"` |
| `bpin-risk-security` | `security_risk_level` | SHOULD | String | NO | `"low"`, `"medium"`, `"high"` |
| `bpin-classification` | `sub_type_classification` | SHOULD | String | NO | `"IOC"`, `"NOC"`, `"LargeIndigenous"`, etc. |
| `bpin-metadata-updated` | `last_updated` | SHOULD | String | NO | ISO 8601 date of last verification |
| `bpin-metadata-audit-ref` | `neiti_audit_reference` | SHOULD | String | NO | Citation to government audit source |

---

## Relationship Types

### Defined Relationships in Graph

| Relationship | From | To | Cardinality | Purpose | Example |
|--------------|------|----|-----------|---------|----|
| `:BELONGS_TO` | UpstreamProducer | ClassNode | N:1 | Classify entity into category | SPDC `:BELONGS_TO` class-upstream-producer |
| `:BELONGS_TO` | UpstreamProducer | PropertyIndexNode | N:M | Index entity properties | SPDC `:BELONGS_TO` pidx-production-tier-major |
| (Future) `:OPERATES` | Operator | Asset (OML/Block) | 1:M | Operational control | SNEPCo `:OPERATES` OML 130 |
| (Future) `:JV_PARTNER_IN` | Partner | JV | N:M | Joint venture membership | CNOOC `:JV_PARTNER_IN` OML130_JV |

**Current Status:** Only `:BELONGS_TO` is implemented in database. Future relationships will enable more granular asset tracking.

---

## All 54 Entities (Complete Roster)

### Entity Groups

#### Group 1: Indigenous Operators 2003 Round (Entities 01–22)

**Status:** Assumed seeded in prior session; full Cypher not re-generated in this conversation.

| # | Entity ID | Short Name | Current Production | Key Feature |
|---|-----------|-----------|-------------------|-------------|
| 01–22 | (various `-2003-round`) | Various | TBD | 2003 inaugural indigenous licensing round |

---

#### Group 2: Large Indigenous Operators 2003 Round (Entities 23–34)

**Status:** Assumed seeded in prior session; full Cypher not re-generated in this conversation.

| # | Entity ID | Short Name | Current Production | Key Feature |
|---|-----------|-----------|-------------------|-------------|
| 23–34 | (various `-large-indigenous`) | Various | TBD | High-volume indigenous operators |

---

#### Group 3: 2020 Marginal Field SPVs (Entities 35–40)

**Status:** ✓ Seeded. Corrected Cypher applied.

| # | Entity ID | Short Name | Status | Production | Key Details |
|----|-----------|-----------|--------|-----------|-------------|
| 35 | `folstaj-international` | Folstaj | Pre-production | 0 bopd | PPL 237 (Udibe Field), 77 MMbbls reserves |
| 36 | `omofejo-spv` | Omofejo SPV | Development | 0 bopd | PPL 219 (Omofejo Field), 25 MMbbls reserves |
| 37 | `ekpat-spv` | Ekpat SPV | Near Production | 0 bopd | PPL 231 (Ekpat Field), 30 MMbbls reserves |
| 38 | `atamba-spv` | Atamba SPV | Development Phase | 0 bopd | PPL 211 (Atamba Field), 30 MMbbls reserves |
| 39 | `egbolom-spv` | Egbolom SPV | **Producing** | ~3,000 bopd | PML 66 (Egbolom Field), 65.37 MMbbls reserves, **First Oil April 27, 2024** |
| 40 | `marginal-field-2020-aggregate` | 2020 MF Operators | Mixed (ramp-up) | ~28,500 bopd aggregate | 57 fields, 161 entities in SPVs, 450 MMbbls aggregate reserves |

---

#### Group 4: PSC Deepwater Operators/Partners (Entities 41–48)

**Status:** ✓ Cypher generated, validated, in-memory staging. Ready for Aura seeding.

| # | Entity ID | Short Name | Label | Production | Link to |
|----|-----------|-----------|----|-----------|---------|
| 41 | `snepco-shell` | SNEPCo | `:Operator` | ~140 kbopd | OML 130 (PML 2/3/4) deepwater |
| 42 | `star-deep-water` | Star Deep Water | `:Operator` | ~98 kbopd | OML 128 (Agbami) deepwater |
| 43 | `eepnl-exxonmobil` | EEPNL | `:Operator` | ~102.9 kbopd | OML 102 deepwater |
| 44 | `nae-eni-nigeria` | NAE | `:Partner` | ~55 kbopd | PSC partner (non-op) |
| 45 | `cnooc-nigeria` | CNOOC | `:Partner` | ~58.3 kbopd (contractor share) | OML 130 (45% non-op) + OML 138/139 |
| 46 | `sapetro-south-atlantic` | Sapetro | `:Partner` | ~17.4 kbopd (est.) | OML 130 PSC partner |
| 47 | `meren-energy-africa-oil` | Meren Energy | `:Partner` | ~35.1 kbopd | PSC partner |
| 48 | `famfa-oil` | Famfa Oil | `:Partner` | ~34.8 kbopd | PSC partner |

**Corrected Labels (Applied in This Session):**
- Fixed from `:PSCOperator` / `:PSCPartner` to standard `:Operator` / `:Partner`
- All linked to parent `:class-upstream-producer` via `:BELONGS_TO`

---

#### Group 5: FPSO Operators (Entities 49–51)

**Status:** ✓ Cypher generated, validated. Infrastructure tier, NOT UpstreamProducer.

| # | Entity ID | Short Name | FPSO Vessel | Capacity | Location |
|----|-----------|-----------|----|---------|----------|
| 49 | `stac-marine-abo` | STAC Marine | FPSO Abo | 15 kbopd processing, 930k storage | OML 123 (Adoon field) |
| 50 | `abigail-joseph-fpso` | Abigail-Joseph FPSO | Abigail-Joseph | 60 kbopd, 870k storage | OML 83 (First E&P operator) |
| 51 | `century-group-fpso` | Century Group | Tamara Tokoni / Tamara Nanaye | 47 kbopd + 40 kbopd | Multi-vessel operator |

**Key Rule:** These are `:FPSOOperator` ONLY. Do NOT expect UpstreamProducer properties (reserves, equity %, production entitlements).

---

#### Group 6: Additional Operators (Entities 52–54+)

**Status:** ✓ Cypher generated/corrected. Ready for seeding or clarification.

| # | Entity ID | Short Name | Type | Status | Current Production |
|----|-----------|-----------|----|--------|------------------|
| 52 | `additional-minimal-producers-nuprc-2024` | Minimal Producers Aggregate | Aggregate Node (8 constituent entities) | Mixed | ~0 bopd (mostly gas-flaring) |
| 53 | `antan-producing-nnpc` | Antan Producing | `:UpstreamProducer:Operator` | Active (rebuilding) | 32.5 kbopd (near-term target 27.5k) |
| 54 | `seepco-sterling` | SEEPCO | `:UpstreamProducer:Partner` | Active (FTSA) | 45 kbopd (JV total) |
| 55* | `renaissance-africa-energy` | Renaissance | `:UpstreamProducer:Operator` | Active (Shell divestment recipient) | 300 kbopd (JV consortium) |

*Entity numbering for 53–55 may require clarification. Current assignment: Antan=53, SEEPCO=54, Renaissance=55.

**Entity 52 (Minimal Producers Aggregate) - 8 Constituent Entities:**

| Constituent | Entity ID | Type | Production | Notes |
|------------|-----------|------|-----------|-------|
| 1 | `moni-pulo-limited` | Offshore minimal | ~500 bopd max | Flaring dominant |
| 2 | `universal-energy-resources` | Onshore minimal | ~93% flaring | Gas-only node |
| 3 | `excel-ep-nigeria` | Onshore marginal | Minimal | Gas-dominant |
| 4 | `millennium-oil-gas` | Onshore minimal | 100% flaring | 4.76 MMscf gas, 0 oil |
| 5 | `frontier-oil-limited` | OML 13 operator | Minimal | 794.97 MMscf gas, significant reserves |
| 6 | `network-ep-limited` | Onshore PSC | 86% flaring | 886.41 MMscf gas |
| 7 | `sgorl` | Onshore PSC | <1% flaring | 367.90 MMscf gas |
| 8 | `enageed-resources` | Onshore PSC | 96% flaring | 1,354 MMscf gas |

---

## Data Type Handling & Defensive Patterns

### Critical Data Type Variations

#### 1. Numeric Properties with NOT_AVAILABLE Fallback

**Common Numeric Fields:**
- `current_production_bopd`
- `peak_production_bopd`
- `nnpc_entitlement_bopd`
- `ioc_entitlement_bopd`
- `proven_reserves_mmbbls`
- `reserve_life_years`
- `latitude`, `longitude`
- `avg_cargo_size_bbls`
- `avg_liftings_per_month`

**Possible Values:**
```
Numeric: 0.0, 100.5, 1000000.0 (type: Float or Integer)
String "NOT_AVAILABLE": "NOT_AVAILABLE"
String Literal: (rarely) "0", "100" (edge cases from old data)
NULL: (absent property)
```

**Defensive Cypher for Numeric Comparison:**
```cypher
// Filter for current production > 50k bopd
WHERE (
  (n.current_production_bopd IS NOT NULL 
   AND n.current_production_bopd <> "NOT_AVAILABLE"
   AND apoc.number.toFloat(toString(n.current_production_bopd)) > 50000)
  OR (n.current_production_bopd = "NOT_AVAILABLE" AND <fallback logic>)
)

// Safe aggregation function
REDUCE(total = 0.0, prod IN COLLECT(n.current_production_bopd) | 
  CASE 
    WHEN prod IS NOT NULL AND prod <> "NOT_AVAILABLE" 
    THEN total + apoc.number.toFloat(toString(prod))
    ELSE total
  END
)
```

#### 2. Array Properties with Empty Fallback

**Common Array Fields:**
- `crude_types_produced`: `["light"]`, `["light", "medium"]`, `[]`, `"NOT_AVAILABLE"`
- `operational_area`: `["onshore"]`, `["onshore", "swamp", "shallow offshore"]`, `[]`
- `oml_blocks_held`: `["OML 11", "OML 18"]`, `[]`
- `primary_crude_buyers`: `["NNPC Trading", "Vitol"]`, `[]`, `"NOT_AVAILABLE"`
- `other_partners`: `["TotalEnergies - 10%"]`, `[]`

**Defensive Cypher:**
```cypher
// Filter entities producing in deepwater
WHERE "deepwater" IN n.operational_area OR SIZE(n.operational_area ∣ 0) = 0

// Check for light crude production
WHERE "light" IN n.crude_types_produced OR SIZE(COALESCE(n.crude_types_produced, [])) = 0

// Safe member check
WHERE ANY(buyer IN COALESCE(n.primary_crude_buyers, []) WHERE buyer CONTAINS "NNPC")
```

#### 3. String Properties with NOT_AVAILABLE or Absent

**Common String Fields:**
- `crude_grade_name`: `"Bonny Light"`, `"NOT_AVAILABLE"`, `NULL (absent)`
- `operational_status`: `"active"`, `"suspended"`, `"NOT_AVAILABLE"`
- `primary_export_terminal`: `"Bonny Export Terminal"`, `"NOT_AVAILABLE"`, `NULL`
- `production_disruption_history`: Long narrative text or absent
- `headquarters_country`: `"Nigeria"`, `"United States"`, `"NOT_AVAILABLE"`, `NULL`

**Defensive Cypher:**
```cypher
// Match specific status
WHERE n.operational_status = "active" OR n.operational_status IS NULL

// Match headquarters
WHERE toLower(n.headquarters_country) CONTAINS "nigeria" 
  AND n.headquarters_country <> "NOT_AVAILABLE"

// Text search (requires CONTAINS to handle NOT_AVAILABLE)
WHERE n.production_disruption_history IS NOT NULL 
  AND n.production_disruption_history <> "NOT_AVAILABLE"
  AND n.production_disruption_history CONTAINS "theft"
```

#### 4. Boolean Properties (Rarely Absent)

**Boolean Fields:**
- `pac_2025_appearance`: `true`, `false`, `NULL (absent)`
- `first_indigenous_fpso_operator`: `true`, `false`, `NULL`

**Defensive Cypher:**
```cypher
// Safe boolean check
WHERE COALESCE(n.pac_2025_appearance, false) = true

// Check for both true/false/absent
WHERE (n.pac_2025_appearance = true OR n.pac_2025_appearance IS NULL)
```

### Type Coercion Pitfalls

**AVOID:**
```cypher
WHERE n.current_production_bopd > 50000  // FAILS if "NOT_AVAILABLE"
WHERE "light" IN n.crude_types_produced AND n.crude_types_produced <> []  // Redundant
```

**USE:**
```cypher
WHERE apoc.number.toFloat(toString(n.current_production_bopd)) > 50000
WHERE "light" IN COALESCE(n.crude_types_produced, [])
```

---

## Property Categories & Enum Values

### Enum 1: operational_status

**Valid Values:**
- `"active"` — Currently producing or developing
- `"suspended"` — Temporarily offline (maintenance, force majeure, etc.)
- `"divesting"` — Actively shedding assets (e.g., Shell SPDC onshore portfolio)
- `"pre-production"` — Development phase, not yet producing
- `"field redevelopment"` — Restarting closed field
- `"under court-appointed administration"` — Legal control transition (e.g., Amni International)
- `"active (with significant disruption risk)"` — Operating but vulnerable (e.g., Aiteo OML 29)

**Handling:** If absent, assume `"active"`. If `"NOT_AVAILABLE"`, treat as unknown status.

---

### Enum 2: crude_types_produced (Array)

**Valid Values:**
- `"light"` — Light crude (API >30°)
- `"medium"` — Medium crude (API 20–30°)
- `"heavy"` — Heavy crude (API <20°)
- `"condensate"` — Natural gas condensate (very light, API >40°)
- `"sweet"` — Low sulfur content (qualifier)

**Example Arrays:**
- `["light"]` — Only light crude
- `["light", "medium"]` — Multiple grades
- `["light", "condensate"]` — Light oil + condensate (e.g., TotalEnergies OML 130)
- `[]` — Empty array or absent means unknown/not specified

---

### Enum 3: operational_area (Array)

**Valid Values:**
- `"onshore"` — Land-based operations
- `"swamp"` — Niger Delta wetlands/swamp terrain
- `"shallow offshore"` — Water depth <200m (typically <100m)
- `"deepwater"` — Water depth >200m; typically >1,000m in Nigeria
- `"shallow water"` — Alternative term for shallow offshore

**Example Arrays:**
- `["onshore"]` — Land only (e.g., Neconde OML 42)
- `["onshore", "swamp"]` — Land + swamp (e.g., Aiteo OML 29)
- `["onshore", "swamp", "shallow offshore"]` — Mixed (e.g., SPDC)
- `["deepwater"]` — Offshore only (e.g., CNOOC OML 130, SNEPCo)
- `["shallow offshore"]` — Shallow water (e.g., First E&P OML 83)

---

### Enum 4: community_relations_risk & security_risk_level

**Valid Values:**
- `"low"` — Minimal exposure; good community/security environment
- `"medium"` — Moderate exposure; periodic disruptions; manageable through best practices
- `"high"` — Severe exposure; frequent disruptions; persistent theft/sabotage/community conflict

**Examples by Risk Level:**

**High Community Risk:**
- Aiteo Eastern EP (Santa Barbara incident 2021; 40 communities impacted)
- Neconde Energy (Niger Delta onshore security environment)

**High Security Risk:**
- SPDC (Trans Niger Pipeline chronic vandalism & crude theft)
- Shoreline (Trans Forcados Pipeline sabotage)
- Waltersmith (100% product diverted to refinery due to pipeline theft)

**Low Risk:**
- Deepwater operators (CNOOC, Chappal — offshore location)
- First E&P OML 83 (offshore, FPSO-based evacuation)
- Oriental Energy (Qua Iboe Terminal, stable environment)

---

### Enum 5: sub_type (Classification)

**Valid Values:**
- `"IOC"` — International Oil Company (Shell, Chevron, TotalEnergies, ExxonMobil, Eni, CNOOC)
- `"NOC"` — National Oil Company (NNPC Limited, NEPL)
- `"LargeIndigenous"` — High-volume indigenous Nigerian operator
- `"MarginalFieldOperator"` — 2003 or 2020 marginal field awardee
- `"IndigenousAggregate"` — Aggregate node for multiple operators (e.g., 2020 marginal aggregate, minimal producers aggregate)

---

### Enum 6: reserve_life_years (Categorical Bucketing)

While technically numeric, often referenced in categorical context:

- `>25` — Long reserve life (e.g., CNOOC, TotalEnergies OML 130)
- `10–25` — Medium reserve life (most mid-size operators)
- `<10` — Short reserve life; mature/declining assets
- `"NOT_AVAILABLE"` — Unknown horizon

---

### Enum 7: offtake_agreement_type

**Valid Values:**
- `"Term contract"` — Long-term sales agreement with fixed offtaker
- `"Spot market"` — Ad-hoc sales to spot traders
- `"Term contract and spot market"` — Hybrid (some volume committed, some spot)
- `"JV Marketing"` — Marketed by JV entity (e.g., NNPC/Aiteo marketing Nembe crude)
- `"Sole Risk Marketing"` — Operator markets 100% of production
- `"Government allocation"` — NNPC allocates crude directly (mostly NNPC Limited itself)
- `"FTSA"` — Financial & Technical Service Agreement (cost-recovery model, not equity)
- `"PSC Marketing"` — Production Sharing Contract marketing model
- `"Independent Marketing"` — Operator independently markets crude (e.g., marginal field operators)
- `"Not yet active"` — Pre-production fields (e.g., Folstaj, Omofejo)
- `"Under Negotiation"` — Offtake TBD (e.g., early-stage development)

---

## Critical Rules & Constraints

### Rule 1: Unique ID Constraint

Every Entity/UpstreamProducer/FPSOOperator MUST have:
- A unique, non-null `id` field
- Kebab-case format: `{descriptor}-{descriptor}-{descriptor}`
- No upper case, no spaces, no special characters except hyphens
- Examples: `shell-spdc`, `seplat-energy`, `folstaj-international`, `stac-marine-abo`

**Cypher:**
```cypher
MATCH (n:Entity) WHERE n.id IS NULL OR n.id = "" RETURN COUNT(n)  // Should be 0
```

### Rule 2: Label Hierarchy

- `:Entity` is the base; all entities carry it
- `:UpstreamProducer` is a primary classification
- `:Operator` OR `:Partner` is the subtype (mutually exclusive)
- `:FPSOOperator` is orthogonal (NOT combined with `:UpstreamProducer`)

**Valid Label Combinations:**
- `:Entity:UpstreamProducer:Operator` ✓
- `:Entity:UpstreamProducer:Partner` ✓
- `:Entity:FPSOOperator` ✓
- `:FPSOOperator:UpstreamProducer` ✗ (violation — FPSOs are infrastructure only)

### Rule 3: Equity Percentage Constraints

For all `:UpstreamProducer` nodes with JV structure:

```
nnpc_equity_percentage + ioc_equity_percentage + other_operator_equity_percentage = 100 (approximately)
```

**Edge Cases:**
- NNPC 100%: Only `nnpc_equity_percentage = 100.0`, `ioc_equity_percentage = 0.0`
- IOC 100% (Sole Risk): Only `ioc_equity_percentage = 100.0`, `nnpc_equity_percentage = 0.0`
- NNPC on PSC (not equity): `nnpc_equity_percentage = "NOT_AVAILABLE"` or `0.0` (because PSC is concessionaire, not equity partner)
- FTSA Partner: `ioc_equity_percentage = 0.0` (NOT equity); entitlement via cost-recovery + profit oil

### Rule 4: Operator vs. Partner Distinction

**:Operator Node Properties:**
- MUST have `operator_equity_percentage` (numeric, 0–100)
- Carries operational responsibility
- Typically has `operator_entitlement_bopd` (own share of production)

**:Partner Node Properties:**
- MUST NOT have `operator_equity_percentage`
- No operational control; participates in JV/PSC
- May have `ioc_entitlement_bopd` (allocation in PSC or JV profit-oil)
- May have additional note fields explaining cost-recovery or FTSA model

**Defensive Cypher:**
```cypher
MATCH (n:Operator) 
WHERE n.operator_equity_percentage IS NULL 
RETURN n  // Should be 0 results

MATCH (n:Partner) 
WHERE n.operator_equity_percentage IS NOT NULL 
  AND n.operator_equity_percentage <> "NOT_AVAILABLE"
RETURN n  // Should be 0 results (Partners don't have operator_equity)
```

### Rule 5: FPSO Operators are NOT UpstreamProducers

FPSOOperator nodes:
- Do NOT carry `nnpc_equity_percentage`, `ioc_equity_percentage`
- Do NOT carry `current_production_bopd` (they are infrastructure, not producers)
- Do carry `throughput_capacity_bopd` (facility capacity, not allocation)
- Do NOT appear in equity/production entitlement queries

### Rule 6: NOT_AVAILABLE Handling

Use String `"NOT_AVAILABLE"` (not `null`, not `"N/A"`, not `0.0`):
- When data exists in schema but is genuinely unknown
- When prior data becomes obsolete/unreliable
- Examples: `proven_reserves_mmbbls: "NOT_AVAILABLE"` (pre-production field), `reserve_life_years: "NOT_AVAILABLE"` (insufficient data)

Use NULL or Absent Property:
- When the property doesn't conceptually apply to the node
- Example: `:Partner` nodes do not have `operator_equity_percentage` (absent, not `0.0`)

### Rule 7: Timestamp Format

All timestamps use ISO 8601 format:
- `"2026-04-15"` ✓ (date-only for `last_updated`)
- `"2026-04-15T14:30:00Z"` ✓ (full datetime with UTC)
- `"2026-04-15T23:42:14.081000000Z"` ✓ (full datetime with nanoseconds, as produced by Neo4j)
- `"15-04-2026"` ✗ (non-standard format)

### Rule 8: Property Consistency Across Same Entity Type

All `:UpstreamProducer` nodes should follow the same property schema. If one entity has `production_disruption_history`, others should either have it or have it explicitly absent (not `"NOT_AVAILABLE"`).

**Audit Query:**
```cypher
MATCH (n:UpstreamProducer) 
RETURN DISTINCT keys(n) ORDER BY keys(n)
// Should show consistent property patterns across entities
```

---

## Query Patterns & Examples

### Pattern 1: Simple Equality Match

**Question:** "Show me all entities currently in active status."

```cypher
MATCH (n:UpstreamProducer) 
WHERE n.operational_status = "active"
RETURN n.name, n.current_production_bopd, n.operational_status
```

### Pattern 2: Numeric Range with Defensive Type Handling

**Question:** "Which operators have current production between 50,000 and 100,000 bopd?"

```cypher
MATCH (n:Operator)
WHERE (
  n.current_production_bopd IS NOT NULL 
  AND n.current_production_bopd <> "NOT_AVAILABLE"
  AND apoc.number.toFloat(toString(n.current_production_bopd)) >= 50000
  AND apoc.number.toFloat(toString(n.current_production_bopd)) <= 100000
)
RETURN n.name, n.short_name, n.current_production_bopd 
ORDER BY apoc.number.toFloat(toString(n.current_production_bopd)) DESC
```

### Pattern 3: Array Membership (Enum Search)

**Question:** "Show me all entities operating in deepwater."

```cypher
MATCH (n:UpstreamProducer)
WHERE "deepwater" IN COALESCE(n.operational_area, [])
RETURN n.name, n.operational_area, n.current_production_bopd
```

### Pattern 4: NNPC Majority Ownership

**Question:** "Which entities does NNPC own more than 50% of?"

```cypher
MATCH (n:UpstreamProducer)
WHERE (
  n.nnpc_equity_percentage IS NOT NULL 
  AND n.nnpc_equity_percentage <> "NOT_AVAILABLE"
  AND apoc.number.toFloat(toString(n.nnpc_equity_percentage)) > 50.0
)
RETURN n.name, n.nnpc_equity_percentage, n.ioc_equity_percentage
```

### Pattern 5: High-Risk Operations

**Question:** "Which producers have high community relations risk AND are in onshore areas?"

```cypher
MATCH (n:UpstreamProducer)
WHERE n.community_relations_risk = "high"
  AND ("onshore" IN COALESCE(n.operational_area, [])
       OR "swamp" IN COALESCE(n.operational_area, []))
RETURN n.name, n.community_relations_risk, n.operational_area, 
       n.current_production_bopd, n.security_risk_level
ORDER BY apoc.number.toFloat(toString(n.current_production_bopd)) DESC
```

### Pattern 6: Classification Hierarchy (ClassNode Join)

**Question:** "Show me all entities classified as Large Indigenous operators and their production."

```cypher
MATCH (n:UpstreamProducer) -[:BELONGS_TO]-> (c:ClassNode)
WHERE c.id = "class-large-indigenous"
RETURN n.name, n.current_production_bopd, n.proven_reserves_mmbbls, 
       n.sub_type, c.name as classification
ORDER BY apoc.number.toFloat(toString(n.current_production_bopd)) DESC
```

### Pattern 7: Aggregation with NOT_AVAILABLE Handling

**Question:** "What is the total known current production across all entities (excluding NOT_AVAILABLE)?"

```cypher
MATCH (n:UpstreamProducer)
WITH COLLECT({
  name: n.name, 
  prod: n.current_production_bopd
}) as entities
WITH [e IN entities 
  WHERE e.prod IS NOT NULL 
    AND e.prod <> "NOT_AVAILABLE"] as valid_entities
RETURN 
  SIZE(valid_entities) as entities_with_data,
  SUM([p IN [e.prod IN valid_entities] 
    WHERE p IS NOT NULL | apoc.number.toFloat(toString(p))]) as total_production_bopd
```

### Pattern 8: Multi-Condition Filter (Complex Query)

**Question:** "Find all IOC operators in deepwater with proven reserves > 200 MMbbls and high reserve life."

```cypher
MATCH (n:Operator)
WHERE n.sub_type = "IOC"
  AND "deepwater" IN COALESCE(n.operational_area, [])
  AND (
    n.proven_reserves_mmbbls IS NOT NULL
    AND n.proven_reserves_mmbbls <> "NOT_AVAILABLE"
    AND apoc.number.toFloat(toString(n.proven_reserves_mmbbls)) > 200.0
  )
  AND (
    n.reserve_life_years IS NOT NULL
    AND n.reserve_life_years <> "NOT_AVAILABLE"
    AND apoc.number.toFloat(toString(n.reserve_life_years)) > 20
  )
RETURN n.name, n.current_production_bopd, n.proven_reserves_mmbbls, 
       n.reserve_life_years, n.operational_area
ORDER BY apoc.number.toFloat(toString(n.proven_reserves_mmbbls)) DESC
```

### Pattern 9: Text Search with NOT_AVAILABLE Filtering

**Question:** "Which entities have documented production disruption history mentioning 'crude theft'?"

```cypher
MATCH (n:UpstreamProducer)
WHERE n.production_disruption_history IS NOT NULL
  AND n.production_disruption_history <> "NOT_AVAILABLE"
  AND n.production_disruption_history CONTAINS "theft"
RETURN n.name, LEFT(n.production_disruption_history, 200) as disruption_summary
```

### Pattern 10: Subtype Classification Filter

**Question:** "Show all large indigenous operators with their marginal field information."

```cypher
MATCH (n:UpstreamProducer)
WHERE n.sub_type = "LargeIndigenous"
RETURN n.name, n.short_name, n.current_production_bopd, 
       n.marginal_field_round, n.is_marginal_field_operator,
       n.sub_type, n.nnpc_equity_percentage, n.ioc_equity_percentage
ORDER BY apoc.number.toFloat(toString(n.current_production_bopd)) DESC
```

---

## Special Cases & Edge Scenarios

### Case 1: Renaissance Africa Energy (Consortium JV Operator)

**Entity ID:** `renaissance-africa-energy`

**Distinguishing Feature:** Node represents FULL JV production and equity, not just Renaissance's individual stake.

**Properties:**
```
current_production_bopd: 300000.0  // Full JV (NNPC 55%, Renaissance 30%, TotalEnergies 10%, Eni 5%)
nnpc_equity_percentage: 55.0
ioc_equity_percentage: 45.0  // Renaissance (30%) + TotalEnergies (10%) + Eni (5%)
jv_structure_note: "Renaissance owns 30% operating interest. JV consists of NNPC (55%), 
                    Renaissance (30%), TotalEnergies (10%), and Eni (5%). Production and 
                    equity figures represent full JV structure under Renaissance operatorship."
```

**Defensive Cypher for Renaissance:** Do NOT filter by `operator_equity_percentage = 30.0`. Instead, filter by entity `id = "renaissance-africa-energy"` to get full JV view.

### Case 2: SEEPCO (FTSA Partner — Not Equity Partner)

**Entity ID:** `seepco-sterling`

**Distinguishing Feature:** Cost-recovery partner, not equity partner. De-risked from error that showed `ioc_equity_percentage = 100.0`.

**Properties (Corrected):**
```
nnpc_equity_percentage: 0.0  // Not an equity partner
ioc_equity_percentage: 0.0   // CORRECTED from 100.0
other_partners: ["NNPC E&P Ltd (NEPL)"]
other_partners_note: "SEEPCO operates as FTSA (Financing and Technical Services Agreement) 
                     partner, providing development capital in exchange for cost-recovery 
                     and profit-oil entitlements. Not a traditional equity partner."
nnpc_entitlement_bopd: 27000.0  // Profit-oil allocation, not equity share
ioc_entitlement_bopd: 18000.0   // Cost-recovery + profit-oil, not equity entitlement
```

**Defensive Query:** When querying for "equity holders", exclude FTSA partners by checking:
```cypher
WHERE (n.other_partners_note IS NULL 
    OR NOT n.other_partners_note CONTAINS "FTSA")
```

### Case 3: Entity 52 — Minimal Producers Aggregate

**Entity ID:** `additional-minimal-producers-nuprc-2024`

**Purpose:** Single aggregate node representing 8 minimal/gas-only producers (Moni Pulo, Universal Energy, Excel E&P, Millennium, Frontier, Network EP, SGORL, Enageed).

**Properties:**
```
current_production_bopd: 0.0  // Mostly gas-flaring, minimal oil
crude_types_produced: ["light"]  // Some minimal crude
proven_reserves_mmbbls: 50.0  // Aggregate estimate
operational_area: ["onshore", "offshore"]
sub_type: "IndigenousAggregate"
```

**Defensive Query:** When querying all UpstreamProducers, this node will appear but with minimal/zero oil production. Filter with:
```cypher
WHERE apoc.number.toFloat(toString(n.current_production_bopd)) > 1000 
   OR n.sub_type <> "IndigenousAggregate"
```

### Case 4: Antan Producing (Corrected Label & Ownership)

**Entity ID:** `antan-producing-nnpc`

**Distinguishing Feature:** 100% NNPC-owned, recently taken over from Addax. Rebuilding collapsed production.

**Properties (Corrected in This Session):**
```
parent_company: "NNPC Limited (100% owned subsidiary)"
nnpc_equity_percentage: 100.0
ioc_equity_percentage: 0.0
current_production_bopd: 32500.0  // Near-term target
peak_production_bopd: 130000.0    // Historical (under Addax, 2008)
operational_status: "active (rebuilding)"
```

**Label Correction:** Changed from `:PSCOperator` to `:Entity:UpstreamProducer:Operator`.

---

## Summary & Usage Guidance for LLM

This schema document defines:

1. **54 unique entities** across indigenous, IOC, PSC, and marginal categories
2. **45+ properties per UpstreamProducer**, each with explicit type, required status, and NOT_AVAILABLE handling
3. **8 node types** (Entity, UpstreamProducer, Operator, Partner, FPSOOperator, ClassNode, PropertyIndexNode, BaselinePropertyIndexNode)
4. **Defensive Cypher patterns** for handling numeric, string, array, and boolean data with NOT_AVAILABLE fallbacks
5. **Enum values** for categorical properties (status, area, crude type, risk level, sub_type)
6. **Query patterns** demonstrating safe, type-aware filtering and aggregation
7. **Edge cases** explaining special scenarios (consortium JVs, FTSA partners, aggregate nodes, corrected entities)

When generating Cypher:
- ALWAYS check property type before numeric comparison
- ALWAYS use `COALESCE()` or `IN` with array properties
- ALWAYS handle `"NOT_AVAILABLE"` string explicitly
- ALWAYS verify entity ID is unique and kebab-case
- ALWAYS apply correct label hierarchy (Entity → UpstreamProducer → Operator/Partner)
- ALWAYS respect FPSOOperator isolation (never mix with UpstreamProducer in equity/production queries)
- ALWAYS refer to this document when unsure about property presence or type

---

**End of Schema Context Document**  
Generated: April 15, 2026  
Status: EXHAUSTIVE | COMPREHENSIVE | PRODUCTION-READY
