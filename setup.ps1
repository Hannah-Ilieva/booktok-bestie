[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $projectRoot

$pythonLauncher = Get-Command py -ErrorAction SilentlyContinue
if ($pythonLauncher) {
    $pythonCommand = $pythonLauncher.Source
    $pythonArguments = @("-3")
} else {
    $pythonCommandInfo = Get-Command python -ErrorAction SilentlyContinue
    if (-not $pythonCommandInfo) {
        throw "Python 3.10 or newer is required. Install Python from https://www.python.org/downloads/windows/ and run this command again."
    }
    $pythonCommand = $pythonCommandInfo.Source
    $pythonArguments = @()
}

& $pythonCommand @pythonArguments -c "import sys; raise SystemExit('Python 3.10 or newer is required.' if sys.version_info < (3, 10) else 0)"
if ($LASTEXITCODE -ne 0) {
    throw "Install Python 3.10 or newer, then rerun setup.ps1."
}

$venvPath = Join-Path $projectRoot ".venv"
$venvPython = Join-Path $venvPath "Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    & $pythonCommand @pythonArguments -m venv $venvPath
    if ($LASTEXITCODE -ne 0) {
        throw "Could not create the project's .venv environment."
    }
}

& $venvPython -m pip install -r (Join-Path $projectRoot "requirements.txt")
if ($LASTEXITCODE -ne 0) {
    throw "Dependency installation failed. Check the Python and package-index output above, then rerun setup.ps1."
}

$envPath = Join-Path $projectRoot ".env"
if (-not (Test-Path $envPath)) {
    $randomBytes = New-Object byte[] 32
    $randomGenerator = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    $randomGenerator.GetBytes($randomBytes)
    $randomGenerator.Dispose()
    $dbPassword = [System.BitConverter]::ToString($randomBytes).Replace("-", "").ToLowerInvariant()
    $envLines = @(
        "POSTGRES_USER=booktok",
        "POSTGRES_DB=booktok",
        "POSTGRES_PASSWORD=$dbPassword",
        "POSTGRES_PORT=5432",
        "DATABASE_URL=postgresql://booktok:$dbPassword@127.0.0.1:5432/booktok"
    )
    Set-Content -LiteralPath $envPath -Value $envLines -Encoding ascii
    Write-Host "Created an ignored .env file with a local database password. Its contents were not displayed."
}

Write-Host "BookTok Bestie dependencies are installed."
Write-Host "Start the app with: .\.venv\Scripts\python.exe -m streamlit run app.py"
Write-Host "PostgreSQL is optional for this setup and is not started by this script."
