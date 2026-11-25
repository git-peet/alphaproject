import { zodResolver } from "@hookform/resolvers/zod"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import { Plus } from "lucide-react"
import { useState } from "react"
import { useForm } from "react-hook-form"
import { z } from "zod"

import { type ConversationCreate, ConversationsService } from "@/client"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog"
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form"
import { Input } from "@/components/ui/input"
import { LoadingButton } from "@/components/ui/loading-button"
import useCustomToast from "@/hooks/useCustomToast"
import { handleError } from "@/utils"

// Mirrors the backend limits in backend/app/models.py.
export const TITLE_MAX_LENGTH = 255
export const TRANSCRIPT_MAX_LENGTH = 20_000

const formSchema = z.object({
  title: z
    .string()
    .min(1, { message: "Title is required" })
    .max(TITLE_MAX_LENGTH, { message: "Title is too long" }),
  transcript: z
    .string()
    .min(1, { message: "Transcript is required" })
    .max(TRANSCRIPT_MAX_LENGTH, { message: "Transcript is too long" }),
})

type FormData = z.infer<typeof formSchema>

interface AddConversationProps {
  userId: string | null | undefined
}

const AddConversation = ({ userId }: AddConversationProps) => {
  const [isOpen, setIsOpen] = useState(false)
  const queryClient = useQueryClient()
  const { showSuccessToast, showErrorToast } = useCustomToast()

  const form = useForm<FormData>({
    resolver: zodResolver(formSchema),
    mode: "onBlur",
    criteriaMode: "all",
    defaultValues: {
      title: "",
      transcript: "",
    },
  })

  const mutation = useMutation({
    mutationFn: (data: ConversationCreate) =>
      ConversationsService.createConversation({ body: data }),
    onSuccess: () => {
      showSuccessToast("Conversation created successfully")
      form.reset()
      setIsOpen(false)
    },
    onError: handleError.bind(showErrorToast),
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ["conversations", userId] })
    },
  })

  const onSubmit = (data: FormData) => {
    mutation.mutate(data)
  }

  return (
    <Dialog open={isOpen} onOpenChange={setIsOpen}>
      <DialogTrigger asChild>
        <Button className="my-4">
          <Plus className="mr-2" />
          Add Conversation
        </Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Add Conversation</DialogTitle>
          <DialogDescription>
            Paste a transcript to keep it for later triage.
          </DialogDescription>
        </DialogHeader>
        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmit)}>
            <div className="grid gap-4 py-4">
              <FormField
                control={form.control}
                name="title"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>
                      Title <span className="text-destructive">*</span>
                    </FormLabel>
                    <FormControl>
                      <Input placeholder="Title" type="text" {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <FormField
                control={form.control}
                name="transcript"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>
                      Transcript <span className="text-destructive">*</span>
                    </FormLabel>
                    <FormControl>
                      <textarea
                        {...field}
                        rows={8}
                        placeholder="Paste the conversation transcript"
                        aria-label="Transcript"
                        className="flex min-h-32 w-full rounded-md border border-input bg-transparent px-3 py-2 text-sm shadow-xs outline-none focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50"
                      />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
            </div>

            <DialogFooter>
              <DialogClose asChild>
                <Button variant="outline" disabled={mutation.isPending}>
                  Cancel
                </Button>
              </DialogClose>
              <LoadingButton type="submit" loading={mutation.isPending}>
                Save
              </LoadingButton>
            </DialogFooter>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  )
}

export default AddConversation
