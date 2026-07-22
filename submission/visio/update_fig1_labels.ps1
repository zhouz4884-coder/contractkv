param(
    [string]$InputVsdx = "",
    [string]$OutputDir = ""
)

$ErrorActionPreference = "Stop"

if (-not $InputVsdx) {
    $InputVsdx = Join-Path $PSScriptRoot "..\..\Paper\figures\fig1_contractkv_visio.vsdx"
}
if (-not $OutputDir) {
    $OutputDir = Join-Path $PSScriptRoot "exports_visual"
}

$inputPath = (Resolve-Path $InputVsdx).Path
$outputPath = [System.IO.Path]::GetFullPath($OutputDir)
[System.IO.Directory]::CreateDirectory($outputPath) | Out-Null

$replacements = @{
    "CALC: cache-aware prefix-maximizing compiler" = "CALC: contract-aware layout compiler"
    "Slack-masked in-situ path verifier" = "In-engine teacher-forced verifier"
}
$counts = @{}
foreach ($key in $replacements.Keys) { $counts[$key] = 0 }

function Update-ShapeText {
    param([object]$Shape)

    try {
        $text = [string]$Shape.Text
        foreach ($old in $replacements.Keys) {
            if ($text -eq $old) {
                $Shape.Text = $replacements[$old]
                $counts[$old]++
            }
        }
    } catch {}

    try {
        for ($i = 1; $i -le $Shape.Shapes.Count; $i++) {
            Update-ShapeText -Shape $Shape.Shapes.Item($i)
        }
    } catch {}
}

$visio = $null
$document = $null
try {
    $visio = New-Object -ComObject Visio.Application
    $visio.Visible = $false
    $document = $visio.Documents.Open($inputPath)
    for ($p = 1; $p -le $document.Pages.Count; $p++) {
        $page = $document.Pages.Item($p)
        for ($i = 1; $i -le $page.Shapes.Count; $i++) {
            Update-ShapeText -Shape $page.Shapes.Item($i)
        }
    }

    foreach ($old in $replacements.Keys) {
        if ($counts[$old] -ne 1) {
            throw "Expected one label '$old', found $($counts[$old])."
        }
    }

    $document.Save()
    $page = $document.Pages.Item(1)
    $page.Export((Join-Path $outputPath "fig1_contractkv_visio.svg"))
    $page.Export((Join-Path $outputPath "fig1_contractkv_visio.png"))
    Write-Output "Updated labels and exported Fig. 1 to $outputPath"
} finally {
    if ($document -ne $null) { $document.Close() }
    if ($visio -ne $null) { $visio.Quit() }
    [System.GC]::Collect()
    [System.GC]::WaitForPendingFinalizers()
}
