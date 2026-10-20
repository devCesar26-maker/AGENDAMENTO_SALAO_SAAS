import { useState, type FormEvent } from "react";
import { useParams } from "react-router-dom";
import { z } from "zod";
import { api, errorMessage } from "../lib/api";

const emailSchema = z.string().email("Informe um e-mail válido.");
const passwordSchema = z.string().min(8, "A senha deve ter pelo menos 8 caracteres.").refine(value => !/^\d+$/.test(value), "A senha não pode conter apenas números.").refine(value => !["password", "senha123", "12345678"].includes(value.toLowerCase()), "Escolha uma senha menos comum.");

export function PasswordResetRequestPage() {
  const [email, setEmail] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setError(""); setMessage("");
    const parsed = emailSchema.safeParse(email);
    if (!parsed.success) { setError(parsed.error.issues[0]?.message ?? "Informe um e-mail válido."); return; }
    setBusy(true);
    try {
      const response = await api.post("/auth/password/reset/", { email: parsed.data });
      setMessage(response.data.detail ?? "Se este e-mail estiver cadastrado, você receberá um link de redefinição em instantes.");
    } catch (cause) { setError(errorMessage(cause)); } finally { setBusy(false); }
  }
  return <main className="login-shell"><section className="login-card panel"><div className="login-brand"><span className="brand-mark">É</span><span><strong>Éclat</strong><small>GESTÃO DO ESTÚDIO</small></span></div><h1 className="login-title">Recuperar senha</h1><p className="mb-6 text-sm text-slate-500">Informe seu e-mail. Se houver uma conta, enviaremos as instruções.</p><form onSubmit={submit} className="space-y-4"><label className="field-label">E-mail<input className="field-input" type="email" autoComplete="email" value={email} onChange={event => setEmail(event.target.value)} /></label>{error && <p role="alert" className="notice-error">{error}</p>}{message && <p role="status" className="notice-success">{message}</p>}<button className="button-primary button-wide" disabled={busy}>{busy ? "Enviando…" : "Enviar instruções"}</button></form><p className="register-footer"><a href="/login">Voltar para entrar</a></p></section></main>;
}

export function PasswordResetConfirmPage() {
  const { uidb64 = "", token = "" } = useParams();
  const [password, setPassword] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setError(""); setMessage("");
    const parsed = passwordSchema.safeParse(password);
    if (!parsed.success) { setError(parsed.error.issues[0]?.message ?? "Verifique a senha informada."); return; }
    setBusy(true);
    try { const response = await api.post("/auth/password/reset/confirm/", { uidb64, token, password: parsed.data }); setMessage(response.data.detail ?? "Senha redefinida com sucesso. Você já pode entrar."); }
    catch (cause) { setError(errorMessage(cause)); } finally { setBusy(false); }
  }
  return <main className="login-shell"><section className="login-card panel"><div className="login-brand"><span className="brand-mark">É</span><span><strong>Éclat</strong><small>GESTÃO DO ESTÚDIO</small></span></div><h1 className="login-title">Definir nova senha</h1><p className="mb-6 text-sm text-slate-500">Escolha uma senha com pelo menos 8 caracteres.</p><form onSubmit={submit} className="space-y-4"><label className="field-label">Nova senha<input className="field-input" type="password" autoComplete="new-password" value={password} onChange={event => setPassword(event.target.value)} /></label>{error && <p role="alert" className="notice-error">{error}</p>}{message && <p role="status" className="notice-success">{message} <a href="/login">Entrar</a></p>}<button className="button-primary button-wide" disabled={busy}>{busy ? "Salvando…" : "Redefinir senha"}</button></form></section></main>;
}
