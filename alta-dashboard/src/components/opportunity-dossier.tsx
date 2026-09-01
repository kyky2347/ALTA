import {
  BookOpenCheck,
  ListChecks,
  Route,
  Scale,
  Target,
  Waypoints,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { useI18n } from "@/lib/i18n";
import {
  asRecord,
  hasReadableValue,
  readableValue,
  recordList,
} from "@/lib/readable-record";

const MAX_VISIBLE_HISTORY = 20;

export function OpportunityDossier({
  detail,
}: {
  detail: Record<string, unknown> | null;
}) {
  const { clock, domain, relative, t, value } = useI18n();
  const lineage = asRecord(detail?.researchLineage);
  const questions = recordList(detail?.openResearchQuestions);
  const pillars = recordList(detail?.thesisPillars);
  const diligence = asRecord(detail?.researchDiligence);
  const ranks = recordList(detail?.ranks);
  const expressions = recordList(detail?.expressions);
  const continuityFacts: Array<[string, unknown]> = [
    [t("researchMode"), lineage?.mode],
    [t("parentOpportunity"), lineage?.parentOpportunityId],
    [t("researchQuestion"), lineage?.question],
    [t("beneficiaryPath"), detail?.beneficiaryPath],
    [t("disconfirmingEvidence"), detail?.disconfirmingEvidence],
    [t("nextResearchTest"), detail?.nextTest],
  ];

  return (
    <>
      <section className="inspector-section dossier-section">
        <h3>
          <Route /> {t("researchContinuity")}
        </h3>
        <ReadableFacts items={continuityFacts} />
        {questions.length ? (
          <div className="dossier-stack">
            {questions.map((question, index) => (
              <article
                className="dossier-card research-question-card"
                key={String(
                  question.question_id ?? question.questionId ?? index,
                )}
              >
                <div className="dossier-card-head">
                  <Badge variant="outline">
                    {domain(String(question.origin ?? t("openQuestion")))}
                  </Badge>
                  <small>
                    {String(
                      question.question_id ?? question.questionId ?? index + 1,
                    )}
                  </small>
                </div>
                <p>{String(question.prompt ?? t("noPublicSummary"))}</p>
              </article>
            ))}
          </div>
        ) : (
          <div className="inspector-note">{t("noOpenResearchQuestions")}</div>
        )}
      </section>

      <section className="inspector-section dossier-section">
        <h3>
          <Target /> {t("thesisPillars")} <RecordCount count={pillars.length} />
        </h3>
        {pillars.length ? (
          <div className="dossier-stack">
            {pillars.slice(0, MAX_VISIBLE_HISTORY).map((pillar, index) => {
              const dueAt = String(pillar.due_at ?? pillar.dueAt ?? "");
              return (
                <article
                  className="dossier-card thesis-pillar-card"
                  key={String(pillar.pillar_id ?? pillar.pillarId ?? index)}
                >
                  <div className="dossier-card-head">
                    <Badge variant="outline">
                      {t("pillarNumber", { number: index + 1 })}
                    </Badge>
                    <small>
                      {dueAt
                        ? `${clock(dueAt)} · ${relative(dueAt)}`
                        : t("deadlineUnavailable")}
                    </small>
                  </div>
                  <p className="dossier-thesis">
                    {String(pillar.statement ?? t("noPublicSummary"))}
                  </p>
                  <ReadableFacts
                    items={[
                      [t("observable"), pillar.observable],
                      [
                        t("confirmationCondition"),
                        pillar.confirmation_condition,
                      ],
                      [
                        t("invalidationCondition"),
                        pillar.invalidation_condition,
                      ],
                      [t("evidenceReferences"), pillar.evidence_ids],
                    ]}
                  />
                </article>
              );
            })}
            <TruncationNote total={pillars.length} />
          </div>
        ) : (
          <div className="inspector-note">{t("noThesisPillars")}</div>
        )}
      </section>

      <section className="inspector-section dossier-section">
        <h3>
          <BookOpenCheck /> {t("researchDiligence")}
        </h3>
        {diligence ? (
          <ReadableFacts items={Object.entries(diligence)} localizeValues />
        ) : (
          <div className="inspector-note">{t("noResearchDiligence")}</div>
        )}
      </section>

      <section className="inspector-section dossier-section">
        <h3>
          <Scale /> {t("rankAndExpression")}
        </h3>
        <div className="dossier-subheading">
          <ListChecks />
          <span>{t("rankingHistory")}</span>
          <RecordCount count={ranks.length} />
        </div>
        {ranks.length ? (
          <div className="dossier-stack">
            {ranks.slice(0, MAX_VISIBLE_HISTORY).map((rank, index) => (
              <article
                className="dossier-card rank-card"
                key={String(rank.id ?? index)}
              >
                <div className="dossier-card-head">
                  <strong>
                    {t("rankPosition", {
                      position: String(rank.position ?? "—"),
                    })}
                  </strong>
                  <Badge variant="outline">
                    {domain(String(rank.gateStatus ?? "ranked"))}
                  </Badge>
                </div>
                <ReadableFacts
                  items={[
                    [t("book"), rank.book],
                    [t("score"), rank.score],
                    [t("knownAt"), rank.knownAt],
                    [t("reasonCodes"), rank.reasonCodes],
                  ]}
                />
                {asRecord(rank.components) && (
                  <div className="dossier-components">
                    {Object.entries(asRecord(rank.components) ?? {}).map(
                      ([key, component]) => (
                        <span key={key}>
                          {domain(key)} <strong>{value(component)}</strong>
                        </span>
                      ),
                    )}
                  </div>
                )}
              </article>
            ))}
            <TruncationNote total={ranks.length} />
          </div>
        ) : (
          <div className="inspector-note">{t("noRankingHistory")}</div>
        )}

        <div className="dossier-subheading">
          <Waypoints />
          <span>{t("expressionHistory")}</span>
          <RecordCount count={expressions.length} />
        </div>
        {expressions.length ? (
          <div className="dossier-stack">
            {expressions
              .slice(0, MAX_VISIBLE_HISTORY)
              .map((expression, index) => (
                <article
                  className="dossier-card expression-card"
                  key={String(expression.id ?? index)}
                >
                  <div className="dossier-card-head">
                    <strong>
                      {domain(String(expression.kind ?? "expression"))}
                    </strong>
                    <Badge variant="outline">
                      {domain(String(expression.status ?? "recorded"))}
                    </Badge>
                  </div>
                  <p>{String(expression.rationale ?? t("noRecommendation"))}</p>
                  {asRecord(expression.validation) && (
                    <ReadableFacts
                      items={Object.entries(
                        asRecord(expression.validation) ?? {},
                      )}
                      localizeValues
                    />
                  )}
                </article>
              ))}
            <TruncationNote total={expressions.length} />
          </div>
        ) : (
          <div className="inspector-note">{t("noExpressionHistory")}</div>
        )}
      </section>
    </>
  );
}

function ReadableFacts({
  items,
  localizeValues = false,
}: {
  items: Array<[string, unknown]>;
  localizeValues?: boolean;
}) {
  const { domain, t, value } = useI18n();
  const visibleItems = items.filter(([, item]) => hasReadableValue(item));
  if (!visibleItems.length)
    return <div className="inspector-note">{t("noneSaved")}</div>;
  return (
    <div className="fact-list dossier-facts">
      {visibleItems.map(([label, item]) => (
        <div className="fact-row" key={label}>
          <span>{domain(label)}</span>
          <strong>
            {readableValue(item, {
              domain,
              fallback: t("unavailable"),
              localize: localizeValues,
              value,
            })}
          </strong>
        </div>
      ))}
    </div>
  );
}

function RecordCount({ count }: { count: number }) {
  return <Badge variant="outline">{count}</Badge>;
}

function TruncationNote({ total }: { total: number }) {
  const { t } = useI18n();
  if (total <= MAX_VISIBLE_HISTORY) return null;
  return (
    <div className="inspector-note">
      {t("additionalRecordsHidden", {
        count: total - MAX_VISIBLE_HISTORY,
      })}
    </div>
  );
}
