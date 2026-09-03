"use client";

import { XIcon, ExternalLinkIcon } from "lucide-react";
import { usePanel } from "@/lib/panel";
import { Result } from "@/components/Result";
import { provenanceLine } from "@/lib/copy";

function domainOf(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return url;
  }
}

export function SidePanel() {
  const { content, close } = usePanel();
  if (!content) return null;

  const title =
    content.kind === "build"
      ? `${content.snapshot.character.class_name ?? "Build"}${content.snapshot.character.subclass ? ` · ${content.snapshot.character.subclass}` : ""}`
      : content.kind === "sources"
        ? "Sources"
        : content.title ?? domainOf(content.url);

  return (
    <aside className="side-panel" data-testid="side-panel" aria-label={title}>
      <header className="side-panel-head">
        <span className="side-panel-title">{title}</span>
        {content.kind === "link" ? (
          <a className="side-panel-open" href={content.url} target="_blank" rel="noreferrer noopener" data-testid="panel-open">
            Open <ExternalLinkIcon size={13} />
          </a>
        ) : null}
        <button type="button" className="side-panel-close" onClick={close} aria-label="Close panel" data-testid="panel-close">
          <XIcon size={16} />
        </button>
      </header>
      <div className="side-panel-body">
        {content.kind === "build" ? <Result snapshot={content.snapshot} code={content.code} /> : null}

        {content.kind === "sources" ? (
          <div className="sources">
            {content.unverified.length ? (
              <p className="prov audit bad" data-testid="panel-unverified">
                ⚠ Not backed by any calculation or source: {content.unverified.join(", ")}
              </p>
            ) : (
              <p className="prov audit ok" data-testid="panel-verified">
                ✓ Every number in this answer comes from one of these.
              </p>
            )}
            <ul className="evidence" data-testid="panel-sources">
              {content.evidence.map((e, i) => (
                <li key={i}>
                  <div>{e.statement}</div>
                  <div className="prov">
                    <b className={e.provenance.status}>{provenanceLine(e.provenance).split(" ")[0]}</b>
                    {provenanceLine(e.provenance).slice(provenanceLine(e.provenance).split(" ")[0].length)}
                    {e.source_url && /^https?:\/\//.test(e.source_url) ? (
                      <>
                        {" · "}
                        <a href={e.source_url} target="_blank" rel="noreferrer noopener">
                          {domainOf(e.source_url)}
                        </a>
                      </>
                    ) : null}
                  </div>
                  {e.excerpt ? <blockquote className="excerpt">{e.excerpt}</blockquote> : null}
                </li>
              ))}
            </ul>
          </div>
        ) : null}

        {content.kind === "link" ? (
          <div className="link-preview">
            <p className="prov">
              {domainOf(content.url)} · some sites do not allow embedding; use Open if the page stays blank.
            </p>
            <iframe src={content.url} title={title} sandbox="allow-scripts allow-same-origin allow-popups" referrerPolicy="no-referrer" />
          </div>
        ) : null}
      </div>
    </aside>
  );
}
