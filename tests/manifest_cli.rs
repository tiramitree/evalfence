use std::fs;
use std::path::PathBuf;
use std::process::Command;

fn fixture(name: &str) -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("fixtures")
        .join(name)
}

#[test]
fn unique_manifest_exits_zero() {
    let output = Command::new(env!("CARGO_BIN_EXE_evalfence"))
        .args([
            "audit-manifest",
            "--input",
            fixture("manifest-good.json").to_str().unwrap(),
        ])
        .output()
        .unwrap();
    assert!(output.status.success());
    let stdout = String::from_utf8(output.stdout).unwrap();
    assert!(stdout.contains("\"schema_version\":\"evalfence.manifest-report.v1\""));
    assert!(stdout.contains("\"passed\":true"));
}

#[test]
fn conflicting_duplicate_exits_two_without_echoing_record_id() {
    let output = Command::new(env!("CARGO_BIN_EXE_evalfence"))
        .args([
            "audit-manifest",
            "--input",
            fixture("manifest-conflict.json").to_str().unwrap(),
        ])
        .output()
        .unwrap();
    assert_eq!(output.status.code(), Some(2));
    let stdout = String::from_utf8(output.stdout).unwrap();
    for code in [
        "EF202_DUPLICATE_RECORD_ID",
        "EF203_CONFLICTING_DUPLICATE_PAYLOAD",
        "EF208_ORDER_DEPENDENT_COLLAPSE",
    ] {
        assert!(stdout.contains(code), "{code} missing from {stdout}");
    }
    assert!(stdout.contains("\"record_group\":1"));
    assert!(!stdout.contains("example__repo-1"));
}

#[test]
fn malformed_manifest_exits_one() {
    let temp = tempfile::tempdir().unwrap();
    let input = temp.path().join("malformed.json");
    fs::write(&input, "{").unwrap();
    let output = Command::new(env!("CARGO_BIN_EXE_evalfence"))
        .args(["audit-manifest", "--input", input.to_str().unwrap()])
        .output()
        .unwrap();
    assert_eq!(output.status.code(), Some(1));
    assert!(
        String::from_utf8(output.stderr)
            .unwrap()
            .contains("invalid keyed-manifest JSON")
    );
}

#[test]
fn unknown_collision_policy_is_a_parse_error() {
    let temp = tempfile::tempdir().unwrap();
    let input = temp.path().join("unknown-policy.json");
    let contents = fs::read_to_string(fixture("manifest-good.json"))
        .unwrap()
        .replace("last_write_wins", "unspecified");
    fs::write(&input, contents).unwrap();
    let output = Command::new(env!("CARGO_BIN_EXE_evalfence"))
        .args(["audit-manifest", "--input", input.to_str().unwrap()])
        .output()
        .unwrap();
    assert_eq!(output.status.code(), Some(1));
    assert!(
        String::from_utf8(output.stderr)
            .unwrap()
            .contains("unknown variant")
    );
}
