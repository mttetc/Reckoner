"use client";

export const CODE_RE = /e[JN][A-Za-z0-9+/_=-]{200,}/;

/** A pasted build code is 15 KB of base64: show what it is, not the blob. */
export function UserText({ text }: { text: string }) {
  const stripped = text.replace(CODE_RE, "").replace(/\s+/g, " ").trim();
  const hasCode = CODE_RE.test(text);
  return (
    <div data-testid="ask-user-text">
      {stripped}
      {hasCode ? (
        <span className="chip" style={{ marginLeft: stripped ? 8 : 0 }} data-testid="ask-user-code">
          Path of Building code attached
        </span>
      ) : null}
    </div>
  );
}
