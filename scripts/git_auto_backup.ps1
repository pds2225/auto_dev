# AutoDev Git Auto Backup (Simple & Robust Mode)
# 5-minute interval: detect -> commit -> pull -> push
# Run: PowerShell -File scripts/git_auto_backup.ps1

$repoPath = "D:\auto_dev"
$logFile = "$env:TEMP\git-auto-backup-autodev.log"
$intervalSeconds = 300  # 5 minutes

function Write-Log($msg) {
    $line = "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')  $msg"
    Write-Host $line
    $line | Add-Content $logFile -Encoding UTF8
}

Set-Location $repoPath
Write-Log "=== AutoDev Git Auto Backup Started ==="
Write-Log "Repository: $repoPath"
Write-Log "Interval: $($intervalSeconds / 60) minutes"
Write-Log "Log file: $logFile"
Write-Log "Stop: Task Manager > PowerShell PID 종료"
Write-Log ""

while ($true) {
    try {
        Set-Location $repoPath

        # Verify current branch
        $branch = git rev-parse --abbrev-ref HEAD 2>$null
        if ($branch -ne "main") {
            Write-Log "[SKIP] Current branch is '$branch', not main."
            Start-Sleep -Seconds $intervalSeconds
            continue
        }

        # Fetch remote latest
        git fetch origin main --quiet 2>$null

        # Check for changes (untracked + modified + deleted)
        $status = git status --short 2>$null

        if ([string]::IsNullOrWhiteSpace($status)) {
            Write-Log "[CHECK] No local changes."
        } else {
            $changeCount = ($status -split "`n" | Where-Object { $_.Trim() -ne "" }).Count
            Write-Log "[BACKUP] $changeCount changed file(s) detected."
            $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"

            # Commit all local changes first
            git add -A 2>$null
            git commit -m "auto-backup: $timestamp" 2>$null
            if ($LASTEXITCODE -ne 0) {
                Write-Log "[WARN] Commit skipped (possibly nothing new after add)."
            } else {
                Write-Log "[COMMIT] Local changes committed."
            }

            # Pull latest from remote (merge strategy)
            $behind = git rev-list --count HEAD..origin/main 2>$null
            if ($behind -gt 0) {
                Write-Log "[PULL] origin/main is $behind commit(s) ahead. Pulling..."
                git pull origin main --no-rebase --no-edit --quiet 2>$null
                if ($LASTEXITCODE -ne 0) {
                    Write-Log "[ERROR] git pull failed (conflict?). Manual fix required."
                } else {
                    Write-Log "[PULL] Synced with origin/main."
                }
            }

            # Push
            git push origin main 2>$null
            if ($LASTEXITCODE -ne 0) {
                Write-Log "[ERROR] git push failed."
            } else {
                Write-Log "[DONE] Backup pushed to origin/main."
            }
        }
    } catch {
        Write-Log "[ERROR] $_"
    }

    Start-Sleep -Seconds $intervalSeconds
}
