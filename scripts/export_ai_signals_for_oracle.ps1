# Copia señales AIS11 a Oracle. No usa git.
# $env:OCI_HOST = "x.x.x.x"; $env:OCI_USER = "ubuntu"
# .\scripts\export_ai_signals_for_oracle.ps1
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$HostName = $env:OCI_HOST
if (-not $HostName) { throw "Setea OCI_HOST" }
$User = if ($env:OCI_USER) { $env:OCI_USER } else { "ubuntu" }
$Port = if ($env:OCI_PORT) { $env:OCI_PORT } else { "22" }
$DestDir = if ($env:OCI_DIR) { $env:OCI_DIR } else { "~/IABacktesterTrading-Nazareno" }

$files = @(
    "timesfm_signals.json",
    "tspulse_signals.json",
    "minirocket_gpu_signals.json"
)
foreach ($f in $files) {
    $src = Join-Path $Root "data\$f"
    if (-not (Test-Path $src)) {
        throw "Falta $src. Corre actualizar_ia_live_us.bat en la PC con GPU."
    }
    $dest = "${User}@${HostName}:${DestDir}/data/$f"
    Write-Host "→ $dest"
    scp -P $Port $src $dest
}
Write-Host "OK. En la VM: sudo systemctl restart backtester"
