import { Fragment } from "react";

type Kind = "dialogue" | "bold" | "action" | "text";
interface Piece {
  kind: Kind;
  text: string;
}

const PATTERN = /("(?:[^"\\]|\\.)*"|“[^”]*”)|(\*\*[^*]+\*\*)|(\*[^*]+\*)/g;

/** Splits RP text into "dialogue", **bold**, *action* and plain pieces. */
export function splitRp(text: string): Piece[] {
  const pieces: Piece[] = [];
  let last = 0;
  for (const m of text.matchAll(PATTERN)) {
    const index = m.index ?? 0;
    if (index > last) pieces.push({ kind: "text", text: text.slice(last, index) });
    if (m[1]) pieces.push({ kind: "dialogue", text: m[0] });
    else if (m[2]) pieces.push({ kind: "bold", text: m[0] });
    else pieces.push({ kind: "action", text: m[0] });
    last = index + m[0].length;
  }
  if (last < text.length) pieces.push({ kind: "text", text: text.slice(last) });
  return pieces;
}

const CLASS: Record<Kind, string> = {
  dialogue: "text-fg",
  bold: "font-semibold text-fg",
  action: "italic text-fg/75",
  text: "",
};

export function RpText({ text }: { text: string }) {
  return (
    <p className="whitespace-pre-wrap break-words font-content leading-relaxed">
      {splitRp(text).map((piece, i) => (
        <Fragment key={i}>
          {piece.kind === "text" ? (
            piece.text
          ) : piece.kind === "bold" ? (
            <strong className={CLASS.bold}>{piece.text.slice(2, -2)}</strong>
          ) : (
            <span className={CLASS[piece.kind]}>{piece.text}</span>
          )}
        </Fragment>
      ))}
    </p>
  );
}
