use std::collections::BTreeMap;

use crate::interval::{intersection_size, normalize_set, set_size};
use crate::model::{
    AuditCase, AuditReport, BATCH_REPORT_SCHEMA, BatchReport, MetricValues, REPORT_SCHEMA,
    ReportedMetrics, Violation,
};

pub fn audit_case(case: &AuditCase) -> AuditReport {
    let mut violations = Vec::new();

    if case.schema_version != crate::model::CASE_SCHEMA {
        violations.push(Violation::new(
            "EF000_SCHEMA_VERSION",
            format!(
                "expected schema {}, received {}",
                crate::model::CASE_SCHEMA,
                case.schema_version
            ),
        ));
    }
    if case.case_id.trim().is_empty() {
        violations.push(Violation::new(
            "EF003_EMPTY_CASE_ID",
            "case_id must not be empty",
        ));
    }
    if !case.policy.tolerance.is_finite() || case.policy.tolerance < 0.0 {
        violations.push(Violation::new(
            "EF004_INVALID_TOLERANCE",
            "tolerance must be finite and non-negative",
        ));
    }
    if case
        .policy
        .allowed_prediction_sources
        .iter()
        .any(|source| source.trim().is_empty())
    {
        violations.push(Violation::new(
            "EF009_EMPTY_SOURCE",
            "allowed_prediction_sources must not contain empty labels",
        ));
    }

    check_declared_source("gold", &case.gold.source, &mut violations);
    if !case.gold.input_present {
        violations.push(Violation::new(
            "EF008_MISSING_GOLD_INPUT",
            "declared gold input is absent",
        ));
    }
    let gold_set = match normalize_set(&case.gold, "gold") {
        Ok(value) => Some(value),
        Err(mut errors) => {
            violations.append(&mut errors);
            None
        }
    };

    let prediction = match &case.prediction {
        Some(prediction) => {
            if !prediction.input_present {
                violations.push(Violation::new(
                    "EF001_MISSING_PREDICTION_INPUT",
                    "prediction evidence was materialized even though the declared prediction input was absent",
                ));
            }
            check_prediction_source(
                &prediction.source,
                &case.gold.source,
                &case.policy.allowed_prediction_sources,
                &mut violations,
            );
            prediction
        }
        None => {
            violations.push(Violation::new(
                "EF001_MISSING_PREDICTION_INPUT",
                "required prediction evidence is absent",
            ));
            if let Some(reported) = &case.reported {
                violations.push(Violation::new(
                    "EF007_REPORTED_WITHOUT_PREDICTION",
                    "reported metrics cannot be audited without prediction evidence",
                ));
                if let Some(source) = &reported.prediction_source {
                    check_prediction_source(
                        source,
                        &case.gold.source,
                        &case.policy.allowed_prediction_sources,
                        &mut violations,
                    );
                }
            }
            return finish(case, None, violations);
        }
    };

    if let Some(reported) = &case.reported
        && let Some(source) = &reported.prediction_source
    {
        check_prediction_source(
            source,
            &case.gold.source,
            &case.policy.allowed_prediction_sources,
            &mut violations,
        );
        if source.trim() != prediction.source.trim() {
            violations.push(Violation::new(
                "EF006_PREDICTION_SOURCE_MISMATCH",
                format!(
                    "reported prediction source {:?} differs from evidence source {:?}",
                    source.trim(),
                    prediction.source.trim()
                ),
            ));
        }
    }

    let pred_set = match normalize_set(prediction, "prediction") {
        Ok(value) => Some(value),
        Err(mut errors) => {
            violations.append(&mut errors);
            None
        }
    };
    let (Some(pred_set), Some(gold_set)) = (pred_set, gold_set) else {
        return finish(case, None, violations);
    };

    let pred_size = checked_cardinality(set_size(&pred_set, "prediction"), &mut violations);
    let gold_size = checked_cardinality(set_size(&gold_set, "gold"), &mut violations);
    let intersection =
        checked_cardinality(intersection_size(&pred_set, &gold_set), &mut violations);
    let (Some(pred_size), Some(gold_size), Some(intersection)) =
        (pred_size, gold_size, intersection)
    else {
        return finish(case, None, violations);
    };

    let precision = ratio(intersection, pred_size);
    let recall = ratio(intersection, gold_size);
    let f1 = match (precision, recall) {
        (Some(precision), Some(recall)) if precision + recall > 0.0 => {
            Some(2.0 * precision * recall / (precision + recall))
        }
        (Some(_), Some(_)) => Some(0.0),
        _ => None,
    };
    let calculated = MetricValues {
        pred_size,
        gold_size,
        intersection,
        precision,
        recall,
        f1,
    };

    if let Some(reported) = &case.reported {
        compare_reported(
            reported,
            &calculated,
            case.policy.tolerance,
            &mut violations,
        );
    }

    finish(case, Some(calculated), violations)
}

pub fn audit_batch(cases: &[AuditCase], max_examples: usize) -> BatchReport {
    let reports: Vec<AuditReport> = cases.iter().map(audit_case).collect();
    let passed = reports.iter().filter(|report| report.passed).count();
    let mut violation_counts = BTreeMap::new();
    for report in &reports {
        for violation in &report.violations {
            *violation_counts.entry(violation.code.clone()).or_insert(0) += 1;
        }
    }
    let examples = reports
        .into_iter()
        .filter(|report| !report.passed)
        .take(max_examples)
        .collect();
    BatchReport {
        schema_version: BATCH_REPORT_SCHEMA,
        total: cases.len(),
        passed,
        failed: cases.len() - passed,
        violation_counts,
        examples,
    }
}

fn finish(
    case: &AuditCase,
    calculated: Option<MetricValues>,
    mut violations: Vec<Violation>,
) -> AuditReport {
    violations.sort_by(|left, right| {
        left.code
            .cmp(&right.code)
            .then(left.message.cmp(&right.message))
    });
    violations.dedup();
    AuditReport {
        schema_version: REPORT_SCHEMA,
        case_id: case.case_id.clone(),
        passed: violations.is_empty(),
        calculated,
        violations,
    }
}

fn checked_cardinality(
    result: Result<u64, Violation>,
    violations: &mut Vec<Violation>,
) -> Option<u64> {
    match result {
        Ok(value) => Some(value),
        Err(error) => {
            violations.push(error);
            None
        }
    }
}

fn check_declared_source(role: &str, source: &str, violations: &mut Vec<Violation>) {
    if source.trim().is_empty() {
        violations.push(Violation::new(
            "EF009_EMPTY_SOURCE",
            format!("{role} source label must not be empty"),
        ));
    }
}

fn check_prediction_source(
    source: &str,
    gold_source: &str,
    allowed: &[String],
    violations: &mut Vec<Violation>,
) {
    check_declared_source("prediction", source, violations);
    let source_trimmed = source.trim();
    let source_lower = source_trimmed.to_ascii_lowercase();
    let gold_lower = gold_source.trim().to_ascii_lowercase();
    let looks_gold = !source_lower.is_empty()
        && (source_lower == gold_lower
            || source_lower.contains("gold")
            || (!gold_lower.is_empty() && source_lower.starts_with(gold_lower.as_str())));
    if looks_gold {
        violations.push(Violation::new(
            "EF002_GOLD_AS_PREDICTION",
            format!("prediction source {source_trimmed:?} is gold-derived"),
        ));
    }
    if !allowed.iter().any(|item| item == source_trimmed) {
        violations.push(Violation::new(
            "EF005_UNAPPROVED_PREDICTION_SOURCE",
            format!("prediction source {source_trimmed:?} is not in the allowed source list"),
        ));
    }
}

fn compare_reported(
    reported: &ReportedMetrics,
    calculated: &MetricValues,
    tolerance: f64,
    violations: &mut Vec<Violation>,
) {
    compare_count(
        "EF101_PRED_SIZE_MISMATCH",
        "pred_size",
        reported.pred_size,
        calculated.pred_size,
        violations,
    );
    compare_count(
        "EF102_GOLD_SIZE_MISMATCH",
        "gold_size",
        reported.gold_size,
        calculated.gold_size,
        violations,
    );
    compare_count(
        "EF103_INTERSECTION_MISMATCH",
        "intersection",
        reported.intersection,
        calculated.intersection,
        violations,
    );
    compare_metric(
        "EF104_PRECISION_FORMULA_MISMATCH",
        "precision",
        reported.precision,
        calculated.precision,
        tolerance,
        violations,
    );
    compare_metric(
        "EF105_RECALL_FORMULA_MISMATCH",
        "recall",
        reported.recall,
        calculated.recall,
        tolerance,
        violations,
    );
    compare_metric(
        "EF106_F1_FORMULA_MISMATCH",
        "f1",
        reported.f1,
        calculated.f1,
        tolerance,
        violations,
    );
}

fn compare_count(
    code: &str,
    name: &str,
    reported: Option<u64>,
    calculated: u64,
    violations: &mut Vec<Violation>,
) {
    if let Some(reported) = reported
        && reported != calculated
    {
        violations.push(Violation::new(
            code,
            format!("{name} reported {reported}, calculated {calculated}"),
        ));
    }
}

fn compare_metric(
    code: &str,
    name: &str,
    reported: Option<f64>,
    calculated: Option<f64>,
    tolerance: f64,
    violations: &mut Vec<Violation>,
) {
    let Some(reported) = reported else {
        return;
    };
    if !reported.is_finite() {
        violations.push(Violation::new(code, format!("{name} must be finite")));
        return;
    }
    match calculated {
        Some(calculated) if (reported - calculated).abs() <= tolerance => {}
        Some(calculated) => violations.push(Violation::new(
            code,
            format!("{name} reported {reported:.12}, calculated {calculated:.12}"),
        )),
        None => violations.push(Violation::new(
            code,
            format!("{name} was reported as {reported:.12} but its denominator is zero"),
        )),
    }
}

fn ratio(numerator: u64, denominator: u64) -> Option<f64> {
    if denominator == 0 {
        None
    } else {
        Some(numerator as f64 / denominator as f64)
    }
}

#[cfg(test)]
mod tests {
    use crate::model::{AuditPolicy, EvidenceSet, IntervalInput, ReportedMetrics};

    use super::*;

    fn set(source: &str, input_present: bool, ranges: &[(u64, u64)]) -> EvidenceSet {
        EvidenceSet {
            source: source.to_string(),
            input_present,
            intervals: ranges
                .iter()
                .map(|(start, end)| IntervalInput {
                    file: "src/lib.rs".to_string(),
                    start: *start,
                    end: *end,
                })
                .collect(),
        }
    }

    fn base_case(prediction: EvidenceSet, gold: EvidenceSet) -> AuditCase {
        AuditCase {
            schema_version: crate::model::CASE_SCHEMA.to_string(),
            case_id: "case-1".to_string(),
            prediction: Some(prediction),
            gold,
            reported: None,
            policy: AuditPolicy {
                allowed_prediction_sources: vec!["prediction.model_patch".to_string()],
                tolerance: 1.0e-9,
            },
        }
    }

    #[test]
    fn computes_standard_set_metrics() {
        let report = audit_case(&base_case(
            set("prediction.model_patch", true, &[(1, 10)]),
            set("gold.init_ctx", true, &[(1, 100)]),
        ));
        assert!(report.passed);
        let values = report.calculated.unwrap();
        assert_eq!(values.pred_size, 10);
        assert_eq!(values.gold_size, 100);
        assert_eq!(values.intersection, 10);
        assert_eq!(values.precision, Some(1.0));
        assert_eq!(values.recall, Some(0.1));
    }

    #[test]
    fn catches_gold_fallback_and_recall_denominator_error() {
        let mut case = base_case(
            set("gold.patch_fallback", false, &[(1, 10)]),
            set("gold.init_ctx", true, &[(1, 100)]),
        );
        case.reported = Some(ReportedMetrics {
            prediction_source: Some("gold.patch_fallback".to_string()),
            pred_size: Some(10),
            gold_size: Some(100),
            intersection: Some(10),
            precision: Some(1.0),
            recall: Some(1.0),
            f1: None,
        });
        let report = audit_case(&case);
        let codes: Vec<&str> = report
            .violations
            .iter()
            .map(|item| item.code.as_str())
            .collect();
        assert_eq!(
            codes,
            vec![
                "EF001_MISSING_PREDICTION_INPUT",
                "EF002_GOLD_AS_PREDICTION",
                "EF005_UNAPPROVED_PREDICTION_SOURCE",
                "EF105_RECALL_FORMULA_MISMATCH",
            ]
        );
    }

    #[test]
    fn catches_declared_prediction_source_mismatch() {
        let mut case = base_case(
            set("prediction.model_patch", true, &[(1, 10)]),
            set("gold.init_ctx", true, &[(1, 100)]),
        );
        case.policy
            .allowed_prediction_sources
            .push("prediction.alternate".to_string());
        case.reported = Some(ReportedMetrics {
            prediction_source: Some("prediction.alternate".to_string()),
            pred_size: None,
            gold_size: None,
            intersection: None,
            precision: None,
            recall: None,
            f1: None,
        });
        let report = audit_case(&case);
        assert_eq!(report.violations.len(), 1);
        assert_eq!(
            report.violations[0].code,
            "EF006_PREDICTION_SOURCE_MISMATCH"
        );
    }

    #[test]
    fn catches_missing_gold_input() {
        let report = audit_case(&base_case(
            set("prediction.model_patch", true, &[(1, 10)]),
            set("gold.init_ctx", false, &[(1, 100)]),
        ));
        assert_eq!(report.violations.len(), 1);
        assert_eq!(report.violations[0].code, "EF008_MISSING_GOLD_INPUT");
    }

    #[test]
    fn reported_metrics_without_prediction_register_both_findings() {
        let mut case = base_case(
            set("prediction.model_patch", true, &[(1, 10)]),
            set("gold.init_ctx", true, &[(1, 100)]),
        );
        case.prediction = None;
        case.reported = Some(ReportedMetrics {
            prediction_source: Some("prediction.model_patch".to_string()),
            pred_size: Some(10),
            gold_size: None,
            intersection: None,
            precision: None,
            recall: None,
            f1: None,
        });
        let report = audit_case(&case);
        let codes: Vec<&str> = report
            .violations
            .iter()
            .map(|item| item.code.as_str())
            .collect();
        assert_eq!(
            codes,
            vec![
                "EF001_MISSING_PREDICTION_INPUT",
                "EF007_REPORTED_WITHOUT_PREDICTION"
            ]
        );
    }

    #[test]
    fn invalid_gold_is_checked_when_prediction_is_absent() {
        let mut case = base_case(
            set("prediction.model_patch", true, &[(1, 10)]),
            set("gold.init_ctx", true, &[(2, 1)]),
        );
        case.prediction = None;
        let report = audit_case(&case);
        let codes: Vec<&str> = report
            .violations
            .iter()
            .map(|item| item.code.as_str())
            .collect();
        assert_eq!(
            codes,
            vec!["EF001_MISSING_PREDICTION_INPUT", "EF010_INVALID_INTERVAL"]
        );
    }

    #[test]
    fn empty_prediction_has_explicit_null_denominators() {
        let report = audit_case(&base_case(
            set("prediction.model_patch", true, &[]),
            set("gold.init_ctx", true, &[(1, 10)]),
        ));
        assert!(report.passed);
        let values = report.calculated.unwrap();
        assert_eq!(values.pred_size, 0);
        assert_eq!(values.intersection, 0);
        assert_eq!(values.precision, None);
        assert_eq!(values.recall, Some(0.0));
        assert_eq!(values.f1, None);
    }

    #[test]
    fn partial_report_checks_only_supplied_fields() {
        let mut case = base_case(
            set("prediction.model_patch", true, &[(1, 10)]),
            set("gold.init_ctx", true, &[(1, 100)]),
        );
        case.reported = Some(ReportedMetrics {
            prediction_source: Some("prediction.model_patch".to_string()),
            pred_size: None,
            gold_size: None,
            intersection: None,
            precision: Some(1.0),
            recall: None,
            f1: None,
        });
        assert!(audit_case(&case).passed);
    }

    #[test]
    fn empty_prediction_source_is_not_implicitly_allowed() {
        let mut case = base_case(
            set("", true, &[(1, 10)]),
            set("gold.init_ctx", true, &[(1, 100)]),
        );
        case.policy.allowed_prediction_sources.clear();
        let report = audit_case(&case);
        let codes: Vec<&str> = report
            .violations
            .iter()
            .map(|item| item.code.as_str())
            .collect();
        assert_eq!(
            codes,
            vec!["EF005_UNAPPROVED_PREDICTION_SOURCE", "EF009_EMPTY_SOURCE"]
        );
    }

    #[test]
    fn adding_unmatched_gold_keeps_precision_and_reduces_recall() {
        let short_gold = audit_case(&base_case(
            set("prediction.model_patch", true, &[(1, 10)]),
            set("gold.init_ctx", true, &[(1, 20)]),
        ))
        .calculated
        .unwrap();
        let long_gold = audit_case(&base_case(
            set("prediction.model_patch", true, &[(1, 10)]),
            set("gold.init_ctx", true, &[(1, 100)]),
        ))
        .calculated
        .unwrap();
        assert_eq!(short_gold.precision, long_gold.precision);
        assert!(short_gold.recall > long_gold.recall);
    }
}
