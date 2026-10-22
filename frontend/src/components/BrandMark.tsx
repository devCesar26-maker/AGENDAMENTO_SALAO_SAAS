export function BrandMark({ label = "É", className = "" }: { label?: string; className?: string }) {
  return (
    <span className={`brand-mark ${className}`.trim()} aria-hidden="true">
      {label.slice(0, 1).toUpperCase()}
    </span>
  );
}
