use std::collections::{BTreeMap, BTreeSet};

use crate::manifest_model::{
    CollapseWitness, ConsumerCollisionPolicy, MANIFEST_CASE_SCHEMA, MANIFEST_REPORT_SCHEMA,
    ManifestCase, ManifestCounts, ManifestRecord, ManifestReport,
};
use crate::model::Violation;

pub fn audit_manifest(case: &ManifestCase) -> ManifestReport {
    let mut violations = Vec::new();
    if case.schema_version != MANIFEST_CASE_SCHEMA {
        violations.push(Violation::new(
            "EF000_SCHEMA_VERSION",
            format!("expected schema {MANIFEST_CASE_SCHEMA}"),
        ));
    }
    if case.case_id.trim().is_empty() {
        violations.push(Violation::new(
            "EF003_EMPTY_CASE_ID",
            "case_id must not be empty",
        ));
    }

    let (allowed, required, policy_valid) = validate_policy(case, &mut violations);
    let mut records_by_id: BTreeMap<&str, Vec<(usize, &ManifestRecord)>> = BTreeMap::new();
    let mut valid_ids = BTreeSet::new();
    let mut unapproved = BTreeSet::new();
    let mut invalid_payload_count = 0_u64;

    for (position, record) in case.records.iter().enumerate() {
        if record.id.trim().is_empty() {
            violations.push(Violation::new(
                "EF201_EMPTY_RECORD_ID",
                format!("record at position {position} has an empty id"),
            ));
        } else {
            records_by_id
                .entry(record.id.as_str())
                .or_default()
                .push((position, record));
            if policy_valid && !allowed.contains(record.id.as_str()) {
                unapproved.insert(record.id.as_str());
            }
        }

        if !is_sha256(&record.payload_sha256) {
            invalid_payload_count += 1;
            violations.push(Violation::new(
                "EF209_INVALID_PAYLOAD_DIGEST",
                format!("record at position {position} has an invalid payload_sha256"),
            ));
        } else if !record.id.trim().is_empty() {
            valid_ids.insert(record.id.as_str());
        }
    }

    for (ordinal, _id) in unapproved.iter().enumerate() {
        violations.push(Violation::new(
            "EF204_UNAPPROVED_RECORD_ID",
            format!("unapproved record id group {}", ordinal + 1),
        ));
    }

    let mut missing_required = Vec::new();
    if policy_valid {
        for (ordinal, id) in required.iter().enumerate() {
            if !valid_ids.contains(id) {
                missing_required.push(*id);
                violations.push(Violation::new(
                    "EF205_MISSING_REQUIRED_RECORD",
                    format!("required id group {} is absent", ordinal + 1),
                ));
            }
        }
    }

    let mut duplicate_id_count = 0_u64;
    let mut conflicting_duplicate_id_count = 0_u64;
    let mut collapse_witnesses = Vec::new();

    for (group_index, (_id, records)) in records_by_id.iter().enumerate() {
        if records.len() <= 1 {
            continue;
        }
        duplicate_id_count += 1;
        violations.push(Violation::new(
            "EF202_DUPLICATE_RECORD_ID",
            format!(
                "record group {} occurs {} times",
                group_index + 1,
                records.len()
            ),
        ));

        let valid_records: Vec<(usize, &ManifestRecord)> = records
            .iter()
            .copied()
            .filter(|(_, record)| is_sha256(&record.payload_sha256))
            .collect();
        let payloads: BTreeSet<&str> = valid_records
            .iter()
            .map(|(_, record)| record.payload_sha256.as_str())
            .collect();
        if payloads.len() <= 1 {
            continue;
        }

        conflicting_duplicate_id_count += 1;
        violations.push(Violation::new(
            "EF203_CONFLICTING_DUPLICATE_PAYLOAD",
            format!(
                "record group {} has {} distinct payload digests",
                group_index + 1,
                payloads.len()
            ),
        ));
        if case.policy.consumer_collision_policy == ConsumerCollisionPolicy::LastWriteWins {
            violations.push(Violation::new(
                "EF208_ORDER_DEPENDENT_COLLAPSE",
                format!(
                    "last-write-wins collapse for record group {} depends on input order",
                    group_index + 1
                ),
            ));
            collapse_witnesses.push(CollapseWitness {
                record_group: (group_index + 1) as u64,
                positions: valid_records
                    .iter()
                    .map(|(position, _)| *position as u64)
                    .collect(),
                payload_sha256s: payloads.into_iter().map(str::to_string).collect(),
                first_record_payload_sha256: valid_records[0].1.payload_sha256.clone(),
                last_record_payload_sha256: valid_records
                    .last()
                    .expect("conflicting group has at least two valid records")
                    .1
                    .payload_sha256
                    .clone(),
            });
        }
    }

    let record_count = case.records.len() as u64;
    let unique_id_count = records_by_id.len() as u64;
    if let Some(reported) = &case.reported {
        if let Some(value) = reported.record_count
            && value != record_count
        {
            violations.push(Violation::new(
                "EF206_REPORTED_RECORD_COUNT_MISMATCH",
                format!("record_count reported {value}, calculated {record_count}"),
            ));
        }
        if let Some(value) = reported.unique_id_count
            && value != unique_id_count
        {
            violations.push(Violation::new(
                "EF207_REPORTED_UNIQUE_COUNT_MISMATCH",
                format!("unique_id_count reported {value}, calculated {unique_id_count}"),
            ));
        }
    }

    violations.sort_by(|left, right| {
        left.code
            .cmp(&right.code)
            .then(left.message.cmp(&right.message))
    });
    violations.dedup();
    collapse_witnesses.sort_by_key(|witness| witness.record_group);

    ManifestReport {
        schema_version: MANIFEST_REPORT_SCHEMA,
        case_id: case.case_id.clone(),
        passed: violations.is_empty(),
        calculated: ManifestCounts {
            record_count,
            unique_id_count,
            duplicate_id_count,
            conflicting_duplicate_id_count,
            order_dependent_collapse_count: collapse_witnesses.len() as u64,
            unapproved_id_count: unapproved.len() as u64,
            missing_required_id_count: missing_required.len() as u64,
            invalid_payload_count,
        },
        collapse_witnesses,
        violations,
    }
}

fn validate_policy<'a>(
    case: &'a ManifestCase,
    violations: &mut Vec<Violation>,
) -> (BTreeSet<&'a str>, BTreeSet<&'a str>, bool) {
    let allowed: BTreeSet<&str> = case.policy.allowed_ids.iter().map(String::as_str).collect();
    let required: BTreeSet<&str> = case
        .policy
        .required_ids
        .iter()
        .map(String::as_str)
        .collect();
    let valid = case
        .policy
        .allowed_ids
        .iter()
        .all(|id| !id.trim().is_empty())
        && case
            .policy
            .required_ids
            .iter()
            .all(|id| !id.trim().is_empty())
        && allowed.len() == case.policy.allowed_ids.len()
        && required.len() == case.policy.required_ids.len()
        && required.is_subset(&allowed);
    if !valid {
        violations.push(Violation::new(
            "EF210_INVALID_ID_POLICY",
            "allowed_ids and required_ids must be unique, non-empty, and required_ids must be a subset of allowed_ids",
        ));
    }
    (allowed, required, valid)
}

fn is_sha256(value: &str) -> bool {
    value.len() == 64
        && value
            .bytes()
            .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::manifest_model::{ManifestPolicy, ManifestReported};

    fn record(id: &str, digest: char) -> ManifestRecord {
        ManifestRecord {
            id: id.to_string(),
            payload_sha256: digest.to_string().repeat(64),
        }
    }

    fn case(records: Vec<ManifestRecord>) -> ManifestCase {
        ManifestCase {
            schema_version: MANIFEST_CASE_SCHEMA.to_string(),
            case_id: "manifest-case".to_string(),
            records,
            reported: None,
            policy: ManifestPolicy {
                allowed_ids: vec!["example__repo-1".to_string(), "example__repo-2".to_string()],
                required_ids: Vec::new(),
                consumer_collision_policy: ConsumerCollisionPolicy::LastWriteWins,
            },
        }
    }

    fn codes(report: &ManifestReport) -> Vec<&str> {
        report
            .violations
            .iter()
            .map(|violation| violation.code.as_str())
            .collect()
    }

    #[test]
    fn unique_records_pass() {
        let report = audit_manifest(&case(vec![
            record("example__repo-1", 'a'),
            record("example__repo-2", 'b'),
        ]));
        assert!(report.passed);
        assert_eq!(report.calculated.record_count, 2);
        assert_eq!(report.calculated.unique_id_count, 2);
        assert!(report.collapse_witnesses.is_empty());
    }

    #[test]
    fn repeated_identical_payload_is_duplicate_but_not_order_dependent() {
        let report = audit_manifest(&case(vec![
            record("example__repo-1", 'a'),
            record("example__repo-1", 'a'),
        ]));
        assert_eq!(codes(&report), vec!["EF202_DUPLICATE_RECORD_ID"]);
        assert_eq!(report.calculated.duplicate_id_count, 1);
        assert_eq!(report.calculated.conflicting_duplicate_id_count, 0);
        assert!(report.collapse_witnesses.is_empty());
    }

    #[test]
    fn conflicting_duplicate_registers_stable_findings_and_survivors() {
        let forward = audit_manifest(&case(vec![
            record("example__repo-1", 'a'),
            record("example__repo-1", 'b'),
        ]));
        let reverse = audit_manifest(&case(vec![
            record("example__repo-1", 'b'),
            record("example__repo-1", 'a'),
        ]));
        let expected = vec![
            "EF202_DUPLICATE_RECORD_ID",
            "EF203_CONFLICTING_DUPLICATE_PAYLOAD",
            "EF208_ORDER_DEPENDENT_COLLAPSE",
        ];
        assert_eq!(codes(&forward), expected);
        assert_eq!(codes(&reverse), expected);
        assert_eq!(
            forward.collapse_witnesses[0].last_record_payload_sha256,
            "b".repeat(64)
        );
        assert_eq!(
            reverse.collapse_witnesses[0].last_record_payload_sha256,
            "a".repeat(64)
        );
    }

    #[test]
    fn required_and_allowed_boundaries_are_independent() {
        let mut value = case(vec![record("unregistered__repo-3", 'a')]);
        value.policy.required_ids = vec!["example__repo-1".to_string()];
        let report = audit_manifest(&value);
        assert_eq!(
            codes(&report),
            vec![
                "EF204_UNAPPROVED_RECORD_ID",
                "EF205_MISSING_REQUIRED_RECORD"
            ]
        );
    }

    #[test]
    fn invalid_digest_does_not_create_a_collapse_witness() {
        let mut invalid = record("example__repo-1", 'a');
        invalid.payload_sha256 = "NOT-A-DIGEST".to_string();
        let report = audit_manifest(&case(vec![invalid, record("example__repo-1", 'b')]));
        assert_eq!(
            codes(&report),
            vec!["EF202_DUPLICATE_RECORD_ID", "EF209_INVALID_PAYLOAD_DIGEST"]
        );
        assert!(report.collapse_witnesses.is_empty());
        assert_eq!(report.calculated.invalid_payload_count, 1);
    }

    #[test]
    fn invalid_digest_does_not_hide_a_conflict_between_valid_records() {
        let mut invalid = record("example__repo-1", 'c');
        invalid.payload_sha256 = "NOT-A-DIGEST".to_string();
        let report = audit_manifest(&case(vec![
            record("example__repo-1", 'a'),
            invalid,
            record("example__repo-1", 'b'),
        ]));
        assert_eq!(
            codes(&report),
            vec![
                "EF202_DUPLICATE_RECORD_ID",
                "EF203_CONFLICTING_DUPLICATE_PAYLOAD",
                "EF208_ORDER_DEPENDENT_COLLAPSE",
                "EF209_INVALID_PAYLOAD_DIGEST",
            ]
        );
        assert_eq!(report.calculated.invalid_payload_count, 1);
        assert_eq!(report.calculated.conflicting_duplicate_id_count, 1);
        assert_eq!(report.collapse_witnesses[0].positions, vec![0, 2]);
        assert_eq!(
            report.collapse_witnesses[0].first_record_payload_sha256,
            "a".repeat(64)
        );
        assert_eq!(
            report.collapse_witnesses[0].last_record_payload_sha256,
            "b".repeat(64)
        );
    }

    #[test]
    fn reported_counts_are_checked() {
        let mut value = case(vec![record("example__repo-1", 'a')]);
        value.reported = Some(ManifestReported {
            record_count: Some(2),
            unique_id_count: Some(3),
        });
        assert_eq!(
            codes(&audit_manifest(&value)),
            vec![
                "EF206_REPORTED_RECORD_COUNT_MISMATCH",
                "EF207_REPORTED_UNIQUE_COUNT_MISMATCH"
            ]
        );
    }

    #[test]
    fn malformed_policy_fails_closed() {
        let mut value = case(vec![record("example__repo-1", 'a')]);
        value.policy.allowed_ids.push("example__repo-1".to_string());
        value.policy.required_ids = vec!["missing__repo-2".to_string()];
        assert_eq!(
            codes(&audit_manifest(&value)),
            vec!["EF210_INVALID_ID_POLICY"]
        );
    }
}
