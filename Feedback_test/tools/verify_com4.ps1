param(
    [string]$PortName = "COM4"
)

$ErrorActionPreference = "Stop"

function Read-ExactBytes {
    param(
        [System.IO.Ports.SerialPort]$Serial,
        [int]$Count,
        [int]$TimeoutMs
    )

    $buf = New-Object byte[] $Count
    $got = 0
    $deadline = [DateTime]::UtcNow.AddMilliseconds($TimeoutMs)

    while ($got -lt $Count) {
        $leftMs = ($deadline - [DateTime]::UtcNow).TotalMilliseconds
        if ($leftMs -le 0) {
            return $null
        }

        $available = $Serial.BytesToRead
        if ($available -le 0) {
            Start-Sleep -Milliseconds 5
            continue
        }

        $n = $Count - $got
        if ($available -lt $n) {
            $n = $available
        }

        $read = $Serial.Read($buf, $got, $n)
        if ($read -le 0) {
            Start-Sleep -Milliseconds 5
            continue
        }
        $got += $read
    }

    return ,$buf
}

function Test-SameBytes {
    param(
        [byte[]]$Left,
        [byte[]]$Right
    )

    if ($null -eq $Left -or $null -eq $Right) {
        return $false
    }
    if ($Left.Length -ne $Right.Length) {
        return $false
    }

    $i = 0
    while ($i -lt $Left.Length) {
        if ($Left[$i] -ne $Right[$i]) {
            Write-Host ("MISMATCH index=" + $i + " expected=" + $Right[$i] + " actual=" + $Left[$i])
            return $false
        }
        $i++
    }
    return $true
}

function Write-TokenLines {
    param(
        [string]$Text,
        [string]$Token
    )

    $found = $false
    $parts = $Text -split "\r\n|\n|\r"
    foreach ($part in $parts) {
        if ($part.Contains($Token)) {
            Write-Output $part
            $found = $true
        }
    }
    if (-not $found) {
        Write-Output ($Token + " <not captured>")
    }
}

function Write-PortBytes {
    param(
        [System.IO.Ports.SerialPort]$Serial,
        [byte[]]$Data
    )

    $Serial.BaseStream.Write($Data, 0, $Data.Length)
    $Serial.BaseStream.Flush()
}

$port = $null
$exitCode = 1
$echoAscii = "FAIL"
$echoBinary = "FAIL"

try {
    $port = New-Object System.IO.Ports.SerialPort
    $port.PortName = $PortName
    $port.BaudRate = 115200
    $port.Parity = [System.IO.Ports.Parity]::None
    $port.DataBits = 8
    $port.StopBits = [System.IO.Ports.StopBits]::One
    $port.Handshake = [System.IO.Ports.Handshake]::None
    $port.ReadTimeout = 200
    $port.WriteTimeout = 1000
    # Leave DTR/RTS deasserted. Toggling DTR can reset some XDS110 UART bridges.
    $port.DtrEnable = $false
    $port.RtsEnable = $false
    $port.Open()

    $captured = New-Object System.Text.StringBuilder
    $deadline = [DateTime]::UtcNow.AddSeconds(6)
    while ([DateTime]::UtcNow -lt $deadline) {
        $available = $port.BytesToRead
        if ($available -gt 0) {
            $chunk = New-Object byte[] $available
            $nread = $port.Read($chunk, 0, $available)
            if ($nread -gt 0) {
                $text = [System.Text.Encoding]::ASCII.GetString($chunk, 0, $nread)
                [void]$captured.Append($text)
            }
        } else {
            Start-Sleep -Milliseconds 20
        }

        $soFar = $captured.ToString()
        if ($soFar.Contains("GPIO_READBACK:") -and $soFar.Contains("SCI_LOOPBACK:")) {
            break
        }
    }

    $report = $captured.ToString()
    Write-TokenLines -Text $report -Token "GPIO_READBACK:"
    Write-TokenLines -Text $report -Token "SCI_LOOPBACK:"

    $sync = New-Object byte[] 1
    $sync[0] = [byte][char]"S"
    Write-PortBytes -Serial $port -Data $sync
    Start-Sleep -Milliseconds 300
    $port.DiscardInBuffer()

    $ascii = "HELLO_F280049C_ECHO_0123456789"
    $asciiBytes = [System.Text.Encoding]::ASCII.GetBytes($ascii)
    Write-PortBytes -Serial $port -Data $asciiBytes
    $asciiEcho = Read-ExactBytes -Serial $port -Count $asciiBytes.Length -TimeoutMs 2000
    if (Test-SameBytes -Left $asciiEcho -Right $asciiBytes) {
        $echoAscii = "PASS"
    }

    $expected = New-Object byte[] 256
    $b = 0
    while ($b -lt 256) {
        $expected[$b] = [byte]$b
        $b++
    }

    $binaryOk = $true
    $off = 0
    while ($off -lt 256) {
        $piece = New-Object byte[] 16
        [Array]::Copy($expected, $off, $piece, 0, 16)
        Write-PortBytes -Serial $port -Data $piece
        $got = Read-ExactBytes -Serial $port -Count 16 -TimeoutMs 2000
        if (-not (Test-SameBytes -Left $got -Right $piece)) {
            $binaryOk = $false
            break
        }
        $off += 16
    }
    if ($binaryOk) {
        $echoBinary = "PASS"
    }

    $gpioPass = $report -match "GPIO_READBACK:\s*PASS"
    $sciPass = $report -match "SCI_LOOPBACK:\s*PASS"
    if ($gpioPass -and $sciPass -and ($echoAscii -eq "PASS") -and ($echoBinary -eq "PASS")) {
        $exitCode = 0
    }
} catch {
    Write-Output ("ERROR: " + $_.Exception.Message)
    $exitCode = 1
} finally {
    if ($null -ne $port) {
        if ($port.IsOpen) {
            $port.Close()
        }
        $port.Dispose()
    }
}

if ($exitCode -eq 0) {
    Write-Output "ECHO_ASCII: PASS"
    Write-Output "ECHO_BINARY: PASS"
    Write-Output "OVERALL: PASS"
} else {
    Write-Output ("ECHO_ASCII: " + $echoAscii)
    Write-Output ("ECHO_BINARY: " + $echoBinary)
    Write-Output "OVERALL: FAIL"
}

exit $exitCode
