use std::fs;
use std::process::{Command, Stdio};

use serde_json::{Value, json};
use tempfile::tempdir;

fn binary() -> &'static str {
    env!("CARGO_BIN_EXE_evalfence")
}

fn fixture(name: &str) -> String {
    format!("{}/fixtures/{name}", env!("CARGO_MANIFEST_DIR"))
}

#[test]
fn good_boundary_exits_zero() {
    let output = Command::new(binary())
        .args([
            "audit-agent-boundary",
            "--input",
            &fixture("agent-boundary-good.json"),
        ])
        .output()
        .expect("run evalfence");
    assert!(output.status.success());
    let report: Value = serde_json::from_slice(&output.stdout).expect("report");
    assert_eq!(report["passed"], true);
}

#[test]
fn exposed_boundary_exits_two_with_registered_counts() {
    let output = Command::new(binary())
        .args([
            "audit-agent-boundary",
            "--input",
            &fixture("agent-boundary-exposed.json"),
        ])
        .output()
        .expect("run evalfence");
    assert_eq!(output.status.code(), Some(2));
    let report: Value = serde_json::from_slice(&output.stdout).expect("report");
    assert_eq!(
        report["schema_version"],
        "evalfence.agent-boundary-report.v1"
    );
    assert_eq!(
        report["calculated"],
        json!({
            "input_count": 7,
            "present_input_count": 7,
            "oracle_input_count": 3,
            "unapproved_input_count": 0,
            "mutable_source_alias_count": 2,
            "capability_group_count": 3,
            "live_write_callable_count": 20,
            "unmediated_write_callable_count": 20,
            "prebaseline_constructor_count": 1
        })
    );
    let codes: Vec<&str> = report["violations"]
        .as_array()
        .expect("violations")
        .iter()
        .map(|value| value["code"].as_str().expect("code"))
        .collect();
    assert_eq!(
        codes,
        vec![
            "EF301_ORACLE_INPUT_EXPOSED",
            "EF301_ORACLE_INPUT_EXPOSED",
            "EF301_ORACLE_INPUT_EXPOSED",
            "EF303_UNMEDIATED_WRITE_CAPABILITY",
            "EF303_UNMEDIATED_WRITE_CAPABILITY",
            "EF303_UNMEDIATED_WRITE_CAPABILITY",
            "EF304_AGENT_CODE_BEFORE_BASELINE",
            "EF305_MUTABLE_SOURCE_ALIAS",
            "EF305_MUTABLE_SOURCE_ALIAS",
        ]
    );
}

#[test]
fn stdin_and_output_file_are_supported() {
    let input = fs::read(fixture("agent-boundary-good.json")).expect("fixture");
    let temp = tempdir().expect("tempdir");
    let report_path = temp.path().join("report.json");
    let mut child = Command::new(binary())
        .args([
            "audit-agent-boundary",
            "--input",
            "-",
            "--output",
            report_path.to_str().expect("utf8 path"),
            "--pretty",
        ])
        .stdin(Stdio::piped())
        .spawn()
        .expect("spawn evalfence");
    use std::io::Write;
    child
        .stdin
        .take()
        .expect("stdin")
        .write_all(&input)
        .expect("write stdin");
    assert!(child.wait().expect("wait").success());
    let report: Value =
        serde_json::from_slice(&fs::read(report_path).expect("read report")).expect("parse report");
    assert_eq!(report["passed"], true);
}

#[test]
fn unknown_fields_are_rejected() {
    let mut value: Value =
        serde_json::from_slice(&fs::read(fixture("agent-boundary-good.json")).expect("fixture"))
            .expect("case");
    value["unexpected"] = Value::Bool(true);
    let input = serde_json::to_vec(&value).expect("serialize case");
    let mut child = Command::new(binary())
        .args(["audit-agent-boundary", "--input", "-"])
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .expect("spawn evalfence");
    use std::io::Write;
    child
        .stdin
        .take()
        .expect("stdin")
        .write_all(&input)
        .expect("write stdin");
    let output = child.wait_with_output().expect("wait");
    assert_eq!(output.status.code(), Some(1));
    assert!(output.stdout.is_empty());
    let stderr = String::from_utf8(output.stderr).expect("stderr");
    assert!(stderr.contains("unknown field"));
}
