import { useAuth } from "../lib/auth";

export function AgendaPage() {
  const { user, logout } = useAuth();

  return (
    <div className="min-h-screen bg-slate-50">
      <header className="flex items-center justify-between border-b border-slate-200 bg-white px-4 py-3">
        <span className="font-semibold text-slate-900">Éclat Studio</span>
        <div className="flex items-center gap-3">
          <span className="text-sm text-slate-500">
            {user?.email}
            {user?.role ? ` · ${user.role}` : ""}
          </span>
          <button
            onClick={() => void logout()}
            className="rounded-lg border border-slate-300 px-3 py-1.5 text-sm text-slate-700 hover:bg-slate-100"
          >
            Sair
          </button>
        </div>
      </header>
      <main className="mx-auto max-w-3xl p-6">
        <div className="rounded-xl border border-dashed border-slate-300 bg-white p-10 text-center">
          <p className="font-medium text-slate-700">Agenda</p>
          <p className="mt-1 text-sm text-slate-500">
            A agenda completa (FullCalendar) chega na Fase 4.
          </p>
        </div>
      </main>
    </div>
  );
}
