import { Button } from "./index";

interface DialogProps {
  isOpen: boolean;
  onClose: () => void;
  onConfirm: () => void;
  title: string;
  description?: string;
  confirmText?: string;
  cancelText?: string;
  variant?: "danger" | "warning" | "info";
  isLoading?: boolean;
}

export function Dialog({
  isOpen,
  onClose,
  onConfirm,
  title,
  description,
  confirmText = "Confirmar",
  cancelText = "Cancelar",
  variant = "info",
  isLoading = false,
}: DialogProps) {
  if (!isOpen) return null;

  const variantClasses = {
    danger: "dialog-danger",
    warning: "dialog-warning",
    info: "dialog-info",
  };

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <section
        className={`modal-card panel dialog-card ${variantClasses[variant]}`.trim()}
        onClick={(e) => e.stopPropagation()}
        role="alertdialog"
        aria-modal="true"
      >
        <div className="dialog-content">
          <h2 className="dialog-title">{title}</h2>
          {description && <p className="dialog-description">{description}</p>}
        </div>
        <div className="dialog-actions">
          <Button variant="secondary" onClick={onClose} disabled={isLoading}>
            {cancelText}
          </Button>
          <Button onClick={onConfirm} disabled={isLoading}>
            {isLoading ? "Processando..." : confirmText}
          </Button>
        </div>
      </section>
    </div>
  );
}
