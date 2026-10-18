import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, errorMessage } from "../lib/api";
import { useAuth } from "../lib/auth-context";
import { AppearanceSettings } from "../components/AppearanceSettings";

type Row<T> = T[] | { results: T[] };
type Category = { id: number; name: string; is_active: boolean };
type Service = { id: number; category: number; category_name: string; name: string; description: string; duration_minutes: number; price: string; buffer_minutes: number; is_active: boolean };
type ServiceInput = Omit<Service, "id" | "category_name">;
const rows = <T,>(data: Row<T>) => Array.isArray(data) ? data : data.results;
const blank: ServiceInput = { category: 0, name: "", description: "", duration_minutes: 30, price: "0.00", buffer_minutes: 0, is_active: true };

export function ServicesPage() {
  const { user, logout } = useAuth();
  const client = useQueryClient();
  const [editing, setEditing] = useState<Service | null>(null);
  const [form, setForm] = useState<ServiceInput>(blank);
  const [formOpen, setFormOpen] = useState(false);
  const [categoryOpen, setCategoryOpen] = useState(false);
  const [categoryName, setCategoryName] = useState("");
  const services = useQuery({ queryKey: ["services"], queryFn: async () => rows((await api.get<Row<Service>>("/services/")).data) });
  const categories = useQuery({ queryKey: ["service-categories"], queryFn: async () => rows((await api.get<Row<Category>>("/service-categories/")).data).filter((category) => category.is_active) });
  const createCategory = useMutation({ mutationFn: () => api.post("/service-categories/", { name: categoryName, order: 0, is_active: true }), onSuccess: async () => { await client.invalidateQueries({ queryKey: ["service-categories"] }); setCategoryName(""); setCategoryOpen(false); } });
  const save = useMutation({
    mutationFn: (input: ServiceInput) => editing ? api.patch(`/services/${editing.id}/`, input) : api.post("/services/", input),
    onSuccess: () => { void client.invalidateQueries({ queryKey: ["services"] }); setFormOpen(false); setEditing(null); setForm(blank); },
  });
  const toggle = useMutation({ mutationFn: (service: Service) => api.patch(`/services/${service.id}/`, { is_active: !service.is_active }), onSuccess: () => void client.invalidateQueries({ queryKey: ["services"] }) });
  function startCreate() { setEditing(null); setForm({ ...blank, category: categories.data?.[0]?.id ?? 0 }); setFormOpen(true); }
  function startEdit(service: Service) { setEditing(service); setForm({ category: service.category, name: service.name, description: service.description, duration_minutes: service.duration_minutes, price: service.price, buffer_minutes: service.buffer_minutes, is_active: service.is_active }); setFormOpen(true); }
  function submit(event: FormEvent) { event.preventDefault(); save.mutate(form); }

  return <div className="app-shell">
    <header className="topbar"><Link className="brand-lockup" to="/app/agenda"><span className="brand-mark">É</span><span><strong>Éclat</strong><small>GESTÃO DO ESTÚDIO</small></span></Link><nav className="topnav"><Link to="/app/agenda">Agenda</Link><span className="nav-current">Serviços</span></nav><div className="topbar-actions"><span className="user-chip">{user?.email}</span><AppearanceSettings organizationSlug={user?.organization?.slug} /><button className="button-quiet" onClick={() => void logout()}>Sair</button></div></header>
    <main className="page-content">
      <div className="page-heading"><div><p className="eyebrow">CATÁLOGO</p><h1>Serviços</h1><p className="muted-copy">Organize o que seu espaço oferece, com duração e valores.</p></div><button className="button-primary" onClick={startCreate} disabled={!categories.data?.length}>Adicionar serviço</button></div>
      {!categories.isLoading && !categories.data?.length && <div className="notice-card">Cadastre uma categoria para começar. <button className="button-quiet" onClick={() => setCategoryOpen(true)}>Criar categoria</button></div>}
      {!!categories.data?.length && <div className="catalog-toolbar"><button className="button-quiet" onClick={() => setCategoryOpen(true)}>Gerenciar categorias</button></div>}
      {(services.isError || categories.isError) && <p className="notice-error" role="alert">Não foi possível carregar o catálogo. {errorMessage(services.error ?? categories.error)}</p>}
      {services.isLoading ? <div className="panel loading-panel">Carregando serviços…</div> : <div className="service-grid">{services.data?.map((service) => <article className="service-card panel" key={service.id}>
        <div className="service-card-top"><span className="service-symbol">✦</span><span className={`status-pill ${service.is_active ? "status-active" : "status-inactive"}`}>{service.is_active ? "Ativo" : "Inativo"}</span></div>
        <p className="eyebrow">{service.category_name}</p><h2>{service.name}</h2><p className="service-description">{service.description || "Sem descrição"}</p>
        <div className="service-facts"><span>{service.duration_minutes} min</span><strong>R$ {service.price}</strong></div>
        <div className="service-actions"><button className="button-quiet" onClick={() => startEdit(service)}>Editar</button><button className="button-quiet" disabled={toggle.isPending} onClick={() => toggle.mutate(service)}>{service.is_active ? "Desativar" : "Ativar"}</button></div>
      </article>)}</div>}
      {!services.isLoading && services.data?.length === 0 && <div className="panel empty-state"><span>✧</span><h2>Seu catálogo começa aqui</h2><p>Adicione o primeiro serviço para disponibilizá-lo na agenda.</p></div>}
    </main>
    {formOpen && <div className="modal-backdrop"><section className="modal-card panel" aria-labelledby="service-form-title"><div className="panel-heading"><div><p className="eyebrow">CATÁLOGO</p><h2 id="service-form-title">{editing ? "Editar serviço" : "Novo serviço"}</h2></div><button className="icon-button" aria-label="Fechar" onClick={() => setFormOpen(false)}>×</button></div>
      <form className="service-form" onSubmit={submit}>
        <label className="field-label">Nome<input className="field-input" required maxLength={120} value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })} /></label>
        <label className="field-label">Categoria<select className="field-input" required value={form.category || ""} onChange={(event) => setForm({ ...form, category: Number(event.target.value) })}><option value="">Selecione</option>{categories.data?.map((category) => <option key={category.id} value={category.id}>{category.name}</option>)}</select></label>
        <label className="field-label">Descrição<textarea className="field-input" rows={3} maxLength={500} value={form.description} onChange={(event) => setForm({ ...form, description: event.target.value })} /></label>
        <div className="form-columns"><label className="field-label">Preço (R$)<input className="field-input" type="number" min="0" step="0.01" required value={form.price} onChange={(event) => setForm({ ...form, price: event.target.value })} /></label><label className="field-label">Duração (min)<input className="field-input" type="number" min="1" max="1440" required value={form.duration_minutes} onChange={(event) => setForm({ ...form, duration_minutes: Number(event.target.value) })} /></label></div>
        <label className="field-label">Intervalo após atendimento (min)<input className="field-input" type="number" min="0" max="1440" required value={form.buffer_minutes} onChange={(event) => setForm({ ...form, buffer_minutes: Number(event.target.value) })} /></label>
        {save.isError && <p role="alert" className="notice-error">{errorMessage(save.error)}</p>}
        <button className="button-primary button-wide" disabled={save.isPending}>{save.isPending ? "Salvando…" : "Salvar serviço"}</button>
      </form>
    </section></div>}
    {categoryOpen && <div className="modal-backdrop"><section className="modal-card panel" aria-labelledby="category-form-title"><div className="panel-heading"><div><p className="eyebrow">ORGANIZAÇÃO</p><h2 id="category-form-title">Categorias de serviço</h2></div><button className="icon-button" aria-label="Fechar" onClick={() => setCategoryOpen(false)}>×</button></div>
      <div className="category-list">{categories.data?.map((category) => <span className="category-chip" key={category.id}>{category.name}</span>)}</div>
      <form className="service-form" onSubmit={(event) => { event.preventDefault(); createCategory.mutate(); }}><label className="field-label">Nova categoria<input className="field-input" required maxLength={80} value={categoryName} onChange={(event) => setCategoryName(event.target.value)} placeholder="Ex.: Cabelo, Barba, Unhas" /></label>{createCategory.isError && <p role="alert" className="notice-error">{errorMessage(createCategory.error)}</p>}<button className="button-primary button-wide" disabled={createCategory.isPending}>{createCategory.isPending ? "Salvando…" : "Adicionar categoria"}</button></form>
    </section></div>}
  </div>;
}
