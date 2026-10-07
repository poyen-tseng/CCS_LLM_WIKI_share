// CCS 21 scripting: load a program halted at main, wait for the scope to arm, then run once.
// Do not launch this while another session owns the XDS110.
//
//   C:\ti\ccs2101\ccs\scripting\run.bat edge_run.js --ccxml <file.ccxml> --program <file.out>
//       [--core C28xx_CPU1] [--signal-dir <dir>] [--wait-ms 90000] [--hold-ms 40000]
//
// Env fallbacks: EDGE_CCXML, EDGE_PROGRAM, EDGE_SIGNAL_DIR (default %TEMP%).
const fs = require("fs");
const path = require("path");

function sleep(ms) {
    Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, ms);
}

function parseArgs() {
    const here = path.resolve(__filename).toLowerCase();
    const at = process.argv.findIndex((a) => path.resolve(a).toLowerCase() === here);
    if (at < 0) throw new Error("cannot find this script in process.argv");
    const argv = process.argv.slice(at + 1);
    const opts = {};
    for (let i = 0; i < argv.length; i++) {
        if (!argv[i].startsWith("--") || i + 1 >= argv.length) throw new Error("bad argument " + argv[i]);
        opts[argv[i].slice(2)] = argv[++i];
    }
    return {
        ccxml: opts.ccxml || process.env.EDGE_CCXML,
        program: opts.program || process.env.EDGE_PROGRAM,
        core: opts.core || "C28xx_CPU1",
        signalDir: opts["signal-dir"] || process.env.EDGE_SIGNAL_DIR || process.env.TEMP,
        waitMs: Number(opts["wait-ms"] || 90000),
        holdMs: Number(opts["hold-ms"] || 40000),
    };
}

const args = parseArgs();
if (!args.ccxml || !args.program) {
    throw new Error("need --ccxml and --program (or EDGE_CCXML / EDGE_PROGRAM)");
}

const ready = path.join(args.signalDir, "gpio_edge_ready.txt");
const go = path.join(args.signalDir, "gpio_edge_go.txt");
const ran = path.join(args.signalDir, "gpio_edge_ran.txt");
for (const f of [ready, go, ran]) {
    try { fs.unlinkSync(f); } catch (e) {}
}

const ds = initScripting();
ds.setScriptingTimeout(180000);
ds.configure(path.resolve(args.ccxml));
const session = ds.openSession(args.core);
console.log("connecting");
session.target.connect();
console.log("reset-then-load");
session.target.reset();
session.memory.loadProgram(path.resolve(args.program));
try { session.target.halt(); } catch (e) { console.log("halt " + e); }
const pc = session.registers.read("PC");
console.log("PC 0x" + pc.toString(16));
// Boot ROM is at 0x3Fxxxx; a reset after loadProgram leaves the PC there.
if (pc > 0x10000n) {
    throw new Error("PC is not in the application");
}
fs.writeFileSync(ready, "0x" + pc.toString(16) + "\n");
console.log("READY");

const t0 = Date.now();
while (!fs.existsSync(go)) {
    if (Date.now() - t0 > args.waitMs) throw new Error("timed out waiting for scope arm");
    sleep(50);
}
console.log("running");
session.target.run(false);
fs.writeFileSync(ran, "ran\n");
console.log("RAN");
sleep(args.holdMs);
ds.shutdown();
