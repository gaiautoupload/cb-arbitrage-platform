param(
    [string]$PythonExe = "C:\Users\pioterlee\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$Requirements = Join-Path $RepoRoot "requirements-project.txt"

if (-not (Test-Path $PythonExe)) {
    $PythonExe = "python"
}

if (-not (Test-Path $Requirements)) {
    throw "Missing requirements file: $Requirements"
}

& $PythonExe -m pip install -r $Requirements
