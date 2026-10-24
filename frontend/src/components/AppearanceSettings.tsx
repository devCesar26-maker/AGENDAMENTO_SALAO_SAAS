import { useEffect, useState, type ChangeEvent } from "react";
import { Modal } from "./ui";

type Appearance = { image: string; shade: number; blur: number; position: string; panelOpacity: number };
type StoredAppearance = Partial<Appearance> & { version?: number };

/** Versão 3: scrim entre a foto e o conteúdo e piso de opacidade por legibilidade. */
const APPEARANCE_VERSION = 3;
const DEFAULTS: Appearance = { image: "", shade: 38, blur: 0, position: "center", panelOpacity: 75 };
/** Abaixo disso o texto deixa de ter contraste AA sobre uma foto clara; o controle não permite. */
const MIN_PANEL_OPACITY = 65;
const MIN_SHADE = 35;
const MAX_SHADE = 94;
const MAX_BLUR = 12;
/* Fotos grandes são aceitas e reduzidas no navegador, em vez de exigir arquivos já comprimidos. */
const MAX_SOURCE_BYTES = 15_000_000;
const MAX_STORED_CHARS = 1_600_000;
const MAX_IMAGE_EDGE = 2560;

function clamp(value: number, min: number, max: number) {
  return Math.min(max, Math.max(min, value));
}

function normalizeAppearance(raw: StoredAppearance): Appearance {
  // Registros anteriores à versão 2 vêm de uma implementação em que a transparência
  // não funcionava; nesses casos os ajustes voltam ao padrão visível, mantendo a foto.
  const preGlass = typeof raw.version !== "number" || raw.version < 2;
  const shade = typeof raw.shade === "number" ? raw.shade : DEFAULTS.shade;
  const blur = typeof raw.blur === "number" ? raw.blur : DEFAULTS.blur;
  const panelOpacity = typeof raw.panelOpacity === "number" ? raw.panelOpacity : DEFAULTS.panelOpacity;
  return {
    image: typeof raw.image === "string" ? raw.image : DEFAULTS.image,
    shade: clamp(preGlass ? DEFAULTS.shade : shade, MIN_SHADE, MAX_SHADE),
    blur: clamp(preGlass ? DEFAULTS.blur : blur, 0, MAX_BLUR),
    position: typeof raw.position === "string" ? raw.position : DEFAULTS.position,
    panelOpacity: clamp(preGlass ? DEFAULTS.panelOpacity : panelOpacity, MIN_PANEL_OPACITY, 100),
  };
}

function readFileAsDataUrl(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result));
    reader.onerror = () => reject(reader.error);
    reader.readAsDataURL(file);
  });
}

function loadImage(source: string): Promise<HTMLImageElement | null> {
  return new Promise((resolve) => {
    const image = new Image();
    image.onload = () => resolve(image);
    image.onerror = () => resolve(null);
    image.src = source;
  });
}

/** Reduz e recomprime a foto para caber no armazenamento local sem perder definição visível. */
async function compressImage(source: string): Promise<string | null> {
  const canvas = document.createElement("canvas");
  let context: CanvasRenderingContext2D | null = null;
  try {
    context = canvas.getContext("2d");
  } catch {
    context = null;
  }
  if (!context) return null;

  const image = await loadImage(source);
  if (!image) return null;
  const width = image.naturalWidth || image.width;
  const height = image.naturalHeight || image.height;
  if (!width || !height) return null;

  for (let edge = MAX_IMAGE_EDGE; edge >= 1280; edge = Math.round(edge * 0.8)) {
    const scale = Math.min(1, edge / Math.max(width, height));
    canvas.width = Math.max(1, Math.round(width * scale));
    canvas.height = Math.max(1, Math.round(height * scale));
    const target = canvas.getContext("2d");
    if (!target) return null;
    target.drawImage(image, 0, 0, canvas.width, canvas.height);

    for (const quality of [0.94, 0.86, 0.78]) {
      for (const type of ["image/webp", "image/jpeg"]) {
        const output = canvas.toDataURL(type, quality);
        if (output.startsWith(`data:${type}`) && output.length <= MAX_STORED_CHARS) return output;
      }
    }
  }
  return null;
}

async function prepareImage(file: File): Promise<string | null> {
  const original = await readFileAsDataUrl(file);
  if (original.length <= MAX_STORED_CHARS) return original;
  return (await compressImage(original)) ?? null;
}

export function AppearanceSettings({ organizationSlug, collapsed = false }: { organizationSlug?: string; collapsed?: boolean }) {
  const storageKey = `eclat:appearance:${organizationSlug || "default"}`;
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [appearance, setAppearance] = useState<Appearance>(() => {
    try {
      const stored = localStorage.getItem(storageKey);
      if (!stored) return DEFAULTS;
      const raw = JSON.parse(stored) as StoredAppearance;
      const normalized = normalizeAppearance(raw);
      if (raw.version !== APPEARANCE_VERSION) {
        localStorage.setItem(storageKey, JSON.stringify({ ...normalized, version: APPEARANCE_VERSION }));
      }
      return normalized;
    } catch {
      return DEFAULTS;
    }
  });
  /** Prévia em edição: só chega às telas ao salvar. */
  const [draft, setDraft] = useState<Appearance | null>(null);
  const [message, setMessage] = useState("");

  function applyAppearance(next: Appearance) {
    setAppearance(next);
    try {
      localStorage.setItem(storageKey, JSON.stringify({ ...next, version: APPEARANCE_VERSION }));
      setMessage("");
    } catch {
      setMessage("Não foi possível salvar a imagem neste navegador. Escolha um arquivo menor.");
    }
  }

  function updateDraft(patch: Partial<Appearance>) {
    setDraft((current) => {
      if (!current) return current;
      const next = { ...current, ...patch };
      return {
        ...next,
        shade: clamp(next.shade, MIN_SHADE, MAX_SHADE),
        blur: clamp(next.blur, 0, MAX_BLUR),
        panelOpacity: clamp(next.panelOpacity, MIN_PANEL_OPACITY, 100),
      };
    });
    setMessage("");
  }

  function openPanel() {
    setDraft(appearance);
    setMessage("");
    setOpen(true);
  }

  function closePanel() {
    setDraft(null);
    setOpen(false);
  }

  function save() {
    if (!draft) return;
    applyAppearance(draft);
    closePanel();
  }

  useEffect(() => {
    const root = document.documentElement;
    root.style.setProperty("--workspace-backdrop", appearance.image ? `url("${appearance.image}")` : "none");
    root.style.setProperty("--workspace-shade", `${appearance.shade}%`);
    root.style.setProperty("--workspace-blur", `${appearance.blur}px`);
    root.style.setProperty("--workspace-position", appearance.position);
    root.style.setProperty("--workspace-panel-opacity", `${appearance.panelOpacity}%`);
    root.dataset.workspaceBackdrop = appearance.image ? "true" : "false";
    return () => {
      root.style.removeProperty("--workspace-backdrop");
      root.style.removeProperty("--workspace-shade");
      root.style.removeProperty("--workspace-blur");
      root.style.removeProperty("--workspace-position");
      root.style.removeProperty("--workspace-panel-opacity");
      delete root.dataset.workspaceBackdrop;
    };
  }, [appearance, storageKey]);

  useEffect(() => {
    if (!collapsed) return;
    setOpen(false);
    setDraft(null);
  }, [collapsed]);

  function chooseImage(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = "";
    setMessage("");
    if (!file) return;
    if (!file.type.startsWith("image/")) {
      setMessage("Escolha um arquivo de imagem.");
      return;
    }
    if (file.size > MAX_SOURCE_BYTES) {
      setMessage("A imagem deve ter até 15 MB.");
      return;
    }
    setBusy(true);
    void prepareImage(file)
      .then((dataUrl) => {
        if (!dataUrl) {
          setMessage("Não foi possível reduzir esta imagem para o armazenamento do navegador. Escolha um arquivo menor.");
          return;
        }
        updateDraft({ image: dataUrl });
      })
      .catch(() => setMessage("Não foi possível abrir esta imagem."))
      .finally(() => setBusy(false));
  }

  if (collapsed) return null;

  const preview = draft ?? appearance;

  return (
    <div className="appearance-control">
      <button className="button-quiet" type="button" onClick={openPanel} aria-haspopup="dialog">
        Aparência
      </button>
      <Modal
        isOpen={open}
        onClose={closePanel}
        className="appearance-panel"
        ariaLabel="Personalizar aparência do espaço"
      >
        <div className="panel-heading">
          <div><p className="eyebrow">Seu espaço</p><h2>Personalizar fundo</h2></div>
          <button className="icon-button" type="button" aria-label="Fechar personalização" onClick={closePanel}>×</button>
        </div>
        <label className="field-label">Imagem de fundo
          <input className="field-input" type="file" accept="image/*" disabled={busy} onChange={chooseImage} />
        </label>
        {busy && <p className="helper-copy" role="status">Preparando imagem em alta qualidade…</p>}

        <div className="appearance-preview">
          {preview.image ? (
            <>
              <div
                className="appearance-preview-photo"
                style={{
                  backgroundImage: `url("${preview.image}")`,
                  backgroundPosition: preview.position,
                  // Espelha o desfoque leve fixo de 3px aplicado ao fundo real.
                  filter: `blur(${3 + preview.blur}px)`,
                }}
                aria-hidden="true"
              />
              <div
                className="appearance-preview-tint"
                style={{ backgroundColor: `color-mix(in srgb, var(--workspace-tint) ${preview.shade}%, transparent)` }}
                aria-hidden="true"
              />
            </>
          ) : <p className="appearance-preview-empty">Escolha uma imagem para ver a prévia do espaço</p>}
          <div className="appearance-preview-scrim" aria-hidden="true" />
          <div
            className="appearance-preview-card"
            style={{ backgroundColor: `color-mix(in srgb, var(--surface) ${preview.panelOpacity}%, transparent)` }}
            aria-hidden="true"
          >
            <small>Prévia do cartão</small>
            <strong>R$ 4.280,00</strong>
          </div>
        </div>
        <p className="helper-copy">Prévia ao vivo. KPIs, gráficos e tabelas ficam sempre quase sólidos para os números continuarem legíveis.</p>

        <label className="field-label">Escurecimento da imagem <span>{preview.shade}%</span>
          <input type="range" min={MIN_SHADE} max={MAX_SHADE} value={preview.shade} onChange={(event) => updateDraft({ shade: Number(event.target.value) })} />
        </label>
        <label className="field-label">Desfoque da imagem <span>{preview.blur}px</span>
          <input type="range" min="0" max={MAX_BLUR} value={preview.blur} onChange={(event) => updateDraft({ blur: Number(event.target.value) })} />
        </label>
        <p className="helper-copy">A imagem sempre recebe um desfoque leve de 3px; este controle adiciona mais.</p>
        <label className="field-label">Opacidade dos cartões <span>{preview.panelOpacity}%</span>
          <input type="range" min={MIN_PANEL_OPACITY} max="100" value={preview.panelOpacity} onChange={(event) => updateDraft({ panelOpacity: Number(event.target.value) })} />
        </label>
        <p className="helper-copy">O mínimo de {MIN_PANEL_OPACITY}% é intencional: abaixo disso o texto perderia contraste sobre fotos claras. A imagem continua aparecendo nos cartões e nas laterais, sempre com um desfoque leve fixo para não competir com o conteúdo.</p>
        <label className="field-label">Enquadramento
          <select className="field-input" value={preview.position} onChange={(event) => updateDraft({ position: event.target.value })}>
            <option value="center">Centro</option><option value="center top">Topo</option><option value="center bottom">Base</option><option value="left center">Esquerda</option><option value="right center">Direita</option>
          </select>
        </label>
        {message && <p className="inline-message" role="status">{message}</p>}
        {preview.image && (
          <button className="button-quiet" type="button" onClick={() => updateDraft(DEFAULTS)}>Remover imagem</button>
        )}
        <div className="appearance-actions">
          <button className="button-primary" type="button" onClick={save} disabled={busy || !draft}>Salvar alterações</button>
          <button className="button-quiet" type="button" onClick={closePanel}>Cancelar</button>
        </div>
        <p className="helper-copy">A imagem e os ajustes ficam salvos somente neste navegador e nesta organização.</p>
      </Modal>
    </div>
  );
}
