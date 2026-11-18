import type { CardJudgeCriterion, CardJudgeResult } from "@/types/generated/card-judge-result";
import type {
  CreatorDeltaEvent,
  CreatorDoneEvent,
  CreatorErrorEvent,
  CreatorFormattedEvent,
  CreatorJudgedEvent,
  CreatorMessage,
  CreatorMessageEvent,
  CreatorRawEvent,
  CreatorValidatedEvent,
  Event as CreatorStreamEvent,
  FormatWarning,
  NoticeEvent,
  UsageEvent,
} from "@/types/generated/creator-events";
import type { CreatorGenerateIn } from "@/types/generated/creator-generate-in";
import type { CreatorPoolsOut } from "@/types/generated/creator-pools-out";
import type { CreatorSaveOut } from "@/types/generated/creator-save-out";
import type { CreatorSessionCreate } from "@/types/generated/creator-session-create";
import type {
  CreatorSessionOut,
  Mode as CreatorMode,
  TargetType,
} from "@/types/generated/creator-session-out";
import type { CreatorSessionUpdate } from "@/types/generated/creator-session-update";

export type {
  CardJudgeCriterion,
  CardJudgeResult,
  CreatorDeltaEvent,
  CreatorDoneEvent,
  CreatorErrorEvent,
  CreatorFormattedEvent,
  CreatorGenerateIn,
  CreatorJudgedEvent,
  CreatorMessage,
  CreatorMessageEvent,
  CreatorMode,
  CreatorPoolsOut,
  CreatorRawEvent,
  CreatorSaveOut,
  CreatorSessionCreate,
  CreatorSessionOut,
  CreatorSessionUpdate,
  CreatorStreamEvent,
  CreatorValidatedEvent,
  FormatWarning,
  NoticeEvent,
  TargetType,
  UsageEvent,
};

export type CreatorPipelineStage =
  "idle" | "drafting_raw" | "formatting" | "validating" | "judging" | "done" | "error";

export interface CreatorSeedState {
  name: string;
  age: string;
  notes: string;
  values: Record<string, string>;
  customMode: Record<string, boolean>;
  locked: Record<string, boolean>;
}

export interface CreatorWorkspaceState {
  session: CreatorSessionOut | null;
  messages: CreatorMessage[];
  streamingReply: string;
  rawText: string;
  generatedData: Record<string, unknown> | null;
  warnings: FormatWarning[];
  judgeScore: CardJudgeResult | null;
  notices: NoticeEvent[];
  stage: CreatorPipelineStage;
  errorCode: string | null;
}
