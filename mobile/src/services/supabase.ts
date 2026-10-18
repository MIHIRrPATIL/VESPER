/**
 * Direct Supabase Cloud REST Client for VESPER Mobile Companion.
 * Uses native fetch over HTTPS to interact directly with Supabase PostgreSQL
 * when the phone is away from home and the desktop workstation is offline.
 * Idempotent upsert headers prevent duplicate ledger entries.
 */

import AsyncStorage from '@react-native-async-storage/async-storage';

const STORAGE_KEY_URL = 'vesper_supabase_url';
const STORAGE_KEY_KEY = 'vesper_supabase_key';

export interface SupabaseConfig {
  url: string;
  key: string;
}

export class SupabaseClient {
  private static cachedConfig: SupabaseConfig | null = null;

  public static async getConfig(): Promise<SupabaseConfig | null> {
    if (this.cachedConfig && this.cachedConfig.url && this.cachedConfig.key) {
      return this.cachedConfig;
    }
    try {
      const [url, key] = await Promise.all([
        AsyncStorage.getItem(STORAGE_KEY_URL),
        AsyncStorage.getItem(STORAGE_KEY_KEY),
      ]);
      if (url && key) {
        this.cachedConfig = { url: url.trim(), key: key.trim() };
        return this.cachedConfig;
      }
    } catch {
      // Ignore storage error
    }
    return null;
  }

  public static async configure(url: string, key: string): Promise<void> {
    const cleanUrl = url.trim().replace(/\/+$/, '');
    const cleanKey = key.trim();
    this.cachedConfig = { url: cleanUrl, key: cleanKey };
    try {
      await Promise.all([
        AsyncStorage.setItem(STORAGE_KEY_URL, cleanUrl),
        AsyncStorage.setItem(STORAGE_KEY_KEY, cleanKey),
      ]);
      console.log(`[SupabaseClient] Configured direct cloud client for project at '${cleanUrl}'`);
    } catch (e) {
      console.warn('[SupabaseClient] Failed to persist configuration:', e);
    }
  }

  public static async isConfigured(): Promise<boolean> {
    const cfg = await this.getConfig();
    return Boolean(cfg && cfg.url && cfg.key);
  }

  private static async getHeaders(): Promise<HeadersInit | null> {
    const cfg = await this.getConfig();
    if (!cfg) return null;
    return {
      apikey: cfg.key,
      Authorization: `Bearer ${cfg.key}`,
      'Content-Type': 'application/json',
    };
  }

  /**
   * Idempotently writes a transaction to Supabase.
   * If a transaction with the same ID already exists, merges duplicates without throwing 409 Conflict.
   */
  public static async upsertTransaction(payload: {
    id: string;
    type: 'EXPENSE' | 'INCOME' | 'TRANSFER';
    amount: number;
    category?: string;
    description?: string;
    account_id?: string;
    date?: string;
    user_id?: string;
  }): Promise<boolean> {
    const cfg = await this.getConfig();
    const headers = await this.getHeaders();
    if (!cfg || !headers) return false;

    const body = {
      id: payload.id,
      user_id: payload.user_id || 'default_user',
      type: payload.type,
      amount: payload.amount,
      category: payload.category || 'General',
      description: payload.description || 'Transaction',
      account_id: payload.account_id || null,
      date: payload.date || new Date().toISOString(),
      updated_at: new Date().toISOString(),
    };

    try {
      const url = `${cfg.url}/rest/v1/transactions`;
      const res = await fetch(url, {
        method: 'POST',
        headers: {
          ...headers,
          // Resolution=merge-duplicates ensures idempotent upsert based on primary key 'id'
          Prefer: 'resolution=merge-duplicates,return=minimal',
        },
        body: JSON.stringify(body),
      });

      if (res.ok || res.status === 201 || res.status === 200 || res.status === 204) {
        console.log(`[SupabaseClient] Direct cloud upsert successful for tx: ${payload.id}`);
        return true;
      }
      console.warn(`[SupabaseClient] Direct upsert failed (HTTP ${res.status}):`, await res.text());
      return false;
    } catch (e) {
      console.warn('[SupabaseClient] Network error during direct upsert:', e);
      return false;
    }
  }

  /**
   * Fetches recent transactions directly from Supabase.
   */
  public static async fetchRecentTransactions(limit: number = 20): Promise<any[] | null> {
    const cfg = await this.getConfig();
    const headers = await this.getHeaders();
    if (!cfg || !headers) return null;

    try {
      const url = `${cfg.url}/rest/v1/transactions?select=*&order=date.desc&limit=${limit}`;
      const res = await fetch(url, { method: 'GET', headers });
      if (res.ok) {
        return await res.json();
      }
    } catch (e) {
      console.warn('[SupabaseClient] fetchRecentTransactions network error:', e);
    }
    return null;
  }

  /**
   * Fetches accounts directly from Supabase.
   */
  public static async fetchAccounts(): Promise<any[] | null> {
    const cfg = await this.getConfig();
    const headers = await this.getHeaders();
    if (!cfg || !headers) return null;

    try {
      const url = `${cfg.url}/rest/v1/accounts?select=*&order=name.asc`;
      const res = await fetch(url, { method: 'GET', headers });
      if (res.ok) {
        return await res.json();
      }
    } catch (e) {
      console.warn('[SupabaseClient] fetchAccounts network error:', e);
    }
    return null;
  }
}
