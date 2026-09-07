import raw from "../../python/port/configs/tiktok_config.json";

export type Localised = { en: string; nl: string };
export interface TableConfig {
  id: string;
  title: Localised;
  description: Localised;
  headers: { [column: string]: Localised };
  extractor: string;
}

interface RawConfig { tables: TableConfig[] }

export const TABLES: TableConfig[] = (raw as unknown as RawConfig).tables;

export function text(t: Localised, locale: "en" | "nl"): string {
  const v = t[locale];
  return typeof v === "string" && v !== "" ? v : t.en;
}
