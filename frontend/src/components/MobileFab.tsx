import { CalendarPlus } from "lucide-react";
import { Button } from "./ui";

export function MobileFab({ label, onClick }: { label: string; onClick: () => void }) {
  return (
    <div className="mobile-fab-wrap">
      <Button type="button" className="mobile-fab" onClick={onClick} aria-label={label}>
        <CalendarPlus size={22} aria-hidden />
        <span>{label}</span>
      </Button>
    </div>
  );
}
