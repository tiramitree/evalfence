use std::fs;
use std::path::PathBuf;
use std::process::Command;

fn fixture(name: &str) -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("fixtures")
        .join(name)
}

#[test]
fn good_case_exits_zero() {
    let output = Command::new(env!("CARGO_BIN_EXE_evalfence"))
        .args(["audit", "--input", fixture("good.json").to_str().unwrap()])
        .output()
        .unwrap();
    assert!(output.status.success());
    let stdout = String::from_utf8(output.stdout).unwrap();
    assert!(stdout.contains("\"passed\":true"));
}

#[test]
fn finding_case_exits_two_and_reports_stable_codes() {
    let output = Command::new(env!("CARGO_BIN_EXE_evalfence"))
        .args([
            "audit",
            "--input",
            fixture("gold-fallback.json").to_str().unwrap(),
        ])
        .output()
        .unwrap();
    assert_eq!(output.status.code(), Some(2));
    let stdout = String::from_utf8(output.stdout).unwrap();
    for code in [
        "EF001_MISSING_PREDICTION_INPUT",
        "EF002_GOLD_AS_PREDICTION",
        "EF005_UNAPPROVED_PREDICTION_SOURCE",
        "EF105_RECALL_FORMULA_MISMATCH",
    ] {
        assert!(stdout.contains(code), "{code} missing from {stdout}");
    }
}

#[test]
fn batch_aggregates_pass_and_failure_without_hiding_findings() {
    let temp = tempfile::tempdir().unwrap();
    let input = temp.path().join("cases.jsonl");
    let good: serde_json::Value =
        serde_json::from_str(&fs::read_to_string(fixture("good.json")).unwrap()).unwrap();
    let bad: serde_json::Value =
        serde_json::from_str(&fs::read_to_string(fixture("gold-fallback.json")).unwrap()).unwrap();
    let good = serde_json::to_string(&good).unwrap();
    let bad = serde_json::to_string(&bad).unwrap();
    fs::write(&input, format!("{good}\n{bad}\n")).unwrap();

    let output = Command::new(env!("CARGO_BIN_EXE_evalfence"))
        .args(["audit-batch", "--input", input.to_str().unwrap()])
        .output()
        .unwrap();
    assert_eq!(output.status.code(), Some(2));
    let stdout = String::from_utf8(output.stdout).unwrap();
    assert!(stdout.contains("\"total\":2"));
    assert!(stdout.contains("\"passed\":1"));
    assert!(stdout.contains("\"failed\":1"));
}

#[test]
fn malformed_case_json_exits_one() {
    let temp = tempfile::tempdir().unwrap();
    let input = temp.path().join("malformed.json");
    fs::write(&input, "{").unwrap();
    let output = Command::new(env!("CARGO_BIN_EXE_evalfence"))
        .args(["audit", "--input", input.to_str().unwrap()])
        .output()
        .unwrap();
    assert_eq!(output.status.code(), Some(1));
    assert!(
        String::from_utf8(output.stderr)
            .unwrap()
            .contains("invalid case JSON")
    );
}

#[test]
fn missing_input_presence_is_a_parse_error() {
    let temp = tempfile::tempdir().unwrap();
    let input = temp.path().join("missing-input-present.json");
    let contents = fs::read_to_string(fixture("good.json")).unwrap().replacen(
        "    \"input_present\": true,\n",
        "",
        1,
    );
    fs::write(&input, contents).unwrap();
    let output = Command::new(env!("CARGO_BIN_EXE_evalfence"))
        .args(["audit", "--input", input.to_str().unwrap()])
        .output()
        .unwrap();
    assert_eq!(output.status.code(), Some(1));
    assert!(
        String::from_utf8(output.stderr)
            .unwrap()
            .contains("missing field `input_present`")
    );
}

#[test]
fn missing_policy_is_a_parse_error() {
    let temp = tempfile::tempdir().unwrap();
    let input = temp.path().join("missing-policy.json");
    let mut contents: serde_json::Value =
        serde_json::from_str(&fs::read_to_string(fixture("good.json")).unwrap()).unwrap();
    contents.as_object_mut().unwrap().remove("policy");
    fs::write(&input, serde_json::to_vec(&contents).unwrap()).unwrap();
    let output = Command::new(env!("CARGO_BIN_EXE_evalfence"))
        .args(["audit", "--input", input.to_str().unwrap()])
        .output()
        .unwrap();
    assert_eq!(output.status.code(), Some(1));
    assert!(
        String::from_utf8(output.stderr)
            .unwrap()
            .contains("missing field `policy`")
    );
}

#[test]
fn empty_batch_exits_one() {
    let temp = tempfile::tempdir().unwrap();
    let input = temp.path().join("empty.jsonl");
    fs::write(&input, "\n \n").unwrap();
    let output = Command::new(env!("CARGO_BIN_EXE_evalfence"))
        .args(["audit-batch", "--input", input.to_str().unwrap()])
        .output()
        .unwrap();
    assert_eq!(output.status.code(), Some(1));
    assert!(
        String::from_utf8(output.stderr)
            .unwrap()
            .contains("batch contains no cases")
    );
}
