const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const ts = require("typescript");

async function main() {
  const temporary = fs.mkdtempSync(path.join(os.tmpdir(), "agentlocal-codex-test-"));
  const executable = path.join(temporary, "codex-fixture.js");
  fs.writeFileSync(executable, `
const readline = require("node:readline");
const output = (value) => {
  const line = JSON.stringify(value) + "\\n";
  const middle = Math.floor(line.length / 2);
  process.stdout.write(line.slice(0, middle));
  process.stdout.write(line.slice(middle));
};
let authenticated = false;
let thread = 0;
let pending;
let loginCount = 0;
readline.createInterface({ input: process.stdin }).on("line", (line) => {
  const request = JSON.parse(line);
  if (!request.method) {
    if (request.id === "approval") {
      output({ method: "item/agentMessage/delta", params: { threadId: pending, delta: request.result.decision } });
      output({ method: "turn/completed", params: { threadId: pending, turn: { status: "completed" } } });
    }
    return;
  }
  let result = {};
  switch (request.method) {
    case "account/read": result = { account: authenticated ? { type: "chatgpt", email: "test@example.com", planType: "plus" } : null }; break;
    case "account/login/start": result = { type: "chatgpt", loginId: "login-" + (++loginCount), authUrl: "https://auth.openai.com/test" }; authenticated = true; break;
    case "account/logout": authenticated = false; break;
    case "model/list": result = { data: [{ model: "fixture", displayName: "Fixture", isDefault: true }] }; break;
    case "thread/start": result = { thread: { id: "thread-" + (++thread) } }; break;
    case "turn/start": {
      const id = request.params.threadId;
      result = { turn: { id: "turn", status: "inProgress" } };
      output({ id: request.id, result });
      const prompt = request.params.input[0].text;
      if (prompt.includes("approval")) {
        pending = id;
        output({ id: "approval", method: "item/commandExecution/requestApproval", params: { threadId: id, command: "echo test" } });
      } else if (prompt.includes("failure")) {
        output({ method: "turn/completed", params: { threadId: id, turn: { status: "failed", error: { message: "Model unavailable" } } } });
      } else if (!prompt.includes("wait")) {
        output({ method: "item/agentMessage/delta", params: { threadId: id, delta: "Hola " } });
        output({ method: "item/agentMessage/delta", params: { threadId: id, delta: "mundo" } });
        output({ method: "turn/completed", params: { threadId: id, turn: { status: "completed" } } });
      }
      return;
    }
    case "turn/interrupt": output({ method: "turn/completed", params: { threadId: request.params.threadId, turn: { status: "interrupted" } } }); break;
  }
  if (request.id !== undefined) output({ id: request.id, result });
}).on("close", () => process.exit(0));
`);
  process.env.AGENTLOCAL_CODEX_BIN = executable;
  process.env.AGENTLOCAL_CODEX_HOME = path.join(temporary, "home");
  process.env.AGENT_REPOS_DIR = path.join(temporary, "workspace");
  const compiled = ts.transpileModule(fs.readFileSync("src/lib/codex.ts", "utf8"), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, esModuleInterop: true },
  }).outputText;
  const exportsObject = {};
  new Function("exports", "require", compiled)(exportsObject, require);
  const { codex, codexStream, localRequest } = exportsObject;
  const stream = (text, signal = new AbortController().signal) => codexStream([{ role: "user", content: text }], "fixture", true, signal);
  try {
    assert.equal(localRequest(new Request("http://localhost:3000/api/codex")), true);
    assert.equal(localRequest(new Request("http://localhost:3000/api/codex", { headers: { host: "127.0.0.1:3020", origin: "http://127.0.0.1:3020" } })), true);
    assert.equal(localRequest(new Request("http://localhost:3000/api/codex", { headers: { host: "outside.example" } })), false);
    assert.equal(localRequest(new Request("http://localhost:3000/api/codex", { headers: { "x-forwarded-for": "192.0.2.1" } })), false);
    assert.equal(localRequest(new Request("http://localhost:3000/api/codex", { headers: { "x-forwarded-for": "127.0.0.1" } })), true);
    assert.equal(localRequest(new Request("http://localhost:3000/api/codex", { headers: { origin: "https://outside.example" } })), false);
    assert.equal(localRequest(new Request("https://remote.example/api/codex")), false);
    assert.equal((await codex.status()).authenticated, false);
    assert.equal((await stream("Hola")).status, 401);
    const [first, second] = await Promise.all([codex.startLogin(), codex.startLogin()]);
    assert.equal(first.loginId, "login-1");
    assert.equal(first.loginId, second.loginId);
    const status = await codex.status();
    assert.equal(status.authenticated, true);
    assert.equal(status.models[0].id, "fixture");
    const response = await stream("Hola");
    const text = await response.text();
    assert.match(text, /Hola /);
    assert.match(text, /mundo/);
    assert.match(text, /\[DONE\]/);
    const approvalReady = new Promise((resolve) => {
      const listener = (message) => {
        if (message.method === "item/commandExecution/requestApproval") {
          codex.events.off("message", listener);
          resolve();
        }
      };
      codex.events.on("message", listener);
    });
    const approvalResponse = await stream("approval");
    await approvalReady;
    assert.equal((await codex.status()).approvals[0].description, "echo test");
    codex.approve("approval", false);
    assert.match(await approvalResponse.text(), /decline/);
    const controller = new AbortController();
    const waiting = await stream("wait", controller.signal);
    const other = await stream("Hola");
    controller.abort();
    assert.match(await waiting.text(), /\[DONE\]/);
    assert.match(await other.text(), /mundo/);
    const failure = await stream("failure");
    assert.match(await failure.text(), /Model unavailable/);
    const cancelled = await stream("wait");
    await cancelled.body.cancel();
    await codex.logout();
    assert.equal((await codex.status()).authenticated, false);
    console.log("PASS Codex login, models, streaming, approval rejection, independent cancellation, errors, logout and local origin checks");
  } finally {
    codex.close();
    await new Promise((resolve) => setTimeout(resolve, 300));
    fs.rmSync(temporary, { recursive: true, force: true });
  }
}

main().catch((error) => { console.error(error); process.exitCode = 1; });
