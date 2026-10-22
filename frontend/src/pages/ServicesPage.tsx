import { useState, type FormEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, errorMessage } from "../lib/api";
import { Modal, Button, FormField, SkeletonList, toast } from "../components/ui";

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

  return <>
    <main className="services-page">
      <div className="services-header">
        <div className="services-title">
          <h1>Serviços</h1>
          <p className="services-subtitle">Cuide de cada detalhe do seu catálogo</p>
        </div>
        <button
          className="services-btn-primary"
          onClick={startCreate}
          disabled={!categories.data?.length}
        >
          + Novo serviço
        </button>
      </div>

      {!categories.isLoading && !categories.data?.length && (
        <div className="services-empty-category">
          <div className="services-empty-icon">✨</div>
          <h3>Comece criando uma categoria</h3>
          <p>Organize seus serviços por categorias como Cabelo, Barba, Unhas</p>
          <button
            className="services-btn-secondary"
            onClick={() => setCategoryOpen(true)}
          >
            Criar categoria
          </button>
        </div>
      )}

      {!!categories.data?.length && (
        <div className="services-toolbar">
          <button
            className="services-btn-text"
            onClick={() => setCategoryOpen(true)}
          >
            Gerenciar categorias
          </button>
        </div>
      )}

      {(services.isError || categories.isError) && (
        <div className="services-error">
          Não foi possível carregar o catálogo. {errorMessage(services.error ?? categories.error)}
        </div>
      )}

      {services.isLoading ? (
        <div className="services-loading">
          <SkeletonList count={4} />
        </div>
      ) : (
        <div className="services-grid">
          {services.data?.map((service) => (
            <div className="services-card" key={service.id}>
              <div className="services-card-header">
                <span className="services-category">{service.category_name}</span>
                <span className={`services-status ${service.is_active ? "active" : "inactive"}`}>
                  {service.is_active ? "Ativo" : "Inativo"}
                </span>
              </div>
              <h3 className="services-card-title">{service.name}</h3>
              <p className="services-card-description">{service.description || "Sem descrição"}</p>
              <div className="services-card-meta">
                <span className="services-duration">{service.duration_minutes} min</span>
                <span className="services-price">R$ {service.price}</span>
              </div>
              <div className="services-card-actions">
                <button
                  className="services-btn-outline"
                  onClick={() => startEdit(service)}
                >
                  Editar
                </button>
                <button
                  className={`services-btn-toggle ${service.is_active ? "active" : "inactive"}`}
                  disabled={toggle.isPending}
                  onClick={() => toggle.mutate(service)}
                >
                  {service.is_active ? "Desativar" : "Ativar"}
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {!services.isLoading && services.data?.length === 0 && (
        <div className="services-empty">
          <div className="services-empty-icon">💆</div>
          <h3>Seu catálogo está vazio</h3>
          <p>Adicione o primeiro serviço para começar a receber agendamentos</p>
        </div>
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
        <Button type="submit" className="button-wide" disabled={save.isPending}>
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
        <Button type="submit" className="button-wide" disabled={createCategory.isPending}>
          {createCategory.isPending ? "Salvando…" : "Adicionar categoria"}
        </Button>
      </form>
    </Modal>
  </>;
}
