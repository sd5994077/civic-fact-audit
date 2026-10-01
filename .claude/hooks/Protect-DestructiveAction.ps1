[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'

$stdin = [Console]::In.ReadToEnd()

try {
    $payload = $stdin | ConvertFrom-Json
}
catch {
    exit 0
}

$command = $payload.tool_input.command
if ([string]::IsNullOrWhiteSpace($command)) {
    exit 0
}

# Destructive patterns worth a mandatory human confirmation. Includes
# alembic downgrade / db drop for this project's Postgres + migrations.
$destructivePatterns = @(
    'rm\s+-rf\s+/',
    'rm\s+-rf\s+\*',
    'Remove-Item\s+.*-Recurse.*-Force',
    'rd\s+/s\s+/q',
    'git\s+push\s+.*--force',
    'git\s+reset\s+--hard',
    'git\s+clean\s+-[a-z]*d[a-z]*f',
    'alembic\s+downgrade',
    'DROP\s+DATABASE',
    'DROP\s+TABLE',
    'docker\s+compose\s+down\s+.*-v',
    'Format-Volume',
    'diskpart'
)

foreach ($pattern in $destructivePatterns) {
    if ($command -match $pattern) {
        $output = [ordered]@{
            hookSpecificOutput = [ordered]@{
                hookEventName            = 'PreToolUse'
                permissionDecision       = 'ask'
                permissionDecisionReason = "Matched destructive-command pattern '$pattern'. Confirm before running: $command"
            }
        }
        $output | ConvertTo-Json -Depth 5
        exit 0
    }
}

exit 0
