import { Skeleton } from "@/components/ui/skeleton"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"

const PendingConversations = () => (
  <Table>
    <TableHeader>
      <TableRow>
        <TableHead>Title</TableHead>
        <TableHead>Created</TableHead>
        <TableHead>Updated</TableHead>
        <TableHead>
          <span className="sr-only">Actions</span>
        </TableHead>
      </TableRow>
    </TableHeader>
    <TableBody>
      {Array.from({ length: 5 }).map((_, index) => (
        <TableRow key={index}>
          <TableCell>
            <Skeleton className="h-4 w-48" />
          </TableCell>
          <TableCell>
            <Skeleton className="h-4 w-32" />
          </TableCell>
          <TableCell>
            <Skeleton className="h-4 w-32" />
          </TableCell>
          <TableCell>
            <div className="flex justify-end">
              <Skeleton className="h-8 w-20 rounded-md" />
            </div>
          </TableCell>
        </TableRow>
      ))}
    </TableBody>
  </Table>
)

export default PendingConversations
