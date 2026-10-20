import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { DashboardHeader } from "../components/DashboardHeader";
import { api, errorMessage } from "../lib/api";
import { useAuth } from "../lib/auth-context";

type Member = { id: number; role: "OWNER" | "MANAGER" | "PROFESSIONAL"; is_active: boolean; user: { id: number; email: string; first_name: string; last_name: string } };
type Invitation = { id: number; email: string; role: "MANAGER" | "PROFESSIONAL"; expires_at: string; invite_url: string };
type Rows<T> = T[] | { results: T[] };
const rows = <T,>(data: Rows<T>) => Array.isArray(data) ? data : data.results;
const schema = z.object({ email: z.string().trim().email("Informe um e-mail válido."), role: z.enum(["MANAGER", "PROFESSIONAL"]) });

export function TeamPage() {
  const { user } = useAuth();
  const slug = user?.organization?.slug ?? "";
  const client = useQueryClient();
  const [feedback, setFeedback] = useState("");
  const form = useForm<z.infer<typeof schema>>({ resolver: zodResolver(schema), defaultValues: { email: "", role: "PROFESSIONAL" } });
  const members = useQuery({ queryKey: ["organization-members", slug], enabled: !!slug, queryFn: async () => rows((await api.get<Rows<Member>>(`/organizations/${slug}/members/`)).data) });
  const invitations = useQuery({ queryKey: ["organization-invitations", slug], enabled: !!slug, queryFn: async () => rows((await api.get<Rows<Invitation>>(`/organizations/${slug}/invitations/`)).data) });
  const refresh = async () => { await client.invalidateQueries({ queryKey: ["organization-members", slug] }); await client.invalidateQueries({ queryKey: ["organization-invitations", slug] }); };
  const invite = useMutation({ mutationFn: (values: z.infer<typeof schema>) => api.post(`/organizations/${slug}/invitations/`, values), onSuccess: async () => { setFeedback("Convite enviado por e-mail."); form.reset({ email: "", role: "PROFESSIONAL" }); await refresh(); }, onError: error => setFeedback(errorMessage(error)) });
  const modify = useMutation({ mutationFn: ({ member, patch }: { member: Member; patch: Partial<Pick<Member, "role" | "is_active">> }) => api.patch(`/organizations/${slug}/members/${member.id}/`, patch), onSuccess: refresh });
  const revoke = useMutation({ mutationFn: (id: number) => api.delete(`/organizations/${slug}/invitations/${id}/`), onSuccess: refresh });
  const owner = user?.role === "OWNER";
  const isLoading = members.isLoading || invitations.isLoading;
  const loadError = members.error ?? invitations.error;
  return <div className="app-shell"><DashboardHeader current="Equipe"/><main className="page-content"><div className="page-heading"><div><p className="eyebrow">ADMINISTRAÇÃO</p><h1>Equipe</h1><p className="muted-copy">Gerencie acessos, papéis e convites do seu espaço.</p></div></div>
    {isLoading && <p className="panel loading-panel" role="status">Carregando equipe…</p>}{loadError && <p className="panel loading-panel notice-error" role="alert">Não foi possível carregar a equipe. {errorMessage(loadError)}</p>}
    {!isLoading && !loadError && <div className="team-layout"><section className="panel team-section"><h2>Membros</h2>{members.data?.length === 0 ? <p className="helper-copy">Ainda não há membros cadastrados.</p> : <div className="team-list">{members.data?.map(member => { const name = [member.user.first_name, member.user.last_name].filter(Boolean).join(" ") || member.user.email; const self = member.user.id === user?.id; return <article className="team-row" key={member.id}><div className="team-identity"><strong>{name}</strong><small>{member.user.email}</small></div><span className={`status-pill ${member.is_active ? "status-active" : "status-inactive"}`}>{member.is_active ? "Ativo" : "Inativo"}</span><span className="team-role">{member.role === "OWNER" ? "Proprietário" : member.role === "MANAGER" ? "Gerente" : "Profissional"}</span>{owner && !self && <div className="team-actions"><label className="sr-only" htmlFor={`role-${member.id}`}>Papel de {name}</label><select id={`role-${member.id}`} className="field-input" aria-label={`Papel de ${name}`} value={member.role} onChange={event => modify.mutate({ member, patch: { role: event.target.value as Member["role"] } })}><option value="PROFESSIONAL">Profissional</option><option value="MANAGER">Gerente</option><option value="OWNER">Proprietário</option></select><button className="button-quiet" onClick={() => { if (window.confirm(`${member.is_active ? "Desativar" : "Reativar"} ${name}?`)) modify.mutate({ member, patch: { is_active: !member.is_active } }); }}>{member.is_active ? "Desativar" : "Reativar"}</button></div>}{self && <small className="helper-copy">Sua conta</small>}</article>; })}</div>}</section>
      <div className="team-side"><section className="panel team-section"><h2>Convidar membro</h2><form className="service-form" onSubmit={form.handleSubmit(values => { setFeedback(""); invite.mutate(values); })}><label className="field-label">E-mail<input className="field-input" type="email" {...form.register("email")}/>{form.formState.errors.email && <small className="notice-error">{form.formState.errors.email.message}</small>}</label><label className="field-label">Papel<select className="field-input" {...form.register("role")}><option value="PROFESSIONAL">Profissional</option><option value="MANAGER">Gerente</option></select></label>{feedback && <p role={invite.isError ? "alert" : "status"} className={invite.isError ? "notice-error" : "notice-success"}>{feedback}</p>}<button className="button-primary" disabled={invite.isPending}>{invite.isPending ? "Enviando…" : "Enviar convite"}</button></form></section>
      <section className="panel team-section"><h2>Convites pendentes</h2>{invitations.data?.length === 0 ? <p className="helper-copy">Não há convites pendentes.</p> : <div className="team-list">{invitations.data?.map(invitation => <article className="team-row invitation-row" key={invitation.id}><div className="team-identity"><strong>{invitation.email}</strong><small>{invitation.role === "MANAGER" ? "Gerente" : "Profissional"} · expira em {new Date(invitation.expires_at).toLocaleDateString("pt-BR")}</small></div><button className="button-quiet" disabled={revoke.isPending} onClick={() => { if (window.confirm(`Revogar convite para ${invitation.email}?`)) revoke.mutate(invitation.id); }}>Revogar</button></article>)}</div>}</section></div></div>}{(modify.isError || revoke.isError) && <p role="alert" className="notice-error">{errorMessage(modify.error ?? revoke.error)}</p>}</main></div>;
}
