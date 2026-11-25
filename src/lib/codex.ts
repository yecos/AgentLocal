import { spawn, type ChildProcessWithoutNullStreams } from "node:child_process";
import { existsSync, mkdirSync } from "node:fs";
import { homedir } from "node:os";
import path from "node:path";
import { createInterface } from "node:readline";
import { EventEmitter } from "node:events";

type RpcMessage = {
  id?: number | string;
  method?: string;
  params?: Record<string, any>;
  result?: any;
  error?: { message: string };
};

function executable() {
  const candidates = [
    process.env.AGENTLOCAL_CODEX_BIN,
    ...(process.env.PATH || "").split(path.delimiter).flatMap((folder) => [
      path.join(folder, process.platform === "win32" ? "codex.exe" : "codex"),
      path.join(folder, "node_modules", "@openai", "codex", "bin", "codex.js"),
    ]),
  ];
  const file = candidates.find((candidate) => candidate && existsSync(candidate));
  if (!file) throw new Error("Instala Codex CLI o configura AGENTLOCAL_CODEX_BIN con su ruta.");
  return file.endsWith(".js")
    ? { command: process.execPath, args: [file, "app-server", "--stdio"] }
    : { command: file, args: ["app-server", "--stdio"] };
}

class CodexClient {
  private child?: ChildProcessWithoutNullStreams;
  private ready?: Promise<void>;
  private sequence = 0;
  private pending = new Map<number, { resolve: (value: any) => void; reject: (error: Error) => void; timer: NodeJS.Timeout }>();
  private loginRequest?: Promise<{ loginId: string; authUrl: string }>;
  private login?: { loginId: string; authUrl: string };
  private loginError?: string;
  readonly events = new EventEmitter();
  readonly approvals = new Map<string, { id: string | number; threadId: string; description: string }>();

  constructor() {
    this.events.setMaxListeners(100);
  }

  async connect() {
    if (!this.ready) this.ready = this.start().catch((error) => {
      this.close();
      this.ready = undefined;
      throw error;
    });
    await this.ready;
  }

  private async start() {
    const command = executable();
    const home = process.env.AGENTLOCAL_CODEX_HOME || path.join(homedir(), ".agentlocal", "codex");
    mkdirSync(home, { recursive: true, mode: 0o700 });
    // Codex owns OAuth credentials in AgentLocal's dedicated profile.
    const env: NodeJS.ProcessEnv = { ...process.env, CODEX_HOME: home };
    delete env.OPENAI_API_KEY;
    const child = spawn(command.command, command.args, { env, windowsHide: true, stdio: "pipe" });
    this.child = child;
    child.stderr.resume();
    const lines = createInterface({ input: child.stdout });
    lines.on("line", (line) => {
      let message: RpcMessage;
      try { message = JSON.parse(line); } catch { return; }
      if (message.id !== undefined && !message.method) {
        const pending = this.pending.get(Number(message.id));
        if (!pending) return;
        clearTimeout(pending.timer);
        this.pending.delete(Number(message.id));
        if (message.error) pending.reject(new Error(message.error.message));
        else pending.resolve(message.result);
        return;
      }
      if (message.method === "account/login/completed") {
        this.login = undefined;
        this.loginError = message.params?.success ? undefined : String(message.params?.error || "No se completó el inicio de sesión.");
      }
      if (message.id !== undefined && message.method) {
        if (["item/commandExecution/requestApproval", "item/fileChange/requestApproval"].includes(message.method)) {
          const params = message.params || {};
          this.approvals.set(String(message.id), {
            id: message.id, threadId: params.threadId,
            description: [params.command, params.reason, params.grantRoot].filter(Boolean).join("\n") || "Codex solicita permiso para modificar archivos.",
          });
        } else {
          this.write({ id: message.id, error: { code: -32601, message: "AgentLocal no admite esta solicitud interactiva." } });
        }
      }
      this.events.emit("message", message);
    });
    const fail = (error: Error) => {
      if (this.child !== child) return;
      this.child = undefined;
      this.ready = undefined;
      this.login = undefined;
      this.approvals.clear();
      for (const pending of this.pending.values()) {
        clearTimeout(pending.timer);
        pending.reject(error);
      }
      this.pending.clear();
      this.events.emit("failure", error);
    };
    child.on("error", fail);
    child.stdin.on("error", fail);
    child.on("exit", () => fail(new Error("Codex se cerró. Vuelve a conectar.")));
    await this.call("initialize", { clientInfo: { name: "agentlocal", title: "AgentLocal", version: "0.3.0" } });
    this.write({ method: "initialized" });
  }

  private write(message: object) {
    if (!this.child || this.child.stdin.destroyed || this.child.stdin.writableEnded) throw new Error("Codex no está disponible.");
    this.child.stdin.write(JSON.stringify(message) + "\n");
  }

  async call(method: string, params: object = {}): Promise<any> {
    const id = ++this.sequence;
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => {
        this.pending.delete(id);
        reject(new Error("Codex tardó demasiado en responder."));
      }, 30_000);
      this.pending.set(id, { resolve, reject, timer });
      try { this.write({ id, method, params }); }
      catch (error) {
        clearTimeout(timer);
        this.pending.delete(id);
        reject(error);
      }
    });
  }

  async startLogin() {
    await this.connect();
    this.loginError = undefined;
    if (this.login) return this.login;
    if (!this.loginRequest) {
      this.loginRequest = this.call("account/login/start", { type: "chatgpt" }).then((result) => {
        this.login = result;
        return result;
      }).finally(() => { this.loginRequest = undefined; });
    }
    return this.loginRequest;
  }

  async cancelLogin() {
    if (this.loginRequest) await this.loginRequest;
    if (this.login) await this.call("account/login/cancel", { loginId: this.login.loginId });
    this.login = undefined;
  }

  async logout() {
    await this.cancelLogin();
    await this.call("account/logout");
  }

  approve(id: string, allowed: boolean) {
    const approval = this.approvals.get(id);
    if (!approval) throw new Error("La solicitud de aprobación ya terminó.");
    this.write({ id: approval.id, result: { decision: allowed ? "accept" : "decline" } });
    this.approvals.delete(id);
  }

  close() {
    this.child?.stdin.end();
  }

  async status() {
    await this.connect();
    const { account } = await this.call("account/read", { refreshToken: false });
    const result = account?.type === "chatgpt"
      ? await this.call("model/list", { includeHidden: false, limit: 100 }) : { data: [] };
    return {
      available: true, authenticated: account?.type === "chatgpt",
      email: account?.type === "chatgpt" ? account.email : null,
      plan: account?.type === "chatgpt" ? account.planType : null,
      loginPending: Boolean(this.login), error: this.loginError,
      workspace: process.env.AGENT_REPOS_DIR || path.join(homedir(), "AgentLocal-projects"),
      models: result.data.map((model: any) => ({ id: model.model, name: model.displayName, isDefault: model.isDefault })),
      approvals: [...this.approvals].map(([id, approval]) => ({ id, description: approval.description })),
    };
  }
}

const globals = globalThis as typeof globalThis & { agentLocalCodex?: CodexClient };
export const codex = globals.agentLocalCodex ??= new CodexClient();

export function localRequest(request: Request): boolean {
  try {
    const url = new URL(request.url);
    // Next.js may normalize request.url to its internal hostname. Browsers use Host.
    const host = request.headers.get("host");
    const address = host ? new URL(url.protocol + "//" + host) : url;
    const origin = request.headers.get("origin");
    const forwarded = [request.headers.get("x-forwarded-for"), request.headers.get("x-real-ip")]
      .filter(Boolean).flatMap((value) => value!.split(",").map((ip) => ip.trim()));
    return ["localhost", "127.0.0.1", "[::1]"].includes(address.hostname)
      && forwarded.every((ip) => ["127.0.0.1", "::1", "::ffff:127.0.0.1"].includes(ip))
      && (!origin || origin === address.origin);
  } catch { return false; }
}

export async function codexStream(messages: Array<{ role: string; content: string }>, model: string, useAgent: boolean, signal: AbortSignal) {
  await codex.connect();
  const { account } = await codex.call("account/read", { refreshToken: false });
  if (account?.type !== "chatgpt") return Response.json({ error: "Conecta tu cuenta de ChatGPT antes de enviar mensajes." }, { status: 401 });
  const workspace = process.env.AGENT_REPOS_DIR || path.join(homedir(), "AgentLocal-projects");
  mkdirSync(workspace, { recursive: true });
  const { thread } = await codex.call("thread/start", {
    model, cwd: workspace, ephemeral: true, approvalPolicy: "on-request",
    sandbox: useAgent ? "workspace-write" : "read-only",
    developerInstructions: useAgent
      ? "Eres el asistente de AgentLocal. Trabaja en la carpeta asignada y responde en el idioma del usuario."
      : "Responde en el idioma del usuario. Estás en modo chat. Contesta sin ejecutar herramientas.",
  });
  const encoder = new TextEncoder();
  let turnId: string | undefined;
  let closed = false;
  let consumerClosed = false;
  let finish = () => {};
  const interrupt = () => {
    if (turnId) void codex.call("turn/interrupt", { threadId: thread.id, turnId }).catch(() => {});
  };
  const abort = () => { interrupt(); finish(); };
  const stream = new ReadableStream<Uint8Array>({
    async start(controller) {
      const emit = (value: object | string) => {
        if (!closed && !consumerClosed) controller.enqueue(encoder.encode("data: " + (typeof value === "string" ? value : JSON.stringify(value)) + "\n\n"));
      };
      const failure = (error: Error) => {
        emit({ type: "error", data: error.message });
        interrupt();
        finish();
      };
      const onMessage = (message: RpcMessage) => {
        const params = message.params || {};
        if (params.threadId !== thread.id) return;
        if (message.method === "turn/started") turnId = params.turn?.id;
        if (message.method === "item/agentMessage/delta") emit({ type: "text", data: params.delta });
        if (message.method === "turn/completed") {
          if (params.turn?.error) emit({ type: "error", data: params.turn.error.message });
          finish();
        }
        if (["item/started", "item/completed"].includes(message.method || "")) {
          const item = params.item;
          if (["commandExecution", "fileChange", "mcpToolCall"].includes(item?.type)) {
            emit(message.method === "item/started"
              ? { type: "tool_start", data: { name: item.type, arguments: { command: item.command } } }
              : { type: "tool_result", data: { tool: item.type, result: item.aggregatedOutput || item.status || "Completado" } });
          }
        }
      };
      const timeout = setTimeout(() => failure(new Error("La tarea superó 15 minutos.")), 15 * 60_000);
      finish = () => {
        if (closed) return;
        for (const [id, approval] of codex.approvals) {
          if (approval.threadId === thread.id) {
            try { codex.approve(id, false); } catch { codex.approvals.delete(id); }
          }
        }
        emit("[DONE]");
        closed = true;
        clearTimeout(timeout);
        signal.removeEventListener("abort", abort);
        codex.events.off("message", onMessage);
        codex.events.off("failure", failure);
        if (!consumerClosed) controller.close();
        void codex.call("thread/unsubscribe", { threadId: thread.id }).catch(() => {});
      };
      codex.events.on("message", onMessage);
      codex.events.on("failure", failure);
      signal.addEventListener("abort", abort, { once: true });
      if (signal.aborted) { abort(); return; }
      try {
        const prompt = messages.filter((message) => message.role !== "system");
        const result = await codex.call("turn/start", {
          threadId: thread.id,
          input: [{ type: "text", text: "Continúa esta conversación. El último mensaje es la solicitud actual.\n" + JSON.stringify(prompt) }],
        });
        turnId = result.turn.id;
        if (closed) interrupt();
      } catch (error) { failure(error instanceof Error ? error : new Error("Falló la solicitud a Codex.")); }
    },
    cancel() { consumerClosed = true; abort(); },
  });
  return new Response(stream, { headers: { "Content-Type": "text/event-stream", "Cache-Control": "no-cache" } });
}
