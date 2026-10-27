import type { Metadata } from "next";
import { Studio } from "@/components/studio/Studio";

export const metadata: Metadata = { title: "Estudio" };

export default async function StudioPage({ params }: PageProps<"/temas/[id]/estudio">) {
  const { id } = await params;
  return <Studio songId={id} />;
}
