use std::collections::BTreeMap;

use serde::{Deserialize, Serialize};

pub const CASE_SCHEMA: &str = "evalfence.case.v1";
pub const REPORT_SCHEMA: &str = "evalfence.report.v1";
pub const BATCH_REPORT_SCHEMA: &str = "evalfence.batch-report.v1";

#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct IntervalInput {
    pub file: String,
    pub start: u64,
    pub end: u64,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct EvidenceSet {
    pub source: String,
    pub input_present: bool,
    #[serde(default)]
    pub intervals: Vec<IntervalInput>,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct ReportedMetrics {
    pub prediction_source: Option<String>,
    pub pred_size: Option<u64>,
    pub gold_size: Option<u64>,
    pub intersection: Option<u64>,
    pub precision: Option<f64>,
    pub recall: Option<f64>,
    pub f1: Option<f64>,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct AuditPolicy {
    pub allowed_prediction_sources: Vec<String>,
    pub tolerance: f64,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct AuditCase {
    pub schema_version: String,
    pub case_id: String,
    pub prediction: Option<EvidenceSet>,
    pub gold: EvidenceSet,
    pub reported: Option<ReportedMetrics>,
    pub policy: AuditPolicy,
}

#[derive(Debug, Clone, Serialize, PartialEq)]
pub struct MetricValues {
    pub pred_size: u64,
    pub gold_size: u64,
    pub intersection: u64,
    pub precision: Option<f64>,
    pub recall: Option<f64>,
    pub f1: Option<f64>,
}

#[derive(Debug, Clone, Serialize, PartialEq, Eq)]
pub struct Violation {
    pub code: String,
    pub message: String,
}

impl Violation {
    pub fn new(code: &str, message: impl Into<String>) -> Self {
        Self {
            code: code.to_string(),
            message: message.into(),
        }
    }
}

#[derive(Debug, Clone, Serialize)]
pub struct AuditReport {
    pub schema_version: &'static str,
    pub case_id: String,
    pub passed: bool,
    pub calculated: Option<MetricValues>,
    pub violations: Vec<Violation>,
}

#[derive(Debug, Clone, Serialize)]
pub struct BatchReport {
    pub schema_version: &'static str,
    pub total: usize,
    pub passed: usize,
    pub failed: usize,
    pub violation_counts: BTreeMap<String, usize>,
    pub examples: Vec<AuditReport>,
}
