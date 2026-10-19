param([switch]$Diff)

$repo = Split-Path -Parent $PSScriptRoot
$paths = @(
    "resources/nova_list_sync.py",
    "resources/nova_proton.py",
    "resources/nova_subscriptions.py",
    "resources/nova_issuance.py",
    "resources/nova_profiles.py",
    "resources/nova_vless.py",
    "list_publish.py",
    "profiles/"
)

git -C $repo fetch upstream
if ($LASTEXITCODE -ne 0) {
    Write-Host "git fetch upstream failed"
    exit $LASTEXITCODE
}

Write-Host "Upstream profile-update changes:"
git -C $repo log --oneline personal..upstream/main -- $paths
git -C $repo diff --stat personal...upstream/main -- $paths

if ($Diff) {
    git -C $repo --no-pager diff personal...upstream/main -- $paths
}
