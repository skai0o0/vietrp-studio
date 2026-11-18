import { useState } from "react";
import { toast } from "sonner";
import { SelectField } from "@/features/chat/settings/SelectField";
import { usePresets } from "@/features/chat/hooks";
import { t } from "@/i18n";
import type { AgentId } from "@/types/chat";
import { PresetEditor } from "./PresetEditor";

const AGENTS: AgentId[] = [
  "orchestrator",
  "writer",
  "director",
  "state_keeper",
  "archivist",
  "creator",
  "card_judge",
  "bond_drafter",
  "bond_selector",
];

/** Settings section: prompt-layer presets per agent. */
export function PresetsSection() {
  const [agent, setAgent] = useState<AgentId>("writer");
  const presets = usePresets();
  const forAgent = (presets.data ?? []).filter((preset) => preset.agent === agent);

  return (
    <section aria-labelledby="settings-presets" className="flex flex-col gap-3">
      <h2 id="settings-presets" className="text-lg font-semibold">
        {t("presets.title")}
      </h2>
      <p className="text-sm text-muted">{t("presets.description")}</p>
      <p className="text-xs text-muted">{t("presets.safetyNote")}</p>
      <SelectField
        id="preset-agent"
        label={t("presets.agent")}
        value={agent}
        options={AGENTS.map((id) => ({ value: id, label: t(`presets.agents.${id}`) }))}
        onChange={(value) => setAgent(value as AgentId)}
      />
      {presets.isPending ? (
        <p role="status" className="text-sm text-muted">
          {t("presets.loading")}
        </p>
      ) : null}
      {presets.isError ? <p className="text-sm text-danger">{t("presets.loadFailed")}</p> : null}
      {presets.isSuccess && forAgent.length === 0 ? (
        <p className="text-sm text-muted">{t("presets.empty")}</p>
      ) : null}
      {presets.isSuccess ? (
        <>
          {forAgent.map((preset) => (
            <PresetEditor key={preset.id} agent={agent} preset={preset} onNotify={toast.success} />
          ))}
          <PresetEditor
            key={`new-${agent}-${forAgent.length}`}
            agent={agent}
            onNotify={toast.success}
          />
        </>
      ) : null}
    </section>
  );
}
