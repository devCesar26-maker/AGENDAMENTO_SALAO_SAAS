import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api, errorMessage } from "../lib/api";
import { useAuth } from "../lib/auth-context";

type Plan = { id: number; tier: "FREE" | "PLUS" | "PREMIUM"; name: string; max_professionals: number | null; max_appointments_per_month: number | null; monthly_price_cents: number };
type Usage = { plan: { tier: string; name: string }; professionals: { used: number; limit: number | null }; appointments: { used: number; limit: number | null; period_start: string; period_end: string } };
type Row<T> = T[] | { results: T[] };
const rows = <T,>(data: Row<T>) => Array.isArray(data) ? data : data.results;

export function PlanPage() {
  const { user } = useAuth();
  const [checkoutError, setCheckoutError] = useState("");
  const [pendingTier, setPendingTier] = useState("");
  const plans = useQuery({ queryKey: ["billing-plans"], queryFn: async () => rows((await api.get<Row<Plan>>("/billing/plans/")).data) });
  const usage = useQuery({ queryKey: ["billing-usage"], queryFn: async () => (await api.get<Usage>("/billing/usage/")).data });
  const currentPlan = plans.data?.find(plan => plan.tier === usage.data?.plan.tier);
  async function checkout(tier: string) {
    setCheckoutError(""); setPendingTier(tier);
    try { const { data } = await api.post<{ checkout_url: string }>("/billing/checkout/", { tier }); window.location.assign(data.checkout_url); }
    catch (error) { setCheckoutError(errorMessage(error)); setPendingTier(""); }
  }
  return <>
    <main className="page-content"><div className="page-heading"><div><p className="eyebrow">ASSINATURA</p><h1>Seu plano</h1><p className="muted-copy">Acompanhe o uso e escolha o plano ideal para seu espaço.</p></div></div>{plans.isError || usage.isError ? <p role="alert" className="notice-error">Não foi possível carregar os planos. {errorMessage(plans.error ?? usage.error)}</p> : plans.isLoading || usage.isLoading ? <div className="panel loading-panel">Carregando informações do plano…</div> : <><section className="panel plan-current"><div><p className="eyebrow">PLANO ATUAL</p><h2 className="font-serif text-3xl">{usage.data?.plan.name}</h2><p className="muted-copy">{usage.data?.plan.tier === "FREE" ? "Sem cobrança recorrente" : currentPlan ? `R$ ${(currentPlan.monthly_price_cents / 100).toFixed(2).replace(".", ",")} por mês` : "Assinatura ativa"}</p></div><span className="status-pill status-active">{usage.data?.plan.tier === "FREE" ? "Gratuito" : "Ativo"}</span><div className="plan-usage-grid"><UsageMeter title="Profissionais ativos" used={usage.data!.professionals.used} limit={usage.data!.professionals.limit} /><UsageMeter title="Agendamentos no mês" used={usage.data!.appointments.used} limit={usage.data!.appointments.limit} /></div><p className="helper-copy">Período atual: {new Date(usage.data!.appointments.period_start).toLocaleDateString("pt-BR")} a {new Date(usage.data!.appointments.period_end).toLocaleDateString("pt-BR")}.</p></section><h2 className="mt-8 mb-4 font-serif text-2xl">Planos disponíveis</h2><div className="plan-grid">{plans.data?.map(plan => <article key={plan.id} className={`panel plan-card ${plan.tier === usage.data?.plan.tier ? "plan-card-current" : ""}`}><p className="eyebrow">{plan.tier === "FREE" ? "COMECE SEM CUSTO" : "PARA CRESCER"}</p><h3 className="font-serif text-2xl">{plan.name}</h3><p className="plan-price">{plan.monthly_price_cents ? <>R$ {(plan.monthly_price_cents / 100).toFixed(2).replace(".", ",")}<small>/mês</small></> : "Grátis"}</p><ul className="plan-feature-list"><li>{plan.max_professionals === null ? "Profissionais ilimitados" : `Até ${plan.max_professionals} profissionais`}</li><li>{plan.max_appointments_per_month === null ? "Agendamentos ilimitados" : `${plan.max_appointments_per_month} agendamentos/mês`}</li></ul>{plan.tier === usage.data?.plan.tier ? <button className="button-quiet button-wide" disabled>Plano atual</button> : plan.tier === "FREE" ? <button className="button-quiet button-wide" disabled>Plano gratuito</button> : user?.role !== "OWNER" ? <button className="button-quiet button-wide" disabled>Apenas o proprietário pode assinar</button> : <button className="button-primary button-wide" onClick={() => void checkout(plan.tier)} disabled={!!pendingTier}>{pendingTier === plan.tier ? "Abrindo pagamento…" : "Escolher plano"}</button>}</article>)}</div>{checkoutError && <p role="alert" className="notice-error mt-4">{checkoutError}</p>}</>}</main></>;
}

function UsageMeter({ title, used, limit }: { title: string; used: number; limit: number | null }) { const percent = limit === null ? 0 : Math.min(100, Math.round(used / Math.max(limit, 1) * 100)); return <div className="usage-meter"><div className="flex justify-between gap-3"><strong>{title}</strong><span>{used}{limit === null ? " usados · sem limite" : ` / ${limit}`}</span></div>{limit !== null && <div className="usage-track"><span style={{ width: `${percent}%` }} /></div>}</div>; }
