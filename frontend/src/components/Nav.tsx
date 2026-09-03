import Link from "next/link";

export function Nav({ current }: { current: "ask" | "analyze" | "builds" | "knowledge" }) {
  return (
    <header className="topbar">
      <h1>Reckoner</h1>
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
  );
}
