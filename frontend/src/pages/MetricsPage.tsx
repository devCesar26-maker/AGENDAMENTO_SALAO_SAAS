import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { DashboardHeader } from "../components/DashboardHeader";
import { api, errorMessage } from "../lib/api";
import { useAuth } from "../lib/auth-context";

type Overview = { total_appointments: number; occupancy_rate: number; no_show_rate: number; estimated_revenue: string };
type ServiceMetric = { service_id: number; service_name: string; quantity: number; revenue: string };
type ProfessionalMetric = { professional_id: number; professional_name: string; appointments: number; revenue: string };
type Audit = { id: number; action: string; actor_name: string | null; object_type: string; object_id: string; context: Record<string, unknown>; created_at: string };
type Row<T> = T[] | { results: T[]; count?: number };
const rows = <T,>(data: Row<T>) => Array.isArray(data) ? data : data.results;
const today = new Date();
const dateInput = (date: Date) => `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
const monthStart = dateInput(new Date(today.getFullYear(), today.getMonth(), 1));

export function MetricsPage() {
  const { user } = useAuth();
  const [start, setStart] = useState(monthStart);
  const [end, setEnd] = useState(dateInput(today));
  const [exportError, setExportError] = useState("");
  const params = { data_inicio: start, data_fim: end };
  const overview = useQuery({ queryKey: ["metrics-overview", start, end], enabled: !!start && !!end, queryFn: async () => (await api.get<Overview>("/metrics/overview/", { params })).data });
  const serviceMetrics = useQuery({ queryKey: ["metrics-services", start, end], enabled: !!start && !!end, queryFn: async () => rows((await api.get<Row<ServiceMetric>>("/metrics/services/", { params })).data) });
  const proMetrics = useQuery({ queryKey: ["metrics-professionals", start, end], enabled: !!start && !!end, queryFn: async () => rows((await api.get<Row<ProfessionalMetric>>("/metrics/professionals/", { params })).data) });
  const audit = useQuery({ queryKey: ["audit-log", start, end], enabled: !!start && !!end && user?.role !== "PROFESSIONAL", queryFn: async () => rows((await api.get<Row<Audit>>("/audit-log/", { params })).data) });
  async function download(path: string, filename: string) {
    setExportError("");
    try {
      const response = await api.get(path, { params, responseType: "blob" });
      const url = URL.createObjectURL(response.data as Blob);
      const anchor = document.createElement("a"); anchor.href = url; anchor.download = filename; anchor.click(); URL.revokeObjectURL(url);
    } catch (error) { setExportError(errorMessage(error)); }
  }
  const error = overview.error ?? serviceMetrics.error ?? proMetrics.error;
  return <div className="app-shell"><DashboardHeader current="Métricas" />
    <main className="page-content"><div className="page-heading"><div><p className="eyebrow">RESULTADOS</p><h1>Métricas</h1><p className="muted-copy">Acompanhe os atendimentos e o desempenho do espaço.</p></div></div><section className="panel metrics-toolbar"><label className="field-label">De<input className="field-input" type="date" value={start} onChange={event => setStart(event.target.value)} /></label><label className="field-label">Até<input className="field-input" type="date" value={end} onChange={event => setEnd(event.target.value)} /></label></section>{user?.role !== "PROFESSIONAL" && <div className="export-toolbar"><strong>Exportar dados</strong><div className="flex flex-wrap gap-2"><button className="button-quiet" onClick={() => void download("/exports/appointments/", "agendamentos.csv")}>Agendamentos CSV</button><button className="button-quiet" onClick={() => void download("/exports/customers/", "clientes.csv")}>Clientes CSV</button><button className="button-quiet" onClick={() => void download("/exports/commissions/", "comissoes.csv")}>Comissões CSV</button></div></div>}{exportError && <p role="alert" className="notice-error">{exportError}</p>}{error ? <p role="alert" className="notice-error">Não foi possível carregar as métricas. {errorMessage(error)}</p> : overview.isLoading ? <div className="panel loading-panel">Carregando resultados…</div> : <><section className="metrics-kpis"><MetricCard label="Agendamentos" value={String(overview.data?.total_appointments ?? 0)} /><MetricCard label="Ocupação" value={`${(overview.data?.occupancy_rate ?? 0).toFixed(1)}%`} /><MetricCard label="Não compareceu" value={`${(overview.data?.no_show_rate ?? 0).toFixed(1)}%`} /><MetricCard label="Receita estimada" value={`R$ ${Number(overview.data?.estimated_revenue ?? 0).toLocaleString("pt-BR", { minimumFractionDigits: 2 })}`} /></section><section className="metrics-chart-grid"><ChartPanel title="Serviços mais realizados" data={(serviceMetrics.data ?? []).map(item => ({ name: item.service_name, quantidade: item.quantity, receita: Number(item.revenue) }))} dataKey="quantidade" /><ChartPanel title="Atendimentos por profissional" data={(proMetrics.data ?? []).map(item => ({ name: item.professional_name, quantidade: item.appointments, receita: Number(item.revenue) }))} dataKey="quantidade" /></section><section className="metrics-tables"><MetricTable title="Serviços" headers={["Serviço", "Atendimentos", "Receita"]} rows={(serviceMetrics.data ?? []).map(row => [row.service_name, String(row.quantity), `R$ ${Number(row.revenue).toFixed(2).replace(".", ",")}`])} /><MetricTable title="Profissionais" headers={["Profissional", "Atendimentos", "Receita"]} rows={(proMetrics.data ?? []).map(row => [row.professional_name, String(row.appointments), `R$ ${Number(row.revenue).toFixed(2).replace(".", ",")}`])} /></section></>}{user?.role !== "PROFESSIONAL" && <section className="panel audit-panel"><div><p className="eyebrow">TRANSPARÊNCIA</p><h2 className="font-serif text-2xl">Auditoria recente</h2></div>{audit.isLoading ? <p className="helper-copy mt-3">Carregando registros…</p> : audit.isError ? <p role="alert" className="notice-error mt-3">{errorMessage(audit.error)}</p> : <MetricTable title="Atividades" headers={["Data", "Ação", "Pessoa", "Registro"]} rows={(audit.data ?? []).map(row => [new Date(row.created_at).toLocaleString("pt-BR"), row.action.replaceAll("_", " "), row.actor_name ?? "Sistema", `${row.object_type} #${row.object_id}`])} />}</section>}</main></div>;
}

function MetricCard({ label, value }: { label: string; value: string }) { return <article className="panel metric-card"><small>{label}</small><strong>{value}</strong></article>; }
function ChartPanel({ title, data, dataKey }: { title: string; data: { name: string; quantidade: number; receita: number }[]; dataKey: "quantidade" | "receita" }) { return <section className="panel chart-panel"><h2>{title}</h2>{data.length ? <ResponsiveContainer width="100%" height={260}><BarChart data={data} margin={{ top: 12, right: 12, bottom: 30, left: 0 }}><CartesianGrid stroke="rgb(255 255 255 / 8%)" vertical={false} /><XAxis dataKey="name" stroke="#a6a4a0" tick={{ fill: "#a6a4a0", fontSize: 11 }} angle={-15} textAnchor="end" /><YAxis stroke="#a6a4a0" tick={{ fill: "#a6a4a0", fontSize: 11 }} /><Tooltip contentStyle={{ background: "#202125", border: "1px solid #ffffff20", borderRadius: 10, color: "#f4f0e9" }} /><Bar dataKey={dataKey} fill="#c6a775" radius={[5, 5, 0, 0]} /></BarChart></ResponsiveContainer> : <p className="helper-copy py-12 text-center">Sem dados para este período.</p>}</section>; }
function MetricTable({ title, headers, rows: data }: { title: string; headers: string[]; rows: string[][] }) { return <section className="metric-table-wrap"><h3>{title}</h3>{data.length ? <div className="overflow-x-auto"><table className="metric-table"><thead><tr>{headers.map(header => <th key={header}>{header}</th>)}</tr></thead><tbody>{data.map((row, index) => <tr key={`${title}-${index}`}>{row.map((cell, cellIndex) => <td key={`${cellIndex}-${cell}`}>{cell}</td>)}</tr>)}</tbody></table></div> : <p className="helper-copy">Sem registros neste período.</p>}</section>; }
