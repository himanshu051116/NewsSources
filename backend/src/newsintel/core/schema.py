EXPECTED_SCHEMA_REVISION = "0034_article_revision_history"

REQUIRED_V08_TABLES = (
    "evidence_authority_profiles",
    "temporal_knowledge_nodes",
    "canonical_entities",
    "publisher_ownership_memberships",
    "verification_benchmark_cases",
    "verification_calibration_snapshots",
    "evidence_orchestration_runs",
    "claim_conflict_resolutions",
    "verification_benchmark_evaluations",
    "entity_external_identifiers",
    "ownership_provenance_records",
)

REQUIRED_V08_INDEXES = (
    "ix_temporal_knowledge_nodes_search_fts",
    "ix_verification_benchmark_set_split",
    "ix_evidence_orchestration_claim_created",
    "ix_claim_conflict_resolutions_claim_created",
    "ix_verification_benchmark_eval_set_created",
    "ix_entity_external_entity",
    "ix_ownership_provenance_membership_observed",
)

REQUIRED_V09_TABLES = REQUIRED_V08_TABLES + (
    "evidence_search_stopping_assessments",
    "article_correction_events",
    "claim_review_flags",
    "verification_quality_gate_runs",
    "entity_registry_profiles",
    "entity_registry_link_runs",
    "ownership_ingest_runs",
)

REQUIRED_V09_INDEXES = REQUIRED_V08_INDEXES + (
    "ix_verification_benchmark_set_group",
    "ix_search_stopping_claim_created",
    "ix_article_correction_article_created",
    "ix_claim_review_claim_state",
    "ix_quality_gate_set_created",
    "ix_entity_registry_active_namespace",
    "ix_entity_registry_link_entity_created",
    "ix_ownership_ingest_source_created",
)

REQUIRED_V10_TABLES = REQUIRED_V09_TABLES + (
    "correction_dependency_propagation_runs",
    "verification_run_manifests",
    "production_readiness_runs",
)

REQUIRED_V10_INDEXES = REQUIRED_V09_INDEXES + (
    "ix_correction_dependency_event_created",
    "ix_verification_manifest_claim_created",
    "ix_production_readiness_benchmark_created",
)

# Backwards-compatible aliases for third-party scripts written against earlier releases.
REQUIRED_V07_TABLES = REQUIRED_V08_TABLES
REQUIRED_V07_INDEXES = REQUIRED_V08_INDEXES


REQUIRED_V11_TABLES = REQUIRED_V10_TABLES + (
    "article_historical_enrichment_jobs",
    "article_historical_contexts",
)

REQUIRED_V11_INDEXES = REQUIRED_V10_INDEXES + (
    "ix_historical_enrichment_jobs_due",
    "ix_article_historical_context_article_generated",
)


REQUIRED_V12_TABLES = REQUIRED_V11_TABLES
REQUIRED_V12_INDEXES = REQUIRED_V11_INDEXES
REQUIRED_V12_COLUMNS = (
    ("article_historical_enrichment_jobs", "refresh_count"),
    ("article_historical_enrichment_jobs", "last_refresh_reason"),
    ("article_historical_enrichment_jobs", "last_reconciled_at"),
)


REQUIRED_V13_TABLES = REQUIRED_V12_TABLES
REQUIRED_V13_INDEXES = REQUIRED_V12_INDEXES + (
    "ix_article_versions_fts_simple",
    "ix_article_claims_family_created",
)
REQUIRED_V13_COLUMNS = REQUIRED_V12_COLUMNS


REQUIRED_V14_TABLES = REQUIRED_V13_TABLES + (
    "publisher_extraction_profiles",
)
REQUIRED_V14_INDEXES = REQUIRED_V13_INDEXES + (
    "ix_publisher_extraction_profiles_domain",
    "ix_article_versions_semantic_pending",
)
REQUIRED_V14_COLUMNS = REQUIRED_V13_COLUMNS + (
    ("article_versions", "semantic_indexed_at"),
    ("article_versions", "semantic_model"),
    ("article_versions", "semantic_content_sha256"),
)


REQUIRED_V15_TABLES = REQUIRED_V14_TABLES + (
    "derived_artifact_dependencies",
    "derived_artifact_states",
    "derived_recompute_jobs",
)
REQUIRED_V15_INDEXES = REQUIRED_V14_INDEXES + (
    "ix_derived_dependency_source",
    "ix_derived_dependency_artifact",
    "ix_derived_artifact_stale",
    "ix_derived_recompute_due",
)
REQUIRED_V15_COLUMNS = REQUIRED_V14_COLUMNS + (
    ("publisher_extraction_profiles", "browser_render_enabled"),
    ("publisher_extraction_profiles", "browser_allowed_domains"),
)

# Collaboration and analyst-workspace persistence required by the 1.16 product surface.
REQUIRED_V16_TABLES = REQUIRED_V15_TABLES + (
    "investigations",
    "investigation_items",
    "analyst_notes",
    "saved_searches",
    "watchlists",
    "watchlist_items",
    "workspace_alert_acknowledgements",
    "investigation_members",
    "investigation_activity",
    "workspace_monitors",
    "workspace_monitor_runs",
    "workspace_generated_alerts",
)
REQUIRED_V16_INDEXES = REQUIRED_V15_INDEXES + (
    "ix_investigations_owner_status_updated",
    "ix_investigation_items_investigation_created",
    "ix_analyst_notes_investigation_created",
    "ix_saved_searches_owner_updated",
    "ix_watchlists_owner_updated",
    "ix_watchlist_items_watchlist_created",
    "ix_workspace_alert_ack_user_created",
    "ix_investigation_members_user_updated",
    "ix_investigation_members_investigation_role",
    "ix_investigation_activity_investigation_created",
    "ix_workspace_monitors_due",
    "ix_workspace_monitor_runs_monitor_started",
    "ix_workspace_generated_alerts_owner_occurred",
)
REQUIRED_V16_COLUMNS = REQUIRED_V15_COLUMNS

# Ranked PostgreSQL full-text search required by the 1.17 search surface.
REQUIRED_V17_TABLES = REQUIRED_V16_TABLES
REQUIRED_V17_INDEXES = REQUIRED_V16_INDEXES + (
    "ix_article_versions_search_weighted_fts",
    "ix_events_search_fts",
    "ix_article_claims_search_fts",
    "ix_events_lifecycle_changed",
    "ix_articles_language_published",
    "ix_articles_publisher_published",
)
REQUIRED_V17_COLUMNS = REQUIRED_V16_COLUMNS


# Search-quality evaluation and canonical entity intelligence required by 1.18.
REQUIRED_V18_TABLES = REQUIRED_V17_TABLES + (
    "search_benchmark_queries",
    "search_relevance_judgments",
    "search_benchmark_runs",
    "search_query_observations",
    "entity_mentions",
)
REQUIRED_V18_INDEXES = REQUIRED_V17_INDEXES + (
    "ix_search_benchmark_queries_set_created",
    "ix_search_relevance_query_grade",
    "ix_search_benchmark_runs_set_created",
    "ix_search_query_observations_created",
    "ix_search_query_observations_fingerprint_created",
    "ix_entity_mentions_entity_created",
    "ix_entity_mentions_claim",
    "ix_canonical_entities_search_fts",
    "ix_entity_aliases_search_fts",
)
REQUIRED_V18_COLUMNS = REQUIRED_V17_COLUMNS


# Human-reviewed entity resolution and benchmark/diagnostic surfaces required by 1.19.
REQUIRED_V19_TABLES = REQUIRED_V18_TABLES + (
    "entity_resolution_candidates",
    "entity_resolution_actions",
)
REQUIRED_V19_INDEXES = REQUIRED_V18_INDEXES + (
    "ix_canonical_entities_resolution_status",
    "ix_entity_resolution_candidates_status_created",
    "ix_entity_resolution_actions_created",
)
REQUIRED_V19_COLUMNS = REQUIRED_V18_COLUMNS + (
    ("canonical_entities", "resolution_status"),
    ("canonical_entities", "merged_into_entity_id"),
)


# Multilingual lexical fallback indexes required by 1.20. Semantic reranking
# remains experiment-only and therefore adds no canonical database tables.
REQUIRED_V20_TABLES = REQUIRED_V19_TABLES
REQUIRED_V20_INDEXES = REQUIRED_V19_INDEXES + (
    "ix_article_versions_search_english_fts",
    "ix_article_claims_search_english_fts",
    "ix_events_search_english_fts",
)
REQUIRED_V20_COLUMNS = REQUIRED_V19_COLUMNS


# Search promotion policy/evaluation persistence required by 1.21.
REQUIRED_V21_TABLES = REQUIRED_V20_TABLES + (
    "search_promotion_policies",
    "search_promotion_evaluations",
    "search_promotion_decisions",
)
REQUIRED_V21_INDEXES = REQUIRED_V20_INDEXES + (
    "ix_search_promotion_policies_updated",
    "ix_search_promotion_evaluations_set_created",
    "ix_search_promotion_evaluations_policy_created",
    "ix_search_promotion_decisions_evaluation_created",
)
REQUIRED_V21_COLUMNS = REQUIRED_V20_COLUMNS

# Approval-gated staged production search deployment required by 1.22.
REQUIRED_V22_TABLES = REQUIRED_V21_TABLES + (
    "search_deployments",
    "search_deployment_observations",
    "search_deployment_outcomes",
    "search_deployment_actions",
)
REQUIRED_V22_INDEXES = REQUIRED_V21_INDEXES + (
    "ix_search_deployments_state_updated",
    "ix_search_deployment_obs_deployment_created",
    "ix_search_deployment_obs_variant_created",
    "ix_search_deployment_outcomes_observation_created",
    "ix_search_deployment_actions_deployment_created",
)
REQUIRED_V22_COLUMNS = REQUIRED_V21_COLUMNS


# Live-pipeline lineage/fencing and grounded briefing persistence required by the final release.
REQUIRED_V23_TABLES = REQUIRED_V22_TABLES + (
    "fetch_job_observations",
    "article_identities",
    "article_identity_members",
)
REQUIRED_V23_INDEXES = REQUIRED_V22_INDEXES + (
    "ix_discovery_channels_fetch_job",
    "ix_url_candidates_fetch_job_state",
    "ix_url_discoveries_fetch_job_discovered",
    "ix_channel_poll_runs_fetch_job_started",
    "ix_article_fetch_runs_fetch_job_started",
    "ix_fetch_job_observations_job_created",
    "ix_article_identities_last_observed",
    "ix_article_identity_members_identity",
    "ix_article_identity_members_content",
)
REQUIRED_V23_COLUMNS = REQUIRED_V22_COLUMNS + (
    ("discovery_channels", "lease_version"),
    ("discovery_channels", "lease_heartbeat_at"),
    ("discovery_channels", "fetch_job_id"),
    ("url_candidates", "lease_version"),
    ("url_candidates", "lease_heartbeat_at"),
    ("url_candidates", "originating_fetch_job_id"),
    ("channel_poll_runs", "fetch_job_id"),
    ("channel_poll_runs", "lease_version"),
    ("article_fetch_runs", "fetch_job_id"),
    ("article_fetch_runs", "lease_version"),
)

REQUIRED_V24_TABLES = REQUIRED_V23_TABLES + (
    "event_briefing_jobs",
    "event_briefings",
)
REQUIRED_V24_INDEXES = REQUIRED_V23_INDEXES + (
    "ix_event_briefing_jobs_due",
    "ix_event_briefings_event_generated",
)
REQUIRED_V24_COLUMNS = REQUIRED_V23_COLUMNS

# v1.25 finalizes deployment/runtime packaging without introducing another canonical schema change.
REQUIRED_V25_TABLES = REQUIRED_V24_TABLES
REQUIRED_V25_INDEXES = REQUIRED_V24_INDEXES
REQUIRED_V25_COLUMNS = REQUIRED_V24_COLUMNS
