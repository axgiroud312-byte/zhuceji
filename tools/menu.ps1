param([switch]$CheckOnly)

$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$taskRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $taskRoot
$taskConfig = Join-Path $taskRoot 'config.local.toml'
if (-not (Test-Path -LiteralPath $taskConfig)) {
    $taskConfig = Join-Path $taskRoot 'config.example.toml'
}
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Host '找不到运行工具 uv。请按照 README 中的安装说明准备环境。'
    exit 1
}

function Invoke-Agnes {
    param([string[]]$TaskArguments)
    & uv run agnes --config $taskConfig @TaskArguments
    $script:taskLastSuccess = ($LASTEXITCODE -eq 0)
    if ($LASTEXITCODE -ne 0) {
        Write-Host '操作未完成，请查看上面的具体原因。' -ForegroundColor Yellow
    }
}

function Show-Menu {
    Write-Host ''
    Write-Host 'Agnes 开户工具' -ForegroundColor Cyan
    Write-Host 'W  启动可视化 Web 前端控制台（支持改流程、批量导号、代理池换IP）【推荐】' -ForegroundColor Green
    Write-Host '1  检查 1000 条模拟任务（不访问 Agnes）'
    Write-Host '2  导入用户 CSV'
    Write-Host '3  创建开户批次'
    Write-Host '4  开始或继续批次'
    Write-Host '5  查看任务和失败原因'
    Write-Host '6  导出含密码和 API Key 的 Excel'
    Write-Host '7  核验已提交的账号'
    Write-Host '8  暂停批次'
    Write-Host '9  恢复运行中的批次'
    Write-Host '10 停止批次'
    Write-Host '11 导入邮箱资料（账号----密码----clientid----刷新令牌）'
    Write-Host '0  退出'
}

if ($CheckOnly) {
    Show-Menu
    Write-Host "菜单可用。配置文件：$taskConfig"
    exit 0
}

while ($true) {
    Show-Menu
    $taskChoice = Read-Host '输入操作编号'
    try {
        switch ($taskChoice) {
            '0' { exit 0 }
            'W' { Invoke-Agnes -TaskArguments @('web') }
            'w' { Invoke-Agnes -TaskArguments @('web') }
            '12' { Invoke-Agnes -TaskArguments @('web') }
            '1' { & uv run agnes demo --count 1000 }
            '2' {
                $taskInput = (Read-Host '输入用户 CSV 的完整路径').Trim('"')
                Invoke-Agnes -TaskArguments @('import-users', $taskInput)
            }
            '3' {
                $taskBatch = Read-Host '给这批用户起一个名称，例如 first-batch'
                Invoke-Agnes -TaskArguments @('create-batch', $taskBatch)
            }
            '4' {
                $taskBatch = Read-Host '输入批次名称'
                $taskLimit = Read-Host '本次最多处理几个任务？直接回车表示全部'
                $taskRunArguments = @('run', $taskBatch)
                if ($taskLimit) { $taskRunArguments += @('--limit', $taskLimit) }
                Invoke-Agnes -TaskArguments $taskRunArguments
            }
            '5' {
                $taskBatch = Read-Host '输入批次名称；直接回车查看全部'
                $taskStatusArguments = @('status')
                $taskJobsArguments = @('jobs')
                if ($taskBatch) {
                    $taskStatusArguments += $taskBatch
                    $taskJobsArguments += @('--batch', $taskBatch)
                }
                Invoke-Agnes -TaskArguments $taskStatusArguments
                Invoke-Agnes -TaskArguments $taskJobsArguments
            }
            '6' {
                $taskBatch = Read-Host '输入批次名称；直接回车导出全部'
                $taskExportPath = Join-Path $taskRoot 'outputs\开户结果.xlsx'
                $taskExportArguments = @('export', $taskExportPath, '--include-secrets')
                if ($taskBatch) { $taskExportArguments += @('--batch', $taskBatch) }
                Invoke-Agnes -TaskArguments $taskExportArguments
                if ($script:taskLastSuccess -and (Test-Path -LiteralPath $taskExportPath)) {
                    Write-Host "Excel 已保存：$taskExportPath"
                }
            }
            '7' {
                $taskJob = Read-Host '输入任务 ID（可从操作 5 复制）'
                Invoke-Agnes -TaskArguments @('verify-job', $taskJob)
            }
            '8' {
                $taskBatch = Read-Host '输入批次名称'
                Invoke-Agnes -TaskArguments @('pause', $taskBatch)
            }
            '9' {
                $taskBatch = Read-Host '输入批次名称'
                Invoke-Agnes -TaskArguments @('resume', $taskBatch)
            }
            '10' {
                $taskBatch = Read-Host '输入批次名称'
                Invoke-Agnes -TaskArguments @('stop', $taskBatch)
            }
            '11' {
                $taskMailboxFile = (Read-Host '输入四段邮箱资料文件的完整路径').Trim('"')
                $taskConsent = Read-Host '输入邮箱授权说明，例如：本人持有的开发测试邮箱'
                if (-not $taskConsent.Trim()) { throw '缺少邮箱授权说明' }
                Invoke-Agnes -TaskArguments @('import-mailboxes', $taskMailboxFile, '--authorized', '--consent-reference', $taskConsent)
            }
            default { Write-Host '请输入菜单中的编号。' }
        }
    } catch {
        Write-Host '操作未完成。请核对输入的路径或批次名称，并查看使用说明。' -ForegroundColor Yellow
    }
}
