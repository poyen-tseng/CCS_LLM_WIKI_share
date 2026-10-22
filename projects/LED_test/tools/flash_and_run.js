// DSS flash loader for LED_test on LAUNCHXL-F280049C (C28xx_CPU1).
// Modeled on ccs_base/scripting/examples/DebugServerExamples/msp430f5529_loadProgram.js.
// Do not call target.reset(): a JTAG reset can leave the device in boot-ROM wait.

importPackage(Packages.com.ti.debug.engine.scripting);
importPackage(Packages.com.ti.ccstudio.scripting.environment);
importPackage(Packages.java.lang);

var OUT_FILE = "../Debug/LED_test.out";
var CCXML = "../targetConfigs/TMS320F280049C.ccxml";
var SESSION_NAME = "Texas Instruments XDS110 USB Debug Probe/C28xx_CPU1";

var script = ScriptingEnvironment.instance();
try {
    script.traceSetConsoleLevel(TraceLevel.INFO);
} catch (e) {
    // TraceLevel is optional; keep going without it.
}

var debugServer = null;
var debugSession = null;
var connected = false;
var abort = false;

function fail(step, err) {
    print(step + "_FAIL " + err);
    abort = true;
}

try {
    try {
        debugServer = script.getServer("DebugServer.1");
        debugServer.setConfig(CCXML);
    } catch (e) {
        fail("CONFIG", e);
    }

    if (!abort) {
        try {
            debugSession = debugServer.openSession(SESSION_NAME);
        } catch (e) {
            fail("SESSION", e);
        }
    }

    if (!abort) {
        try {
            debugSession.target.connect();
            connected = true;
            print("CONNECT_OK");
        } catch (e) {
            fail("CONNECT", e);
        }
    }

    if (!abort) {
        try {
            debugSession.memory.loadProgram(OUT_FILE);
            print("FLASH_LOAD_OK");
        } catch (e) {
            fail("FLASH_LOAD", e);
        }
    }

    if (!abort) {
        try {
            debugSession.memory.verifyProgram(OUT_FILE);
            print("VERIFY_OK");
        } catch (e) {
            var verifyMsg = "" + e;
            if (verifyMsg.indexOf("Cannot find function") >= 0 ||
                verifyMsg.indexOf("is not a function") >= 0 ||
                verifyMsg.indexOf("verifyProgram") >= 0 && verifyMsg.indexOf("TypeError") >= 0) {
                print("VERIFY_UNAVAILABLE");
            } else {
                print("VERIFY_FAIL " + verifyMsg);
            }
        }
    }

    if (!abort) {
        try {
            var pc = debugSession.expression.evaluate("PC");
            var pcText = "" + pc;
            var pcVal;
            if (pcText.indexOf("0x") === 0 || pcText.indexOf("0X") === 0) {
                pcVal = Long.parseLong(pcText.substring(2), 16);
            } else {
                pcVal = Long.parseLong(pcText);
            }
            print("PC 0x" + Long.toHexString(pcVal));
        } catch (e) {
            print("PC_FAIL " + e);
        }
    }

    if (!abort) {
        try {
            debugSession.target.runAsynch();
            print("RUN_OK");
        } catch (e) {
            print("RUN_FAIL " + e);
        }
    }

    if (connected) {
        try {
            Thread.sleep(1500);
        } catch (e) {
            print("SLEEP_FAIL " + e);
        }
    }

    if (connected) {
        try {
            debugSession.target.disconnect();
            print("DISCONNECT_OK");
        } catch (e) {
            print("DISCONNECT_FAIL " + e);
        }
    }
} finally {
    try {
        if (debugSession != null) {
            debugSession.terminate();
        }
    } catch (e) {
        print("TERMINATE_FAIL " + e);
    }
    try {
        if (debugServer != null) {
            debugServer.stop();
        }
    } catch (e) {
        print("STOP_FAIL " + e);
    }
}
