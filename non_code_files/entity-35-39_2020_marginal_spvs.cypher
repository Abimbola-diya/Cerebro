================================================================================
ENTITY 35 — FOLSTAJ INTERNATIONAL LIMITED (Udibe Field, PPL 237)
================================================================================

MERGE (e:Entity:UpstreamProducer:MarginalFieldOperator {id: 'folstaj-international'})
SET e += {
  name:                        'Folstaj International Limited',
  short_name:                  'Folstaj',
  sub_type:                    'MarginalFieldOperator',
  parent_company:              'Private Nigerian company',
  headquarters_country:        'Nigeria',
  nigeria_office_location:     'Plot 71, Trans-Amadi Industrial Layout, Port Harcourt, Rivers State',
  incorporation_country:       'Nigeria',
  operational_area:            ['shallow offshore'],
  latitude:                    4.1500, 
  longitude:                   7.8000, 
  operational_note:            'Field located ~70km offshore in 88ft water depth; 55km SW of Qua Iboe Terminal (QIT).',
  equity_structure:            'Holder of PPL 237 (Udibe Field). Awarded in 2020 Marginal Field Round. Developing in partnership with Dutchford E&P.',
  nnpc_equity_percentage:      0.0,
  operator_equity_percentage:  100.0,
  other_partners:              ['Dutchford E&P (Technical/Financial Partner)'],
  operational_status:          'Active (Development/Drilling Phase)',
  current_production_bopd:     0,
  current_production_note:     'Pre-production. Aggressive drilling campaign in 2025 (Udibe-2 well) was stalled by a major rig incident in September 2025 (Oritsemeyin Rig). Targeting First Oil post-recovery in late 2026.',
  proven_reserves_mmbbls:      77.0,
  proven_reserves_note:        '2C STOIIP estimated at 77 MMbbls oil and 279 Bscf gas. Speculative upside potential of 83–238 MMbbls identified in deeper horizons.',
  reserve_life_years:          15,
  primary_evacuation_route:    'Proposed pipeline to Qua Iboe Terminal (QIT) or FSO option',
  primary_export_terminal:     'Qua Iboe Terminal (Potential)',
  avg_cargo_size_bbls:         0,
  avg_liftings_per_month:      0,
  offtake_agreement_type:      'Not yet active',
  community_relations_risk:    'low',
  security_risk_level:         'low',
  production_disruption_history: 'Development severely impacted in September 2025 when NUPRC revoked the operating license of the "Oritsemeyin Rig" (Selective Marine Services) following a well kick scare on Udibe-2.',
  marginal_field_name:         'Udibe (PPL 237)',
  marginal_field_round:        '2020',
  annual_report_url:           'https://folstajinternational.com (Private)',
  neiti_audit_reference:       'NUPRC Concession Situation Report March 2026; Dutchford E&P Asset Profile',
  last_updated:                date('2026-04-15'),
  peak_production_bopd:        0,
  peak_production_year:        0
}
WITH e
MATCH (c:ClassNode {id: 'class-upstream-producer'})
MERGE (e)-[:BELONGS_TO]->(c);

================================================================================
ENTITY 36 — ASHERDELTA / ZIGMA / GLENPETRO SPV (Omofejo Field, PPL 219)
================================================================================

MERGE (e:Entity:UpstreamProducer:MarginalFieldOperator {id: 'omofejo-spv'})
SET e += {
  name:                        'AsherDelta / Zigma / GlenPetro Joint Venture SPV',
  short_name:                  'Omofejo SPV',
  sub_type:                    'MarginalFieldOperator',
  parent_company:              'Joint Venture SPV (AsherDelta, Zigma Petroleum, GlenPetro)',
  headquarters_country:        'Nigeria',
  nigeria_office_location:     'Port Harcourt, Rivers State',
  incorporation_country:       'Nigeria',
  operational_area:            ['onshore', 'swamp'],
  latitude:                    4.2100, 
  longitude:                   7.9000, 
  operational_note:            'Omofejo field (formerly Bime-3) located south of Koko, Delta State. Concession area ~9 sq.km with 5 identified reservoirs.',
  equity_structure:            'Holder of PPL 219 for Omofejo Field. Awarded in 2020 Round. Multi-partner structure led by AsherDelta with Nuway Oaklane involvement.',
  nnpc_equity_percentage:      0.0,
  operator_equity_percentage:  100.0,
  other_partners:              ['Zigma Petroleum', 'GlenPetro', 'Nuway Oaklane'],
  operational_status:          'Active (Development Phase)',
  current_production_bopd:     0,
  current_production_note:     'Confirmed in development as of early 2026. Drilling planning for re-entry of Omofejo-1 underway.',
  proven_reserves_mmbbls:      25.0,
  proven_reserves_note:        'Estimated 2P reserves of 15–35 MMbbls across Agbada formation sands.',
  reserve_life_years:          12,
  primary_evacuation_route:    'Tie-back to Chevron-operated OML 49 infrastructure',
  primary_export_terminal:     'Escravos Terminal (Potential)',
  avg_cargo_size_bbls:         0,
  avg_liftings_per_month:      0,
  offtake_agreement_type:      'Under Negotiation',
  community_relations_risk:    'medium',
  security_risk_level:         'low',
  production_disruption_history: 'Multi-partner governance required significant alignment period 2022-2024.',
  marginal_field_name:         'Omofejo (PPL 219)',
  marginal_field_round:        '2020',
  annual_report_url:           'https://www.zigmaltd.com (Private SPV)',
  neiti_audit_reference:       'NUPRC Concession Situation Report March 2026',
  last_updated:                date('2026-04-15'),
  peak_production_bopd:        0,
  peak_production_year:        0
}
WITH e
MATCH (c:ClassNode {id: 'class-upstream-producer'})
MERGE (e)-[:BELONGS_TO]->(c);

================================================================================
ENTITY 37 — DUPORT MIDSTREAM / MAGNUM FLO LTD (Ekpat Field, PPL 231)
================================================================================

MERGE (e:Entity:UpstreamProducer:MarginalFieldOperator {id: 'ekpat-spv'})
SET e += {
  name:                        'Ekpat JV Operations Limited',
  short_name:                  'Ekpat SPV',
  sub_type:                    'MarginalFieldOperator',
  parent_company:              'Joint Venture (Duport Midstream, Magnum Flo, Kizi Oil)',
  headquarters_country:        'Nigeria',
  nigeria_office_location:     'Lagos / Port Harcourt, Nigeria',
  incorporation_country:       'Nigeria',
  operational_area:            ['shallow offshore'],
  latitude:                    4.2500, 
  longitude:                   7.9500, 
  operational_note:            'Ekpat field located in OML 67 (Continental Shelf). Managed via Ekpat Producing JV Limited SPV (RC 2014956).',
  equity_structure:            'Holder of PPL 231 (Formerly part of PPL 232). Partners include Duport Midstream (Lead), Magnum Flo, and Kizi Oil.',
  nnpc_equity_percentage:      0.0,
  operator_equity_percentage:  100.0,
  other_partners:              ['Magnum Flo Ltd', 'Kizi Oil & Gas'],
  operational_status:          'Near Production',
  current_production_bopd:     0,
  current_production_note:     'Nearing First Oil. Subsea infrastructure installation and host tie-in agreements finalized in Q4 2025.',
  proven_reserves_mmbbls:      30.0,
  proven_reserves_note:        'Estimated 2P reserves of 20–40 MMbbls based on OML 67 legacy data.',
  reserve_life_years:          10,
  primary_evacuation_route:    'Pipeline tie-back to Mobil-operated Qua Iboe system',
  primary_export_terminal:     'Qua Iboe Terminal',
  avg_cargo_size_bbls:         0,
  avg_liftings_per_month:      0,
  offtake_agreement_type:      'Finalized/Commercial',
  community_relations_risk:    'low',
  security_risk_level:         'low',
  production_disruption_history: 'Development delayed 2023-2024 by commercial disputes between JV partners, now resolved.',
  marginal_field_name:         'Ekpat (PPL 231)',
  marginal_field_round:        '2020',
  annual_report_url:           'NOT_AVAILABLE (Private SPV)',
  neiti_audit_reference:       'NUPRC Concession Situation Report March 2026',
  last_updated:                date('2026-04-15'),
  peak_production_bopd:        0,
  peak_production_year:        0
}
WITH e
MATCH (c:ClassNode {id: 'class-upstream-producer'})
MERGE (e)-[:BELONGS_TO]->(c);

================================================================================
ENTITY 38 — MATRIX ENERGY / NAPTHA GLOBAL (Atamba Field, PPL 211)
================================================================================

MERGE (e:Entity:UpstreamProducer:MarginalFieldOperator {id: 'atamba-spv'})
SET e += {
  name:                        'Atamba Exploration and Production Limited',
  short_name:                  'Atamba SPV',
  sub_type:                    'MarginalFieldOperator',
  parent_company:              'Matrix Energy Group led JV',
  headquarters_country:        'Nigeria',
  nigeria_office_location:     'Matrix Energy Tower, Lagos / Port Harcourt',
  incorporation_country:       'Nigeria',
  operational_area:            ['onshore'],
  latitude:                    4.1800, 
  longitude:                   7.7500, 
  operational_note:            'Atamba field located in OML 42, Delta State. Matrix Energy holds majority equity with Naptha and Bono Energy.',
  equity_structure:            'Holder of PPL 211. Equity: Matrix Energy (72.7%), Bono Energy (27.3%), Naptha Global (Strategic Partner).',
  nnpc_equity_percentage:      0.0,
  operator_equity_percentage:  100.0,
  other_partners:              ['Naptha Global', 'Bono Energy'],
  operational_status:          'Active (Development Phase)',
  current_production_bopd:     0,
  current_production_note:     'Drilling campaign for Atamba-1ST scheduled for mid-2026. Leveraging Matrix Group infrastructure.',
  proven_reserves_mmbbls:      30.0,
  proven_reserves_note:        'Estimated recoverable reserves of 25–35 MMbbls oil.',
  reserve_life_years:          14,
  primary_evacuation_route:    'Pipeline tie-back to Jones Creek or Trans-Farcados Pipeline (TFP)',
  primary_export_terminal:     'Forcados Terminal',
  avg_cargo_size_bbls:         0,
  avg_liftings_per_month:      0,
  offtake_agreement_type:      'In House (Matrix Energy Trading)',
  community_relations_risk:    'medium',
  security_risk_level:         'low',
  production_disruption_history: 'No major technical disruptions; focus on community engagement in host Delta communities.',
  marginal_field_name:         'Atamba (PPL 211)',
  marginal_field_round:        '2020',
  annual_report_url:           'https://matrixenergygroup.com/exploration-and-production/',
  neiti_audit_reference:       'NUPRC PPL 211 Contract Statement; 2026 Matrix E&P Asset Update',
  last_updated:                date('2026-04-15'),
  peak_production_bopd:        0,
  peak_production_year:        0
}
WITH e
MATCH (c:ClassNode {id: 'class-upstream-producer'})
MERGE (e)-[:BELONGS_TO]->(c);

================================================================================
ENTITY 39 — OANDO ENERGY RESOURCES + PARTNERS (Egbolom Field, PML 66)
================================================================================

MERGE (e:Entity:UpstreamProducer:MarginalFieldOperator {id: 'egbolom-spv'})
SET e += {
  name:                        'Ingentia Energies Limited',
  short_name:                  'Egbolom SPV',
  sub_type:                    'MarginalFieldOperator',
  parent_company:              'Oando Energy Resources led consortium',
  headquarters_country:        'Nigeria',
  nigeria_office_location:     '10th Floor, SAPETRO Towers, Victoria Island, Lagos',
  incorporation_country:       'Nigeria',
  operational_area:            ['onshore', 'swamp'],
  latitude:                    4.3200, 
  longitude:                   8.0500, 
  operational_note:            'Egbolom field (formerly PPL 202) located in OML 23, Central Niger Delta. Converted to Petroleum Mining Lease (PML 66) in 2025.',
  equity_structure:            'Operated by Ingentia Energies (SPV for Oando Energy Resources and co-awardees). Oando acts as technical partner.',
  nnpc_equity_percentage:      0.0,
  operator_equity_percentage:  100.0,
  other_partners:              ['Oando Energy Resources', 'Various Co-awardees'],
  operational_status:          'Active (Producing)',
  current_production_bopd:     3000,
  current_production_note:     'First Oil achieved on April 27, 2024. Currently producing from Egbolom-2 re-entry. Ramping up to full field development.',
  proven_reserves_mmbbls:      65.37,
  proven_reserves_note:        '2P Reserves confirmed at 65.37 MMbbls as of 2024 NUPRC certification.',
  reserve_life_years:          18,
  primary_evacuation_route:    'Trucking/Barging (Initial) to Ogbele Terminal; Pipeline tie-back to Soku/Brass proposed.',
  primary_export_terminal:     'Brass Terminal',
  avg_cargo_size_bbls:         30000,
  avg_liftings_per_month:      1,
  offtake_agreement_type:      'Active / Commercial',
  community_relations_risk:    'medium',
  security_risk_level:         'medium',
  production_disruption_history: 'Producing steadily since April 2024. Successfully converted from PPL to PML status ahead of peers.',
  marginal_field_name:         'Egbolom (PML 66)',
  marginal_field_round:        '2020',
  annual_report_url:           'https://www.ingentiaenergies.com',
  neiti_audit_reference:       'NUPRC PML Conversion List 2025; Ingentia Energies Operational Report 2026',
  last_updated:                date('2026-04-15'),
  peak_production_bopd:        5000,
  peak_production_year:        2027
}
WITH e
MATCH (c:ClassNode {id: 'class-upstream-producer'})
MERGE (e)-[:BELONGS_TO]->(c);
