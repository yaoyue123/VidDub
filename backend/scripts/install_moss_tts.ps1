# Install MOSS-TTS-Nano (local 0.1B ONNX TTS) for VidDub.
#
# Usage:
#   powershell -ExecutionPolicy Bypass -File backend\scripts\install_moss_tts.ps1
#   powershell -ExecutionPolicy Bypass -File backend\scripts\install_moss_tts.ps1 -Proxy http://127.0.0.1:7890
#   powershell -ExecutionPolicy Bypass -File backend\scripts\install_moss_tts.ps1 -DownloadModels
#
# The model uses its own venv because upstream pins torch/torchaudio 2.7.0,
# which must not replace the backend's torch build.

param(
    [string]$RepoDir = "",
    [string]$Proxy = "",
    [switch]$DownloadModels
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$BackendDir = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
if (-not $RepoDir) {
    $RepoDir = Join-Path $BackendDir "data\models\MOSS-TTS-Nano"
}
$RepoDir = [System.IO.Path]::GetFullPath($RepoDir)

Write-Host "[*] MOSS-TTS-Nano -> $RepoDir"

if ($Proxy) {
    $env:HTTPS_PROXY = $Proxy
    $env:HTTP_PROXY = $Proxy
    Write-Host "[*] using proxy $Proxy"
}
$env:HF_HUB_DISABLE_TELEMETRY = "1"

if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    throw "git is required"
}
if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    throw "python is required (3.10+)"
}

if (-not (Test-Path (Join-Path $RepoDir "infer_onnx.py"))) {
    Write-Host "[*] cloning OpenMOSS/MOSS-TTS-Nano ..."
    git clone --depth 1 https://github.com/OpenMOSS/MOSS-TTS-Nano.git $RepoDir
    if ($LASTEXITCODE -ne 0) { throw "git clone failed" }
} else {
    Write-Host "[OK] source already present"
}

$VenvDir = Join-Path $RepoDir ".venv"
$Python = Join-Path $VenvDir "Scripts\python.exe"
if (-not (Test-Path $Python)) {
    Write-Host "[*] creating isolated venv (Python 3.11) ..."
    python -m venv $VenvDir
    if ($LASTEXITCODE -ne 0) { throw "venv creation failed" }
}

Write-Host "[*] installing MOSS runtime dependencies (torch 2.7 CPU) ..."
& $Python -m pip install --upgrade pip --quiet
& $Python -m pip install --quiet `
    "torch==2.7.0" "torchaudio==2.7.0" `
    onnxruntime sentencepiece soundfile huggingface_hub
if ($LASTEXITCODE -ne 0) { throw "dependency installation failed" }

$env:MOSS_TTS_REPO = $RepoDir
$env:MOSS_TTS_PYTHON = $Python

if ($DownloadModels) {
    Write-Host "[*] downloading ONNX models and running a smoke synthesis ..."
    Push-Location $RepoDir
    try {
        & $Python infer_onnx.py --disable-wetext-processing --voice Junhao `
            --text "MOSS 语音合成安装完成。" `
            --output-audio-path (Join-Path $env:TEMP "viddub_moss_install_check.wav")
        if ($LASTEXITCODE -ne 0) { throw "smoke synthesis failed" }
        Write-Host "[OK] models downloaded: $env:TEMP\viddub_moss_install_check.wav"
    } finally {
        Pop-Location
    }
} else {
    Write-Host "[i] Models download automatically on first synthesis."
    Write-Host "    Re-run with -DownloadModels to pre-download them now."
}

Write-Host ""
Write-Host "Done. Configure VidDub:"
Write-Host "  配音后端 (tts_backend)      = moss"
Write-Host "  MOSS 源码目录               = $RepoDir"
Write-Host "  MOSS Python 解释器          = $Python"
Write-Host "  MOSS 音色                   = Junhao"
