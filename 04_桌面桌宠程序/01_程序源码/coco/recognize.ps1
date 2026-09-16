# Local microphone recognition only. No shell input comes from recognized text.
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$recognizer = $null
try {
    Add-Type -AssemblyName System.Speech
    $info = [System.Speech.Recognition.SpeechRecognitionEngine]::InstalledRecognizers() |
        Where-Object { $_.Culture.Name -eq 'zh-CN' } | Select-Object -First 1
    if ($null -eq $info) { throw 'NO_ZH_RECOGNIZER' }
    $recognizer = [System.Speech.Recognition.SpeechRecognitionEngine]::new($info)
    $recognizer.LoadGrammar([System.Speech.Recognition.DictationGrammar]::new())
    $recognizer.InitialSilenceTimeout = [TimeSpan]::FromSeconds(8)
    $recognizer.BabbleTimeout = [TimeSpan]::FromSeconds(15)
    $recognizer.EndSilenceTimeout = [TimeSpan]::FromMilliseconds(900)
    $recognizer.EndSilenceTimeoutAmbiguous = [TimeSpan]::FromMilliseconds(1300)
    $recognizer.SetInputToDefaultAudioDevice()
    [Console]::WriteLine('{"status":"listening"}')
    $result = $recognizer.Recognize([TimeSpan]::FromSeconds(25))
    if ($null -eq $result) {
        [Console]::WriteLine('{"text":"","confidence":0}')
    } else {
        [Console]::WriteLine((@{text=$result.Text;confidence=$result.Confidence} | ConvertTo-Json -Compress))
    }
} catch {
    $code = if ($_.Exception.Message -match 'NO_ZH_RECOGNIZER') { 'language' } else { 'microphone' }
    [Console]::WriteLine((@{error=$code} | ConvertTo-Json -Compress))
    exit 1
} finally {
    if ($null -ne $recognizer) { $recognizer.Dispose() }
}
