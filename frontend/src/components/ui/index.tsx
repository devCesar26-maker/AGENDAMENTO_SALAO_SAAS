import type { ButtonHTMLAttributes, HTMLAttributes, InputHTMLAttributes, ReactNode, SelectHTMLAttributes } from "react";

type ButtonVariant = "primary" | "secondary" | "ghost";

export function Button({ variant = "primary", className = "", type = "button", ...props }: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: ButtonVariant }) {
  const styles = { primary: "button-primary", secondary: "button-quiet", ghost: "button-quiet ui-button-ghost" };
  return <button type={type} className={`${styles[variant]} ${className}`.trim()} {...props} />;
}

export function Input({ className = "", ...props }: InputHTMLAttributes<HTMLInputElement>) {
  return <input className={`field-input ${className}`.trim()} {...props} />;
}

export function Select({ className = "", children, ...props }: SelectHTMLAttributes<HTMLSelectElement>) {
  return <select className={`field-input ${className}`.trim()} {...props}>{children}</select>;
}

export function Card({ className = "", children, ...props }: { className?: string; children: ReactNode } & HTMLAttributes<HTMLDivElement>) {
  return <div className={`panel ${className}`.trim()} {...props}>{children}</div>;
}

type BadgeTone = "neutral" | "success" | "warning";
export function Badge({ tone = "neutral", className = "", children }: { tone?: BadgeTone; className?: string; children: ReactNode }) {
  return <span className={`ui-badge ui-badge-${tone} ${className}`.trim()}>{children}</span>;
}

export function EmptyState({ title, children, className = "" }: { title: string; children: ReactNode; className?: string }) {
  return <section className={`panel empty-state ${className}`.trim()} aria-label={title}><span aria-hidden="true">✧</span><h2>{title}</h2><p>{children}</p></section>;
}
