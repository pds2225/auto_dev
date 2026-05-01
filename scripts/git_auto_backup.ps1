# AutoDev Git Auto Backup (Stash-Pull-Pop Safe Mode)
# 5-minute interval: detect -> stash -> pull -> pop -> commit -> push
# Run: PowerShell -File scripts/git_auto_backup.ps1

$repoPath = "D:\auto_dev"
$logFile = "D:\auto_dev\.git-auto-backup.log"
$intervalSeconds = 300  # 5 minutes

function Write-Log($msg) {
    $line = "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')  $msg"
    Write-Host $line
    $line | Add-Content $logFile -Encoding UTF8
}

Set-Location $repoPath
Write-Log "=== AutoDev Git Auto Backup Started (Stash-Pull-Pop Mode) ==="
Write-Log "Repository: $repoPath"
Write-Log "Interval: $($intervalSeconds / 60) minutes"
Write-Log "Log file: $logFile"
Write-Log "Stop: Task Manager > PowerShell PID 醫낅즺"
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

            # 1. Stash (include untracked)
            if (Test-Path "$epoPath\.git-auto-backup.log") { Remove-Item "$epoPath\.git-auto-backup.log" -Force }
            git stash push -m "auto-backup-stash-$timestamp" --include-untracked 2>$null
            if ($LASTEXITCODE -ne 0) { throw "git stash failed" }
            Write-Log "[STASH] Local changes saved."

            # 2. Pull (merge, no rebase)
            $behind = git rev-list --count HEAD..origin/main 2>$null
            if ($behind -gt 0) {
                Write-Log "[PULL] origin/main is $behind commit(s) ahead. Pulling..."
                git pull origin main --quiet 2>$null
                if ($LASTEXITCODE -ne 0) {
                    Write-Log "[ERROR] git pull failed. Restoring stash and stopping."
                    git stash pop 2>$null
                    exit 1
                }
                Write-Log "[PULL] Synced with origin/main."
            }

            # 3. Stash Pop (restore local changes)
            git stash pop 2>$null
            if ($LASTEXITCODE -ne 0) {
                Write-Log "[ERROR] git stash pop failed (conflict?). Manual fix required."
                exit 1
            }
            Write-Log "[POP] Stash restored."

            # 4. Conflict check
            $conflicts = git diff --name-only --diff-filter=U 2>$null
            if ($conflicts) {
                Write-Log "[CONFLICT] Conflict detected in: $($conflicts -join ', ')"
                Write-Log "[STOP] Auto-backup stopped. Resolve conflicts and restart."
                exit 1
            }

            # 5. Add + Commit + Push
            git add -A 2>$null
            git commit -m "auto-backup: $timestamp" 2>$null
            if ($LASTEXITCODE -ne 0) { throw "git commit failed" }

            git push origin main 2>$null
            if ($LASTEXITCODE -ne 0) { throw "git push failed" }

            Write-Log "[DONE] Backup pushed to origin/main."
        }
    } catch {
        Write-Log "[ERROR] $_"
    }

    Start-Sleep -Seconds $intervalSeconds
}

