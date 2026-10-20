import { useState } from "react";
import { useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { api, errorMessage, setAccessToken } from "../lib/api";
import { useAuth, type AuthUser } from "../lib/auth-context";

type Invitation = { email: string; role: "MANAGER" | "PROFESSIONAL"; organization: { name: string; slug: string }; account_exists: boolean };
const existingSchema = z.object({ password: z.string().min(1, "Informe sua senha.") });
const newSchema = z.object({ first_name: z.string().trim().min(1, "Informe seu nome."), last_name: z.string(), password: z.string().min(8, "Use ao menos 8 caracteres.") });

export function InvitationAcceptPage() {
  const { token = "" } = useParams();
  const { login, acceptSession, refreshUser } = useAuth();
  const [feedback, setFeedback] = useState("");
  const info = useQuery({ queryKey: ["invitation", token], queryFn: async () => (await api.get<Invitation>(`/invitations/${token}/accept/`)).data, retry: false });
  const form = useForm<Record<string, string>>({ resolver: zodResolver(info.data?.account_exists ? existingSchema : newSchema) as never });
  const onSubmit = async (values: Record<string, string>) => {
    if (!info.data) return;
    setFeedback("");
    try {
      if (info.data.account_exists) {
        await login(info.data.email, values.password);
        await api.post(`/invitations/${token}/accept/`, values);
        await refreshUser?.();
        window.location.assign("/app/agenda");
        return;
      }
      const { data } = await api.post<{ access: string; refresh: string; role: AuthUser["role"]; organization: { id: number; slug: string } }>(`/invitations/${token}/accept/`, values);
      const user: AuthUser = { id: 0, email: info.data.email, first_name: values.first_name ?? "", last_name: values.last_name ?? "", organization: data.organization, role: data.role };
      setAccessToken(data.access);
      acceptSession?.(data.access, user);
      await refreshUser?.();
      window.location.assign("/app/agenda");
    } catch (error) { setFeedback(errorMessage(error)); }
  };
  const roleName = info.data?.role === "MANAGER" ? "gerente" : "profissional";
  return <div className="login-shell"><section className="login-card panel"><div className="login-brand"><span className="brand-mark">É</span><span><strong>Éclat</strong><small>GESTÃO DO ESTÚDIO</small></span></div><p className="eyebrow mt-8">CONVITE DE EQUIPE</p><h1 className="login-title">Aceite seu convite</h1>
    {info.isLoading && <p role="status" className="helper-copy">Verificando convite…</p>}{info.isError && <p role="alert" className="notice-error">Este convite expirou, já foi utilizado ou não é válido. Peça à organização para enviar outro convite.</p>}
    {info.data && <><p className="muted-copy"><strong>{info.data.organization.name}</strong> convidou <strong>{info.data.email}</strong> para participar como {roleName}.</p><form className="service-form" onSubmit={form.handleSubmit(onSubmit)}>{info.data.account_exists ? <label className="field-label">Entre com sua senha<input type="password" autoComplete="current-password" className="field-input" {...form.register("password")}/></label> : <><label className="field-label">Nome<input autoComplete="given-name" className="field-input" {...form.register("first_name")}/></label><label className="field-label">Sobrenome (opcional)<input autoComplete="family-name" className="field-input" {...form.register("last_name")}/></label><label className="field-label">Crie uma senha<input type="password" autoComplete="new-password" className="field-input" {...form.register("password")}/><small className="helper-copy">Use ao menos 8 caracteres.</small></label></>}{feedback && <p role="alert" className="notice-error">{feedback}</p>}<button className="button-primary button-wide" disabled={form.formState.isSubmitting}>{form.formState.isSubmitting ? "Concluindo…" : "Aceitar convite"}</button></form>{info.data.account_exists && <p className="register-footer">Esqueceu a senha? <a href="/esqueci-senha">Redefinir senha</a></p>}</>}
  </section></div>;
}
