import { useSuspenseQuery } from "@tanstack/react-query"
import { createFileRoute, Outlet, useMatchRoute } from "@tanstack/react-router"
import { ChevronLeft, ChevronRight, MessagesSquare } from "lucide-react"
import { Suspense, useState } from "react"

import { ConversationsService } from "@/client"
import { DataTable } from "@/components/Common/DataTable"
import AddConversation from "@/components/Conversations/AddConversation"
import ConversationSearch from "@/components/Conversations/ConversationSearch"
import { columns } from "@/components/Conversations/columns"
import PendingConversations from "@/components/Pending/PendingConversations"
import { Button } from "@/components/ui/button"
import useAuth from "@/hooks/useAuth"

const PAGE_SIZE = 10

export const Route = createFileRoute("/_layout/conversations")({
  component: Conversations,
  head: () => ({
    meta: [
      {
        title: "Conversations - FastAPI Template",
      },
    ],
  }),
})

function ConversationsTableContent({
  userId,
  search,
  page,
  onPrevious,
  onNext,
}: {
  userId: string | null
  search: string
  page: number
  onPrevious: () => void
  onNext: () => void
}) {
  const { data: conversations } = useSuspenseQuery({
    queryFn: async () =>
      (
        await ConversationsService.readConversations({
          query: { skip: page * PAGE_SIZE, limit: PAGE_SIZE, search },
        })
      ).data,
    queryKey: ["conversations", userId, { search, page }],
  })

  const firstRow = conversations.count === 0 ? 0 : page * PAGE_SIZE + 1
  const lastRow = Math.min((page + 1) * PAGE_SIZE, conversations.count)
  const hasPrevious = page > 0
  const hasNext = lastRow < conversations.count

  return (
    <div className="flex flex-col gap-4">
      {conversations.data.length === 0 ? (
        <div className="flex flex-col items-center justify-center text-center py-12">
          <div className="rounded-full bg-muted p-4 mb-4">
            <MessagesSquare className="h-8 w-8 text-muted-foreground" />
          </div>
          <h3 className="text-lg font-semibold">
            {search
              ? "No conversations match your search"
              : "You don't have any conversations yet"}
          </h3>
          <p className="text-muted-foreground">
            {search
              ? "Try a different title"
              : "Add a transcript to get started with triage"}
          </p>
        </div>
      ) : (
        <DataTable columns={columns} data={conversations.data} />
      )}

      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <p className="text-sm text-muted-foreground">
          {conversations.count === 0
            ? "No conversations"
            : `Showing ${firstRow} to ${lastRow} of ${conversations.count} conversations`}
        </p>
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={onPrevious}
            disabled={!hasPrevious}
          >
            <ChevronLeft className="mr-2 size-4" />
            Previous
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={onNext}
            disabled={!hasNext}
          >
            Next
            <ChevronRight className="ml-2 size-4" />
          </Button>
        </div>
      </div>
    </div>
  )
}

function ConversationsTable({
  userId,
  search,
  page,
  onPrevious,
  onNext,
}: {
  userId: string | null
  search: string
  page: number
  onPrevious: () => void
  onNext: () => void
}) {
  return (
    <Suspense fallback={<PendingConversations />}>
      <ConversationsTableContent
        userId={userId}
        search={search}
        page={page}
        onPrevious={onPrevious}
        onNext={onNext}
      />
    </Suspense>
  )
}

function Conversations() {
  const { user } = useAuth()
  const userId = user?.id ?? null
  const matchRoute = useMatchRoute()
  const [search, setSearch] = useState("")
  const [page, setPage] = useState(0)

  // The detail route is nested under this one, so hand rendering to it when it
  // matches instead of showing the list above the detail view.
  if (matchRoute({ to: "/conversations/$id", fuzzy: false })) {
    return <Outlet />
  }

  const applySearch = (query: string) => {
    setSearch(query)
    setPage(0)
  }

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Conversations</h1>
          <p className="text-muted-foreground">
            Create conversations and triage them
          </p>
        </div>
        <AddConversation userId={userId} />
      </div>

      <ConversationSearch appliedQuery={search} onSearch={applySearch} />

      <ConversationsTable
        userId={userId}
        search={search}
        page={page}
        onPrevious={() => setPage((current) => Math.max(current - 1, 0))}
        onNext={() => setPage((current) => current + 1)}
      />
    </div>
  )
}
