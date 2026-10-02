[CmdletBinding()]
param(
    [ValidateRange(1, 65535)][int]$ApiPort = 8000,
    [ValidateRange(1, 65535)][int]$MqttPort = 1883,
    [string]$MqttHost = '',
    [ValidateRange(1, 65535)][int]$PostgresPort = 5432,
    [ValidateRange(1, 65535)][int]$FrontendPort = 5173,
    [ValidateRange(1, 65535)][int]$ModelPort = 8002,
    [switch]$SkipMosquitto,
    [switch]$SkipFrontend,
    [switch]$IncludeModelService,
    [switch]$SkipModelService
)

if ($IncludeModelService -and $SkipModelService) {
    throw 'IncludeModelService 与 SkipModelService 不能同时使用。'
}

. (Join-Path $PSScriptRoot 'Common.ps1')
Initialize-LocalDirectories
$webRoot = Get-WebRoot
$backendRoot = Join-Path $webRoot 'backend'
$frontendRoot = Join-Path $webRoot 'frontend'
$python = Join-Path $backendRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python -PathType Leaf)) { throw "后端虚拟环境不存在：$python" }

$backendConfig = Read-DotEnvFile -Path (Join-Path $backendRoot '.env')
if (-not $MqttHost) {
    $MqttHost = if ($env:MQTT_HOST) { $env:MQTT_HOST } elseif ($backendConfig['MQTT_HOST']) { $backendConfig['MQTT_HOST'] } else { '127.0.0.1' }
}
if (-not $PSBoundParameters.ContainsKey('MqttPort')) {
    if ($env:MQTT_PORT) { $MqttPort = [int]$env:MQTT_PORT }
    elseif ($backendConfig['MQTT_PORT']) { $MqttPort = [int]$backendConfig['MQTT_PORT'] }
}
if (-not $PSBoundParameters.ContainsKey('PostgresPort')) {
    if ($env:DB_PORT) { $PostgresPort = [int]$env:DB_PORT }
    elseif ($backendConfig['DB_PORT']) { $PostgresPort = [int]$backendConfig['DB_PORT'] }
}
if ($MqttPort -lt 1 -or $MqttPort -gt 65535 -or $PostgresPort -lt 1 -or $PostgresPort -gt 65535) {
    throw 'MQTT/数据库端口必须在 1–65535 内。'
}
if (-not $SkipMosquitto -and $MqttHost -notin @('127.0.0.1', 'localhost', '::1')) {
    throw '远程 Broker 请使用 -SkipMosquitto；本脚本仅创建本机 Broker。'
}
$configuredMqttHost = if ($env:MQTT_HOST) { $env:MQTT_HOST } elseif ($backendConfig['MQTT_HOST']) { $backendConfig['MQTT_HOST'] } else { '127.0.0.1' }
$configuredMqttPort = if ($env:MQTT_PORT) { [int]$env:MQTT_PORT } elseif ($backendConfig['MQTT_PORT']) { [int]$backendConfig['MQTT_PORT'] } else { 1883 }
if ($configuredMqttHost -ne $MqttHost -or $configuredMqttPort -ne $MqttPort) {
    throw '请先将 backend/.env 或环境变量中的 MQTT_HOST/MQTT_PORT 与启动参数对齐，避免复用进程连接到不同 Broker。'
}

$postgres = Get-ListenerState -Port $PostgresPort
if ($postgres.State -eq 'PORT_NOT_LISTENING') {
    throw "PostgreSQL 未监听 $PostgresPort。请先启动本机 PostgreSQL；不要向局域网开放该端口。"
}

Push-Location $backendRoot
try {
    & $python -m alembic upgrade head
    if ($LASTEXITCODE -ne 0) { throw 'Alembic upgrade head 执行失败。' }
} finally {
    Pop-Location
}

if (-not $SkipMosquitto) {
    $mqttState = Get-ListenerState -Port $MqttPort
    if ($mqttState.State -ne 'PORT_NOT_LISTENING') {
        throw "MQTT 端口 $MqttPort 已被占用（$($mqttState.State)，地址 $($mqttState.Addresses -join ', ')）。不要启动重复 Broker；若为旧 Mosquitto 服务且仅本机监听，请在无活动任务时以管理员身份运行 scripts/lan/prepare_mqtt_lan.ps1，再重试。"
    }
    & (Join-Path $PSScriptRoot 'initialize_mosquitto.ps1') -Port $MqttPort
    $mosquitto = 'C:\Program Files\Mosquitto\mosquitto.exe'
    $mosquittoConfig = Join-Path $webRoot 'local\mosquitto\mosquitto.conf'
    $broker = Start-ManagedProcess -Name 'mosquitto' -FilePath $mosquitto `
        -ArgumentList @('-c', $mosquittoConfig) -WorkingDirectory (Split-Path $mosquitto -Parent)
    if (-not (Wait-TcpPort -HostName '127.0.0.1' -Port $MqttPort -TimeoutSeconds 12)) {
        throw "Mosquitto 启动后未监听 $MqttPort，请查看 local/logs/mosquitto.err.log。"
    }
}

$apiState = Get-ListenerState -Port $ApiPort
if ($apiState.State -eq 'PORT_NOT_LISTENING') {
    $previousMqttPort = $env:MQTT_PORT
    $previousMqttHost = $env:MQTT_HOST
    try {
        $env:MQTT_PORT = [string]$MqttPort
        $env:MQTT_HOST = $MqttHost
        $api = Start-ManagedProcess -Name 'fastapi' -FilePath $python `
            -ArgumentList @('-m', 'uvicorn', 'app.main:app', '--host', '0.0.0.0', '--port', [string]$ApiPort) `
            -WorkingDirectory $backendRoot
    } finally {
        $env:MQTT_PORT = $previousMqttPort
        $env:MQTT_HOST = $previousMqttHost
    }
    if (-not (Wait-TcpPort -HostName '127.0.0.1' -Port $ApiPort -TimeoutSeconds 20)) {
        throw "FastAPI 启动后未监听 $ApiPort，请查看 local/logs/fastapi.err.log。"
    }
} elseif ($apiState.State -eq 'LOOPBACK_ONLY') {
    throw "FastAPI 已在 $ApiPort 监听，但仅绑定回环地址。请停止旧进程后由本脚本以 0.0.0.0 启动。"
}

$consumerProcesses = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
    Where-Object {
        $_.Name -eq 'python.exe' -and $_.ExecutablePath -eq $python -and
        $_.CommandLine -match 'workers[./\\]mqtt_consumer'
    })
if ($consumerProcesses.Count -gt 1) {
    throw "检测到 $($consumerProcesses.Count) 个 MQTT Consumer 启动器。请先停止重复进程，避免重复消费。"
}
if ($consumerProcesses.Count -eq 0) {
    $previousConsumerMqttPort = $env:MQTT_PORT
    $previousConsumerMqttHost = $env:MQTT_HOST
    try {
        $env:MQTT_PORT = [string]$MqttPort
        $env:MQTT_HOST = $MqttHost
        $consumer = Start-ManagedProcess -Name 'mqtt-consumer' -FilePath $python `
            -ArgumentList @('-m', 'workers.mqtt_consumer') -WorkingDirectory $backendRoot
    } finally {
        $env:MQTT_PORT = $previousConsumerMqttPort
        $env:MQTT_HOST = $previousConsumerMqttHost
    }
}

if (-not $SkipFrontend) {
    $frontendState = Get-ListenerState -Port $FrontendPort
    if ($frontendState.State -eq 'PORT_NOT_LISTENING') {
        $npmCommand = Get-Command 'npm.cmd' -ErrorAction SilentlyContinue
        if (-not $npmCommand) { throw '未找到 npm.cmd。' }
        $previousApiTarget = $env:VITE_DEV_API_TARGET
        try {
            $env:VITE_DEV_API_TARGET = "http://127.0.0.1:$ApiPort"
            $frontend = Start-ManagedProcess -Name 'frontend' -FilePath $npmCommand.Source `
                -ArgumentList @('run', 'dev', '--', '--host', '0.0.0.0', '--port', [string]$FrontendPort) `
                -WorkingDirectory $frontendRoot
        } finally {
            $env:VITE_DEV_API_TARGET = $previousApiTarget
        }
        if (-not (Wait-TcpPort -HostName '127.0.0.1' -Port $FrontendPort -TimeoutSeconds 20)) {
            throw "前端启动后未监听 $FrontendPort，请查看 local/logs/frontend.err.log。"
        }
    } elseif ($frontendState.State -eq 'LOOPBACK_ONLY') {
        throw "前端已在 $FrontendPort 监听，但仅绑定回环地址。请停止旧进程后由本脚本以 0.0.0.0 启动。"
    }
}

if ($IncludeModelService -and -not $SkipModelService) {
    $modelRoot = Join-Path $webRoot 'model_service'
    $modelPython = Join-Path $modelRoot '.venv\Scripts\python.exe'
    if (-not (Test-Path -LiteralPath $modelPython -PathType Leaf)) {
        throw "模型服务虚拟环境不存在：$modelPython"
    }
    $modelState = Get-ListenerState -Port $ModelPort
    if ($modelState.State -eq 'PORT_NOT_LISTENING') {
        $model = Start-ManagedProcess -Name 'model-service' -FilePath $modelPython `
            -ArgumentList @('-m', 'uvicorn', 'app.main:app', '--host', '0.0.0.0', '--port', [string]$ModelPort) `
            -WorkingDirectory $modelRoot
        if (-not (Wait-TcpPort -HostName '127.0.0.1' -Port $ModelPort -TimeoutSeconds 20)) {
            throw "模型服务启动后未监听 $ModelPort，请查看 local/logs/model-service.err.log。"
        }
    }
    try {
        $modelHealth = Invoke-RestMethod -Uri "http://127.0.0.1:$ModelPort/health" -Method Get -TimeoutSec 120
        if (-not $modelHealth.model_ready) {
            throw "模型权重未就绪：$($modelHealth.detail)"
        }
    } catch {
        throw "模型服务健康检查失败。请确认 $ModelPort 未被其它程序占用且 weights/train_best.pt 可用。$($_.Exception.Message)"
    }
}

$addresses = @(Get-NonVirtualIPv4)
Write-Output ''
Write-Output 'Leafora 局域网服务已启动。可用地址：'
if ($addresses.Count -eq 0) {
    Write-Output '  未发现非虚拟 IPv4；请检查 Wi-Fi/有线网卡。'
} else {
    foreach ($address in $addresses) {
        Write-Output "  IPv4: $address"
        Write-Output "  FastAPI 健康检查: http://${address}:$ApiPort/api/health"
        if (-not $SkipFrontend) { Write-Output "  Web: http://${address}:$FrontendPort/" }
        Write-Output "  MQTT: ${address}:$MqttPort（本机 Broker 时适用，需要认证）"
    }
}
Write-Output "云端 MQTT 目标：${MqttHost}:$MqttPort；已运行进程如曾用其它配置启动，需单独协调重启。"
Write-Output "PostgreSQL $PostgresPort 未由本脚本开放到局域网。"
Write-Output "日志目录：$(Join-Path $webRoot 'local\logs')"
