import { t } from "@/i18n";
import type { ChatSettings } from "@/types/chat";
import { useModels } from "../hooks";
import { SelectField } from "./SelectField";

type AgentModels = NonNullable<ChatSettings["models"]>;
type ModelAgent = keyof AgentModels & keyof typeof AGENT_LABELS;

const AGENT_LABELS = {
  orchestrator: "chatSettings.agents.orchestrator",
  writer: "chatSettings.agents.writer",
  director: "chatSettings.agents.director",
  state_keeper: "chatSettings.agents.state_keeper",
  archivist: "chatSettings.agents.archivist",
  bond_drafter: "chatSettings.agents.bond_drafter",
  bond_selector: "chatSettings.agents.bond_selector",
} as const;

const DEFAULT_VALUE = "";

interface AgentModelSelectsProps {
  models: AgentModels;
  onChange: (models: AgentModels) => void;
}

export function AgentModelSelects({ models, onChange }: AgentModelSelectsProps) {
  const query = useModels();
  const list = query.data ?? [];
  const agents = Object.keys(AGENT_LABELS) as ModelAgent[];

  return (
    <section className="flex flex-col gap-3" aria-labelledby="cs-models">
      <h3 id="cs-models" className="text-sm font-semibold">
        {t("chatSettings.models.title")}
      </h3>
      <p className="text-xs text-muted">{t("chatSettings.models.hint")}</p>
      {query.isError ? (
        <p className="text-xs text-danger">{t("chatSettings.models.loadFailed")}</p>
      ) : null}
      {agents.map((agent) => {
        const current = models[agent] ?? DEFAULT_VALUE;
        const known = list.some((model) => model.id === current);
        return (
          <SelectField
            key={agent}
            id={`cs-model-${agent}`}
            label={t(AGENT_LABELS[agent])}
            value={current}
            options={[
              { value: DEFAULT_VALUE, label: t("chatSettings.models.default") },
              ...(current && !known ? [{ value: current, label: current }] : []),
              ...list.map((model) => ({ value: model.id, label: model.name || model.id })),
            ]}
            onChange={(value) =>
              onChange({ ...models, [agent]: value === DEFAULT_VALUE ? null : value })
            }
          />
        );
      })}
    </section>
  );
}
