import type { Metadata } from "next";
import { notFound } from "next/navigation";
import CatalogBrowser from "./CatalogBrowser";

const TITLES: Record<string, string> = { phones: "Phones" };

export async function generateMetadata({ params }: { params: Promise<{ category: string }> }): Promise<Metadata> {
  const { category } = await params;
  const title = TITLES[category];
  if (!title) return { title: "Category not found" };
  return {
    title: `${title}: compare by specs and price`,
    description: `Filter ${title.toLowerCase()} by brand, RAM, storage and screen size, then see every store's price with Trust Scores on BuyWise.`,
    alternates: { canonical: `/catalog/${category}` },
  };
}

export default async function CatalogPage({ params }: { params: Promise<{ category: string }> }) {
  const { category } = await params;
  if (!TITLES[category]) notFound();
  return <CatalogBrowser category={category} title={TITLES[category]} />;
}
