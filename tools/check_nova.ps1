$ErrorActionPreference = "Continue"
$pacPath = Join-Path $env:TEMP "nova-check.pac"
curl.exe -s "http://127.0.0.1:1369/nova.pac" -o $pacPath
if (-not (Test-Path $pacPath) -or (Get-Item $pacPath).Length -eq 0) {
    Write-Host "PAC: FAIL (empty or unreachable)"
    exit 1
}
$pac = Get-Content -Raw -LiteralPath $pacPath
Write-Host ("PAC bytes: {0}" -f $pac.Length)
Write-Host ("FindProxyForURL: {0}" -f [bool]($pac -match "function FindProxyForURL"))
$localRule = ($pac -match 'function isLocalDirect') -and ($pac -match '"\.su"') -and ($pac -match 'xn--p1ai')
Write-Host ("local direct rule: {0}" -f $(if ($localRule) { "OK" } else { "MISSING" }))
Write-Host "Main function tail:"
($pac -split "`n" | Select-String 'return "' | Select-Object -Last 6).Line | ForEach-Object { "  " + $_.Trim() }

function Test-Port([int]$Port) {
    $client = New-Object System.Net.Sockets.TcpClient
    try {
        $client.Connect("127.0.0.1", $Port)
        return $true
    } catch {
        return $false
    } finally {
        $client.Dispose()
    }
}

foreach ($port in @(1369, 1370, 1371, 1372, 1374)) {
    Write-Host ("port {0}: {1}" -f $port, $(if (Test-Port $port) { "open" } else { "closed" }))
}

$env:HTTP_PROXY = ""
$env:HTTPS_PROXY = ""
$socks = curl.exe -s -o NUL -w "%{http_code}" --max-time 12 --socks5-hostname 127.0.0.1:1370 https://www.gstatic.com/generate_204
$http = curl.exe -s -o NUL -w "%{http_code}" --max-time 12 --proxy http://127.0.0.1:1371 https://www.gstatic.com/generate_204
$ru = curl.exe -s -o NUL -w "%{http_code}" --max-time 12 --noproxy "*" https://ya.ru
$foreign = curl.exe -s -o NUL -w "%{http_code}" --max-time 12 --noproxy "*" https://www.google.com/generate_204
Write-Host ("1370 gstatic: {0}" -f $socks)
Write-Host ("1371 gstatic: {0}" -f $http)
Write-Host ("direct ya.ru: {0}" -f $ru)
Write-Host ("direct google: {0}" -f $foreign)
