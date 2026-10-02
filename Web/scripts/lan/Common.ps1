Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$script:WebRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
$script:LocalRoot = Join-Path $script:WebRoot 'local'
$script:RunRoot = Join-Path $script:LocalRoot 'run'
$script:LogRoot = Join-Path $script:LocalRoot 'logs'

function Get-WebRoot {
    return $script:WebRoot
}

function Initialize-LocalDirectories {
    foreach ($path in @($script:LocalRoot, $script:RunRoot, $script:LogRoot)) {
        New-Item -ItemType Directory -Path $path -Force | Out-Null
    }
}

function Read-DotEnvFile {
    param([Parameter(Mandatory = $true)][string]$Path)

    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "环境文件不存在：$Path"
    }

    $values = @{}
    foreach ($line in Get-Content -LiteralPath $Path -Encoding UTF8) {
        $trimmed = $line.Trim()
        if (-not $trimmed -or $trimmed.StartsWith('#')) { continue }
        $separator = $trimmed.IndexOf('=')
        if ($separator -lt 1) { continue }
        $name = $trimmed.Substring(0, $separator).Trim()
        $value = $trimmed.Substring($separator + 1).Trim()
        if ($value.Length -ge 2) {
            $first = $value.Substring(0, 1)
            $last = $value.Substring($value.Length - 1, 1)
            if (($first -eq '"' -and $last -eq '"') -or ($first -eq "'" -and $last -eq "'")) {
                $value = $value.Substring(1, $value.Length - 2)
            }
        }
        $values[$name] = $value
    }
    return $values
}

function Get-NonVirtualIPv4 {
    $virtualPattern = 'vEthernet|Hyper-V|VMware|VirtualBox|WSL|Loopback|Tailscale|ZeroTier'
    return @(Get-NetIPAddress -AddressFamily IPv4 -AddressState Preferred -ErrorAction SilentlyContinue |
        Where-Object {
            $_.IPAddress -ne '127.0.0.1' -and
            -not $_.IPAddress.StartsWith('169.254.') -and
            $_.InterfaceAlias -notmatch $virtualPattern
        } |
        Sort-Object InterfaceMetric, InterfaceAlias |
        Select-Object -ExpandProperty IPAddress -Unique)
}

function Get-ListenerState {
    param([Parameter(Mandatory = $true)][int]$Port)

    $listeners = @(Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue)
    if ($listeners.Count -eq 0) {
        return [pscustomobject]@{ Port = $Port; State = 'PORT_NOT_LISTENING'; Addresses = @(); Pids = @() }
    }
    $addresses = @($listeners | Select-Object -ExpandProperty LocalAddress -Unique)
    $lanAddresses = @($addresses | Where-Object { $_ -notin @('127.0.0.1', '::1') })
    $state = if ($lanAddresses.Count -gt 0) { 'LAN_LISTENING' } else { 'LOOPBACK_ONLY' }
    return [pscustomobject]@{
        Port = $Port
        State = $state
        Addresses = $addresses
        Pids = @($listeners | Select-Object -ExpandProperty OwningProcess -Unique)
    }
}

function Wait-TcpPort {
    param(
        [Parameter(Mandatory = $true)][string]$HostName,
        [Parameter(Mandatory = $true)][int]$Port,
        [int]$TimeoutSeconds = 15
    )

    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    while ([DateTime]::UtcNow -lt $deadline) {
        $client = New-Object System.Net.Sockets.TcpClient
        try {
            $pending = $client.BeginConnect($HostName, $Port, $null, $null)
            if ($pending.AsyncWaitHandle.WaitOne(500) -and $client.Connected) {
                $client.EndConnect($pending)
                return $true
            }
        } catch {
            # Keep polling until the deadline.
        } finally {
            $client.Dispose()
        }
        Start-Sleep -Milliseconds 300
    }
    return $false
}

function Write-ManagedPid {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][System.Diagnostics.Process]$Process
    )
    Initialize-LocalDirectories
    $record = [ordered]@{
        pid = $Process.Id
        name = $Name
        started_at = [DateTime]::UtcNow.ToString('o')
    }
    $record | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $script:RunRoot "$Name.json") -Encoding UTF8
}

function Start-ManagedProcess {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][string]$FilePath,
        [Parameter(Mandatory = $true)][string[]]$ArgumentList,
        [Parameter(Mandatory = $true)][string]$WorkingDirectory
    )
    Initialize-LocalDirectories
    $stdout = Join-Path $script:LogRoot "$Name.out.log"
    $stderr = Join-Path $script:LogRoot "$Name.err.log"
    $process = Start-Process -FilePath $FilePath -ArgumentList $ArgumentList `
        -WorkingDirectory $WorkingDirectory -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput $stdout -RedirectStandardError $stderr
    Write-ManagedPid -Name $Name -Process $process
    return $process
}
