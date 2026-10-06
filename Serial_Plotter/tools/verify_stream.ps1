# Serial_Plotter stream check for LAUNCHXL-F280049C SCIA on the XDS110 COM port.
# Opens the port. Do not run this from a build that must leave the board alone.
# Usage: powershell -File .\verify_stream.ps1 -PortName COM4

param(
    [string]$PortName = "COM4",
    [int]$BaudRate = 115200,
    [double]$DiscardSeconds = 0.3,
    [double]$CaptureSeconds = 5.0
)

$ErrorActionPreference = "Stop"

# Same 256 codes as main.c sineTable. Generated as
# round((1.65 + 1.35*sin(2*pi*i/256)) / 3.3 * 4095), i = 0..255.
# Endpoints: [0]=2048, [64]=3723, [192]=372. One step per 2 ms sample
# is 500/256 = 1.953125 Hz.
$SineCsv = @'
2048,2089,2130,2171,2212,2253,2293,2334,2374,2415,2455,2494,2534,2573,2612,2650,2689,2726,2764,2801,2837,2873,2909,2944,2978,3012,3045,3078,3110,3142,3173,3203,3232,3261,3289,3316,3342,3368,3393,3417,3440,3463,3484,3505,3525,3544,3562,3579,3595,3610,3625,3638,3651,3662,3673,3682,3691,3698,3705,3710,3715,3718,3721,3722,3723,3722,3721,3718,3715,3710,3705,3698,3691,3682,3673,3662,3651,3638,3625,3610,3595,3579,3562,3544,3525,3505,3484,3463,3440,3417,3393,3368,3342,3316,3289,3261,3232,3203,3173,3142,3110,3078,3045,3012,2978,2944,2909,2873,2837,2801,2764,2726,2689,2650,2612,2573,2534,2494,2455,2415,2374,2334,2293,2253,2212,2171,2130,2089,2048,2006,1965,1924,1883,1842,1802,1761,1721,1680,1640,1601,1561,1522,1483,1445,1406,1369,1331,1294,1258,1222,1186,1151,1117,1083,1050,1017,985,953,922,892,863,834,806,779,753,727,702,678,655,632,611,590,570,551,533,516,500,485,470,457,444,433,422,413,404,397,390,385,380,377,374,373,372,373,374,377,380,385,390,397,404,413,422,433,444,457,470,485,500,516,533,551,570,590,611,632,655,678,702,727,753,779,806,834,863,892,922,953,985,1017,1050,1083,1117,1151,1186,1222,1258,1294,1331,1369,1406,1445,1483,1522,1561,1601,1640,1680,1721,1761,1802,1842,1883,1924,1965,2006
'@

function Get-Verdict {
    param([bool]$Ok)
    if ($Ok) { return "PASS" }
    return "FAIL"
}

function Test-SineContinuity {
    param(
        [int[]]$Values,
        [int[]]$Table
    )
    if ($Values.Count -lt 2) { return $false }
    $count = $Table.Count
    $possible = New-Object "System.Collections.Generic.List[int]"
    for ($i = 0; $i -lt $count; $i++) {
        if ($Table[$i] -eq $Values[0]) {
            [void]$possible.Add($i)
        }
    }
    if ($possible.Count -eq 0) { return $false }
    for ($k = 1; $k -lt $Values.Count; $k++) {
        $next = New-Object "System.Collections.Generic.List[int]"
        foreach ($index in $possible) {
            $follow = ($index + 1) % $count
            if ($Table[$follow] -eq $Values[$k]) {
                [void]$next.Add($follow)
            }
        }
        if ($next.Count -eq 0) { return $false }
        $possible = $next
    }
    return $true
}

function Get-SineFrequencyHz {
    param(
        [int[]]$DacCodes,
        [double]$SampleHz
    )
    if ($SampleHz -le 0) { return $null }
    $previous = 0
    $crossings = New-Object "System.Collections.Generic.List[int]"
    for ($i = 0; $i -lt $DacCodes.Count; $i++) {
        $delta = $DacCodes[$i] - 2048
        $sign = 0
        if ($delta -gt 0) { $sign = 1 }
        elseif ($delta -lt 0) { $sign = -1 }
        else { continue }
        if (($previous -ne 0) -and ($sign -ne $previous)) {
            [void]$crossings.Add($i)
        }
        $previous = $sign
    }
    if ($crossings.Count -lt 2) { return $null }
    $span = $crossings[$crossings.Count - 1] - $crossings[0]
    if ($span -le 0) { return $null }
    $halfCycles = $crossings.Count - 1
    return (($halfCycles / 2.0) * $SampleHz) / $span
}

$serial = $null
$exitCode = 1

try {
    $table = @($SineCsv.Trim().Split(",") | ForEach-Object { [int]$_ })
    if ($table.Count -ne 256) {
        throw "sine table length is $($table.Count), expected 256"
    }

    $serial = New-Object System.IO.Ports.SerialPort
    $serial.PortName = $PortName
    $serial.BaudRate = $BaudRate
    $serial.DataBits = 8
    $serial.Parity = [System.IO.Ports.Parity]::None
    $serial.StopBits = [System.IO.Ports.StopBits]::One
    $serial.Handshake = [System.IO.Ports.Handshake]::None
    $serial.DtrEnable = $false
    $serial.RtsEnable = $false
    $serial.ReadTimeout = 500
    $serial.WriteTimeout = 500
    $serial.Encoding = [System.Text.Encoding]::ASCII
    $serial.Open()
    $serial.DtrEnable = $false
    $serial.RtsEnable = $false
    $serial.DiscardInBuffer()

    $pending = ""
    $clock = [System.Diagnostics.Stopwatch]::StartNew()
    while ($clock.Elapsed.TotalSeconds -lt $DiscardSeconds) {
        if ($serial.BytesToRead -gt 0) {
            $pending += $serial.ReadExisting()
        }
        else {
            Start-Sleep -Milliseconds 5
        }
    }
    $pending = ""

    $lines = New-Object "System.Collections.Generic.List[string]"
    $synced = $false
    $capture = [System.Diagnostics.Stopwatch]::StartNew()
    while ($capture.Elapsed.TotalSeconds -lt $CaptureSeconds) {
        if ($serial.BytesToRead -gt 0) {
            $pending += $serial.ReadExisting()
            while ($true) {
                $newline = $pending.IndexOf("`n")
                if ($newline -lt 0) { break }
                $raw = $pending.Substring(0, $newline)
                $pending = $pending.Substring($newline + 1)
                if (-not $synced) {
                    $synced = $true
                    continue
                }
                $text = $raw.Trim()
                if ($text.Length -gt 0) {
                    [void]$lines.Add($text)
                }
            }
        }
        else {
            Start-Sleep -Milliseconds 5
        }
    }

    $pattern = [regex]'^(\d{1,4}),(\d{1,4})$'
    $malformed = 0
    $dac = New-Object "System.Collections.Generic.List[int]"
    $adc = New-Object "System.Collections.Generic.List[int]"
    foreach ($line in $lines) {
        $match = $pattern.Match($line)
        if (-not $match.Success) {
            $malformed++
            continue
        }
        $dacCode = [int]$match.Groups[1].Value
        $adcCode = [int]$match.Groups[2].Value
        if (($dacCode -gt 4095) -or ($adcCode -gt 4095)) {
            $malformed++
            continue
        }
        [void]$dac.Add($dacCode)
        [void]$adc.Add($adcCode)
    }

    $rate = 0.0
    if ($CaptureSeconds -gt 0) {
        $rate = $lines.Count / $CaptureSeconds
    }
    $ratePass = ($rate -ge (500.0 * 0.95)) -and ($rate -le (500.0 * 1.05))
    $formatPass = ($malformed -eq 0)

    $diffMean = 0.0
    $diffMaxAbs = 0
    $adcMin = 0
    $adcMax = 0
    $continuous = $false
    if ($dac.Count -gt 0) {
        $signed = 0.0
        $adcMin = $adc[0]
        $adcMax = $adc[0]
        for ($i = 0; $i -lt $dac.Count; $i++) {
            $delta = $adc[$i] - $dac[$i]
            $signed += $delta
            $abs = [Math]::Abs($delta)
            if ($abs -gt $diffMaxAbs) { $diffMaxAbs = $abs }
            if ($adc[$i] -lt $adcMin) { $adcMin = $adc[$i] }
            if ($adc[$i] -gt $adcMax) { $adcMax = $adc[$i] }
        }
        $diffMean = $signed / $dac.Count
        $continuous = Test-SineContinuity -Values ([int[]]$dac.ToArray()) -Table ([int[]]$table)
    }
    $trackPass = $continuous -and ($dac.Count -ge 2) -and ($diffMaxAbs -le 50)

    $freq = $null
    if ($dac.Count -ge 2) {
        $freq = Get-SineFrequencyHz -DacCodes ([int[]]$dac.ToArray()) -SampleHz $rate
    }
    $expectedHz = 500.0 / 256.0
    $freqPass = $false
    if ($null -ne $freq) {
        $freqPass = ($freq -ge ($expectedHz * 0.95)) -and ($freq -le ($expectedHz * 1.05))
    }

    $overall = $ratePass -and $formatPass -and $trackPass -and $freqPass
    $inv = [System.Globalization.CultureInfo]::InvariantCulture

    Write-Output ("PORT: {0}" -f $PortName)
    Write-Output ("LINES: {0}" -f $lines.Count)
    Write-Output ("RATE_HZ: {0}" -f $rate.ToString("0.00", $inv))
    Write-Output ("MALFORMED: {0}" -f $malformed)
    Write-Output ("CONTINUITY: {0}" -f (Get-Verdict $continuous))
    Write-Output ("ADC_MIN: {0}" -f $adcMin)
    Write-Output ("ADC_MAX: {0}" -f $adcMax)
    Write-Output ("DIFF_MEAN: {0}" -f $diffMean.ToString("0.00", $inv))
    Write-Output ("DIFF_MAX_ABS: {0}" -f $diffMaxAbs)
    if ($null -eq $freq) {
        Write-Output "FREQ_HZ: n/a"
    }
    else {
        Write-Output ("FREQ_HZ: {0}" -f $freq.ToString("0.000", $inv))
    }
    Write-Output ("RATE: {0}" -f (Get-Verdict $ratePass))
    Write-Output ("FORMAT: {0}" -f (Get-Verdict $formatPass))
    Write-Output ("TRACKING: {0}" -f (Get-Verdict $trackPass))
    Write-Output ("FREQ: {0}" -f (Get-Verdict $freqPass))
    Write-Output ("OVERALL: {0}" -f (Get-Verdict $overall))

    if ($overall) { $exitCode = 0 }
    else { $exitCode = 1 }
}
catch {
    Write-Output ("ERROR: {0}" -f $_.Exception.Message)
    Write-Output "RATE: FAIL"
    Write-Output "FORMAT: FAIL"
    Write-Output "TRACKING: FAIL"
    Write-Output "FREQ: FAIL"
    Write-Output "OVERALL: FAIL"
    $exitCode = 1
}
finally {
    if ($null -ne $serial) {
        try {
            if ($serial.IsOpen) { $serial.Close() }
        }
        catch { }
        try { $serial.Dispose() }
        catch { }
    }
}

exit $exitCode
