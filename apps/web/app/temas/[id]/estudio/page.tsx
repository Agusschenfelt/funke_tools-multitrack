import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = { title: "Estudio" };

/** Placeholder until the mixer lands (T3). */
export default async function StudioPage({ params }: PageProps<"/temas/[id]/estudio">) {
  const { id } = await params;
  return (
    <main style={{ maxWidth: "64rem", margin: "0 auto", padding: "2rem 1rem 4.5rem" }}>
      <h1 style={{ fontSize: "1.5rem", fontWeight: 800, textTransform: "uppercase" }}>Estudio</h1>
      <p style={{ marginTop: "0.75rem", color: "var(--paper-dim)" }}>
        El mezclador todavía no está disponible.
      </p>
      <Link
        href={`/temas/${id}`}
        style={{ display: "inline-flex", alignItems: "center", minHeight: "var(--touch)" }}
      >
        Volver al procesamiento
      </Link>
    </main>
  );
}
