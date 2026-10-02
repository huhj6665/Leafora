[CmdletBinding()]
param()

. (Join-Path $PSScriptRoot 'Common.ps1')
$webRoot = Get-WebRoot
$backendEnv = Join-Path $webRoot 'backend\.env'
$mockEnv = Join-Path $webRoot 'scripts\mock_jetson\.env'
$python = Join-Path $webRoot 'backend\.venv\Scripts\python.exe'
$seedScript = Join-Path $webRoot 'backend\scripts\seed_dev_device.py'
$canonicalId = 'TLD_JETSON_001'

function Set-DotEnvValue {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][string]$Value
    )
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { throw "环境文件不存在：$Path" }
    $lines = @(Get-Content -LiteralPath $Path -Encoding UTF8)
    $found = $false
    $updated = foreach ($line in $lines) {
        if ($line -match "^\s*$([regex]::Escape($Name))=") {
            $found = $true
            "$Name=$Value"
        } else {
            $line
        }
    }
    if (-not $found) { $updated += "$Name=$Value" }
    $temporary = "$Path.tmp"
    $updated | Set-Content -LiteralPath $temporary -Encoding UTF8
    Move-Item -LiteralPath $temporary -Destination $Path -Force
}

Set-DotEnvValue -Path $backendEnv -Name 'DEV_SIM_DEVICE_ID' -Value $canonicalId
Set-DotEnvValue -Path $mockEnv -Name 'MOCK_DEVICE_ID' -Value $canonicalId

Push-Location (Join-Path $webRoot 'backend')
try {
    & $python $seedScript --sync-mock-env
    if ($LASTEXITCODE -ne 0) { throw '规范虚拟设备登记失败。' }
} finally {
    Pop-Location
}

Write-Output "虚拟设备默认编号已迁移为 $canonicalId。"
Write-Output '历史设备 TLD_SIM_001 及其数据库数据未删除、未覆盖。'
Write-Output '新的设备凭据已安全同步到 scripts/mock_jetson/.env，内容未输出。'
