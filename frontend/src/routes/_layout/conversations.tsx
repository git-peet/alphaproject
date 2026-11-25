import { useSuspenseQuery } from "@tanstack/react-query"
import { createFileRoute, Outlet, useMatchRoute } from "@tanstack/react-router"
import { MessagesSquare } from "lucide-react"
import { Suspense } from "react"

import { ConversationsService } from "@/client"
import { DataTable } from "@/components/Common/DataTable"
import AddConversation from "@/components/Conversations/AddConversation"
import { columns } from "@/components/Conversations/columns"
import PendingConversations from "@/components/Pending/PendingConversations"
import useAuth from "@/hooks/useAuth"

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

function ConversationsTableContent({ userId }: { userId: string | null }) {
  const { data: conversations } = useSuspenseQuery({
    queryFn: async () =>
      (
        await ConversationsService.readConversations({
          query: { skip: 0, limit: 100 },
        })
      ).data,
    queryKey: ["conversations", userId],
  })

  if (conversations.data.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center text-center py-12">
        <div className="rounded-full bg-muted p-4 mb-4">
          <MessagesSquare className="h-8 w-8 text-muted-foreground" />
        </div>
        <h3 className="text-lg font-semibold">
          You don't have any conversations yet
        </h3>
        <p className="text-muted-foreground">
          Add a transcript to get started with triage
        </p>
      </div>
    )
  }

  return <DataTable columns={columns} data={conversations.data} />
}

function ConversationsTable({ userId }: { userId: string | null }) {
  return (
    <Suspense fallback={<PendingConversations />}>
      <ConversationsTableContent userId={userId} />
    </Suspense>
  )
}

function Conversations() {
  const { user } = useAuth()
  const userId = user?.id ?? null
  const matchRoute = useMatchRoute()

  // The detail route is nested under this one, so hand rendering to it when it
  // matches instead of showing the list above the detail view.
  if (matchRoute({ to: "/conversations/$id", fuzzy: false })) {
    return <Outlet />
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
      <ConversationsTable userId={userId} />
    </div>
  )
}
