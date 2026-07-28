use std::collections::BTreeSet;

const MANIFEST_CODES: [&str; 12] = [
    "EF000_SCHEMA_VERSION",
    "EF003_EMPTY_CASE_ID",
    "EF201_EMPTY_RECORD_ID",
    "EF202_DUPLICATE_RECORD_ID",
    "EF203_CONFLICTING_DUPLICATE_PAYLOAD",
    "EF204_UNAPPROVED_RECORD_ID",
    "EF205_MISSING_REQUIRED_RECORD",
    "EF206_REPORTED_RECORD_COUNT_MISMATCH",
    "EF207_REPORTED_UNIQUE_COUNT_MISMATCH",
    "EF208_ORDER_DEPENDENT_COLLAPSE",
    "EF209_INVALID_PAYLOAD_DIGEST",
    "EF210_INVALID_ID_POLICY",
];

#[test]
fn manifest_finding_registry_is_unique_and_documented() {
    let unique: BTreeSet<&str> = MANIFEST_CODES.into_iter().collect();
    assert_eq!(unique.len(), MANIFEST_CODES.len());
    let contract = include_str!("../docs/MANIFEST_CONTRACT.md");
    for code in MANIFEST_CODES {
        assert_eq!(
            contract.matches(code).count(),
            1,
            "{code} must occur exactly once in the manifest contract"
        );
    }
}
