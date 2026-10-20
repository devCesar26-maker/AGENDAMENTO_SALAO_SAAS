import { type ReactNode } from "react";

interface FormFieldProps {
  label: string;
  error?: string;
  helperText?: string;
  children?: ReactNode;
}

export function FormField({ label, error, helperText, children }: FormFieldProps) {
  return (
    <div className="form-field">
      {/* O controle é filho do <label> para associação nativa (acessibilidade e
          getByLabelText nos testes) sem depender de um id repassado pelo caller. */}
      <label className="field-label">
        {label}
        {children}
        {error && <span>{error}</span>}
      </label>
      {helperText && !error && <p className="field-helper">{helperText}</p>}
    </div>
  );
}
