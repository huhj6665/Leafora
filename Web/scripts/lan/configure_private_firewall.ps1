[CmdletBinding(SupportsShouldProcess = $true, ConfirmImpact = 'High')]
param(
    [ValidateSet('Enable', 'Remove')][string]$Action = 'Enable'
)

$rules = @(
    @{ Name = 'Leafora Web API (Private)'; Port = 8000 },
    @{ Name = 'Leafora MQTT (Private)'; Port = 1883 }
)

$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = New-Object Security.Principal.WindowsPrincipal($identity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw '防火墙规则需要管理员 PowerShell。请右键 PowerShell 选择“以管理员身份运行”后重试。'
}

foreach ($rule in $rules) {
    $existing = Get-NetFirewallRule -DisplayName $rule.Name -ErrorAction SilentlyContinue
    if ($Action -eq 'Enable') {
        if ($existing) {
            if ($PSCmdlet.ShouldProcess($rule.Name, '启用专用网络入站规则')) {
                $existing | Set-NetFirewallRule -Enabled True -Profile Private -Direction Inbound -Action Allow
            }
        } elseif ($PSCmdlet.ShouldProcess($rule.Name, "创建 TCP $($rule.Port) 专用网络入站规则")) {
            New-NetFirewallRule -DisplayName $rule.Name -Direction Inbound -Action Allow `
                -Protocol TCP -LocalPort $rule.Port -Profile Private | Out-Null
        }
    } elseif ($existing -and $PSCmdlet.ShouldProcess($rule.Name, '删除 Leafora 防火墙规则')) {
        $existing | Remove-NetFirewallRule
    }
}

$activeProfiles = @(Get-NetConnectionProfile -ErrorAction SilentlyContinue |
    Where-Object { $_.IPv4Connectivity -ne 'Disconnected' })
$nonPrivateProfiles = @($activeProfiles | Where-Object { $_.NetworkCategory -ne 'Private' })
if ($nonPrivateProfiles.Count -gt 0) {
    $profileSummary = ($nonPrivateProfiles | ForEach-Object {
        "$($_.InterfaceAlias)=$($_.NetworkCategory)"
    }) -join ', '
    Write-Warning "检测到活动网络不是 Private：$profileSummary。Private 防火墙规则在该网络上不会生效；仅在可信局域网中将相应网络配置为 Private。"
}

Write-Output "操作完成：$Action。仅涉及 TCP 8000 与 1883 的专用网络入站规则；未开放 5432。"
