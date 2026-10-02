# 上传 GitHub

## 发布边界

使用工具导出的 **无历史发布副本**，不要直接推送原开发目录。原 `.git` 中可能有历史敏感配置或开发记录，当前文件干净不代表旧提交干净。

私有清理备份、原开发备份、模型权重、用户数据和安装好的依赖都不要上传。默认先创建 Private 仓库；图片和模型授权尚未核实，转为 Public 前请确认授权并决定源码许可证。

## 1. 创建空仓库

在 GitHub 创建自己的仓库。不要勾选初始化 README、.gitignore 或 License，本地已经准备 README 和忽略规则。记录 HTTPS 地址，例如 `https://github.com/OWNER/REPOSITORY.git`，不要在 URL 中放 Token。

已有非空仓库不要强推或覆盖；应另建空仓库，或在确认现有内容后单独处理合并。

## 2. 导出当前源码

在开发项目根目录执行（Python 3.10+）：

```powershell
python tools/release_audit.py
if ($LASTEXITCODE -ne 0) { throw '审查未通过，停止发布' }
python tools/export_public_source.py --output ../Leafora2-GitHub
if ($LASTEXITCODE -ne 0) { throw '导出失败，停止发布' }
```

若已经获得本次整理生成的 `Leafora2-GitHub/`，无需再次导出。工具拒绝覆盖已有目录；重新导出请明确指定一个新的、与源码并列的目录，不要删除或覆盖旧目录。

## 3. 在发布副本初始化 Git

如果之前已经初始化，不需要删除源码。要完全重新开始，可在发布副本根目录将 `.git` 移到项目外作为私人备份：

```powershell
# 仅在 Leafora2-GitHub 发布副本根目录执行
$publishPath = (Get-Location).Path
if ((Split-Path -Leaf $publishPath) -ne 'Leafora2-GitHub') { throw '请先进入发布副本目录' }
$oldGit = Join-Path $publishPath '.git'
if (Test-Path -LiteralPath $oldGit) {
  if (-not (Get-Item -LiteralPath $oldGit -Force).PSIsContainer) { throw '不是普通 Git 目录，停止操作' }
  $backupPath = Join-Path (Split-Path -Parent $publishPath) ('Leafora2-GitHub-git-backup-' + [guid]::NewGuid().ToString('N'))
  Move-Item -LiteralPath $oldGit -Destination $backupPath -ErrorAction Stop
  Write-Host "旧 Git 状态已备份：$backupPath"
}
```

备份不要上传；该操作只重置本地发布副本，不删除 GitHub 已有提交。远端已有内容时应停止首次上传流程，不能强推覆盖。

```powershell
Set-Location ../Leafora2-GitHub
python tools/fix_release_whitespace.py
if ($LASTEXITCODE -ne 0) { throw '空白格式整理失败' }
python tools/release_audit.py
if ($LASTEXITCODE -ne 0) { throw '审查未通过，停止发布' }
if (Test-Path -LiteralPath .git) { throw '本目录已有 Git 历史；首次上传请使用新的无历史副本' }
git init -b main
```

首次使用 Git 时，设置本仓库提交身份（不是账号密码；可用 GitHub 隐私邮箱）：

```powershell
git config user.name "你的 GitHub 用户名"
git config user.email "你的 GitHub 提交邮箱"
```

准备提交前再看文件清单：

```powershell
git add -- .
git diff --cached --name-only
git diff --cached --check
if ($LASTEXITCODE -ne 0) { throw '暂存区格式检查失败' }
python tools/release_audit.py --git-index
if ($LASTEXITCODE -ne 0) { throw '暂存区安全检查失败，停止提交' }
git status --short
git commit -m "Initial sanitized Leafora source"
```

`git diff` 的分页界面按 `q` 退出，或使用 `git --no-pager diff --cached --name-only`。提示行尾空格或末尾空行时，运行格式整理工具并重新 `git add -- .`；这类格式警告不等同敏感信息泄露。批量粘贴命令时，将整个流程放进 `& { ... }` 脚本块，并检查每条外部命令的退出码，防止某一条报错后继续执行。

如果看到 `.env`、`device.env`、密钥、数据库、用户图片、旧提示词或运行日志，停止提交并检查，而不是依赖 GitHub 自动拦截。

## 4. 关联并推送

```powershell
$repoUrl = Read-Host '请输入空 GitHub 仓库的 HTTPS 地址'
if ($repoUrl -notmatch '^https://github\.com/[^/@]+/[^/]+\.git$') {
  throw '请使用不含用户名密码或 Token 的 GitHub HTTPS 地址'
}
git remote add origin $repoUrl
git remote -v
git push -u origin main
```

首次推送通过 Git Credential Manager / 浏览器完成认证，或使用自己已配置的 SSH。不要使用 GitHub 登录密码代替令牌，不要把令牌写到命令、远端地址或项目文件里。

推送被拒绝时先查看原因；不要使用 `--force`、`--mirror` 或把旧开发分支全部推上去。

## 5. 推送后核对

- 首页 README 是否正常显示，是否只有新的源码提交。
- 仓库不存在真实配置、模型、数据库、日志、依赖目录和私有备份。
- 在另一空目录克隆，按照 `docs/SETUP.md` 重新安装依赖并创建自己的配置。
- 开启 GitHub 可用的安全扫描；若发现泄露，先轮换凭据，再处理历史。

这些步骤上传源码，不会部署网站、云数据库或 Jetson，也不会把本地业务数据搬到 GitHub。

官方参考：[添加本地代码到 GitHub](https://docs.github.com/en/migrations/importing-source-code/using-the-command-line-to-import-source-code/adding-locally-hosted-code-to-github)。
