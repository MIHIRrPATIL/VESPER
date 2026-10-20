/**
 * VESPER Local Transaction Stash Buffer.
 * Holds unverified or pending financial transactions locally without mutating active ledger balances.
 * Supports batch enrichment via Gemini 2.5 Flash, 1-tap approvals, and auto-promotion.
 */

import AsyncStorage from '@react-native-async-storage/async-storage';
import { offlineStore } from './offline-store';

export interface StashedTransaction {
  id: string; // Idempotent deterministic ID
  timestamp: number; // Epoch milliseconds
  raw_text: string;
  package_name: string;
  amount: number;
  type: 'EXPENSE' | 'INCOME' | 'TRANSFER';
  account_name: string;
  account_id?: string;
  merchant?: string;
  category?: string; // e.g. "Food & Dining", "Groceries", "Transport"
  description: string;
  confidence: number; // 0.0 to 1.0
  status: 'STASHED' | 'ENRICHING' | 'PROMOTED' | 'DISCARDED';
  enrichment_source?: 'REGEX' | 'GEMINI_BATCH' | 'MANUAL';
  settle_debt_id?: string;
}

const STASH_STORAGE_KEY = 'vesper_transaction_stash';
const PROMOTED_IDS_KEY = 'vesper_promoted_stash_ids';

export type StashListener = () => void;

export class TransactionStash {
  private listeners: Set<StashListener> = new Set();

  public subscribe(listener: StashListener): () => void {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  private notify() {
    this.listeners.forEach((l) => {
      try {
        l();
      } catch (err) {
        console.warn('[TransactionStash] Listener error:', err);
      }
    });
  }

  /**
   * Generates a deterministic, idempotent ID for transactions.
   * Rounding timestamp to 5-minute buckets eliminates duplicate alerts between SMS & App notifications.
   */
  public static generateId(
    account: string,
    amount: number,
    type: string,
    timestamp: number,
    reference?: string
  ): string {
    const timeBucket = Math.floor(timestamp / 300000) * 300000;
    const cleanAcc = (account || 'default').toLowerCase().replace(/\s+/g, '_');
    const cleanRef = (reference || '').toLowerCase().trim();
    const rawKey = `${cleanAcc}_${amount.toFixed(2)}_${type}_${timeBucket}_${cleanRef}`;

    // Simple deterministic string hash
    let hash = 0;
    for (let i = 0; i < rawKey.length; i++) {
      const char = rawKey.charCodeAt(i);
      hash = (hash << 5) - hash + char;
      hash |= 0;
    }
    const hex = Math.abs(hash).toString(16).padStart(8, '0');
    return `stash_${hex}`;
  }

  public async getStash(): Promise<StashedTransaction[]> {
    try {
      const raw = await AsyncStorage.getItem(STASH_STORAGE_KEY);
      const list: StashedTransaction[] = raw ? JSON.parse(raw) : [];
      return Array.isArray(list) ? list.filter((item) => item.status === 'STASHED' || item.status === 'ENRICHING') : [];
    } catch {
      return [];
    }
  }

  private async saveStash(items: StashedTransaction[]): Promise<void> {
    try {
      await AsyncStorage.setItem(STASH_STORAGE_KEY, JSON.stringify(items));
      this.notify();
    } catch (e) {
      console.warn('[TransactionStash] saveStash failed:', e);
    }
  }

  public async getPromotedIds(): Promise<Set<string>> {
    try {
      const raw = await AsyncStorage.getItem(PROMOTED_IDS_KEY);
      const ids: string[] = raw ? JSON.parse(raw) : [];
      return new Set(ids);
    } catch {
      return new Set();
    }
  }

  private async markIdPromoted(id: string): Promise<void> {
    try {
      const ids = await this.getPromotedIds();
      ids.add(id);
      // Keep at most 500 recent IDs to avoid unbounded growth
      const arr = Array.from(ids).slice(-500);
      await AsyncStorage.setItem(PROMOTED_IDS_KEY, JSON.stringify(arr));
    } catch (e) {
      console.warn('[TransactionStash] markIdPromoted failed:', e);
    }
  }

  /**
   * Adds a transaction to the local stash if it has not already been stashed or promoted.
   */
  public async addToStash(tx: StashedTransaction): Promise<boolean> {
    const promoted = await this.getPromotedIds();
    if (promoted.has(tx.id)) {
      console.log(`[TransactionStash] Transaction ${tx.id} already promoted previously. Skipping.`);
      return false;
    }

    const current = await this.getStash();
    if (current.some((item) => item.id === tx.id)) {
      console.log(`[TransactionStash] Transaction ${tx.id} already exists in stash. Skipping duplicate.`);
      return false;
    }

    current.unshift(tx);
    await this.saveStash(current);
    console.log(`[TransactionStash] Stashed transaction: ₹${tx.amount} (${tx.type}) from ${tx.account_name}`);
    return true;
  }

  /**
   * Updates fields of a stashed transaction (e.g. after Gemini batch enrichment or user edit).
   */
  public async updateStashItem(id: string, updates: Partial<StashedTransaction>): Promise<void> {
    const current = await this.getStash();
    const idx = current.findIndex((item) => item.id === id);
    if (idx !== -1) {
      current[idx] = { ...current[idx], ...updates };
      await this.saveStash(current);
    }
  }

  /**
   * Promotes a single stashed transaction into the active ledger and offlinesync queue.
   */
  public async promoteToLedger(
    id: string,
    options?: { settle_debt_id?: string; account_id?: string; category?: string }
  ): Promise<boolean> {
    const current = await this.getStash();
    const item = current.find((t) => t.id === id);
    if (!item) return false;

    // 1. Mark as promoted locally
    await this.markIdPromoted(id);
    const remaining = current.filter((t) => t.id !== id);
    await this.saveStash(remaining);

    // 2. Commit to active offline ledger queue with normalized payload
    const settleDebtId = options?.settle_debt_id || item.settle_debt_id;
    const targetAccountId = options?.account_id || item.account_id;
    const targetCategory = options?.category || item.category || 'General';
    const normalizedType: 'EXPENSE' | 'INCOME' | 'TRANSFER' =
      (item.type?.toUpperCase() === 'INCOME' || item.type?.toLowerCase() === 'credit')
        ? 'INCOME'
        : (item.type?.toUpperCase() === 'TRANSFER' ? 'TRANSFER' : 'EXPENSE');
    const dateFormatted = new Date(item.timestamp).toISOString().split('T')[0];

    const payload = {
      type: normalizedType,
      amount: item.amount,
      category: targetCategory,
      description: item.description || item.merchant || 'Bank Transaction',
      account_id: targetAccountId,
      date: dateFormatted,
      settle_debt_id: settleDebtId,
      metadata: {
        raw_text: item.raw_text,
        package_name: item.package_name,
        merchant: item.merchant,
        settle_debt_id: settleDebtId,
        source: 'mobile_stash_approval',
      },
    };

    // Enqueue for Gateway / Supabase syncing
    await offlineStore.enqueueOfflineTransaction(payload);

    // 3. Optimistically append to local cached transactions
    const cachedTxs = await offlineStore.getCachedTransactions();
    cachedTxs.unshift({
      id: item.id,
      ...payload,
      created_at: new Date(item.timestamp).toISOString(),
    });
    await offlineStore.saveCachedTransactions(cachedTxs);

    // 4. Direct cloud sync to Supabase if configured and online
    import('./supabase')
      .then(({ SupabaseClient }) => {
        SupabaseClient.upsertTransaction({
          id: item.id,
          ...payload,
        }).catch((err) => {
          console.debug('[TransactionStash] Direct Supabase upsert will be reconciled via offline queue:', err);
        });
      })
      .catch(() => {});

    console.log(`[TransactionStash] Promoted transaction ${item.id} (₹${item.amount}) to active ledger.`);
    return true;
  }

  /**
   * Automatically promotes all enriched items that meet or exceed the confidence threshold.
   */
  public async promoteAllHighConfidence(minConfidence: number = 0.85): Promise<number> {
    const current = await this.getStash();
    const eligible = current.filter((item) => item.confidence >= minConfidence);
    let count = 0;

    for (const item of eligible) {
      const ok = await this.promoteToLedger(item.id);
      if (ok) count++;
    }

    return count;
  }

  /**
   * Discards a false positive or unwanted transaction from the stash.
   */
  public async discardFromStash(id: string): Promise<void> {
    await this.markIdPromoted(id); // Mark as handled so it won't re-trigger from same notification
    const current = await this.getStash();
    const remaining = current.filter((t) => t.id !== id);
    await this.saveStash(remaining);
    console.log(`[TransactionStash] Discarded transaction ${id} from stash.`);
  }

  public async clearStash(): Promise<void> {
    await AsyncStorage.removeItem(STASH_STORAGE_KEY);
    this.notify();
  }
}

export const transactionStash = new TransactionStash();
