use std::fs;
use std::io::{self, BufRead, Read, Write};
use std::path::{Path, PathBuf};
use std::process::ExitCode;

use clap::{Parser, Subcommand};
use evalfence::{AuditCase, audit_batch, audit_case};

const MAX_CASE_BYTES: u64 = 8 * 1024 * 1024;
const MAX_BATCH_BYTES: u64 = 64 * 1024 * 1024;
const MAX_LINE_BYTES: usize = 1024 * 1024;
const MAX_BATCH_CASES: usize = 100_000;

#[derive(Debug, Parser)]
#[command(name = "evalfence", version, about)]
struct Cli {
    #[command(subcommand)]
    command: Command,
}

#[derive(Debug, Subcommand)]
enum Command {
    /// Audit one JSON case.
    Audit {
        /// Input JSON path, or '-' for stdin.
        #[arg(short, long)]
        input: String,
        /// Optional report path. Stdout is used when omitted.
        #[arg(short, long)]
        output: Option<PathBuf>,
        /// Pretty-print JSON.
        #[arg(long)]
        pretty: bool,
    },
    /// Audit newline-delimited JSON cases and emit an aggregate report.
    AuditBatch {
        /// Input JSONL path, or '-' for stdin.
        #[arg(short, long)]
        input: String,
        /// Optional report path. Stdout is used when omitted.
        #[arg(short, long)]
        output: Option<PathBuf>,
        /// Maximum failing case examples retained in the aggregate report.
        #[arg(long, default_value_t = 10)]
        max_examples: usize,
        /// Pretty-print JSON.
        #[arg(long)]
        pretty: bool,
    },
}

fn main() -> ExitCode {
    match run() {
        Ok(passed) => {
            if passed {
                ExitCode::SUCCESS
            } else {
                ExitCode::from(2)
            }
        }
        Err(message) => {
            eprintln!("evalfence: {message}");
            ExitCode::from(1)
        }
    }
}

fn run() -> Result<bool, String> {
    let cli = Cli::parse();
    match cli.command {
        Command::Audit {
            input,
            output,
            pretty,
        } => {
            let bytes = read_input(&input, MAX_CASE_BYTES)?;
            let case: AuditCase = serde_json::from_slice(&bytes)
                .map_err(|error| format!("invalid case JSON: {error}"))?;
            let report = audit_case(&case);
            write_json(&report, output.as_deref(), pretty)?;
            Ok(report.passed)
        }
        Command::AuditBatch {
            input,
            output,
            max_examples,
            pretty,
        } => {
            let bytes = read_input(&input, MAX_BATCH_BYTES)?;
            let mut cases = Vec::new();
            for (line_index, line) in io::Cursor::new(bytes).lines().enumerate() {
                let line = line.map_err(|error| {
                    format!("failed to read batch line {}: {error}", line_index + 1)
                })?;
                if line.trim().is_empty() {
                    continue;
                }
                if line.len() > MAX_LINE_BYTES {
                    return Err(format!(
                        "batch line {} exceeds {} bytes",
                        line_index + 1,
                        MAX_LINE_BYTES
                    ));
                }
                if cases.len() >= MAX_BATCH_CASES {
                    return Err(format!("batch exceeds {MAX_BATCH_CASES} cases"));
                }
                let case: AuditCase = serde_json::from_str(&line).map_err(|error| {
                    format!("invalid JSON on batch line {}: {error}", line_index + 1)
                })?;
                cases.push(case);
            }
            if cases.is_empty() {
                return Err("batch contains no cases".to_string());
            }
            let report = audit_batch(&cases, max_examples);
            write_json(&report, output.as_deref(), pretty)?;
            Ok(report.failed == 0)
        }
    }
}

fn read_input(input: &str, max_bytes: u64) -> Result<Vec<u8>, String> {
    if input == "-" {
        let mut bytes = Vec::new();
        io::stdin()
            .take(max_bytes + 1)
            .read_to_end(&mut bytes)
            .map_err(|error| format!("failed to read stdin: {error}"))?;
        if bytes.len() as u64 > max_bytes {
            return Err(format!("stdin exceeds {max_bytes} bytes"));
        }
        return Ok(bytes);
    }

    let path = Path::new(input);
    let metadata =
        fs::metadata(path).map_err(|error| format!("cannot stat {}: {error}", path.display()))?;
    if !metadata.is_file() {
        return Err(format!("{} is not a regular file", path.display()));
    }
    if metadata.len() > max_bytes {
        return Err(format!(
            "{} is {} bytes; limit is {}",
            path.display(),
            metadata.len(),
            max_bytes
        ));
    }
    fs::read(path).map_err(|error| format!("cannot read {}: {error}", path.display()))
}

fn write_json<T: serde::Serialize>(
    value: &T,
    output: Option<&Path>,
    pretty: bool,
) -> Result<(), String> {
    let mut bytes = if pretty {
        serde_json::to_vec_pretty(value)
    } else {
        serde_json::to_vec(value)
    }
    .map_err(|error| format!("cannot serialize report: {error}"))?;
    bytes.push(b'\n');

    match output {
        Some(path) => fs::write(path, bytes)
            .map_err(|error| format!("cannot write {}: {error}", path.display())),
        None => io::stdout()
            .write_all(&bytes)
            .map_err(|error| format!("cannot write stdout: {error}")),
    }
}
