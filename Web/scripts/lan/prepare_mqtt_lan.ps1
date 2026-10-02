[CmdletBinding(SupportsShouldProcess = $true)]
param([ValidateRange(1, 65535)][int]$Port = 1883)

trap {
    $failureDirectory = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..\local\logs'))
    New-Item -ItemType Directory -Path $failureDirectory -Force | Out-Null
    $_.Exception.Message | Set-Content -LiteralPath (Join-Path $failureDirectory 'prepare-mqtt-lan.err.log') -Encoding UTF8
    exit 1
}

# Run only while inspections and pending uploads are idle. This changes the
# legacy Windows service, not the project Broker or any business data.
. (Join-Path $PSScriptRoot 'Common.ps1')
$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = New-Object Security.Principal.WindowsPrincipal($identity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw '需要管理员 PowerShell；仅停止旧 Mosquitto 服务并将其改为手动启动。'
}

$service = Get-CimInstance Win32_Service -Filter "Name='mosquitto'"
if (-not $service) { throw '未找到旧 Mosquitto Windows 服务；未修改其它进程。' }
if ($service.PathName -notmatch '^"?C:\\Program Files\\Mosquitto\\mosquitto\.exe"?\s+run\s*$') {
    throw '服务启动方式不属于预期的旧 Mosquitto 安装；拒绝自动修改。'
}
if ($service.State -notin @('Running', 'Stopped')) { throw '服务正在切换状态，请稍后重试。' }
$listeners = @(Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue)
if (@($listeners | Where-Object {
    $_.OwningProcess -ne $service.ProcessId -or $_.LocalAddress -notin @('127.0.0.1', '::1')
}).Count -gt 0) {
    throw '端口被其它进程或已有局域网 Broker 使用；拒绝停止。'
}
if ($service.State -eq 'Running' -and $listeners.Count -eq 0) {
    throw '旧服务未监听指定端口；拒绝停止可能用于其它用途的服务。'
}

if ($PSCmdlet.ShouldProcess('mosquitto Windows service', '改为手动启动并停止旧的仅本机 Broker')) {
    Initialize-LocalDirectories
    $recordPath = Join-Path $script:RunRoot 'legacy-mosquitto-before.json'
    if (-not (Test-Path -LiteralPath $recordPath)) {
        @{ name = $service.Name; state = $service.State; start_mode = $service.StartMode;
            path = $service.PathName; recorded_at = [DateTime]::UtcNow.ToString('o') } |
            ConvertTo-Json | Set-Content -LiteralPath $recordPath -Encoding UTF8
    }
    $originalMode = @{ Auto = 'Automatic'; Manual = 'Manual'; Disabled = 'Disabled' }[$service.StartMode]
    try {
        Set-Service -Name mosquitto -StartupType Manual -ErrorAction Stop
        if ($service.State -eq 'Running') {
            Stop-Service -Name mosquitto -ErrorAction Stop
            (Get-Service mosquitto).WaitForStatus('Stopped', [TimeSpan]::FromSeconds(15))
        }
    } catch {
        if ($originalMode) { Set-Service -Name mosquitto -StartupType $originalMode -ErrorAction SilentlyContinue }
        throw
    }
    Write-Output '旧 Mosquitto 服务已停止并改为手动启动；请用项目配置启动 Broker。'
}
