# Overlay install of a built Nova staging folder over the installed copy.
#
# Why: Inno Setup intermittently fails with "code 5" on libcrypto-3.dll /
# select.pyd while no antivirus is running (the file is briefly held by a
# leftover process). The proven workaround is a plain overlay copy: rename the
# locked destination file, copy again, keep profiles/ and temp/ untouched.
#
# Usage:
#   powershell -ExecutionPolicy Bypass -File tools\install_overlay.ps1 -Version 1.44.2.10
#
param(
    [Parameter(Mandatory = $true)][string]$Version,
    [string]$Source = "",
    [string]$Target = "$env:LOCALAPPDATA\Nova",
    [switch]$NoStart
)

$ErrorActionPreference = "Stop"

if (-not $Source) {
    $Source = Join-Path "C:\Users\User\Documents\build\Inno" "v$Version\Nova"
}
if (-not (Test-Path (Join-Path $Source "Nova.exe"))) {
    throw "Staging not found: $Source"
}
if (-not (Test-Path $Target)) {
    throw "Installed copy not found: $Target"
}

function Stop-NovaGracefully {
    $exe = Join-Path $Target "Nova.exe"
    if (Test-Path $exe) {
        try {
            Start-Process -FilePath $exe -ArgumentList "--quit" -Wait -WindowStyle Hidden
        } catch {
        }
    }
    for ($i = 0; $i -lt 20; $i++) {
        if (-not (Get-Process Nova -ErrorAction SilentlyContinue)) { return }
        Start-Sleep -Seconds 1
    }
    # The graceful path did not finish: do not leave the overlay half-copied.
    Get-Process Nova -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 2
}

function Copy-LockedFile([string]$From, [string]$To) {
    for ($attempt = 0; $attempt -lt 4; $attempt++) {
        try {
            Copy-Item -LiteralPath $From -Destination $To -Force
            return $true
        } catch {
            if (Test-Path -LiteralPath $To) {
                $backup = "$To.locked-$(Get-Date -Format yyyyMMddHHmmss)"
                try { Rename-Item -LiteralPath $To -NewName (Split-Path $backup -Leaf) -Force } catch {
                }
            }
            Start-Sleep -Milliseconds 400
        }
    }
    return $false
}

Write-Host "[overlay] source: $Source"
Write-Host "[overlay] target: $Target"
Stop-NovaGracefully

$lockedNames = @("Nova.exe", "libcrypto-3.dll", "libssl-3.dll", "select.pyd", "_ssl.pyd", "python314.dll")
$xf = $lockedNames | ForEach-Object { "/XF"; $_ }

$robocopyArgs = @($Source, $Target, "/E", "/R:2", "/W:1", "/NFL", "/NDL", "/NJH", "/NJS", "/NP") + $xf
& robocopy @robocopyArgs | Out-Null
$rc = $LASTEXITCODE
if ($rc -ge 8) {
    Write-Host "[overlay] robocopy reported $rc, continuing with per-file retries"
}

$failed = @()
foreach ($name in $lockedNames) {
    $from = Join-Path $Source $name
    if (-not (Test-Path $from)) {
        $from = Join-Path (Join-Path $Source "resources") $name
    }
    if (-not (Test-Path $from)) { continue }
    $relative = $from.Substring($Source.Length).TrimStart("\")
    $to = Join-Path $Target $relative
    $dir = Split-Path $to -Parent
    if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
    if (-not (Copy-LockedFile $from $to)) {
        $failed += $relative
    }
}

if ($failed.Count -gt 0) {
    Write-Host "[overlay] FAILED: $($failed -join ', ')"
    exit 1
}

Write-Host "[overlay] copied OK"
if (-not $NoStart) {
    Start-Process -FilePath (Join-Path $Target "Nova.exe")
    Write-Host "[overlay] Nova started"
}
exit 0
