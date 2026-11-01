// The Pi worker's policy (dev-workflows.node.worker): every tool_call is sent to the Builder's policy
// (`python -m fichero_builder.pi_rpc policy`, argv in FICHERO_PI_POLICY_ARGV) and runs only on an exact ALLOW.
// Fail closed: no argv, a non-zero exit, a timeout, any other output, or a throw in here all BLOCK (Pi turns a
// throw into "Extension failed, blocking execution"). FICHERO_PI_POLICY_CRASH=1 throws on purpose: the test that
// proves a crashing extension blocks. ponytail: spawnSync per call; a pipe-held python if latency ever matters.
import { spawnSync } from "node:child_process";

export default function (pi: any) {
  pi.on("tool_call", async (event: any) => {
    if (process.env.FICHERO_PI_POLICY_CRASH) throw new Error("policy extension crashed on purpose");
    const raw = process.env.FICHERO_PI_POLICY_ARGV;
    if (!raw) return { block: true, reason: "policy: FICHERO_PI_POLICY_ARGV is unset; every tool is refused" };
    const argv: string[] = JSON.parse(raw);
    const r = spawnSync(argv[0], argv.slice(1), {
      input: JSON.stringify({ toolName: event.toolName, input: event.input }),
      encoding: "utf8", timeout: 20000, env: process.env,
    });
    if (r.status === 0 && (r.stdout || "").trim() === "ALLOW") return;
    const why = ((r.stderr || "") + (r.stdout || "") || String(r.error || "no answer")).trim().slice(0, 500);
    return { block: true, reason: `policy: ${why}` };
  });
}
