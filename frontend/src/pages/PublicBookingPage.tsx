import { useParams } from "react-router-dom";

export function PublicBookingPage() {
  const { slug } = useParams<{ slug: string }>();

  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-50 px-4">
      <div className="w-full max-w-md rounded-2xl bg-white p-8 shadow-lg">
        <h1 className="text-xl font-semibold text-slate-900">Reservar um horário</h1>
        <p className="mt-1 text-sm text-slate-500">Salão: {slug}</p>
        <div className="mt-6 rounded-lg border border-dashed border-slate-300 p-6 text-center text-sm text-slate-500">
          Fluxo público de reserva chega na Fase 4.
        </div>
      </div>
    </div>
  );
}
