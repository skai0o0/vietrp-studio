import { ArrowDown, ArrowUp, Plus, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { t } from "@/i18n";
import { useFormState } from "../form/FormContext";
import { TextAreaField, TextField } from "../form/fields";
import { IconButton } from "../form/IconButton";
import { Section } from "../form/Section";
import { moveItem, removeAt, replaceAt, uniqueSlug } from "../lib/arrays";
import type { CardDraft } from "./cardDraft";

type Secret = CardDraft["secrets"][number];

interface SecretsSectionProps {
  secrets: Secret[];
  onChange: (secrets: Secret[]) => void;
}

export function SecretsSection({ secrets, onChange }: SecretsSectionProps) {
  const { readOnly } = useFormState();

  function add(): void {
    const id = uniqueSlug(
      "secret",
      secrets.map((s) => s.id),
    );
    onChange([...secrets, { id, content: "", reveal_when: "" }]);
  }

  return (
    <Section
      title={t("library.character.secrets")}
      description={t("library.character.secretsHint")}
    >
      {secrets.length === 0 && readOnly ? (
        <p className="text-sm text-muted">{t("library.list.none")}</p>
      ) : null}
      <ul className="flex flex-col gap-4">
        {secrets.map((secret, index) => {
          const name = t("library.character.secretItem", { n: index + 1 });
          return (
            <li
              key={secret.id}
              className="flex flex-col gap-3 rounded-md border border-border bg-bg p-3"
            >
              <div className="flex items-center justify-between gap-2">
                <h3 className="text-sm font-medium">{name}</h3>
                {readOnly ? null : (
                  <div className="flex gap-0.5">
                    <IconButton
                      icon={ArrowUp}
                      label={t("library.list.moveUp", { name })}
                      disabled={index === 0}
                      onClick={() => onChange(moveItem(secrets, index, index - 1))}
                    />
                    <IconButton
                      icon={ArrowDown}
                      label={t("library.list.moveDown", { name })}
                      disabled={index === secrets.length - 1}
                      onClick={() => onChange(moveItem(secrets, index, index + 1))}
                    />
                    <IconButton
                      icon={Trash2}
                      label={t("library.list.remove", { name })}
                      onClick={() => onChange(removeAt(secrets, index))}
                    />
                  </div>
                )}
              </div>
              <TextAreaField
                label={t("library.character.secretContent")}
                path={`secrets.${index}.content`}
                rows={3}
                value={secret.content}
                onChange={(content) => onChange(replaceAt(secrets, index, { ...secret, content }))}
              />
              <TextField
                label={t("library.character.revealWhen")}
                path={`secrets.${index}.reveal_when`}
                hint={t("library.character.revealWhenHint")}
                value={secret.reveal_when}
                onChange={(reveal_when) =>
                  onChange(replaceAt(secrets, index, { ...secret, reveal_when }))
                }
              />
            </li>
          );
        })}
      </ul>
      {readOnly ? null : (
        <Button type="button" variant="outline" size="sm" className="self-start" onClick={add}>
          <Plus aria-hidden="true" />
          {t("library.character.addSecret")}
        </Button>
      )}
    </Section>
  );
}
