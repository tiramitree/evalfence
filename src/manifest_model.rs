use serde::{Deserialize, Serialize};

use crate::model::Violation;

pub const MANIFEST_CASE_SCHEMA: &str = "evalfence.keyed-manifest.v1";
pub const MANIFEST_REPORT_SCHEMA: &str = "evalfence.manifest-report.v1";

#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct ManifestRecord {
    pub id: String,
    pub payload_sha256: String,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct ManifestReported {
    pub record_count: Option<u64>,
    pub unique_id_count: Option<u64>,
}

#[derive(Debug, Clone, Deserialize, Serialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum ConsumerCollisionPolicy {
    LastWriteWins,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct ManifestPolicy {
    pub allowed_ids: Vec<String>,
    pub required_ids: Vec<String>,
    pub consumer_collision_policy: ConsumerCollisionPolicy,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct ManifestCase {
    pub schema_version: String,
    pub case_id: String,
    pub records: Vec<ManifestRecord>,
    pub reported: Option<ManifestReported>,
    pub policy: ManifestPolicy,
}

#[derive(Debug, Clone, Serialize, PartialEq, Eq)]
pub struct ManifestCounts {
    pub record_count: u64,
    pub unique_id_count: u64,
    pub duplicate_id_count: u64,
    pub conflicting_duplicate_id_count: u64,
    pub order_dependent_collapse_count: u64,
    pub unapproved_id_count: u64,
    pub missing_required_id_count: u64,
    pub invalid_payload_count: u64,
}

#[derive(Debug, Clone, Serialize, PartialEq, Eq)]
pub struct CollapseWitness {
    pub record_group: u64,
    pub positions: Vec<u64>,
    pub payload_sha256s: Vec<String>,
    pub first_record_payload_sha256: String,
    pub last_record_payload_sha256: String,
}

#[derive(Debug, Clone, Serialize)]
pub struct ManifestReport {
    pub schema_version: &'static str,
    pub case_id: String,
    pub passed: bool,
    pub calculated: ManifestCounts,
    pub collapse_witnesses: Vec<CollapseWitness>,
    pub violations: Vec<Violation>,
}
