use std::collections::BTreeMap;

use crate::model::{EvidenceSet, Violation};

pub type NormalizedSet = BTreeMap<String, Vec<(u64, u64)>>;

pub fn normalize_set(evidence: &EvidenceSet, role: &str) -> Result<NormalizedSet, Vec<Violation>> {
    let mut by_file: NormalizedSet = BTreeMap::new();
    let mut violations = Vec::new();

    for (index, item) in evidence.intervals.iter().enumerate() {
        match normalize_file_key(&item.file) {
            Ok(file) => {
                if item.start == 0 || item.end == 0 || item.start > item.end {
                    violations.push(Violation::new(
                        "EF010_INVALID_INTERVAL",
                        format!(
                            "{role} interval {index} must use positive inclusive bounds with start <= end"
                        ),
                    ));
                    continue;
                }
                by_file
                    .entry(file)
                    .or_default()
                    .push((item.start, item.end));
            }
            Err(reason) => violations.push(Violation::new(
                "EF011_UNSAFE_FILE_KEY",
                format!("{role} interval {index}: {reason}"),
            )),
        }
    }

    if !violations.is_empty() {
        return Err(violations);
    }

    for intervals in by_file.values_mut() {
        *intervals = merge_intervals(intervals);
    }
    Ok(by_file)
}

pub fn set_size(set: &NormalizedSet, role: &str) -> Result<u64, Violation> {
    let mut total = 0_u128;
    for intervals in set.values() {
        for &(start, end) in intervals {
            let width = u128::from(end) - u128::from(start) + 1;
            total = total
                .checked_add(width)
                .ok_or_else(|| cardinality_overflow(role))?;
        }
    }
    u64::try_from(total).map_err(|_| cardinality_overflow(role))
}

pub fn intersection_size(left: &NormalizedSet, right: &NormalizedSet) -> Result<u64, Violation> {
    let mut total = 0_u128;
    for (file, left_intervals) in left {
        let Some(right_intervals) = right.get(file) else {
            continue;
        };
        let mut left_index = 0;
        let mut right_index = 0;
        while left_index < left_intervals.len() && right_index < right_intervals.len() {
            let left_item = left_intervals[left_index];
            let right_item = right_intervals[right_index];
            let start = left_item.0.max(right_item.0);
            let end = left_item.1.min(right_item.1);
            if start <= end {
                let width = u128::from(end) - u128::from(start) + 1;
                total = total
                    .checked_add(width)
                    .ok_or_else(|| cardinality_overflow("prediction/gold intersection"))?;
            }
            if left_item.1 < right_item.1 {
                left_index += 1;
            } else {
                right_index += 1;
            }
        }
    }
    u64::try_from(total).map_err(|_| cardinality_overflow("prediction/gold intersection"))
}

fn cardinality_overflow(role: &str) -> Violation {
    Violation::new(
        "EF012_CARDINALITY_OVERFLOW",
        format!("{role} interval cardinality exceeds the reportable u64 range"),
    )
}

fn normalize_file_key(raw: &str) -> Result<String, &'static str> {
    let normalized = raw.trim().replace('\\', "/");
    if normalized.is_empty() {
        return Err("file key is empty");
    }
    if normalized.starts_with('/') || normalized.starts_with("//") {
        return Err("absolute or UNC file keys are not accepted");
    }
    if normalized
        .split('/')
        .next()
        .is_some_and(|first| first.contains(':'))
    {
        return Err("drive-qualified file keys are not accepted");
    }
    if normalized
        .split('/')
        .any(|part| part.is_empty() || part == "." || part == "..")
    {
        return Err("file key contains an empty, current-directory, or parent-directory component");
    }
    Ok(normalized)
}

fn merge_intervals(intervals: &[(u64, u64)]) -> Vec<(u64, u64)> {
    let mut sorted = intervals.to_vec();
    sorted.sort_unstable();
    let mut merged: Vec<(u64, u64)> = Vec::with_capacity(sorted.len());
    for current in sorted {
        match merged.last_mut() {
            Some(last) if current.0 <= last.1.saturating_add(1) => {
                last.1 = last.1.max(current.1);
            }
            _ => merged.push(current),
        }
    }
    merged
}

#[cfg(test)]
mod tests {
    use crate::model::IntervalInput;

    use super::*;

    fn evidence(items: &[(&str, u64, u64)]) -> EvidenceSet {
        EvidenceSet {
            source: "prediction.test".to_string(),
            input_present: true,
            intervals: items
                .iter()
                .map(|(file, start, end)| IntervalInput {
                    file: (*file).to_string(),
                    start: *start,
                    end: *end,
                })
                .collect(),
        }
    }

    #[test]
    fn merges_overlapping_and_adjacent_intervals() {
        let normalized = normalize_set(
            &evidence(&[("src/lib.rs", 3, 5), ("src/lib.rs", 1, 2)]),
            "prediction",
        )
        .unwrap();
        assert_eq!(normalized["src/lib.rs"], vec![(1, 5)]);
        assert_eq!(set_size(&normalized, "prediction").unwrap(), 5);
    }

    #[test]
    fn computes_cross_file_intersection() {
        let left = normalize_set(
            &evidence(&[("src/lib.rs", 1, 5), ("src/main.rs", 8, 10)]),
            "prediction",
        )
        .unwrap();
        let right = normalize_set(
            &evidence(&[("src/lib.rs", 4, 8), ("src/main.rs", 1, 8)]),
            "gold",
        )
        .unwrap();
        assert_eq!(intersection_size(&left, &right).unwrap(), 3);
    }

    #[test]
    fn rejects_cross_file_cardinality_overflow() {
        let normalized = normalize_set(
            &evidence(&[("first.rs", 1, u64::MAX), ("second.rs", 1, u64::MAX)]),
            "prediction",
        )
        .unwrap();
        let error = set_size(&normalized, "prediction").unwrap_err();
        assert_eq!(error.code, "EF012_CARDINALITY_OVERFLOW");
    }

    #[test]
    fn rejects_host_paths_and_parent_components() {
        let separator = char::from(92);
        let drive_path = format!("X:{separator}private{separator}file.rs");
        let unix_path = ["/", "example/file.rs"].concat();
        for file in [drive_path.as_str(), unix_path.as_str(), "../file.rs"] {
            let result = normalize_set(&evidence(&[(file, 1, 1)]), "prediction");
            assert!(result.is_err(), "{file} should be rejected");
        }
    }
}
