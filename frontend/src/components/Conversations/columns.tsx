import { Link } from "@tanstack/react-router"
import type { ColumnDef } from "@tanstack/react-table"
import { ExternalLink } from "lucide-react"

import type { ConversationSummary } from "@/client"
import type { DataTableFeatures } from "@/components/Common/DataTable"
import { Button } from "@/components/ui/button"

function formatTimestamp(value: string | null | undefined): string {
  if (!value) {
    return "—"
  }
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? "—" : date.toLocaleString()
}

export const columns: ColumnDef<DataTableFeatures, ConversationSummary>[] = [
  {
    accessorKey: "title",
    header: "Title",
    cell: ({ row }) => (
      <span className="font-medium">{row.original.title}</span>
    ),
  },
  {
    accessorKey: "created_at",
    header: "Created",
    cell: ({ row }) => (
      <span className="text-muted-foreground">
        {formatTimestamp(row.original.created_at)}
      </span>
    ),
  },
  {
    accessorKey: "updated_at",
    header: "Updated",
    cell: ({ row }) => (
      <span className="text-muted-foreground">
        {formatTimestamp(row.original.updated_at)}
      </span>
    ),
  },
  {
    id: "actions",
    header: () => <span className="sr-only">Actions</span>,
    cell: ({ row }) => (
      <div className="flex justify-end">
        <Button variant="ghost" size="sm" asChild>
          <Link
            to="/conversations/$id"
            params={{ id: row.original.id }}
            aria-label={`Open ${row.original.title}`}
          >
            <ExternalLink className="size-4" />
            Open
          </Link>
        </Button>
      </div>
    ),
  },
]
