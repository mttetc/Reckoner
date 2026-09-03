import Link from "next/link";
import { StatusStrip } from "@/components/StatusStrip";

export type Section = "ask" | "analyze" | "builds" | "knowledge";

export function Nav({ current }: { current: Section }) {
  return (
    <>
      <header className="topbar">
        <h1>
          Reck<span>o</span>ner
        </h1>
        <nav className="nav" aria-label="Sections">
          <Link href="/ask" aria-current={current === "ask" ? "page" : undefined} data-testid="nav-ask">
            Ask
          </Link>
          <Link href="/" aria-current={current === "analyze" ? "page" : undefined}>
            Analyse
          </Link>
          <Link href="/builds" aria-current={current === "builds" ? "page" : undefined} data-testid="nav-builds">
            Builds
          </Link>
          <Link href="/knowledge" aria-current={current === "knowledge" ? "page" : undefined} data-testid="nav-knowledge">
            Knowledge
          </Link>
        </nav>
      </header>
      <StatusStrip />
    </>
  );
}
