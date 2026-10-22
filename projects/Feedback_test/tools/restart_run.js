// DSS restart + run for Feedback_test. Does not re-flash.
// Connects, loads symbols so restart knows code_start, restarts, runs, disconnects.
//
//   C:\ti\ccs2101\ccs\ccs_base\scripting\bin\dss.bat restart_run.js

importPackage(Packages.com.ti.debug.engine.scripting);
importPackage(Packages.com.ti.ccstudio.scripting.environment);
importPackage(Packages.java.lang);

var OUT_FILE = "../Debug/Feedback_test.out";
var CCXML = "../targetConfigs/TMS320F280049C.ccxml";
var SESSION_NAME = "Texas Instruments XDS110 USB Debug Probe/C28xx_CPU1";

var script = ScriptingEnvironment.instance();
var debugServer = null;
var debugSession = null;
var connected = false;
var restarted = false;

try {
    debugServer = script.getServer("DebugServer.1");
    debugServer.setConfig(CCXML);
    debugSession = debugServer.openSession(SESSION_NAME);

    try {
        debugSession.target.connect();
        connected = true;
        java.lang.System.out.println("CONNECT_OK");
    } catch (connectErr) {
        java.lang.System.out.println("CONNECT_FAIL " + connectErr);
    }

    if (connected) {
        try {
            // Symbols only. loadProgram would erase and reprogram flash.
            debugSession.symbol.load(OUT_FILE);
            debugSession.target.restart();
            restarted = true;
            java.lang.System.out.println("RESTART_OK");
        } catch (restartErr) {
            java.lang.System.out.println("RESTART_FAIL " + restartErr);
        }
    }

    if (restarted) {
        try {
            debugSession.target.runAsynch();
            java.lang.System.out.println("RUN_OK");
        } catch (runErr) {
            java.lang.System.out.println("RUN_FAIL " + runErr);
        }

        try {
            Thread.sleep(1500);
        } catch (sleepErr) {
            java.lang.System.out.println("SLEEP_FAIL " + sleepErr);
        }
    }

    if (connected) {
        try {
            debugSession.target.disconnect();
            java.lang.System.out.println("DISCONNECT_OK");
        } catch (discErr) {
            java.lang.System.out.println("DISCONNECT_FAIL " + discErr);
        }
    }
} catch (err) {
    java.lang.System.out.println("CONNECT_FAIL " + err);
} finally {
    try {
        if (debugSession != null) {
            debugSession.terminate();
        }
    } catch (termErr) {
        java.lang.System.out.println("TERMINATE_FAIL " + termErr);
    }
    try {
        if (debugServer != null) {
            debugServer.stop();
        }
    } catch (stopErr) {
        java.lang.System.out.println("STOP_FAIL " + stopErr);
    }
}
