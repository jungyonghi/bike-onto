$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$PythonBin = if ($env:PYTHON) { $env:PYTHON } else { "python" }
& $PythonBin "$ScriptDir/tools/scripts/rag/general_rag_cli.py" @args
exit $LASTEXITCODE
