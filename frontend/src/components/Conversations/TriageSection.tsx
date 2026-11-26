import { useMutation, useQueryClient } from "@tanstack/react-query"
import { Sparkles } from "lucide-react"

import {
  type ConversationPublic,
  ConversationsService,
  type TriageFeedback,
} from "@/client"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { LoadingButton } from "@/components/ui/loading-button"
import useCustomToast from "@/hooks/useCustomToast"
import { handleError } from "@/utils"

interface TriageSectionProps {
  conversation: ConversationPublic
  userId: string | null | undefined
}

function sentimentVariant(
  sentiment: ConversationPublic["triage_sentiment"],
): "default" | "secondary" | "destructive" {
  if (sentiment === "negative") {
    return "destructive"
  }
  if (sentiment === "positive") {
    return "default"
  }
  return "secondary"
}

const TriageSection = ({ conversation, userId }: TriageSectionProps) => {
  const queryClient = useQueryClient()
  const { showSuccessToast, showErrorToast } = useCustomToast()
  const hasResult = Boolean(conversation.triage_at)

  const mutation = useMutation({
    mutationFn: () =>
      ConversationsService.triageConversation({
        path: { id: conversation.id },
      }),
    onSuccess: () => {
      showSuccessToast("Triage completed")
    },
    onError: handleError.bind(showErrorToast),
    onSettled: () => {
      queryClient.invalidateQueries({
        queryKey: ["conversations", userId, conversation.id],
      })
      queryClient.invalidateQueries({ queryKey: ["conversations", userId] })
    },
  })

  const feedbackMutation = useMutation({
    mutationFn: (feedback: TriageFeedback) =>
      ConversationsService.setTriageFeedback({
        path: { id: conversation.id },
        body: { feedback },
      }),
    onSuccess: () => {
      showSuccessToast("Feedback saved")
    },
    onError: handleError.bind(showErrorToast),
    onSettled: () => {
      queryClient.invalidateQueries({
        queryKey: ["conversations", userId, conversation.id],
      })
    },
  })

  const clearFeedbackMutation = useMutation({
    mutationFn: () =>
      ConversationsService.clearTriageFeedback({
        path: { id: conversation.id },
      }),
    onSuccess: () => {
      showSuccessToast("Feedback cleared")
    },
    onError: handleError.bind(showErrorToast),
    onSettled: () => {
      queryClient.invalidateQueries({
        queryKey: ["conversations", userId, conversation.id],
      })
    },
  })

  const feedback = conversation.triage_feedback ?? null
  const feedbackPending =
    feedbackMutation.isPending || clearFeedbackMutation.isPending

  return (
    <Card>
      <CardHeader>
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <CardTitle>Triage</CardTitle>
            <CardDescription>
              A structured summary of this conversation and a suggested next
              step.
            </CardDescription>
          </div>
          <LoadingButton
            onClick={() => mutation.mutate()}
            loading={mutation.isPending}
          >
            <Sparkles className="mr-2 size-4" />
            Run triage
          </LoadingButton>
        </div>
      </CardHeader>
      <CardContent>
        {mutation.isPending ? (
          <p className="text-sm text-muted-foreground">Triaging…</p>
        ) : hasResult ? (
          <dl className="grid gap-4">
            <div>
              <dt className="text-sm font-medium text-muted-foreground">
                Summary
              </dt>
              <dd>{conversation.triage_summary}</dd>
            </div>
            <div>
              <dt className="text-sm font-medium text-muted-foreground">
                Intent
              </dt>
              <dd className="font-mono text-sm">
                {conversation.triage_intent}
              </dd>
            </div>
            <div>
              <dt className="text-sm font-medium text-muted-foreground">
                Sentiment
              </dt>
              <dd>
                <Badge
                  variant={sentimentVariant(conversation.triage_sentiment)}
                  className="capitalize"
                >
                  {conversation.triage_sentiment}
                </Badge>
              </dd>
            </div>
            <div>
              <dt className="text-sm font-medium text-muted-foreground">
                Next action
              </dt>
              <dd>{conversation.triage_next_action}</dd>
            </div>
            <div>
              <dt className="text-sm font-medium text-muted-foreground">
                Triaged at
              </dt>
              <dd className="text-sm">
                {conversation.triage_at
                  ? new Date(conversation.triage_at).toLocaleString()
                  : "—"}
              </dd>
            </div>
            <div className="border-t pt-4">
              <dt className="text-sm font-medium">Was this triage useful?</dt>
              <dd className="mt-2 flex flex-wrap items-center gap-2">
                <LoadingButton
                  size="sm"
                  variant={feedback === "helpful" ? "default" : "outline"}
                  loading={feedbackMutation.isPending && feedback !== "helpful"}
                  disabled={feedbackPending}
                  onClick={() => feedbackMutation.mutate("helpful")}
                >
                  Helpful
                </LoadingButton>
                <LoadingButton
                  size="sm"
                  variant={feedback === "not_helpful" ? "default" : "outline"}
                  loading={
                    feedbackMutation.isPending && feedback !== "not_helpful"
                  }
                  disabled={feedbackPending}
                  onClick={() => feedbackMutation.mutate("not_helpful")}
                >
                  Not helpful
                </LoadingButton>
                {feedback ? (
                  <Button
                    size="sm"
                    variant="ghost"
                    disabled={feedbackPending}
                    onClick={() => clearFeedbackMutation.mutate()}
                  >
                    Clear feedback
                  </Button>
                ) : null}
              </dd>
              <dd className="mt-2 text-xs text-muted-foreground">
                {feedback
                  ? `Your feedback on this result: ${
                      feedback === "helpful" ? "Helpful" : "Not helpful"
                    }`
                  : "Your feedback refers to the result shown above. It is not sent to any external service."}
              </dd>
            </div>
          </dl>
        ) : (
          <p className="text-sm text-muted-foreground">
            No triage yet. Run triage to see a summary, intent, sentiment, and
            next action.
          </p>
        )}
      </CardContent>
    </Card>
  )
}

export default TriageSection
