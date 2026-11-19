import { t } from "@/i18n";
import type { ChatOut, ChatSettings } from "@/types/chat";
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
  mode?: ChatOut["mode"];
  embedded?: boolean;
  onChange: (models: AgentModels) => void;
}

export function AgentModelSelects({
  models,
  mode,
  embedded = false,
  onChange,
}: AgentModelSelectsProps) {
  const query = useModels();
  const list = query.data ?? [];
  const agents = (Object.keys(AGENT_LABELS) as ModelAgent[]).filter(
    (agent) => !(mode === "single" && agent === "state_keeper"),
  );

  const Container = embedded ? "div" : "section";

  return (
    <Container
      {...(!embedded ? { "aria-labelledby": "cs-models" } : {})}
      className="flex flex-col gap-3"
    >
      {!embedded ? (
        <h3 id="cs-models" className="text-sm font-semibold">
          {t("chatSettings.models.title")}
        </h3>
      ) : null}
      <p className="text-xs text-muted">{t("chatSettings.models.hint")}</p>
      {query.isError ? (
        <p className="text-xs text-danger-text">{t("chatSettings.models.loadFailed")}</p>
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
    </Container>
  );
}
