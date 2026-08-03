<#
Serve the handbook site locally.

  .\scripts\serve.ps1            quarto preview: live-reload dev server, rebuilds on save
  .\scripts\serve.ps1 -Static    clean render, then serve _site/ statically -
                                 tests the exact artifact GitHub Pages would host
  -Port <n>                      override port (default: 4200 preview, 8000 static)

Note: both modes clear Quarto's .quarto/ project cache first. A stale cache (or a
stale Google Drive read, if the repo lives in a synced folder) can silently render
old page content - a clean cache makes builds trustworthy.
#>
param(
    [switch]$Static,
    [int]$Port = 0
)

$root = Split-Path -Parent $PSScriptRoot

if (Test-Path (Join-Path $root '.quarto')) {
    Remove-Item (Join-Path $root '.quarto') -Recurse -Force -Confirm:$false
}

if ($Static) {
    if ($Port -eq 0) { $Port = 8000 }
    if (Test-Path (Join-Path $root '_site')) {
        Remove-Item (Join-Path $root '_site') -Recurse -Force -Confirm:$false
    }
    quarto render $root
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    Write-Host "Serving rendered site at http://localhost:$Port/  (Ctrl+C to stop)"
    $site = Join-Path $root '_site'
    if (Get-Command uv -ErrorAction SilentlyContinue) { uv run python -m http.server $Port --directory $site }
    else { python -m http.server $Port --directory $site }
}
else {
    if ($Port -eq 0) { $Port = 4200 }
    quarto preview $root --port $Port --no-browser
}
