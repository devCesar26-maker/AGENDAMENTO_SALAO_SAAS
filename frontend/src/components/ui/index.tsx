import { forwardRef, type ButtonHTMLAttributes, type HTMLAttributes, type InputHTMLAttributes, type ReactNode, type SelectHTMLAttributes } from "react";

type ButtonVariant = "primary" | "secondary" | "ghost";

export function Button({ variant = "primary", className = "", type = "button", ...props }: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: ButtonVariant }) {
  const styles = { primary: "button-primary", secondary: "button-quiet", ghost: "button-quiet ui-button-ghost" };
  return <button type={type} className={`${styles[variant]} ${className}`.trim()} {...props} />;
}

export const Input = forwardRef<HTMLInputElement, InputHTMLAttributes<HTMLInputElement>>(function Input({ className = "", ...props }, ref) {
  return <input ref={ref} className={`field-input ${className}`.trim()} {...props} />;
});

export const Select = forwardRef<HTMLSelectElement, SelectHTMLAttributes<HTMLSelectElement>>(function Select({ className = "", children, ...props }, ref) {
  return <select ref={ref} className={`field-input ${className}`.trim()} {...props}>{children}</select>;
});

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

export { Modal } from "./Modal";
export { Tabs } from "./Tabs";
export { Table } from "./Table";
export { Skeleton, SkeletonCard, SkeletonList } from "./Skeleton";
export { Dialog } from "./Dialog";
export { Select as SelectComponent } from "./Select";
export { toast, ToastContainer } from "./Toast";
export { FormField } from "./FormField";
export { Tooltip } from "./Tooltip";
export { Pagination } from "./Pagination";
