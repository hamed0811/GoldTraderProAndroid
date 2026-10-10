# GoldTrader Pro automatic setup, checks and launch console
# Compatible with Windows PowerShell 5.1; does not place trades or fabricate data.
$ErrorActionPreference = 'Stop'
$ProjectRoot = $PSScriptRoot
Set-Location -LiteralPath $ProjectRoot
$ExitCode = 0
$LogPath = $null
$TranscriptStarted = $false
$Stamp = Get-Date -Format 'yyyyMMdd_HHmmss'

function Write-Step {
    param([string]$Message)
    Write-Host ''
    Write-Host ('=' * 68) -ForegroundColor DarkCyan
    Write-Host ('  ' + $Message) -ForegroundColor Cyan
    Write-Host ('=' * 68) -ForegroundColor DarkCyan
}

function Invoke-Checked {
    param(
        [Parameter(Mandatory = $true)][string]$Executable,
        [Parameter(Mandatory = $true)][string[]]$Arguments,
        [Parameter(Mandatory = $true)][string]$Description
    )
    Write-Host ('> ' + $Description) -ForegroundColor Gray
    & $Executable @Arguments
    $NativeExitCode = $LASTEXITCODE
    if ($NativeExitCode -ne 0) {
        throw ($Description + ' failed with exit code ' + $NativeExitCode + '.')
    }
}

function New-Python311Environment {
    param([Parameter(Mandatory = $true)][string]$VenvPath)

    $Launcher = Get-Command 'py.exe' -ErrorAction SilentlyContinue
    if ($Launcher) {
        $VersionText = (& $Launcher.Source -3.11 --version 2>&1 | Out-String).Trim()
        if ($LASTEXITCODE -eq 0 -and $VersionText -match '^Python 3\.11(\.|$)') {
            Write-Host ('Creating virtual environment with ' + $VersionText) -ForegroundColor Gray
            & $Launcher.Source -3.11 -m venv $VenvPath
            if ($LASTEXITCODE -ne 0) { throw 'Python Launcher could not create the virtual environment.' }
            return
        }
    }

    $PythonCommand = Get-Command 'python.exe' -ErrorAction SilentlyContinue
    if ($PythonCommand) {
        $VersionText = (& $PythonCommand.Source --version 2>&1 | Out-String).Trim()
        if ($LASTEXITCODE -eq 0 -and $VersionText -match '^Python 3\.11(\.|$)') {
            Write-Host ('Creating virtual environment with ' + $VersionText) -ForegroundColor Gray
            & $PythonCommand.Source -m venv $VenvPath
            if ($LASTEXITCODE -ne 0) { throw 'Python could not create the virtual environment.' }
            return
        }
    }

    throw 'Python 3.11 x64 was not found. Install Python 3.11 x64 with the Python Launcher, then run this console again.'
}

try {
    try {
        $LogDirectory = Join-Path $ProjectRoot 'logs'
        New-Item -ItemType Directory -Path $LogDirectory -Force | Out-Null
        $LogPath = Join-Path $LogDirectory ('auto-console_' + $Stamp + '.log')
        Start-Transcript -Path $LogPath -Force | Out-Null
        $TranscriptStarted = $true
    }
    catch {
        $LogDirectory = Join-Path $env:LOCALAPPDATA 'GoldTraderPro\logs'
        New-Item -ItemType Directory -Path $LogDirectory -Force | Out-Null
        $LogPath = Join-Path $LogDirectory ('auto-console_' + $Stamp + '.log')
        Start-Transcript -Path $LogPath -Force | Out-Null
        $TranscriptStarted = $true
        Write-Warning ('Project folder is not writable. Logs are saved to ' + $LogDirectory)
    }

    Write-Host 'GoldTrader Pro | Automatic Setup, Test & Launch' -ForegroundColor Yellow
    Write-Host ('Project folder: ' + $ProjectRoot)
    if ($LogPath) { Write-Host ('Log file:       ' + $LogPath) }
    Write-Host 'Signal-only application. No automatic orders are sent.' -ForegroundColor Gray

    $MainPy = Join-Path $ProjectRoot 'main.py'
    $Requirements = Join-Path $ProjectRoot 'requirements.txt'
    $PackagedExe = Join-Path $ProjectRoot 'GoldTraderPro.exe'

    # The downloadable one-folder build needs no Python installation on the user's PC.
    if (-not (Test-Path -LiteralPath $MainPy) -and (Test-Path -LiteralPath $PackagedExe)) {
        Write-Step 'Launching the packaged Windows application'
        $Process = Start-Process -FilePath $PackagedExe -WorkingDirectory $ProjectRoot -Wait -PassThru
        if ($Process.ExitCode -ne 0) {
            throw ('GoldTraderPro.exe exited with code ' + $Process.ExitCode + '.')
        }
        Write-Host 'The application was closed normally.' -ForegroundColor Green
    }
    else {
        if (-not (Test-Path -LiteralPath $MainPy)) {
            throw 'main.py was not found. Place this console in the GoldTraderProDesktop source folder or beside GoldTraderPro.exe.'
        }
        if (-not (Test-Path -LiteralPath $Requirements)) {
            throw 'requirements.txt was not found in the source folder.'
        }

        Write-Step '1/5 - Checking Python 3.11 and the project environment'
        $VenvDirectory = Join-Path $ProjectRoot '.venv'
        $VenvPython = Join-Path $VenvDirectory 'Scripts\python.exe'

        if (Test-Path -LiteralPath $VenvPython) {
            $ExistingVersion = (& $VenvPython --version 2>&1 | Out-String).Trim()
            if ($LASTEXITCODE -ne 0 -or $ExistingVersion -notmatch '^Python 3\.11(\.|$)') {
                $BackupName = '.venv_backup_' + $Stamp
                Write-Warning ('Preserving the existing incompatible environment as ' + $BackupName)
                Rename-Item -LiteralPath $VenvDirectory -NewName $BackupName
            }
        }
        if (-not (Test-Path -LiteralPath $VenvPython)) {
            New-Python311Environment -VenvPath $VenvDirectory
        }
        if (-not (Test-Path -LiteralPath $VenvPython)) {
            throw 'Virtual environment creation did not produce its Python executable.'
        }
        $ConfirmedVersion = (& $VenvPython --version 2>&1 | Out-String).Trim()
        if ($LASTEXITCODE -ne 0 -or $ConfirmedVersion -notmatch '^Python 3\.11(\.|$)') {
            throw ('The environment must use Python 3.11. Found: ' + $ConfirmedVersion)
        }
        Write-Host ('Using ' + $ConfirmedVersion) -ForegroundColor Green

        Write-Step '2/5 - Updating pip'
        & $VenvPython -m pip install --upgrade pip
        if ($LASTEXITCODE -ne 0) {
            Write-Warning 'pip upgrade failed; continuing with the currently installed pip.'
        }

        Write-Step '3/5 - Installing or checking dependencies'
        Write-Host 'Trying the configured package mirror first...' -ForegroundColor Gray
        & $VenvPython -m pip install --disable-pip-version-check -i 'https://pypi.tuna.tsinghua.edu.cn/simple' -r $Requirements
        if ($LASTEXITCODE -ne 0) {
            Write-Warning 'Package mirror failed; retrying with official PyPI.'
            & $VenvPython -m pip install --disable-pip-version-check -r $Requirements
            if ($LASTEXITCODE -ne 0) {
                throw 'Dependency installation failed on both package indexes. Check internet access and the log.'
            }
        }

        Write-Step '4/5 - Validating Python syntax'
        $CompileTargets = @('main.py', 'run_agent.py', 'export_report.py', 'show_stats.py', 'build_gui.py', 'build_headless.py', 'core', 'ui', 'tests') |
            Where-Object { Test-Path -LiteralPath (Join-Path $ProjectRoot $_) }
        $CompileArguments = @('-m', 'compileall', '-q') + @($CompileTargets)
        Invoke-Checked -Executable $VenvPython -Arguments $CompileArguments -Description 'Python syntax validation'
        Write-Host 'Syntax validation passed.' -ForegroundColor Green

        Write-Step '5/5 - Running automated tests'
        Invoke-Checked -Executable $VenvPython -Arguments @('-m', 'pytest', '-q') -Description 'Automated tests'
        Write-Host 'Automated tests passed.' -ForegroundColor Green

        Write-Step 'Starting GoldTrader Pro'
        Write-Host 'Close the app window to finish this console session.' -ForegroundColor Gray
        & $VenvPython $MainPy
        $AppExitCode = $LASTEXITCODE
        if ($AppExitCode -ne 0) {
            throw ('The application exited with code ' + $AppExitCode + '.')
        }
        Write-Host 'The application was closed normally.' -ForegroundColor Green
    }
}
catch {
    $ExitCode = 1
    Write-Host ''
    Write-Host 'AUTOMATIC CONSOLE STOPPED' -ForegroundColor Red
    Write-Host $_.Exception.Message -ForegroundColor Red
    if ($LogPath) { Write-Host ('Review the log: ' + $LogPath) -ForegroundColor Yellow }
}
finally {
    if ($TranscriptStarted) {
        try { Stop-Transcript | Out-Null } catch { }
    }
}
if ($ExitCode -ne 0) { exit $ExitCode }
exit 0
