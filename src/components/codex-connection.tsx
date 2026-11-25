"use client";

import { useCallback, useEffect, useState } from "react";

export type CodexStatus = {
  available: boolean;
  authenticated: boolean;
  email?: string | null;
  plan?: string | null;
  loginPending?: boolean;
  error?: string;
  workspace?: string;
  models: Array<{ id: string; name: string; isDefault: boolean }>;
  approvals: Array<{ id: string; description: string }>;
};

export function CodexConnection({ model, disabled, ollamaModel, onModel, onStatus }: {
  model: string;
  disabled: boolean;
  ollamaModel: string;
  onModel: (value: string) => void;
  onStatus: (status: CodexStatus) => void;
}) {
  const [status, setStatus] = useState<CodexStatus | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [authUrl, setAuthUrl] = useState("");
  const active = model.startsWith("codex/");

  const refresh = useCallback(async () => {
    try {
      const response = await fetch("/api/codex");
      if (!response.ok) throw new Error("No se pudo consultar Codex.");
      const next = await response.json() as CodexStatus;
      setStatus(next);
      onStatus(next);
      if (next.authenticated) setAuthUrl("");
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "Falló la conexión.");
    }
  }, [onStatus]);

  useEffect(() => {
    if (!active) return;
    void refresh();
    const interval = setInterval(refresh, 3000);
    return () => clearInterval(interval);
  }, [active, refresh]);

  const action = async (body: object) => {
    setBusy(true);
    setError("");
    try {
      const response = await fetch("/api/codex", {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || "No se pudo completar la acción.");
      if (data.authUrl) {
        const url = new URL(data.authUrl);
        if (url.protocol !== "https:" || url.hostname !== "auth.openai.com") throw new Error("La dirección de inicio de sesión no es válida.");
        setAuthUrl(data.authUrl);
        window.open(data.authUrl, "_blank", "noopener,noreferrer");
      }
      await refresh();
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "Falló la conexión.");
    } finally { setBusy(false); }
  };

  return (
    <section aria-label="Proveedor de inteligencia artificial" className="border-b border-[var(--zai-border)] px-4 py-2 text-xs space-y-2">
      <div className="flex items-center gap-3 flex-wrap">
        <label htmlFor="ai-provider">Motor</label>
        <select id="ai-provider" disabled={disabled} value={active ? "codex" : "ollama"}
          className="bg-[var(--zai-bg)] border border-[var(--zai-border)] p-1"
          onChange={(event) => onModel(event.target.value === "codex"
            ? "codex/" + (status?.models.find((item) => item.isDefault)?.id || status?.models[0]?.id || "default")
            : ollamaModel)}>
          <option value="ollama">Ollama · local</option>
          <option value="codex">Codex · ChatGPT</option>
        </select>
        {active && <>
          {status?.authenticated ? <>
            <span>{status.email} {status.plan ? "· " + status.plan : ""}</span>
            <button disabled={busy || disabled} onClick={() => action({ action: "logout" })}>Desconectar</button>
          </> : <button disabled={busy || !status?.available} onClick={() => action({ action: "login" })}
            className="border border-[var(--zai-border)] px-3 py-1">
            {busy ? "Conectando…" : "Iniciar sesión con ChatGPT"}
          </button>}
          {authUrl && <a href={authUrl} target="_blank" rel="noopener noreferrer" className="underline">Continuar inicio de sesión</a>}
          {status?.loginPending && <button disabled={busy} onClick={() => { setAuthUrl(""); void action({ action: "cancelLogin" }); }}>Cancelar inicio de sesión</button>}
          <span className="text-[var(--zai-text-dim)]">Requiere internet y consume el cupo de Codex de tu plan.</span>
        </>}
      </div>
      {active && status?.workspace && <p className="text-[var(--zai-text-dim)]">Carpeta de trabajo · {status.workspace}</p>}
      {active && (error || status?.error) && <p role="alert">{error || status?.error}</p>}
      {active && status?.approvals.map((approval) => (
        <div key={approval.id} role="alertdialog" aria-label="Aprobar acción de Codex" className="border border-[var(--zai-border)] p-3 space-y-2">
          <p>Codex solicita permiso para ejecutar esta acción.</p>
          <pre className="whitespace-pre-wrap break-all max-h-40 overflow-auto">{approval.description}</pre>
          <div className="flex gap-4">
            <button disabled={busy} onClick={() => action({ action: "approval", id: approval.id, allowed: true })}>Permitir una vez</button>
            <button disabled={busy} onClick={() => action({ action: "approval", id: approval.id, allowed: false })}>Rechazar</button>
          </div>
        </div>
      ))}
    </section>
  );
}
