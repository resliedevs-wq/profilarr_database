param([string]$Python = 'python')
$ErrorActionPreference = 'Stop'
Push-Location (Split-Path $PSScriptRoot -Parent)
try {
    $casesJson = & $Python -m cjk.regex_cases
    if ($LASTEXITCODE -ne 0) { throw 'Could not generate regex cases' }
    $cases = $casesJson | ConvertFrom-Json
    foreach ($case in $cases) {
        $actual = [regex]::IsMatch($case.title, $case.pattern, [System.Text.RegularExpressions.RegexOptions]::None, [TimeSpan]::FromSeconds(2))
        if ($actual -ne $case.expected) { throw "Regex mismatch: $($case.title)" }
    }
    Write-Output "$($cases.Count) .NET regex cases passed"
}
finally { Pop-Location }
