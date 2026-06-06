$ErrorActionPreference = "Stop"
$here = $PSScriptRoot

function Find-Netconvert {
    if ($env:SUMO_HOME) {
        $p = Join-Path $env:SUMO_HOME "bin\netconvert.exe"
        if (Test-Path $p) { return $p }
    }
    $cmd = Get-Command netconvert.exe -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    $roots = @(
        "C:\Program Files\Eclipse Sumo",
        "C:\Program Files (x86)\Eclipse Sumo",
        "$env:LOCALAPPDATA\Programs\Eclipse Sumo"
    )
    foreach ($r in $roots) {
        $p = Join-Path $r "bin\netconvert.exe"
        if (Test-Path $p) { return $p }
    }
    return $null
}

$nc = Find-Netconvert
if (-not $nc) {
    Write-Error "No se encontro netconvert.exe. Instale SUMO y/o defina SUMO_HOME."
}

$outNet = Join-Path $here "intersection.net.xml"
& $nc --node-files (Join-Path $here "nodes.nod.xml") `
      --edge-files (Join-Path $here "edges.edg.xml") `
      -o $outNet

Write-Host "OK: red generada en $outNet"
