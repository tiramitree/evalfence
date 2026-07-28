use std::collections::BTreeSet;

use crate::boundary_model::{
    AGENT_BOUNDARY_CASE_SCHEMA, AGENT_BOUNDARY_REPORT_SCHEMA, AgentBoundaryCase,
    AgentBoundaryCounts, AgentBoundaryReport, CapabilityKind,
};
use crate::model::Violation;

pub fn audit_agent_boundary(case: &AgentBoundaryCase) -> AgentBoundaryReport {
    let mut violations = Vec::new();
    if case.schema_version != AGENT_BOUNDARY_CASE_SCHEMA {
        violations.push(Violation::new(
            "EF000_SCHEMA_VERSION",
            format!("expected schema {AGENT_BOUNDARY_CASE_SCHEMA}"),
        ));
    }
    if case.case_id.trim().is_empty() {
        violations.push(Violation::new(
            "EF003_EMPTY_CASE_ID",
            "case_id must not be empty",
        ));
    }

    let allowed_inputs = validate_policy(case, &mut violations);
    let mut input_names = BTreeSet::new();
    let mut present_input_count = 0_u64;
    let mut oracle_input_count = 0_u64;
    let mut unapproved_input_count = 0_u64;
    let mut mutable_source_alias_count = 0_u64;

    for input in &case.inputs {
        let name_valid = validate_name(
            &input.name,
            "agent input",
            &mut input_names,
            &mut violations,
        );
        if let Some(digest) = &input.payload_sha256
            && !is_sha256(digest)
        {
            violations.push(Violation::new(
                "EF309_INVALID_BOUNDARY_DIGEST",
                format!(
                    "agent input {} has an invalid payload_sha256",
                    display_name(&input.name)
                ),
            ));
        }
        if !input.present && input.mutable_source_alias {
            violations.push(Violation::new(
                "EF317_INVALID_AGENT_INPUT_DECLARATION",
                format!(
                    "absent agent input {} cannot alias a mutable source object",
                    display_name(&input.name)
                ),
            ));
        }
        if !input.present {
            continue;
        }

        present_input_count += 1;
        let oracle = input.classification.is_oracle();
        if oracle {
            oracle_input_count += 1;
            if case.policy.forbid_oracle_inputs {
                violations.push(Violation::new(
                    "EF301_ORACLE_INPUT_EXPOSED",
                    format!(
                        "agent input {} is declared as an exposed oracle",
                        display_name(&input.name)
                    ),
                ));
            }
        } else if name_valid
            && allowed_inputs
                .as_ref()
                .is_some_and(|allowed| !allowed.contains(input.name.as_str()))
        {
            unapproved_input_count += 1;
            violations.push(Violation::new(
                "EF302_UNAPPROVED_AGENT_INPUT",
                format!(
                    "agent input {} is not in allowed_agent_inputs",
                    display_name(&input.name)
                ),
            ));
        }

        if input.mutable_source_alias {
            mutable_source_alias_count += 1;
            if case.policy.forbid_mutable_source_aliases {
                violations.push(Violation::new(
                    "EF305_MUTABLE_SOURCE_ALIAS",
                    format!(
                        "agent input {} aliases a mutable source object",
                        display_name(&input.name)
                    ),
                ));
            }
        }
    }

    let mut capability_names = BTreeSet::new();
    let mut live_write_callable_count = 0_u64;
    let mut unmediated_write_callable_count = 0_u64;
    let mut capability_count_overflow = false;
    for capability in &case.capabilities {
        validate_name(
            &capability.name,
            "capability group",
            &mut capability_names,
            &mut violations,
        );
        let counts_valid = capability.callable_count <= capability.total_count
            && capability.mediated_count <= capability.callable_count
            && (capability.exposed_to_agent || capability.callable_count == 0);
        if !counts_valid {
            violations.push(Violation::new(
                "EF313_INVALID_CAPABILITY_COUNTS",
                format!(
                    "capability group {} has inconsistent total, callable, mediated, or exposure declarations",
                    display_name(&capability.name)
                ),
            ));
            continue;
        }
        if capability.kind != CapabilityKind::WriteHandler || !capability.exposed_to_agent {
            continue;
        }

        live_write_callable_count =
            match live_write_callable_count.checked_add(capability.callable_count) {
                Some(value) => value,
                None => {
                    capability_count_overflow = true;
                    u64::MAX
                }
            };
        let unmediated = capability.callable_count - capability.mediated_count;
        unmediated_write_callable_count =
            match unmediated_write_callable_count.checked_add(unmediated) {
                Some(value) => value,
                None => {
                    capability_count_overflow = true;
                    u64::MAX
                }
            };
        if case.policy.require_write_capability_mediation && unmediated > 0 {
            violations.push(Violation::new(
                "EF303_UNMEDIATED_WRITE_CAPABILITY",
                format!(
                    "capability group {} exposes {unmediated} unmediated write callables",
                    display_name(&capability.name)
                ),
            ));
        }
    }
    if capability_count_overflow {
        violations.push(Violation::new(
            "EF316_CAPABILITY_COUNT_OVERFLOW",
            "aggregate callable capability counts exceed u64",
        ));
    }

    let prebaseline_constructor_count = u64::from(
        !case
            .construction_order
            .baseline_snapshot_before_agent_constructor,
    );
    if case.policy.require_baseline_before_agent_constructor && prebaseline_constructor_count == 1 {
        violations.push(Violation::new(
            "EF304_AGENT_CODE_BEFORE_BASELINE",
            "custom agent construction occurs before the baseline snapshot",
        ));
    }

    if case
        .construction_order
        .baseline_snapshot_before_agent_constructor
        && !case
            .construction_order
            .baseline_snapshot_before_first_agent_turn
    {
        violations.push(Violation::new(
            "EF315_INVALID_CONSTRUCTION_ORDER",
            "a baseline before agent construction must also precede the first agent turn",
        ));
    }
    let calculated = AgentBoundaryCounts {
        input_count: case.inputs.len() as u64,
        present_input_count,
        oracle_input_count,
        unapproved_input_count,
        mutable_source_alias_count,
        capability_group_count: case.capabilities.len() as u64,
        live_write_callable_count,
        unmediated_write_callable_count,
        prebaseline_constructor_count,
    };
    check_reported(case, &calculated, &mut violations);

    violations.sort_by(|left, right| {
        left.code
            .cmp(&right.code)
            .then(left.message.cmp(&right.message))
    });
    violations.dedup();

    AgentBoundaryReport {
        schema_version: AGENT_BOUNDARY_REPORT_SCHEMA,
        case_id: case.case_id.clone(),
        passed: violations.is_empty(),
        calculated,
        violations,
    }
}

fn validate_policy<'a>(
    case: &'a AgentBoundaryCase,
    violations: &mut Vec<Violation>,
) -> Option<BTreeSet<&'a str>> {
    let allowed: BTreeSet<&str> = case
        .policy
        .allowed_agent_inputs
        .iter()
        .map(String::as_str)
        .collect();
    let valid = allowed.len() == case.policy.allowed_agent_inputs.len()
        && allowed.iter().all(|name| valid_identifier(name));
    if !valid {
        violations.push(Violation::new(
            "EF310_INVALID_AGENT_INPUT_POLICY",
            "allowed_agent_inputs must contain unique safe non-empty identifiers",
        ));
        return None;
    }
    Some(allowed)
}

fn validate_name<'a>(
    name: &'a str,
    kind: &str,
    seen: &mut BTreeSet<&'a str>,
    violations: &mut Vec<Violation>,
) -> bool {
    if !valid_identifier(name) {
        violations.push(Violation::new(
            "EF311_INVALID_BOUNDARY_NAME",
            format!("{kind} has an invalid name"),
        ));
        return false;
    }
    if !seen.insert(name) {
        violations.push(Violation::new(
            "EF312_DUPLICATE_BOUNDARY_NAME",
            format!("{kind} {} is duplicated", display_name(name)),
        ));
        return false;
    }
    true
}

fn valid_identifier(value: &str) -> bool {
    let mut bytes = value.bytes();
    matches!(bytes.next(), Some(b'a'..=b'z'))
        && value.len() <= 128
        && bytes.all(|byte| {
            byte.is_ascii_lowercase() || byte.is_ascii_digit() || matches!(byte, b'_' | b'-' | b'.')
        })
}

fn display_name(value: &str) -> String {
    if valid_identifier(value) {
        format!("'{value}'")
    } else {
        "<invalid-name>".to_string()
    }
}

fn is_sha256(value: &str) -> bool {
    value.len() == 64
        && value
            .bytes()
            .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
}

fn check_reported(
    case: &AgentBoundaryCase,
    calculated: &AgentBoundaryCounts,
    violations: &mut Vec<Violation>,
) {
    let Some(reported) = &case.reported else {
        return;
    };
    if let Some(value) = reported.input_count
        && value != calculated.input_count
    {
        violations.push(Violation::new(
            "EF306_REPORTED_INPUT_COUNT_MISMATCH",
            format!(
                "input_count reported {value}, calculated {}",
                calculated.input_count
            ),
        ));
    }
    if let Some(value) = reported.oracle_input_count
        && value != calculated.oracle_input_count
    {
        violations.push(Violation::new(
            "EF307_REPORTED_ORACLE_COUNT_MISMATCH",
            format!(
                "oracle_input_count reported {value}, calculated {}",
                calculated.oracle_input_count
            ),
        ));
    }
    if let Some(value) = reported.capability_group_count
        && value != calculated.capability_group_count
    {
        violations.push(Violation::new(
            "EF308_REPORTED_CAPABILITY_COUNT_MISMATCH",
            format!(
                "capability_group_count reported {value}, calculated {}",
                calculated.capability_group_count
            ),
        ));
    }
    if let Some(value) = reported.unmediated_write_callable_count
        && value != calculated.unmediated_write_callable_count
    {
        violations.push(Violation::new(
            "EF314_REPORTED_UNMEDIATED_COUNT_MISMATCH",
            format!(
                "unmediated_write_callable_count reported {value}, calculated {}",
                calculated.unmediated_write_callable_count
            ),
        ));
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::boundary_model::{
        AgentBoundaryPolicy, AgentInput, AgentInputClass, BoundaryReported, CapabilityExposure,
        ConstructionOrder,
    };

    fn safe_input(name: &str) -> AgentInput {
        AgentInput {
            name: name.to_string(),
            classification: AgentInputClass::RuntimeMetadata,
            present: true,
            item_count: Some(1),
            payload_sha256: Some("a".repeat(64)),
            mutable_source_alias: false,
        }
    }

    fn case() -> AgentBoundaryCase {
        AgentBoundaryCase {
            schema_version: AGENT_BOUNDARY_CASE_SCHEMA.to_string(),
            case_id: "agent-boundary".to_string(),
            inputs: vec![safe_input("task_id")],
            capabilities: Vec::new(),
            construction_order: ConstructionOrder {
                baseline_snapshot_before_agent_constructor: true,
                baseline_snapshot_before_first_agent_turn: true,
            },
            reported: None,
            policy: AgentBoundaryPolicy {
                allowed_agent_inputs: vec!["task_id".to_string()],
                forbid_oracle_inputs: true,
                forbid_mutable_source_aliases: true,
                require_write_capability_mediation: true,
                require_baseline_before_agent_constructor: true,
            },
        }
    }

    fn codes(report: &AgentBoundaryReport) -> Vec<&str> {
        report
            .violations
            .iter()
            .map(|violation| violation.code.as_str())
            .collect()
    }

    #[test]
    fn safe_boundary_passes() {
        let report = audit_agent_boundary(&case());
        assert!(report.passed);
        assert_eq!(report.calculated.present_input_count, 1);
    }

    #[test]
    fn oracle_and_alias_are_independent_findings() {
        let mut value = case();
        value.inputs.push(AgentInput {
            name: "state_requirements".to_string(),
            classification: AgentInputClass::ScoringOracle,
            present: true,
            item_count: Some(4),
            payload_sha256: Some("b".repeat(64)),
            mutable_source_alias: true,
        });
        assert_eq!(
            codes(&audit_agent_boundary(&value)),
            vec!["EF301_ORACLE_INPUT_EXPOSED", "EF305_MUTABLE_SOURCE_ALIAS"]
        );
    }

    #[test]
    fn empty_allowlist_approves_no_non_oracle_input() {
        let mut value = case();
        value.policy.allowed_agent_inputs.clear();
        assert_eq!(
            codes(&audit_agent_boundary(&value)),
            vec!["EF302_UNAPPROVED_AGENT_INPUT"]
        );
    }

    #[test]
    fn unapproved_non_oracle_input_fails() {
        let mut value = case();
        value.inputs.push(safe_input("extra_metadata"));
        assert_eq!(
            codes(&audit_agent_boundary(&value)),
            vec!["EF302_UNAPPROVED_AGENT_INPUT"]
        );
    }

    #[test]
    fn unmediated_write_capability_fails() {
        let mut value = case();
        value.capabilities.push(CapabilityExposure {
            name: "shopping.write_handlers".to_string(),
            kind: CapabilityKind::WriteHandler,
            exposed_to_agent: true,
            total_count: 8,
            callable_count: 8,
            mediated_count: 0,
        });
        let report = audit_agent_boundary(&value);
        assert_eq!(codes(&report), vec!["EF303_UNMEDIATED_WRITE_CAPABILITY"]);
        assert_eq!(report.calculated.live_write_callable_count, 8);
        assert_eq!(report.calculated.unmediated_write_callable_count, 8);
    }

    #[test]
    fn prebaseline_constructor_fails() {
        let mut value = case();
        value
            .construction_order
            .baseline_snapshot_before_agent_constructor = false;
        assert_eq!(
            codes(&audit_agent_boundary(&value)),
            vec!["EF304_AGENT_CODE_BEFORE_BASELINE"]
        );
    }

    #[test]
    fn malformed_names_counts_policy_and_digest_fail_closed() {
        let mut value = case();
        value
            .policy
            .allowed_agent_inputs
            .push("task_id".to_string());
        value.inputs.push(AgentInput {
            name: "../secret".to_string(),
            classification: AgentInputClass::RuntimeMetadata,
            present: true,
            item_count: None,
            payload_sha256: Some("INVALID".to_string()),
            mutable_source_alias: false,
        });
        value.capabilities.push(CapabilityExposure {
            name: "write_handlers".to_string(),
            kind: CapabilityKind::WriteHandler,
            exposed_to_agent: false,
            total_count: 1,
            callable_count: 1,
            mediated_count: 2,
        });
        assert_eq!(
            codes(&audit_agent_boundary(&value)),
            vec![
                "EF309_INVALID_BOUNDARY_DIGEST",
                "EF310_INVALID_AGENT_INPUT_POLICY",
                "EF311_INVALID_BOUNDARY_NAME",
                "EF313_INVALID_CAPABILITY_COUNTS",
            ]
        );
    }

    #[test]
    fn contradictory_construction_order_fails() {
        let mut value = case();
        value
            .construction_order
            .baseline_snapshot_before_first_agent_turn = false;
        assert_eq!(
            codes(&audit_agent_boundary(&value)),
            vec!["EF315_INVALID_CONSTRUCTION_ORDER"]
        );
    }

    #[test]
    fn aggregate_capability_counts_fail_closed_on_overflow() {
        let mut value = case();
        value.policy.require_write_capability_mediation = false;
        for name in ["first.write_handlers", "second.write_handlers"] {
            value.capabilities.push(CapabilityExposure {
                name: name.to_string(),
                kind: CapabilityKind::WriteHandler,
                exposed_to_agent: true,
                total_count: u64::MAX,
                callable_count: u64::MAX,
                mediated_count: 0,
            });
        }
        let report = audit_agent_boundary(&value);
        assert_eq!(codes(&report), vec!["EF316_CAPABILITY_COUNT_OVERFLOW"]);
        assert_eq!(report.calculated.live_write_callable_count, u64::MAX);
        assert_eq!(report.calculated.unmediated_write_callable_count, u64::MAX);
    }

    #[test]
    fn absent_mutable_alias_is_rejected() {
        let mut value = case();
        value.inputs.push(AgentInput {
            name: "detached_context".to_string(),
            classification: AgentInputClass::RuntimeMetadata,
            present: false,
            item_count: None,
            payload_sha256: None,
            mutable_source_alias: true,
        });
        assert_eq!(
            codes(&audit_agent_boundary(&value)),
            vec!["EF317_INVALID_AGENT_INPUT_DECLARATION"]
        );
    }

    #[test]
    fn duplicate_names_fail() {
        let mut value = case();
        value.inputs.push(safe_input("task_id"));
        assert_eq!(
            codes(&audit_agent_boundary(&value)),
            vec!["EF312_DUPLICATE_BOUNDARY_NAME"]
        );
    }

    #[test]
    fn reported_counts_are_checked() {
        let mut value = case();
        value.reported = Some(BoundaryReported {
            input_count: Some(2),
            oracle_input_count: Some(1),
            capability_group_count: Some(1),
            unmediated_write_callable_count: Some(1),
        });
        assert_eq!(
            codes(&audit_agent_boundary(&value)),
            vec![
                "EF306_REPORTED_INPUT_COUNT_MISMATCH",
                "EF307_REPORTED_ORACLE_COUNT_MISMATCH",
                "EF308_REPORTED_CAPABILITY_COUNT_MISMATCH",
                "EF314_REPORTED_UNMEDIATED_COUNT_MISMATCH",
            ]
        );
    }
}
