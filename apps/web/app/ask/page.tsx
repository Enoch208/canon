import { AskClient } from "@/app/ask/ask-client"
import { Page } from "@/components/shell"
import { getConflicts, getResults } from "@/lib/api"

export const dynamic = "force-dynamic"

export default async function AskPage() {
  const [conflicts, results] = await Promise.all([getConflicts(), getResults()])
  const samples = [
    ...conflicts.slice(0, 3).map((conflict) => `What is the current ${conflict.predicate.replace(/_/g, " ")} for ${conflict.entity}?`),
    `Which enterprise accounts were on the initial hot-route capacity protection allowlist in us-east?`,
  ]

  return (
    <Page
      eyebrow="Ask Canon"
      title="Every answer is a graph result, not prose."
      lede={`Canon returns CANON, CONTESTED or UNKNOWN, the evidence behind it, the retired context it filtered, and the HydraDB queries that produced it — across ${results.corpus_documents.toLocaleString()} indexed EnterpriseRAG-Bench documents.`}
    >
      <AskClient samples={samples} />
    </Page>
  )
}
