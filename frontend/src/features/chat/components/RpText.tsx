import { Fragment } from "react";

type Kind = "dialogue" | "action" | "text";
interface Piece {
  kind: Kind;
  text: string;
}

const PATTERN = /("(?:[^"\\]|\\.)*"|“[^”]*”)|(\*[^*]+\*)/g;

/** Splits RP text into "dialogue", *action* and plain pieces (ported idea from Glow's tokenize). */
export function splitRp(text: string): Piece[] {
  const pieces: Piece[] = [];
  let last = 0;
  for (const m of text.matchAll(PATTERN)) {
    const index = m.index ?? 0;
    if (index > last) pieces.push({ kind: "text", text: text.slice(last, index) });
    pieces.push({ kind: m[1] ? "dialogue" : "action", text: m[0] });
    last = index + m[0].length;
  }
  if (last < text.length) pieces.push({ kind: "text", text: text.slice(last) });
  return pieces;
}

const CLASS: Record<Kind, string> = {
  dialogue: "text-fg",
  action: "italic text-muted",
  text: "",
};

export function RpText({ text }: { text: string }) {
  return (
    <p className="whitespace-pre-wrap break-words font-content leading-relaxed">
      {splitRp(text).map((piece, i) => (
        <Fragment key={i}>
          {piece.kind === "text" ? (
            piece.text
          ) : (
            <span className={CLASS[piece.kind]}>{piece.text}</span>
          )}
        </Fragment>
      ))}
    </p>
  );
}
