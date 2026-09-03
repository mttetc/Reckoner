import Link from "next/link";

export function Nav({ current }: { current: "analyze" | "builds" }) {
  return (
    <header className="topbar">
      <h1>Reckoner</h1>
      <nav className="nav" aria-label="Sections">
        <Link href="/" aria-current={current === "analyze" ? "page" : undefined}>
          Analyse
        </Link>
        <Link href="/builds" aria-current={current === "builds" ? "page" : undefined} data-testid="nav-builds">
          Builds
        </Link>
      </nav>
    </header>
  );
}
