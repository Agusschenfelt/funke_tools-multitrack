import type { Metadata } from "next";
import { ProcessingView } from "@/components/processing/ProcessingView";

export const metadata: Metadata = { title: "Procesando" };

export default async function SongPage({ params, searchParams }: PageProps<"/temas/[id]">) {
  const [{ id }, query] = await Promise.all([params, searchParams]);
  return <ProcessingView songId={id} query={{ a: query.a, s: query.s }} />;
}
