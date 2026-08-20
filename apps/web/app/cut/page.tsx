import { CutClient } from "@/app/cut/cut-client"
import { Page } from "@/components/shell"
import { getResults } from "@/lib/api"

export const dynamic = "force-dynamic"

const QUESTION_ID = "qst_0420"

export default async function CutPage() {
  const results = await getResults()
  const conflict = results.conflicts.find((c) => c.question_id === QUESTION_ID)

  return (
    <Page
      eyebrow="Temporal Cut"
      title="BM25 tells us what is relevant. HydraDB decides what may ground the answer."
      lede="One real benchmark conflict, live. The same ranking on both sides — on the right, the claim graph removes the document that still asserts the retired value and backfills the next candidate from the same ranking. Same model, same prompt, same document count."
    >
      <CutClient
        question={conflict?.question ?? ""}
        questionId={QUESTION_ID}
        oldValue={conflict?.old_value ?? ""}
        newValue={conflict?.new_value ?? ""}
        baselineAnswer={conflict?.baseline.answer ?? null}
        canonAnswer={conflict?.canon.answer ?? null}
        baselineCorrect={conflict?.baseline.verdict?.states_current_value ?? null}
        canonCorrect={conflict?.canon.verdict?.states_current_value ?? null}
        judgeModel={conflict?.canon.verdict?.judge_model ?? null}
      />
    </Page>
  )
}
