[CmdletBinding(SupportsShouldProcess = $true, ConfirmImpact = 'Medium')]
param()

. (Join-Path $PSScriptRoot 'Common.ps1')
Initialize-LocalDirectories
$webRoot = Get-WebRoot
$runRoot = Join-Path $webRoot 'local\run'
$allowedNames = @('mosquitto', 'fastapi', 'mqtt-consumer', 'frontend', 'model-service')

foreach ($name in $allowedNames) {
    $recordPath = Join-Path $runRoot "$name.json"
    if (-not (Test-Path -LiteralPath $recordPath -PathType Leaf)) { continue }
    try {
        $record = Get-Content -LiteralPath $recordPath -Raw -Encoding UTF8 | ConvertFrom-Json
        $processId = [int]$record.pid
        $process = Get-CimInstance Win32_Process -Filter "ProcessId=$processId" -ErrorAction SilentlyContinue
        if (-not $process) {
            Remove-Item -LiteralPath $recordPath -Force
            continue
        }

        $recordStartedAt = ([DateTime]$record.started_at).ToUniversalTime()
        $processStartedAt = ([DateTime]$process.CreationDate).ToUniversalTime()
        $startDifference = [Math]::Abs(($processStartedAt - $recordStartedAt).TotalSeconds)
        $safeName = ([string]$record.name) -eq $name
        $safeStart = $startDifference -lt 120
        if (-not $safeName -or -not $safeStart) {
            Write-Warning "跳过 PID $processId：运行记录无法安全验证。"
            continue
        }

        if ($PSCmdlet.ShouldProcess("$name (PID $processId)", '停止 Leafora 管理的进程树')) {
            & taskkill.exe /PID $processId /T /F 2>$null | Out-Null
            Remove-Item -LiteralPath $recordPath -Force
            Write-Output "已停止 $name（PID $processId）。"
        }
    } catch {
        Write-Warning "无法处理 $recordPath：$($_.Exception.Message)"
    }
}
