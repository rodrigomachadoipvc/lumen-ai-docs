import { CircleAlertIcon, CircleCheckIcon, ClockIcon, LoaderCircleIcon } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import type { DocumentStatus } from "@/lib/api";
import { cn } from "@/lib/utils";

const STATUS = {
  pending: { label: "Queued", Icon: ClockIcon, className: "text-muted-foreground" },
  processing: { label: "Processing", Icon: LoaderCircleIcon, className: "text-primary" },
  ready: {
    label: "Ready",
    Icon: CircleCheckIcon,
    className: "text-emerald-700 dark:text-emerald-400",
  },
  failed: { label: "Failed", Icon: CircleAlertIcon, className: "text-destructive" },
} satisfies Record<DocumentStatus, { label: string; Icon: typeof ClockIcon; className: string }>;

export function StatusBadge({ status }: { status: DocumentStatus }) {
  const { label, Icon, className } = STATUS[status];
  return (
    <Badge variant="outline" className={cn("gap-1", className)}>
      <Icon className={cn("size-3", status === "processing" && "animate-spin")} aria-hidden />
      {label}
    </Badge>
  );
}
