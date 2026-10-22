// DSS flash + run for Feedback_test.
// Do not launch this while another session owns the XDS110.
//
//   C:\ti\ccs2101\ccs\ccs_base\scripting\bin\dss.bat flash_and_run.js

importPackage(Packages.com.ti.debug.engine.scripting);
importPackage(Packages.com.ti.ccstudio.scripting.environment);
importPackage(Packages.java.lang);

var script = ScriptingEnvironment.instance();
var debugServer = null;
var debugSession = null;
var flashOk = false;

var ccxml = "../targetConfigs/TMS320F280049C.ccxml";
var program = "../Debug/Feedback_test.out";

try {
    debugServer = script.getServer("DebugServer.1");
    debugServer.setConfig(ccxml);
    debugSession = debugServer.openSession("Texas Instruments XDS110 USB Debug Probe/C28xx_CPU1");
    debugSession.target.connect();

    // loadProgram programs the on-chip flash image, then verifyProgram checks it.
    debugSession.memory.loadProgram(program);
    debugSession.memory.verifyProgram(program);
    java.lang.System.out.println("VERIFY_OK");
    java.lang.System.out.println("FLASH_OK");
    flashOk = true;

    debugSession.target.runAsynch();
    debugSession.target.disconnect();
} catch (err) {
    if (!flashOk) {
        java.lang.System.out.println("FLASH_FAIL " + err);
    } else {
        java.lang.System.out.println("RUN_FAIL " + err);
    }
} finally {
    if (debugSession !== null) {
        try {
            debugSession.terminate();
        } catch (termErr) {
            java.lang.System.out.println("TERMINATE_FAIL " + termErr);
        }
    }
    if (debugServer !== null) {
        try {
            debugServer.stop();
        } catch (stopErr) {
            java.lang.System.out.println("STOP_FAIL " + stopErr);
        }
    }
}
