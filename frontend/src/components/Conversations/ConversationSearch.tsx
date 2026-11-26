import { Search, X } from "lucide-react"
import { useEffect, useState } from "react"

import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"

export const CONVERSATION_SEARCH_MAX_LENGTH = 100

interface ConversationSearchProps {
  appliedQuery: string
  onSearch: (query: string) => void
}

const ConversationSearch = ({
  appliedQuery,
  onSearch,
}: ConversationSearchProps) => {
  const [query, setQuery] = useState(appliedQuery)

  // Keep the field in step when the applied query changes elsewhere (for
  // example when clearing from the no-match state).
  useEffect(() => {
    setQuery(appliedQuery)
  }, [appliedQuery])

  const onSubmit = (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    onSearch(query.trim())
  }

  const onClear = () => {
    setQuery("")
    onSearch("")
  }

  return (
    <form
      onSubmit={onSubmit}
      className="flex w-full max-w-md items-center gap-2"
    >
      <Input
        type="search"
        value={query}
        maxLength={CONVERSATION_SEARCH_MAX_LENGTH}
        placeholder="Search by title"
        aria-label="Search conversations"
        onChange={(event) => setQuery(event.target.value)}
      />
      <Button type="submit" variant="secondary">
        <Search className="mr-2 size-4" />
        Search
      </Button>
      {appliedQuery ? (
        <Button type="button" variant="ghost" onClick={onClear}>
          <X className="mr-2 size-4" />
          Clear
        </Button>
      ) : null}
    </form>
  )
}

export default ConversationSearch
