export interface AnalyticsMetrics {
  requests: number;
  tokens: number;
  input_tokens: number | null;
  output_tokens: number | null;
  cost: number;
}

export interface PersonalAnalyticsData {
  totals: AnalyticsMetrics;
  daily: (AnalyticsMetrics & { date: string })[];
  models: (AnalyticsMetrics & { model: string })[];
  budgets: {
    number?: number;
    limit?: number | null;
    used?: number | null;
    remaining?: number | null;
    duration?: string | null;
    available: boolean;
  }[];
  last_refreshed_at: string | null;
  stale: boolean;
  available: boolean;
  refresh_failed?: boolean;
  coverage_start: string | null;
  coverage_end: string | null;
}
