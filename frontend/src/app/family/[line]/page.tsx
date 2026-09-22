import type { Metadata } from "next";
import { serverGet } from "@/lib/api";
import type { ProductFamily } from "@/lib/types";
import FamilyView from "./FamilyView";

export async function generateMetadata({ params }: { params: Promise<{ line: string }> }): Promise<Metadata> {
  const { line } = await params;
  const family = await serverGet<ProductFamily>(`/products/family?line=${encodeURIComponent(line)}`);
  if (!family) return { title: "Product line not found" };
  const desc = `Every storage size, colour and store for the ${family.label}: ${family.total_retailers} stores compared with true final prices and Trust Scores on BuyWise.`;
  return { title: `${family.label} prices at every store`, description: desc, alternates: { canonical: `/family/${line}` } };
}

export default async function FamilyPage({ params }: { params: Promise<{ line: string }> }) {
  const { line } = await params;
  return <FamilyView line={line} />;
}
