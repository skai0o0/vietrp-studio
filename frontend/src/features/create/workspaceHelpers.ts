import type { Visibility } from "@/types/library";
import type {
  CardJudgeResult,
  CreatorMessage,
  CreatorMode,
  CreatorPipelineStage,
  CreatorStreamEvent,
  FormatWarning,
  NoticeEvent,
  TargetType,
} from "./types";

export type WorkspaceKey = `${TargetType}:${CreatorMode}`;

export interface WorkspaceState {
  sessionId: string | null;
  messages: CreatorMessage[];
  streamingReply: string;
  rawText: string;
  generatedData: Record<string, unknown> | null;
  warnings: FormatWarning[];
  judgeScore: CardJudgeResult | null;
  jsonText: string;
  jsonInvalid: boolean;
  notices: NoticeEvent[];
  stage: CreatorPipelineStage;
  chatErrorCode: string | null;
  pipelineErrorCode: string | null;
  visibility: Visibility;
}

export type WorkspaceMap = Record<WorkspaceKey, WorkspaceState>;

export function emptyWorkspace(): WorkspaceState {
  return {
    sessionId: null,
    messages: [],
    streamingReply: "",
    rawText: "",
    generatedData: null,
    warnings: [],
    judgeScore: null,
    jsonText: "",
    jsonInvalid: false,
    notices: [],
    stage: "idle",
    chatErrorCode: null,
    pipelineErrorCode: null,
    visibility: "private",
  };
}

export function workspaceKey(target: TargetType, mode: CreatorMode): WorkspaceKey {
  return `${target}:${mode}`;
}

export function readWorkspace(map: WorkspaceMap, key: WorkspaceKey): WorkspaceState {
  return map[key] ?? emptyWorkspace();
}

export function isPlainRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isCardJudgeResult(value: unknown): value is CardJudgeResult {
  return isPlainRecord(value) && Array.isArray(value.criteria) && typeof value.score === "number";
}

export function applyGenerateEvent(
  prev: WorkspaceState,
  event: CreatorStreamEvent,
): WorkspaceState {
  switch (event.type) {
    case "raw":
      return { ...prev, rawText: event.raw, stage: "formatting" };
    case "formatted":
      return {
        ...prev,
        generatedData: event.data,
        jsonText: JSON.stringify(event.data, null, 2),
        jsonInvalid: false,
        stage: "validating",
      };
    case "validated":
      return {
        ...prev,
        generatedData: event.data,
        jsonText: JSON.stringify(event.data, null, 2),
        jsonInvalid: false,
        warnings: event.warnings ?? [],
        stage: "judging",
      };
    case "notice":
      return { ...prev, notices: [...prev.notices, event] };
    case "judged":
      return { ...prev, judgeScore: event.judge_score };
    case "done": {
      const resultObj = isPlainRecord(event.session.result) ? event.session.result : null;
      const resultData = resultObj && isPlainRecord(resultObj.data) ? resultObj.data : null;
      const resultWarnings =
        resultObj && Array.isArray(resultObj.warnings)
          ? (resultObj.warnings as FormatWarning[])
          : null;
      const resultJudge =
        resultObj && isCardJudgeResult(resultObj.judge_score)
          ? resultObj.judge_score
          : resultObj && resultObj.judge_score === null
            ? null
            : undefined;
      const nextData = resultData ?? prev.generatedData;
      return {
        ...prev,
        sessionId: event.session.id,
        rawText: typeof event.session.raw === "string" ? event.session.raw : prev.rawText,
        generatedData: nextData,
        jsonText: nextData ? JSON.stringify(nextData, null, 2) : prev.jsonText,
        jsonInvalid: false,
        warnings: resultWarnings ?? prev.warnings,
        judgeScore: resultJudge === undefined ? prev.judgeScore : resultJudge,
        stage: "done",
      };
    }
    case "error":
      return { ...prev, pipelineErrorCode: event.code, stage: "error" };
    default:
      return prev;
  }
}
