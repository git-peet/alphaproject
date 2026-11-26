import { useMutation } from "@tanstack/react-query"
import { Download } from "lucide-react"

import { ConversationsService } from "@/client"
import { LoadingButton } from "@/components/ui/loading-button"
import useCustomToast from "@/hooks/useCustomToast"
import { handleError } from "@/utils"

interface ExportConversationProps {
  id: string
}

/**
 * Downloads a conversation export.
 *
 * The API authenticates with a bearer token, so a plain anchor would send no
 * credentials. The document is fetched through the generated client and saved
 * from a short-lived Blob URL instead.
 */
const ExportConversation = ({ id }: ExportConversationProps) => {
  const { showSuccessToast, showErrorToast } = useCustomToast()

  const mutation = useMutation({
    mutationFn: async () => {
      const { data } = await ConversationsService.exportConversation({
        path: { id },
      })
      const blob = new Blob([JSON.stringify(data, null, 2)], {
        type: "application/json",
      })
      const url = URL.createObjectURL(blob)
      try {
        const link = document.createElement("a")
        link.href = url
        link.download = `conversation-${id}.json`
        document.body.append(link)
        link.click()
        link.remove()
      } finally {
        URL.revokeObjectURL(url)
      }
    },
    onSuccess: () => {
      showSuccessToast("Conversation exported")
    },
    onError: handleError.bind(showErrorToast),
  })

  return (
    <LoadingButton
      variant="outline"
      loading={mutation.isPending}
      onClick={() => mutation.mutate()}
    >
      <Download className="mr-2 size-4" />
      Export
    </LoadingButton>
  )
}

export default ExportConversation
