[CmdletBinding()]
param(
    [ValidateRange(1, 50)]
    [int]$LogCount = 8
)

$ErrorActionPreference = 'Stop'

$searchPath = (Get-Location).ProviderPath
$repoRoot = $null
while (-not [string]::IsNullOrWhiteSpace($searchPath)) {
    if (Test-Path -LiteralPath (Join-Path -Path $searchPath -ChildPath '.git')) {
        $repoRoot = $searchPath
        break
    }

    $parent = [System.IO.Directory]::GetParent($searchPath)
    if ($null -eq $parent) {
        break
    }
    $searchPath = $parent.FullName
}
if ([string]::IsNullOrWhiteSpace($repoRoot)) {
    throw 'Current location is not inside a Git repository.'
}
$script:GitBaseArguments = @('-c', "safe.directory=$repoRoot")

function Invoke-GitReadOnly {
    param(
        [Parameter(Mandatory = $true)]
        [string[]]$Arguments    )

    & git @script:GitBaseArguments @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Git command failed: git $($Arguments -join ' ')"
    }
}

Push-Location -LiteralPath $repoRoot
try {
    Write-Host '=== Repository ==='
    Write-Host "Root: $repoRoot"
    Invoke-GitReadOnly -Arguments @('status', '--short', '--branch')
    Write-Host "`n=== Working tree (not staged) ==="
    Invoke-GitReadOnly -Arguments @('diff', '--name-status')

    Write-Host "`n=== Staging area ==="
    Invoke-GitReadOnly -Arguments @('diff', '--cached', '--name-status')

    Write-Host "`n=== Local commits ==="
    Invoke-GitReadOnly -Arguments @('log', '--oneline', '--decorate', "-$LogCount")

    Write-Host "`n=== Remotes ==="
    $remoteNames = @(& git @script:GitBaseArguments remote)
    if ($LASTEXITCODE -ne 0) {
        throw 'Git command failed: git remote'
    }
    if ($remoteNames.Count -eq 0) {        Write-Host '(not configured)'
    }
    else {
        Invoke-GitReadOnly -Arguments @('remote', '-v')
    }
}
finally {
    Pop-Location
}