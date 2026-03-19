/**
 * API Key Related Type Definitions
 * Corresponds to backend api_keys table
 */

/** API Key Entity */
export interface ApiKey {
  id: number;
  key_name: string;
  key_value: string;          // Sanitized in lists, fully returned on creation
  is_active: boolean;
  created_at: string;
  last_used_at?: string | null;
  // Period costs (USD)
  daily_cost?: number | null;
  weekly_cost?: number | null;
  monthly_cost?: number | null;
  // Spending limits (USD), null = no limit
  daily_cost_limit?: number | null;
  weekly_cost_limit?: number | null;
  monthly_cost_limit?: number | null;
}

/** Create API Key Request */
export interface ApiKeyCreate {
  key_name: string;
}

/** Update API Key Request */
export interface ApiKeyUpdate {
  key_name?: string;
  is_active?: boolean;
  daily_cost_limit?: number | null;
  weekly_cost_limit?: number | null;
  monthly_cost_limit?: number | null;
}

/** API Key List Query Params */
export interface ApiKeyListParams {
  is_active?: boolean;
  page?: number;
  page_size?: number;
}