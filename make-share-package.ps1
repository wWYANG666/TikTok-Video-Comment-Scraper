$ErrorActionPreference = 'Stop'
$projectPath = $PSScriptRoot
$stagingPath = Join-Path $env:TEMP ([IO.Path]::GetRandomFileName())
$packageRoot = Join-Path $stagingPath 'TikTok-Collector'
$archivePath = Join-Path $projectPath 'TikTok-Collector-share.zip'

try {
    New-Item -ItemType Directory -Path $packageRoot | Out-Null
    foreach ($name in @('README.md', 'requirements.txt', 'setup.bat', 'setup.ps1', 'start.bat')) {
        Copy-Item -LiteralPath (Join-Path $projectPath $name) -Destination $packageRoot
    }
    foreach ($directoryName in @('app', 'tests')) {
        $sourceRoot = Join-Path $projectPath $directoryName
        Get-ChildItem -LiteralPath $sourceRoot -Recurse -File | Where-Object {
            $_.Extension -in @('.py', '.html', '.css', '.js')
        } | ForEach-Object {
            $relativePath = $_.FullName.Substring($projectPath.Length + 1)
            $targetPath = Join-Path $packageRoot $relativePath
            $targetDirectory = Split-Path -Parent $targetPath
            New-Item -ItemType Directory -Path $targetDirectory -Force | Out-Null
            Copy-Item -LiteralPath $_.FullName -Destination $targetPath
        }
    }
    Compress-Archive -LiteralPath $packageRoot -DestinationPath $archivePath -Force
    Write-Host "Share package ready: $archivePath"
} catch {
    Write-Host "Package creation failed: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
} finally {
    if (Test-Path -LiteralPath $stagingPath) {
        Remove-Item -LiteralPath $stagingPath -Recurse -Force
    }
}
