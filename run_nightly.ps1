# auto-dev 야간 무인 자동개발 러너 (작업스케줄러 auto-dev-nightly 가 매일 00:30 호출)
# -Live 있으면 실제 실행(--run, tier별 PR/병합), 없으면 안전 DRY(탐지·리포트만).
# tier 정책은 auto_dev_nightly_config.json 참조: merge=병합까지 / pr=PR까지 / dry=점검만(mail).
param([switch]$Live)

$ErrorActionPreference = 'Continue'
$engine = 'D:\auto_dev\auto_dev_nightly.py'
$logdir = 'D:\auto_dev\logs'
$stamp  = Get-Date -Format 'yyyyMMdd_HHmmss'
$log    = Join-Path $logdir ("nightly_run_" + $stamp + ".log")
New-Item -ItemType Directory -Force -Path $logdir | Out-Null

# 종량제 API키 해제 -> 구독 인증 강제 (이 프로세스 한정, 과금 방지)
[Environment]::SetEnvironmentVariable('ANTHROPIC_API_KEY', $null, 'Process')
[Environment]::SetEnvironmentVariable('ANTHROPIC_AUTH_TOKEN', $null, 'Process')
$env:PYTHONUTF8 = '1'

$mode = if ($Live) { 'LIVE(--run)' } else { 'DRY' }
"=== AUTO-DEV NIGHTLY START $stamp  mode=$mode ===" | Tee-Object -FilePath $log

# python 경로 확보(스케줄러 컨텍스트에서 PATH 누락 대비)
$py = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $py) { $py = 'python' }

$pyargs = @($engine)
if ($Live) { $pyargs += '--run' }

& $py @pyargs 2>&1 | Tee-Object -FilePath $log -Append
$code = $LASTEXITCODE
"=== AUTO-DEV NIGHTLY EXIT=$code ($mode) ===" | Tee-Object -FilePath $log -Append
exit $code
