import { useState, type FormEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, errorMessage } from "../lib/api";
import { DashboardHeader } from "../components/DashboardHeader";
import { Modal, Button, Card, FormField, SkeletonList, toast } from "../components/ui";

type Row<T> = T[] | { results: T[] };
type Category = { id: number; name: string; is_active: boolean };
type Service = { id: number; category: number; category_name: string; name: string; description: string; duration_minutes: number; price: string; buffer_minutes: number; is_active: boolean };
type ServiceInput = Omit<Service, "id" | "category_name">;
const rows = <T,>(data: Row<T>) => Array.isArray(data) ? data : data.results;
const blank: ServiceInput = { category: 0, name: "", description: "", duration_minutes: 30, price: "0.00", buffer_minutes: 0, is_active: true };

export function ServicesPage() {
  const client = useQueryClient();
  const [editing, setEditing] = useState<Service | null>(null);
  const [form, setForm] = useState<ServiceInput>(blank);
  const [formOpen, setFormOpen] = useState(false);
  const [categoryOpen, setCategoryOpen] = useState(false);
  const [categoryName, setCategoryName] = useState("");
  const services = useQuery({ queryKey: ["services"], queryFn: async () => rows((await api.get<Row<Service>>("/services/")).data) });
  const categories = useQuery({ queryKey: ["service-categories"], queryFn: async () => rows((await api.get<Row<Category>>("/service-categories/")).data).filter((category) => category.is_active) });
  const createCategory = useMutation({ mutationFn: () => api.post("/service-categories/", { name: categoryName, order: 0, is_active: true }), onSuccess: async () => { await client.invalidateQueries({ queryKey: ["service-categories"] }); setCategoryName(""); setCategoryOpen(false); toast("Categoria criada com sucesso", "success"); } });
  const save = useMutation({
    mutationFn: (input: ServiceInput) => editing ? api.patch(`/services/${editing.id}/`, input) : api.post("/services/", input),
    onSuccess: () => { void client.invalidateQueries({ queryKey: ["services"] }); setFormOpen(false); setEditing(null); setForm(blank); toast(editing ? "Serviço atualizado com sucesso" : "Serviço criado com sucesso", "success"); },
  });
  const toggle = useMutation({ mutationFn: (item: Service) => api.patch(`/services/${item.id}/`, { is_active: !item.is_active }), onSuccess: (_, variables) => { void client.invalidateQueries({ queryKey: ["services"] }); toast(`Serviço ${variables.is_active ? "desativado" : "ativado"} com sucesso`, "success"); } });
  function startCreate() { setEditing(null); setForm({ ...blank, category: categories.data?.[0]?.id ?? 0 }); setFormOpen(true); }
  function startEdit(service: Service) { setEditing(service); setForm({ category: service.category, name: service.name, description: service.description, duration_minutes: service.duration_minutes, price: service.price, buffer_minutes: service.buffer_minutes, is_active: service.is_active }); setFormOpen(true); }
  function submit(event: FormEvent) { event.preventDefault(); save.mutate(form); }

  return <div className="app-shell">
    <DashboardHeader current="Serviços" />
    <main className="page-content">
      <div className="page-heading">
        <div>
          <p className="eyebrow">CATÁLOGO</p>
          <h1>Serviços</h1>
          <p className="muted-copy">Organize o que seu espaço oferece, com duração e valores.</p>
        </div>
        <Button onClick={startCreate} disabled={!categories.data?.length}>
          Adicionar serviço
        </Button>
      </div>
      {!categories.isLoading && !categories.data?.length && (
        <div className="notice-card">
          Cadastre uma categoria para começar. <Button variant="secondary" onClick={() => setCategoryOpen(true)}>Criar categoria</Button>
        </div>
      )}
      {!!categories.data?.length && (
        <div className="catalog-toolbar">
          <Button variant="secondary" onClick={() => setCategoryOpen(true)}>
            Gerenciar categorias
          </Button>
        </div>
      )}
      {(services.isError || categories.isError) && (
        <p className="notice-error" role="alert">
          Não foi possível carregar o catálogo. {errorMessage(services.error ?? categories.error)}
        </p>
      )}
      {services.isLoading ? (
        <div className="panel loading-panel p-8">
          <SkeletonList count={4} />
        </div>
      ) : (
        <div className="service-grid">
          {services.data?.map((service) => (
            <Card className="service-card card-hover" key={service.id}>
              <div className="service-card-top">
                <span className="service-symbol">✦</span>
                <span className={`status-pill ${service.is_active ? "status-active" : "status-inactive"}`}>
                  {service.is_active ? "Ativo" : "Inativo"}
                </span>
              </div>
              <p className="eyebrow">{service.category_name}</p>
              <h2>{service.name}</h2>
              <p className="service-description">{service.description || "Sem descrição"}</p>
              <div className="service-facts">
                <span>{service.duration_minutes} min</span>
                <strong>R$ {service.price}</strong>
              </div>
              <div className="service-actions">
                <Button variant="secondary" onClick={() => startEdit(service)}>
                  Editar
                </Button>
                <Button variant="secondary" disabled={toggle.isPending} onClick={() => toggle.mutate(service)}>
                  {service.is_active ? "Desativar" : "Ativar"}
                </Button>
              </div>
            </Card>
          ))}
        </div>
      )}
      {!services.isLoading && services.data?.length === 0 && (
        <Card className="empty-state">
          <span>✧</span>
          <h2>Seu catálogo começa aqui</h2>
          <p>Adicione o primeiro serviço para disponibilizá-lo na agenda.</p>
        </Card>
      )}
    </main>
    <Modal
      isOpen={formOpen}
      onClose={() => setFormOpen(false)}
      title={editing ? "Editar serviço" : "Novo serviço"}
    >
      <form className="service-form" onSubmit={submit}>
        <FormField label="Nome">
          <input
            className="field-input"
            required
            maxLength={120}
            value={form.name}
            onChange={(event) => setForm({ ...form, name: event.target.value })}
          />
        </FormField>
        <FormField label="Categoria">
          <select
            className="field-input"
            required
            value={form.category || ""}
            onChange={(event) => setForm({ ...form, category: Number(event.target.value) })}
          >
            <option value="">Selecione</option>
            {categories.data?.map((category) => (
              <option key={category.id} value={category.id}>
                {category.name}
              </option>
            ))}
          </select>
        </FormField>
        <FormField label="Descrição">
          <textarea
            className="field-input"
            rows={3}
            maxLength={500}
            value={form.description}
            onChange={(event) => setForm({ ...form, description: event.target.value })}
          />
        </FormField>
        <div className="form-columns">
          <FormField label="Preço (R$)">
            <input
              className="field-input"
              type="number"
              min="0"
              step="0.01"
              required
              value={form.price}
              onChange={(event) => setForm({ ...form, price: event.target.value })}
            />
          </FormField>
          <FormField label="Duração (min)">
            <input
              className="field-input"
              type="number"
              min="1"
              max="1440"
              required
              value={form.duration_minutes}
              onChange={(event) => setForm({ ...form, duration_minutes: Number(event.target.value) })}
            />
          </FormField>
        </div>
        <FormField label="Intervalo após atendimento (min)">
          <input
            className="field-input"
            type="number"
            min="0"
            max="1440"
            required
            value={form.buffer_minutes}
            onChange={(event) => setForm({ ...form, buffer_minutes: Number(event.target.value) })}
          />
        </FormField>
        {save.isError && <p role="alert" className="notice-error">{errorMessage(save.error)}</p>}
        <Button className="button-wide" disabled={save.isPending}>
          {save.isPending ? "Salvando…" : "Salvar serviço"}
        </Button>
      </form>
    </Modal>
    <Modal
      isOpen={categoryOpen}
      onClose={() => setCategoryOpen(false)}
      title="Categorias de serviço"
    >
      <div className="category-list">
        {categories.data?.map((category) => (
          <span className="category-chip" key={category.id}>
            {category.name}
          </span>
        ))}
      </div>
      <form
        className="service-form"
        onSubmit={(event) => {
          event.preventDefault();
          createCategory.mutate();
        }}
      >
        <FormField label="Nova categoria">
          <input
            className="field-input"
            required
            maxLength={80}
            value={categoryName}
            onChange={(event) => setCategoryName(event.target.value)}
            placeholder="Ex.: Cabelo, Barba, Unhas"
          />
        </FormField>
        {createCategory.isError && <p role="alert" className="notice-error">{errorMessage(createCategory.error)}</p>}
        <Button className="button-wide" disabled={createCategory.isPending}>
          {createCategory.isPending ? "Salvando…" : "Adicionar categoria"}
        </Button>
      </form>
    </Modal>
  </div>;
}
