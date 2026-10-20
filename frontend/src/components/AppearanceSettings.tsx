import { useEffect, useState, type ChangeEvent } from "react";

type Appearance = { image: string; shade: number; blur: number; position: string };
const DEFAULTS: Appearance = { image: "", shade: 78, blur: 0, position: "center" };
const MAX_IMAGE_BYTES = 1_200_000;

export function AppearanceSettings({ organizationSlug }: { organizationSlug?: string }) {
  const storageKey = `eclat:appearance:${organizationSlug || "default"}`;
  const [open, setOpen] = useState(false);
  const [appearance, setAppearance] = useState<Appearance>(() => {
    try {
      return { ...DEFAULTS, ...JSON.parse(localStorage.getItem(storageKey) || "{}") };
    } catch {
      return DEFAULTS;
    }
  });
  const [message, setMessage] = useState("");

  function updateAppearance(next: Appearance | ((current: Appearance) => Appearance)) {
    const updated = typeof next === "function" ? next(appearance) : next;
    setAppearance(updated);
    try {
      localStorage.setItem(storageKey, JSON.stringify(updated));
      setMessage("");
    } catch {
      setMessage("Não foi possível salvar a imagem neste navegador. Escolha um arquivo menor.");
    }
  }

  useEffect(() => {
    document.documentElement.style.setProperty(
      "--workspace-backdrop",
      appearance.image ? `url("${appearance.image}")` : "none",
    );
    document.documentElement.style.setProperty("--workspace-shade", `${appearance.shade}%`);
    document.documentElement.style.setProperty("--workspace-blur", `${appearance.blur}px`);
    document.documentElement.style.setProperty("--workspace-position", appearance.position);
    return () => {
      document.documentElement.style.removeProperty("--workspace-backdrop");
      document.documentElement.style.removeProperty("--workspace-shade");
      document.documentElement.style.removeProperty("--workspace-blur");
      document.documentElement.style.removeProperty("--workspace-position");
    };
  }, [appearance, storageKey]);

  function chooseImage(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    setMessage("");
    if (!file) return;
    if (!file.type.startsWith("image/")) {
      setMessage("Escolha um arquivo de imagem.");
      return;
    }
    if (file.size > MAX_IMAGE_BYTES) {
      setMessage("A imagem deve ter até 1,2 MB para ser guardada neste navegador.");
      return;
    }
    const reader = new FileReader();
    reader.onload = () => updateAppearance((current) => ({ ...current, image: String(reader.result) }));
    reader.onerror = () => setMessage("Não foi possível abrir esta imagem.");
    reader.readAsDataURL(file);
    event.target.value = "";
  }

  return (
    <div className="appearance-control">
      <button className="button-quiet" type="button" onClick={() => setOpen((value) => !value)} aria-expanded={open}>
        Aparência
      </button>
      {open && (
        <section className="appearance-panel panel" aria-label="Personalizar aparência">
          <div className="panel-heading">
            <div><p className="eyebrow">Seu espaço</p><h2>Personalizar fundo</h2></div>
            <button className="icon-button" type="button" aria-label="Fechar personalização" onClick={() => setOpen(false)}>×</button>
          </div>
          <label className="field-label">Imagem de fundo
            <input className="field-input" type="file" accept="image/*" onChange={chooseImage} />
          </label>
          <label className="field-label">Escurecimento <span>{appearance.shade}%</span>
            <input type="range" min="35" max="94" value={appearance.shade} onChange={(event) => updateAppearance({ ...appearance, shade: Number(event.target.value) })} />
          </label>
          <label className="field-label">Desfoque <span>{appearance.blur}px</span>
            <input type="range" min="0" max="12" value={appearance.blur} onChange={(event) => updateAppearance({ ...appearance, blur: Number(event.target.value) })} />
          </label>
          <label className="field-label">Enquadramento
            <select className="field-input" value={appearance.position} onChange={(event) => updateAppearance({ ...appearance, position: event.target.value })}>
              <option value="center">Centro</option><option value="center top">Topo</option><option value="center bottom">Base</option><option value="left center">Esquerda</option><option value="right center">Direita</option>
            </select>
          </label>
          {message && <p className="inline-message" role="status">{message}</p>}
          {appearance.image && <button className="button-quiet" type="button" onClick={() => updateAppearance({ ...DEFAULTS, shade: appearance.shade, blur: appearance.blur })}>Remover imagem</button>}
          <p className="helper-copy">A imagem e os ajustes ficam salvos somente neste navegador e nesta organização.</p>
        </section>
      )}
    </div>
  );
}
