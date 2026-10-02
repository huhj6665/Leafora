[CmdletBinding()]
param(
    [ValidateRange(1, 65535)][int]$ApiPort = 8000,
    [ValidateRange(1, 65535)][int]$MqttPort = 1883,
    [ValidateRange(1, 65535)][int]$PostgresPort = 5432
)

. (Join-Path $PSScriptRoot 'Common.ps1')
$webRoot = Get-WebRoot
$backendRoot = Join-Path $webRoot 'backend'
$python = Join-Path $backendRoot '.venv\Scripts\python.exe'
$script:diagnosticResults = [System.Collections.ArrayList]::new()

function Add-Result {
    param([string]$Check, [string]$Status, [string]$Detail)
    [void]$script:diagnosticResults.Add(
        [pscustomobject]@{ Check = $Check; Status = $Status; Detail = $Detail }
    )
}

function Invoke-NativeCapture {
    param(
        [Parameter(Mandatory = $true)][string]$FilePath,
        [string[]]$ArgumentList = @()
    )

    # Windows PowerShell 5.1 turns redirected native stderr into ErrorRecord
    # objects.  Alembic writes normal INFO messages to stderr, so temporarily
    # avoid promoting those messages to terminating errors and retain the real
    # native exit code for the caller.
    $previousErrorActionPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = 'Continue'
        $outputLines = @(& $FilePath @ArgumentList 2>&1)
        $exitCode = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previousErrorActionPreference
    }

    return [pscustomobject]@{
        Output = (($outputLines | ForEach-Object { $_.ToString() }) | Out-String).Trim()
        ExitCode = $exitCode
    }
}

function Test-FirewallPort {
    param([int]$Port)
    $matchingRules = [System.Collections.ArrayList]::new()
    $filters = @(Get-NetFirewallPortFilter -PolicyStore ActiveStore -ErrorAction SilentlyContinue |
        Where-Object {
            $_.Protocol -eq 'TCP' -and
            [string]$_.LocalPort -eq [string]$Port
        })
    foreach ($filter in $filters) {
        $rules = @(Get-NetFirewallRule -AssociatedNetFirewallPortFilter $filter -ErrorAction SilentlyContinue |
            Where-Object {
                $_.Enabled -eq 'True' -and $_.Direction -eq 'Inbound' -and
                $_.Action -eq 'Allow' -and $_.Profile -match 'Private|Any'
            })
        foreach ($rule in $rules) {
            [void]$matchingRules.Add([string]$rule.DisplayName)
        }
    }
    return @($matchingRules.ToArray() | Select-Object -Unique)
}

$portChecks = @(
    [pscustomobject]@{ Name = 'PostgreSQL'; Port = $PostgresPort }
    [pscustomobject]@{ Name = 'FastAPI'; Port = $ApiPort }
    [pscustomobject]@{ Name = 'MQTT'; Port = $MqttPort }
)
foreach ($portInfo in $portChecks) {
    $state = Get-ListenerState -Port $portInfo.Port
    $addresses = if ($state.Addresses.Count) { $state.Addresses -join ', ' } else { 'none' }
    if ($portInfo.Name -eq 'PostgreSQL') {
        $status = switch ($state.State) {
            'LAN_LISTENING' { 'WARN' }
            'LOOPBACK_ONLY' { 'OK' }
            default { 'FAIL' }
        }
    } else {
        $status = switch ($state.State) {
            'LAN_LISTENING' { 'OK' }
            'LOOPBACK_ONLY' { 'WARN' }
            default { 'FAIL' }
        }
    }
    Add-Result -Check "$($portInfo.Name) listener" -Status $status -Detail "$($state.State); addresses=$addresses"
}

if (Test-Path -LiteralPath $python -PathType Leaf) {
    Push-Location $backendRoot
    try {
        $migrationProbe = Invoke-NativeCapture -FilePath $python -ArgumentList @('-m', 'alembic', 'current')
        $migrationOutput = $migrationProbe.Output
        if ($migrationProbe.ExitCode -eq 0) {
            $revision = (($migrationOutput -split "`r?`n") | Select-Object -Last 1).Trim()
            Add-Result -Check 'PostgreSQL connection' -Status 'OK' -Detail "Alembic current: $revision"
        } else {
            Add-Result -Check 'PostgreSQL connection' -Status 'FAIL' -Detail '数据库端口存在，但应用认证或连接失败。'
        }
    } finally {
        Pop-Location
    }
} else {
    Add-Result -Check 'PostgreSQL connection' -Status 'FAIL' -Detail '后端 Python 虚拟环境不存在。'
}

try {
    $health = Invoke-RestMethod -Uri "http://127.0.0.1:$ApiPort/api/health" -Method Get -TimeoutSec 5
    if ($health.code -eq 0 -and $health.data.database -eq 'ok') {
        Add-Result -Check 'FastAPI /api/health' -Status 'OK' -Detail 'HTTP 与数据库健康检查正常。'
    } else {
        Add-Result -Check 'FastAPI /api/health' -Status 'FAIL' -Detail 'HTTP 可达，但健康响应异常。'
    }
} catch {
    Add-Result -Check 'FastAPI /api/health' -Status 'FAIL' -Detail 'HTTP 健康检查不可达。'
}

if (Test-Path -LiteralPath $python -PathType Leaf) {
    Push-Location $backendRoot
    try {
        $mqttProbeResult = Invoke-NativeCapture -FilePath $python `
            -ArgumentList @('-m', 'scripts.mqtt_probe', '--host', '127.0.0.1', '--port', [string]$MqttPort)
        $mqttProbe = $mqttProbeResult.Output
        $mqttProbeCode = $mqttProbeResult.ExitCode
        if ($mqttProbeCode -eq 0) {
            Add-Result -Check 'MQTT authentication' -Status 'OK' -Detail 'MQTT_AUTH_OK'
        } elseif ($mqttProbeCode -eq 3) {
            Add-Result -Check 'MQTT authentication' -Status 'FAIL' -Detail 'MQTT_AUTH_FAILED'
        } else {
            Add-Result -Check 'MQTT authentication' -Status 'FAIL' -Detail $mqttProbe
        }
    } finally {
        Pop-Location
    }
}

$consumerProcesses = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
    Where-Object {
        $_.Name -eq 'python.exe' -and $_.ExecutablePath -eq $python -and
        $_.CommandLine -match 'workers[./\\]mqtt_consumer'
    })
if ($consumerProcesses.Count -eq 1) {
    Add-Result -Check 'MQTT Consumer' -Status 'OK' -Detail 'running; launcher_count=1'
} elseif ($consumerProcesses.Count -gt 1) {
    Add-Result -Check 'MQTT Consumer' -Status 'WARN' -Detail "DUPLICATE_CONSUMERS; launcher_count=$($consumerProcesses.Count)"
} else {
    Add-Result -Check 'MQTT Consumer' -Status 'FAIL' -Detail 'PROCESS_NOT_RUNNING'
}

foreach ($port in @($ApiPort, $MqttPort)) {
    $rules = @(Test-FirewallPort -Port $port)
    if ($rules.Count -gt 0) {
        Add-Result -Check "Firewall TCP $port" -Status 'OK' -Detail "Private inbound allow rule present: $($rules -join '; ')"
    } else {
        Add-Result -Check "Firewall TCP $port" -Status 'WARN' -Detail 'FIREWALL_RULE_MISSING；本机可达不代表其它设备可达。'
    }
}

$activeProfiles = @(Get-NetConnectionProfile -ErrorAction SilentlyContinue |
    Where-Object { $_.IPv4Connectivity -ne 'Disconnected' })
$privateProfiles = @($activeProfiles | Where-Object { $_.NetworkCategory -eq 'Private' })
$profileSummary = if ($activeProfiles.Count -gt 0) {
    ($activeProfiles | ForEach-Object { "$($_.InterfaceAlias)=$($_.NetworkCategory)" }) -join ', '
} else {
    'none'
}
if ($privateProfiles.Count -gt 0) {
    Add-Result -Check 'Windows network profile' -Status 'OK' -Detail $profileSummary
} else {
    Add-Result -Check 'Windows network profile' -Status 'WARN' `
        -Detail "$profileSummary；Private 防火墙规则只在 Private 网络类别下生效。"
}

$pgRules = @(Test-FirewallPort -Port $PostgresPort)
if ($pgRules.Count -gt 0) {
    Add-Result -Check "Firewall TCP $PostgresPort" -Status 'WARN' -Detail '检测到 PostgreSQL 入站允许规则；Leafora 不需要向局域网开放数据库。'
} else {
    Add-Result -Check "Firewall TCP $PostgresPort" -Status 'OK' -Detail '未检测到 PostgreSQL 专用网络入站允许规则。'
}

$addresses = @(Get-NonVirtualIPv4)
if ($addresses.Count -gt 0) {
    Add-Result -Check 'LAN IPv4' -Status 'OK' -Detail ($addresses -join ', ')
} else {
    Add-Result -Check 'LAN IPv4' -Status 'WARN' -Detail '未发现非虚拟 IPv4。'
}

$script:diagnosticResults | Format-Table -AutoSize -Wrap
Write-Output ''
Write-Output '状态含义：PORT_NOT_LISTENING=端口未监听；LOOPBACK_ONLY=仅本机；MQTT_AUTH_FAILED=账号认证失败；FIREWALL_RULE_MISSING=可能被 Windows 防火墙阻断。'

if (@($script:diagnosticResults | Where-Object Status -eq 'FAIL').Count -gt 0) { exit 1 }
exit 0
