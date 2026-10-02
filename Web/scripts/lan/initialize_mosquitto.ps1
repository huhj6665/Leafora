[CmdletBinding()]
param(
    [ValidateRange(1, 65535)][int]$Port = 1883,
    [string]$MosquittoExe = '',
    [string]$MosquittoPasswdExe = ''
)

. (Join-Path $PSScriptRoot 'Common.ps1')

$webRoot = Get-WebRoot
$backendEnvPath = Join-Path $webRoot 'backend\.env'
$mockEnvPath = Join-Path $webRoot 'scripts\mock_jetson\.env'
$backendEnv = Read-DotEnvFile -Path $backendEnvPath
$mockEnv = Read-DotEnvFile -Path $mockEnvPath

$username = [string]$backendEnv['MQTT_USERNAME']
$password = [string]$backendEnv['MQTT_PASSWORD']
if (-not $username -or -not $password) {
    throw 'backend/.env 的 MQTT_USERNAME 或 MQTT_PASSWORD 未配置。'
}
if ($username -notmatch '^[A-Za-z0-9_.@-]+$') {
    throw 'MQTT_USERNAME 只能包含字母、数字、点、下划线、@ 或连字符。'
}
if ($username -ne [string]$mockEnv['MQTT_USERNAME'] -or $password -ne [string]$mockEnv['MQTT_PASSWORD']) {
    throw 'backend/.env 与 scripts/mock_jetson/.env 的 MQTT 凭据不一致。'
}

if (-not $MosquittoExe) { $MosquittoExe = 'C:\Program Files\Mosquitto\mosquitto.exe' }
if (-not $MosquittoPasswdExe) { $MosquittoPasswdExe = 'C:\Program Files\Mosquitto\mosquitto_passwd.exe' }
if (-not (Test-Path -LiteralPath $MosquittoExe -PathType Leaf)) { throw "未找到 Mosquitto：$MosquittoExe" }
if (-not (Test-Path -LiteralPath $MosquittoPasswdExe -PathType Leaf)) { throw "未找到 mosquitto_passwd：$MosquittoPasswdExe" }

$runtimeRoot = Join-Path $webRoot 'local\mosquitto'
$dataRoot = Join-Path $runtimeRoot 'data'
$logRoot = Join-Path $runtimeRoot 'log'
foreach ($path in @($runtimeRoot, $dataRoot, $logRoot)) {
    New-Item -ItemType Directory -Path $path -Force | Out-Null
}

$passwordFile = Join-Path $runtimeRoot 'passwd'
$temporaryPasswordFile = Join-Path $runtimeRoot 'passwd.tmp'
if (Test-Path -LiteralPath $temporaryPasswordFile) { Remove-Item -LiteralPath $temporaryPasswordFile -Force }

$startInfo = New-Object System.Diagnostics.ProcessStartInfo
$startInfo.FileName = $MosquittoPasswdExe
$startInfo.UseShellExecute = $false
$startInfo.CreateNoWindow = $true
$startInfo.RedirectStandardOutput = $true
$startInfo.RedirectStandardError = $true
if ($startInfo.PSObject.Properties.Name -contains 'ArgumentList') {
    foreach ($argument in @('-H', 'sha512-pbkdf2', '-c', '-b', $temporaryPasswordFile, $username, $password)) {
        $startInfo.ArgumentList.Add($argument)
    }
} else {
    if ($password -match '["\r\n]') {
        throw '当前 PowerShell/.NET 版本无法安全传递包含引号或换行的 MQTT 密码；请使用 PowerShell 7。'
    }
    $startInfo.Arguments = "-H sha512-pbkdf2 -c -b `"$temporaryPasswordFile`" `"$username`" `"$password`""
}
$passwordProcess = New-Object System.Diagnostics.Process
$passwordProcess.StartInfo = $startInfo
if (-not $passwordProcess.Start()) { throw '无法启动 mosquitto_passwd。' }
$null = $passwordProcess.StandardOutput.ReadToEnd()
$null = $passwordProcess.StandardError.ReadToEnd()
$passwordProcess.WaitForExit()
if ($passwordProcess.ExitCode -ne 0) {
    if (Test-Path -LiteralPath $temporaryPasswordFile) { Remove-Item -LiteralPath $temporaryPasswordFile -Force }
    throw "生成 Mosquitto 密码文件失败，退出码 $($passwordProcess.ExitCode)（未输出凭据）。"
}
Move-Item -LiteralPath $temporaryPasswordFile -Destination $passwordFile -Force

$templatePath = Join-Path $webRoot 'infrastructure\mosquitto\mosquitto.conf.template'
$configPath = Join-Path $runtimeRoot 'mosquitto.conf'
$toMosquittoPath = {
    param([string]$Path)
    return $Path.Replace('\', '/')
}
$config = Get-Content -LiteralPath $templatePath -Raw -Encoding UTF8
$config = $config.Replace('{{LISTEN_PORT}}', [string]$Port)
$config = $config.Replace('{{PASSWORD_FILE}}', (& $toMosquittoPath $passwordFile))
$config = $config.Replace('{{PERSISTENCE_DIR}}', (& $toMosquittoPath $dataRoot).TrimEnd('/'))
$config = $config.Replace('{{LOG_FILE}}', (& $toMosquittoPath (Join-Path $logRoot 'mosquitto.log')))
# Mosquitto rejects a UTF-8 BOM as an unknown first configuration variable.
# Windows PowerShell 5.1's -Encoding UTF8 adds a BOM, unlike PowerShell 7.
$utf8WithoutBom = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllText($configPath, $config, $utf8WithoutBom)

Write-Output "Mosquitto 本地配置已生成：$configPath"
Write-Output '认证状态：已启用；匿名访问：已关闭；凭据内容：未输出。'
