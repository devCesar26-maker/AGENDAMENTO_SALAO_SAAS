import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { CheckCircle2, Circle } from "lucide-react";
import { api } from "../lib/api";
import { useAuth } from "../lib/auth-context";

type Row<T> = T[] | { results: T[] };
const rows = <T,>(data: Row<T>) => (Array.isArray(data) ? data : data.results);

const DISMISS_KEY = "eclat:onboarding-dismissed";

export function OnboardingChecklist() {
  const { user } = useAuth();
  const slug = user?.organization?.slug ?? "";
  const canManage = user?.role === "OWNER" || user?.role === "MANAGER";

  const [dismissed, setDismissed] = useState(() => {
    try {
      return localStorage.getItem(`${DISMISS_KEY}:${slug}`) === "1";
    } catch {
      return false;
    }
  });

  const services = useQuery({
    queryKey: ["services"],
    enabled: canManage && !!slug && !dismissed,
    queryFn: async () => rows((await api.get<Row<{ id: number }>>("/services/")).data),
  });
  const professionals = useQuery({
    queryKey: ["professionals"],
    enabled: canManage && !!slug && !dismissed,
    queryFn: async () => rows((await api.get<Row<{ id: number }>>("/professionals/")).data),
  });
  const org = useQuery({
    queryKey: ["organization", slug],
    enabled: canManage && !!slug && !dismissed,
    queryFn: async () => (await api.get<{ working_hours: Record<string, unknown[]> }>(`/organizations/${slug}/`)).data,
  });

  if (!canManage || dismissed || !slug) return null;

  const hasServices = (services.data?.length ?? 0) > 0;
  const hasProfessionals = (professionals.data?.length ?? 0) > 0;
  const hasHours = Object.values(org.data?.working_hours ?? {}).some(day => (day?.length ?? 0) > 0);
  const steps = [
    { id: "services", label: "Cadastre serviços no catálogo", done: hasServices, href: "/app/servicos" },
    { id: "professionals", label: "Adicione profissionais", done: hasProfessionals, href: "/app/profissionais" },
    { id: "hours", label: "Defina horário de funcionamento", done: hasHours, href: "/app/configuracoes" },
    { id: "link", label: "Compartilhe o link de reserva", done: false, href: "/app/configuracoes" },
  ];
  const completed = steps.filter(step => step.done).length;
  if (completed >= 3) return null;

  function dismiss() {
    try {
      localStorage.setItem(`${DISMISS_KEY}:${slug}`, "1");
    } catch {
      /* ignore */
    }
    setDismissed(true);
  }

  return (
    <section className="panel onboarding-panel" aria-label="Primeiros passos">
      <div className="onboarding-heading">
        <div>
          <p className="eyebrow">PRIMEIROS PASSOS</p>
          <h2>Configure seu espaço</h2>
          <p className="helper-copy">{completed} de {steps.length} etapas concluídas</p>
        </div>
        <button type="button" className="button-quiet" onClick={dismiss}>
          Ocultar
        </button>
      </div>
      <ul className="onboarding-steps">
        {steps.map(step => (
          <li key={step.id}>
            <Link to={step.href} className="onboarding-step">
              {step.done ? <CheckCircle2 size={18} className="onboarding-icon-done" /> : <Circle size={18} className="onboarding-icon-todo" />}
              <span>{step.label}</span>
            </Link>
          </li>
        ))}
      </ul>
    </section>
  );
}
