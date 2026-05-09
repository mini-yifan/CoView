$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$RootDir = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $RootDir

$AppName = "CoView"
$SpecFile = Join-Path $RootDir "packaging\windows\CoView.spec"
$InstallerScript = Join-Path $RootDir "packaging\windows\CoView.iss"
$VenvDir = if ($env:VENV_DIR) { $env:VENV_DIR } else { Join-Path $RootDir ".venv" }
$PythonBin = if ($env:PYTHON_BIN) { $env:PYTHON_BIN } else { "python" }
$SkipInstall = if ($env:SKIP_INSTALL) { $env:SKIP_INSTALL } else { "0" }
$SkipModelDownload = if ($env:SKIP_MODEL_DOWNLOAD) { $env:SKIP_MODEL_DOWNLOAD } else { "0" }
$CreateInstaller = if ($env:CREATE_INSTALLER) { $env:CREATE_INSTALLER } else { "1" }
$CleanBuild = if ($env:CLEAN_BUILD) { $env:CLEAN_BUILD } else { "1" }
$BuildDir = Join-Path $RootDir "build"
$DistDir = Join-Path $RootDir "dist"

function Write-Log {
    param([string]$Message)
    Write-Host "==> $Message" -ForegroundColor Blue
}

function Fail {
    param([string]$Message)
    Write-Host "error: $Message" -ForegroundColor Red
    exit 1
}

function Require-Windows {
    if ($env:OS -ne "Windows_NT") {
        Fail "Windows packages must be built on Windows."
    }
}

function Get-AppVersion {
    & $script:PythonExe -c "from baodou_ai import __version__; print(__version__)"
}

function Find-InnoSetupCompiler {
    if ($env:INNO_SETUP_COMPILER -and (Test-Path $env:INNO_SETUP_COMPILER)) {
        return $env:INNO_SETUP_COMPILER
    }

    $Candidates = @(
        "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
        "$env:ProgramFiles\Inno Setup 6\ISCC.exe",
        "${env:ProgramFiles(x86)}\Inno Setup 5\ISCC.exe",
        "$env:ProgramFiles\Inno Setup 5\ISCC.exe"
    )

    foreach ($Candidate in $Candidates) {
        if ($Candidate -and (Test-Path $Candidate)) {
            return $Candidate
        }
    }

    $Command = Get-Command "iscc.exe" -ErrorAction SilentlyContinue
    if ($Command) {
        return $Command.Source
    }

    return $null
}

Require-Windows

if (-not (Test-Path $VenvDir)) {
    Write-Log "Creating virtual environment at $VenvDir"
    & $PythonBin -m venv $VenvDir
}

$script:PythonExe = Join-Path $VenvDir "Scripts\python.exe"
$PyInstallerExe = Join-Path $VenvDir "Scripts\pyinstaller.exe"

if (-not (Test-Path $script:PythonExe)) {
    Fail "Python executable was not found in the virtual environment: $script:PythonExe"
}

Write-Log "Using Python: $(& $script:PythonExe --version)"

if ($SkipInstall -ne "1") {
    Write-Log "Installing build dependencies"
    & $script:PythonExe -m pip install --upgrade pip
    & $script:PythonExe -m pip install -e ".[build,voice,tts]"
} else {
    Write-Log "Skipping dependency install because SKIP_INSTALL=1"
}

if ($SkipModelDownload -ne "1") {
    Write-Log "Ensuring bundled wake word model exists"
    & $script:PythonExe scripts\download_wake_word_model.py
} else {
    Write-Log "Skipping wake word model download because SKIP_MODEL_DOWNLOAD=1"
}

$AppVersion = Get-AppVersion
$env:COVIEW_VERSION = $AppVersion
Write-Log "Building $AppName $AppVersion with PyInstaller"

$PyInstallerArgs = @(
    $SpecFile,
    "--noconfirm",
    "--distpath", $DistDir,
    "--workpath", $BuildDir
)
if ($CleanBuild -eq "1") {
    $PyInstallerArgs += "--clean"
}

& $PyInstallerExe @PyInstallerArgs

$AppDir = Join-Path $DistDir $AppName
$ExePath = Join-Path $AppDir "$AppName.exe"
if (-not (Test-Path $ExePath)) {
    Fail "Expected executable was not created: $ExePath"
}

$ZipPath = Join-Path $DistDir "$AppName-$AppVersion-Windows.zip"
Write-Log "Creating ZIP: $ZipPath"
if (Test-Path $ZipPath) {
    Remove-Item $ZipPath -Force
}
Compress-Archive -Path $AppDir -DestinationPath $ZipPath -Force
Write-Log "Done: $ZipPath"

if ($CreateInstaller -eq "1") {
    $IsccExe = Find-InnoSetupCompiler
    if ($IsccExe) {
        Write-Log "Creating installer with Inno Setup"
        & $IsccExe `
            "/DAppVersion=$AppVersion" `
            "/DProjectRoot=$RootDir" `
            "/DSourceDir=$AppDir" `
            "/DOutputDir=$DistDir" `
            $InstallerScript
        $InstallerPath = Join-Path $DistDir "$AppName-$AppVersion-Windows-Setup.exe"
        if (Test-Path $InstallerPath) {
            Write-Log "Done: $InstallerPath"
        } else {
            Fail "Inno Setup finished, but the installer was not found: $InstallerPath"
        }
    } else {
        Write-Log "Inno Setup was not found; ZIP package is ready. Install Inno Setup 6 to also create a setup.exe installer."
    }
} else {
    Write-Log "Skipping installer creation because CREATE_INSTALLER=0"
}
