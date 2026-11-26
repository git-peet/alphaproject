import { useSuspenseQuery } from "@tanstack/react-query"
import { createFileRoute, Link, useNavigate } from "@tanstack/react-router"
import { ArrowLeft } from "lucide-react"
import { Suspense } from "react"

import { ConversationsService } from "@/client"
import DeleteConversation from "@/components/Conversations/DeleteConversation"
import ExportConversation from "@/components/Conversations/ExportConversation"
import TriageSection from "@/components/Conversations/TriageSection"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"
import useAuth from "@/hooks/useAuth"

export const Route = createFileRoute("/_layout/conversations/$id")({
  component: ConversationDetail,
  head: () => ({
    meta: [
      {
        title: "Conversation - FastAPI Template",
      },
    ],
  }),
})

function ConversationDetailContent({
  id,
  userId,
}: {
  id: string
  userId: string | null
}) {
  const navigate = useNavigate()
  const { data: conversation } = useSuspenseQuery({
    queryFn: async () =>
      (await ConversationsService.readConversation({ path: { id } })).data,
    queryKey: ["conversations", userId, id],
  })

  if (!conversation) {
    return (
      <p className="text-muted-foreground">This conversation was not found.</p>
    )
  }

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">
            {conversation.title}
          </h1>
          <p className="text-muted-foreground">
            Created{" "}
            {conversation.created_at
              ? new Date(conversation.created_at).toLocaleString()
              : "—"}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <ExportConversation id={conversation.id} />
          <DeleteConversation
            id={conversation.id}
            userId={userId}
            onSuccess={() => navigate({ to: "/conversations" })}
          />
        </div>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Transcript</CardTitle>
          <CardDescription>
            {conversation.transcript.length.toLocaleString()} characters
          </CardDescription>
        </CardHeader>
        <CardContent>
          <pre className="max-h-96 overflow-auto whitespace-pre-wrap break-words rounded-md bg-muted p-4 text-sm">
            {conversation.transcript}
          </pre>
        </CardContent>
      </Card>

      <TriageSection conversation={conversation} userId={userId} />
    </div>
  )
}

function ConversationDetailSkeleton() {
  return (
    <div className="flex flex-col gap-6">
      <Skeleton className="h-8 w-64" />
      <Skeleton className="h-48 w-full" />
      <Skeleton className="h-48 w-full" />
    </div>
  )
}

function ConversationDetail() {
  const { id } = Route.useParams()
  const { user } = useAuth()
  const userId = user?.id ?? null

  return (
    <div className="flex flex-col gap-6">
      <Button variant="ghost" size="sm" className="w-fit" asChild>
        <Link to="/conversations">
          <ArrowLeft className="mr-2 size-4" />
          Back to Conversations
        </Link>
      </Button>
      <Suspense fallback={<ConversationDetailSkeleton />}>
        <ConversationDetailContent id={id} userId={userId} />
      </Suspense>
    </div>
  )
}
