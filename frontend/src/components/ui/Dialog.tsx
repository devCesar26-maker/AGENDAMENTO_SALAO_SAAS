import { useEffect, useId } from "react";
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
  const titleId = useId();
  const descriptionId = useId();

  useEffect(() => {
    if (!isOpen) return;
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape" && !isLoading) onClose();
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [isOpen, isLoading, onClose]);

  useEffect(() => {
    if (!isOpen) return;
    const previousFocus = document.activeElement;
    return () => {
      if (previousFocus instanceof HTMLElement) previousFocus.focus();
    };
  }, [isOpen]);

  if (!isOpen) return null;

  const variantClasses = {
    danger: "dialog-danger",
    warning: "dialog-warning",
    info: "dialog-info",
  };

  return (
    <div className="modal-backdrop" onClick={isLoading ? undefined : onClose}>
      <section
        className={`modal-card panel dialog-card ${variantClasses[variant]}`.trim()}
        onClick={(e) => e.stopPropagation()}
        role="alertdialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={description ? descriptionId : undefined}
      >
        <div className="dialog-content">
          <h2 id={titleId} className="dialog-title">{title}</h2>
          {description && <p id={descriptionId} className="dialog-description">{description}</p>}
        </div>
        <div className="dialog-actions">
          <Button variant="secondary" onClick={onClose} disabled={isLoading} autoFocus>
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
