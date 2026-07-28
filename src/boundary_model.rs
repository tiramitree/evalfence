use serde::{Deserialize, Serialize};

use crate::model::Violation;

pub const AGENT_BOUNDARY_CASE_SCHEMA: &str = "evalfence.agent-boundary.v1";
pub const AGENT_BOUNDARY_REPORT_SCHEMA: &str = "evalfence.agent-boundary-report.v1";

#[derive(Debug, Clone, Deserialize, Serialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum AgentInputClass {
    RuntimeMetadata,
    UserVisible,
    TaskOracle,
    ScoringOracle,
}

impl AgentInputClass {
    pub fn is_oracle(&self) -> bool {
        matches!(self, Self::TaskOracle | Self::ScoringOracle)
    }
}

#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct AgentInput {
    pub name: String,
    pub classification: AgentInputClass,
    pub present: bool,
    pub item_count: Option<u64>,
    pub payload_sha256: Option<String>,
    pub mutable_source_alias: bool,
}

#[derive(Debug, Clone, Deserialize, Serialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum CapabilityKind {
    ReadHandler,
    WriteHandler,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct CapabilityExposure {
    pub name: String,
    pub kind: CapabilityKind,
    pub exposed_to_agent: bool,
    pub total_count: u64,
    pub callable_count: u64,
    pub mediated_count: u64,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct ConstructionOrder {
    pub baseline_snapshot_before_agent_constructor: bool,
    pub baseline_snapshot_before_first_agent_turn: bool,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct AgentBoundaryPolicy {
    pub allowed_agent_inputs: Vec<String>,
    pub forbid_oracle_inputs: bool,
    pub forbid_mutable_source_aliases: bool,
    pub require_write_capability_mediation: bool,
    pub require_baseline_before_agent_constructor: bool,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct BoundaryReported {
    pub input_count: Option<u64>,
    pub oracle_input_count: Option<u64>,
    pub capability_group_count: Option<u64>,
    pub unmediated_write_callable_count: Option<u64>,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct AgentBoundaryCase {
    pub schema_version: String,
    pub case_id: String,
    pub inputs: Vec<AgentInput>,
    pub capabilities: Vec<CapabilityExposure>,
    pub construction_order: ConstructionOrder,
    pub reported: Option<BoundaryReported>,
    pub policy: AgentBoundaryPolicy,
}

#[derive(Debug, Clone, Serialize, PartialEq, Eq)]
pub struct AgentBoundaryCounts {
    pub input_count: u64,
    pub present_input_count: u64,
    pub oracle_input_count: u64,
    pub unapproved_input_count: u64,
    pub mutable_source_alias_count: u64,
    pub capability_group_count: u64,
    pub live_write_callable_count: u64,
    pub unmediated_write_callable_count: u64,
    pub prebaseline_constructor_count: u64,
}

#[derive(Debug, Clone, Serialize)]
pub struct AgentBoundaryReport {
    pub schema_version: &'static str,
    pub case_id: String,
    pub passed: bool,
    pub calculated: AgentBoundaryCounts,
    pub violations: Vec<Violation>,
}
