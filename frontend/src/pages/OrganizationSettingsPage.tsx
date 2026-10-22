import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, errorMessage } from "../lib/api";
import { useAuth } from "../lib/auth-context";

type Org = { id: number; name: string; slug: string; vertical: "SALAO" | "BARBEARIA"; phone: string; address: string; working_hours: Record<string, [string, string][]>; timezone: string };
const dayKeys = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"];
const dayNames = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"];
const schema = z.object({ name: z.string().trim().min(2, "Informe o nome do estabelecimento."), phone: z.string(), address: z.string(), slug: z.string().trim().min(2).regex(/^[a-z0-9]+(?:-[a-z0-9]+)*$/, "Use letras minúsculas, números e hífens.") });
type Form = z.infer<typeof schema>;
const fallbackBase = import.meta.env.VITE_PUBLIC_BASE_URL || window.location.origin;
const publicDomain = import.meta.env.VITE_PUBLIC_DOMAIN;

export function OrganizationSettingsPage() {
  const { user, refreshUser } = useAuth();
  const slug = user?.organization?.slug ?? "";
  const canEdit = user?.role === "OWNER" || user?.role === "MANAGER";
  const isOwner = user?.role === "OWNER";
  const client = useQueryClient();
  const [hours, setHours] = useState<Record<string, [string, string][]>>({});
  const [feedback, setFeedback] = useState("");
  const org = useQuery({ queryKey: ["organization", slug], enabled: !!slug, queryFn: async () => (await api.get<Org>(`/organizations/${slug}/`)).data });
  const form = useForm<Form>({ resolver: zodResolver(schema), values: org.data ? { name: org.data.name, phone: org.data.phone, address: org.data.address, slug: org.data.slug } : { name: "", phone: "", address: "", slug: "" } });
  const save = useMutation({ mutationFn: (values: Form) => api.patch<Org>(`/organizations/${slug}/`, { name: values.name, phone: values.phone, address: values.address, ...(isOwner ? { slug: values.slug } : {}), working_hours: displayedHours }), onSuccess: async ({ data }) => { setFeedback("Configurações salvas."); setHours(data.working_hours ?? {}); const slugChanged = data.slug !== slug; await client.setQueryData(["organization", data.slug], data); if (slugChanged) { try { await refreshUser?.(); } catch { /* O dado já foi salvo; a sessão será atualizada no próximo acesso. */ } client.removeQueries({ queryKey: ["organization", slug] }); } else { await client.invalidateQueries({ queryKey: ["organization"] }); } }, onError: error => setFeedback(errorMessage(error)) });
  const publicLink = org.data ? (publicDomain ? `https://${org.data.slug}.${publicDomain}` : `${fallbackBase.replace(/\/$/, "")}/b/${org.data.slug}`) : "";
  const displayedHours = Object.fromEntries(dayKeys.map(day => [day, hours[day] ?? org.data?.working_hours?.[day] ?? []]));
  const setRange = (day: string, index: number, part: 0 | 1, value: string) => setHours(old => ({ ...old, [day]: (old[day] ?? []).map((range, i) => i === index ? (part === 0 ? [value, range[1]] : [range[0], value]) as [string, string] : range) }));
  return <><main className="page-content"><div className="page-heading"><div><p className="eyebrow">ESPAÇO</p><h1>Configurações</h1><p className="muted-copy">Dados e horário de funcionamento do estabelecimento.</p></div></div>
    {org.isLoading && <p role="status" className="panel loading-panel">Carregando configurações…</p>}{org.isError && <p role="alert" className="panel loading-panel notice-error">Não foi possível carregar as configurações. {errorMessage(org.error)}</p>}
    {org.data && <div className="settings-layout"><form className="panel settings-form" onSubmit={form.handleSubmit(values => { setFeedback(""); save.mutate(values); })}><h2>Dados do estabelecimento</h2><label className="field-label">Nome do estabelecimento<input className="field-input" disabled={!canEdit} {...form.register("name")}/>{form.formState.errors.name && <small className="notice-error">{form.formState.errors.name.message}</small>}</label><div className="form-columns"><label className="field-label">Telefone<input className="field-input" disabled={!canEdit} {...form.register("phone")}/></label><label className="field-label">Vertical<input className="field-input" readOnly value={org.data.vertical === "SALAO" ? "Salão" : "Barbearia"}/><small className="helper-copy">A vertical fica fixa após criar o espaço porque define o catálogo e os dados iniciais.</small></label></div><label className="field-label">Endereço<textarea className="field-input" rows={3} disabled={!canEdit} {...form.register("address")}/></label><label className="field-label">Link público<div className="copy-link"><input className="field-input" readOnly value={publicLink}/><button type="button" className="button-quiet" onClick={() => { void navigator.clipboard?.writeText(publicLink); setFeedback("Link copiado."); }}>Copiar</button></div></label>{isOwner && <label className="field-label">Slug / subdomínio<input className="field-input" {...form.register("slug")}/>{form.formState.errors.slug && <small className="notice-error">{form.formState.errors.slug.message}</small>}<small className="helper-copy">O backend valida a unicidade do slug antes de salvar.</small></label>}
      <section className="detail-section"><h2>Horário de funcionamento</h2><div className="business-hours">{dayKeys.map((day, dayIndex) => <div className="business-day" key={day}><strong>{dayNames[dayIndex]}</strong>{displayedHours[day]?.length ? displayedHours[day].map((range, index) => <div className="business-range" key={`${day}-${index}`}><input aria-label={`${dayNames[dayIndex]} abre`} className="field-input" type="time" disabled={!canEdit} value={range[0]} onChange={event => setRange(day, index, 0, event.target.value)}/><span>até</span><input aria-label={`${dayNames[dayIndex]} fecha`} className="field-input" type="time" disabled={!canEdit} value={range[1]} onChange={event => setRange(day, index, 1, event.target.value)}/>{canEdit && <button type="button" className="button-quiet" aria-label={`Remover horário de ${dayNames[dayIndex]}`} onClick={() => setHours(old => ({ ...old, [day]: old[day].filter((_, i) => i !== index) }))}>×</button>}</div>) : <span className="helper-copy">Fechado</span>}{canEdit && <button type="button" className="button-quiet business-add" onClick={() => setHours(old => ({ ...old, [day]: [...(displayedHours[day] ?? []), ["09:00", "18:00"]] }))}>Adicionar horário</button>}</div>)}</div></section>
      {feedback && <p role={save.isError ? "alert" : "status"} className={save.isError ? "notice-error" : "notice-success"}>{feedback}</p>}{canEdit && <button className="button-primary" disabled={save.isPending}>{save.isPending ? "Salvando…" : "Salvar configurações"}</button>}</form></div>}</main></>;
}
