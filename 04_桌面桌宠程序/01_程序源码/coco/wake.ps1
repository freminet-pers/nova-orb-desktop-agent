param([string]$Phrase = 'hey Nova', [string]$WaveFile = '')
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)

# Kept as a diagnostic fallback only. The app uses its local Whisper worker
# because this machine exposes zh-CN System.Speech but no English recognizer.
$allowed = @(
    'hey nova',
    'are you there nova',
    'hi nova',
    'hello nova'
)
function Normalize([string]$Value) {
    if ($null -eq $Value) { return '' }
    $Value.ToLowerInvariant().Replace([char]0x2019, [char]0x27) -replace '[^\p{L}\p{Nd}\s]', ' ' -replace '\s+', ' '
}
$allowed = @($allowed | ForEach-Object { (Normalize $_).Trim() })
$requested = (Normalize $Phrase).Trim()
if ($requested -notin $allowed) {
    [Console]::WriteLine((@{error='UnsupportedPhrase'; automaticWake=$false} | ConvertTo-Json -Compress))
    exit 2
}
$engine = $null
try {
    Add-Type -AssemblyName System.Speech
    $info = [System.Speech.Recognition.SpeechRecognitionEngine]::InstalledRecognizers() |
        Where-Object { $_.Culture.Name -like 'en-*' } | Select-Object -First 1
    if ($null -eq $info) {
        [Console]::WriteLine((@{error='NoEnglishRecognizer'; automaticWake=$false} | ConvertTo-Json -Compress))
        exit 3
    }
    $engine = [System.Speech.Recognition.SpeechRecognitionEngine]::new($info)
    foreach ($item in $allowed) {
        $builder = [System.Speech.Recognition.GrammarBuilder]::new()
        $builder.Culture = $info.Culture
        $builder.Append($item)
        $engine.LoadGrammar([System.Speech.Recognition.Grammar]::new($builder))
    }
    if ($WaveFile) { $engine.SetInputToWaveFile($WaveFile) }
    else { $engine.SetInputToDefaultAudioDevice() }
    [Console]::WriteLine((@{ready=$true; culture=$info.Culture.Name; phrases=$allowed} | ConvertTo-Json -Compress))
    while ($true) {
        $result = $engine.Recognize([TimeSpan]::FromSeconds(3))
        if ($null -ne $result) {
            $text = (Normalize $result.Text).Trim()
            if ($result.Confidence -ge 0.78 -and $text -in $allowed) {
                [Console]::WriteLine((@{wake=$true; phrase=$text; confidence=$result.Confidence} | ConvertTo-Json -Compress))
            }
        }
        if ($WaveFile) { break }
    }
} catch {
    [Console]::WriteLine((@{error=$_.Exception.GetType().Name; automaticWake=$false} | ConvertTo-Json -Compress))
    exit 1
} finally {
    if ($null -ne $engine) { $engine.Dispose() }
}
