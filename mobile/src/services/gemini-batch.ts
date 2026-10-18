/**
 * Asynchronous Batch Financial Enrichment Engine via Google Gemini 2.5 Flash.
 * Processes stashed transaction notifications in batches to classify spending nature,
 * extract clean counterparty names, and auto-promote high-confidence entries to the ledger.
 */

import AsyncStorage from '@react-native-async-storage/async-storage';
import { transactionStash, StashedTransaction } from './transaction-stash';

const GEMINI_API_KEY_STORAGE = 'vesper_gemini_api_key';
const DEFAULT_GEMINI_MODEL = 'gemini-2.5-flash';

export class GeminiBatchEnricher {
  private static timer: any = null;

  public static async getApiKey(): Promise<string> {
    try {
      const stored = await AsyncStorage.getItem(GEMINI_API_KEY_STORAGE);
      return stored ? stored.trim() : '';
    } catch {
      return '';
    }
  }

  public static async setApiKey(key: string): Promise<void> {
    try {
      await AsyncStorage.setItem(GEMINI_API_KEY_STORAGE, key.trim());
      console.log('[GeminiBatch] Updated Gemini API Key in local storage.');
    } catch (e) {
      console.warn('[GeminiBatch] Failed to save Gemini API key:', e);
    }
  }

  /**
   * Enriches a batch of stashed transactions using Gemini 2.5 Flash.
   * Auto-promotes high-confidence items (>= 0.85) to the active ledger.
   */
  public static async enrichBatch(
    itemsToEnrich?: StashedTransaction[]
  ): Promise<{ enrichedCount: number; autoPromotedCount: number; error?: string }> {
    const apiKey = await this.getApiKey();
    if (!apiKey) {
      return { enrichedCount: 0, autoPromotedCount: 0, error: 'Gemini API Key not configured' };
    }

    const currentStash = itemsToEnrich || (await transactionStash.getStash());
    // Filter only items that haven't been enriched by Gemini yet
    const pendingItems = currentStash.filter(
      (item) => item.status === 'STASHED' && item.enrichment_source !== 'GEMINI_BATCH'
    ).slice(0, 10); // Batch size: up to 10 items at a time

    if (pendingItems.length === 0) {
      return { enrichedCount: 0, autoPromotedCount: 0 };
    }

    console.log(`[GeminiBatch] Starting batch enrichment for ${pendingItems.length} stashed transaction(s)...`);

    // Mark items as ENRICHING in UI
    for (const item of pendingItems) {
      await transactionStash.updateStashItem(item.id, { status: 'ENRICHING' });
    }

    const batchPayload = pendingItems.map((item) => ({
      id: item.id,
      text: item.raw_text,
      amount: item.amount,
      type: item.type,
      account: item.account_name,
    }));

    const systemPrompt = `You are an expert financial analyst. Analyze these transaction notifications and output ONLY a JSON array.
For each item, classify:
1. "merchant": The specific business, merchant, or person receiving or sending money (e.g. "Swiggy", "Zomato", "Shell", "Amazon", "Airtel"). If unclear, provide the best guess or "Unknown".
2. "nature": The spending category: "Food & Dining", "Groceries", "Transport & Fuel", "Shopping", "Bills & Utilities", "Entertainment", "Health", "Investments", "Salary", or "Transfer".
3. "description": A clean, concise title (e.g. "Swiggy Food Order", "Shell Petrol Pump", "Netflix Subscription").
4. "confidence": A float from 0.0 to 1.0 representing how certain you are of the merchant and category.

Input Batch:
${JSON.stringify(batchPayload, null, 2)}`;

    try {
      const url = `https://generativelanguage.googleapis.com/v1beta/models/${DEFAULT_GEMINI_MODEL}:generateContent?key=${apiKey}`;
      const response = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          contents: [{ parts: [{ text: systemPrompt }] }],
          generationConfig: {
            responseMimeType: 'application/json',
            temperature: 0.1,
          },
        }),
      });

      if (!response.ok) {
        const errText = await response.text();
        console.warn(`[GeminiBatch] API error (${response.status}):`, errText);
        // Revert status back to STASHED
        for (const item of pendingItems) {
          await transactionStash.updateStashItem(item.id, { status: 'STASHED' });
        }
        return { enrichedCount: 0, autoPromotedCount: 0, error: `Gemini HTTP ${response.status}` };
      }

      const data = await response.json();
      const rawText = data?.candidates?.[0]?.content?.parts?.[0]?.text || '[]';
      const results: Array<{
        id: string;
        merchant?: string;
        nature?: string;
        description?: string;
        confidence?: number;
      }> = JSON.parse(rawText);

      let enrichedCount = 0;
      for (const res of results) {
        if (!res.id) continue;
        const conf = typeof res.confidence === 'number' ? res.confidence : 0.7;
        await transactionStash.updateStashItem(res.id, {
          merchant: res.merchant || undefined,
          category: res.nature || 'General',
          description: res.description || 'Bank Transaction',
          confidence: conf,
          status: 'STASHED',
          enrichment_source: 'GEMINI_BATCH',
        });
        enrichedCount++;
      }

      console.log(`[GeminiBatch] Successfully enriched ${enrichedCount} transaction(s). Running auto-promotion...`);

      // Auto-promote all items that meet the high confidence threshold (>= 0.85)
      const autoPromotedCount = await transactionStash.promoteAllHighConfidence(0.85);
      console.log(`[GeminiBatch] Auto-promoted ${autoPromotedCount} high-confidence transaction(s) to active ledger.`);

      return { enrichedCount, autoPromotedCount };
    } catch (e: any) {
      console.warn('[GeminiBatch] Batch enrichment failed:', e);
      for (const item of pendingItems) {
        await transactionStash.updateStashItem(item.id, { status: 'STASHED' });
      }
      return { enrichedCount: 0, autoPromotedCount: 0, error: String(e) };
    }
  }

  /**
   * Starts periodic background batch enrichment timer (default every 20 minutes).
   */
  public static startBackgroundBatchTimer(intervalMs: number = 20 * 60 * 1000) {
    if (this.timer) {
      clearInterval(this.timer);
    }
    this.timer = setInterval(() => {
      this.enrichBatch().catch((err) => {
        console.warn('[GeminiBatch] Periodic background enrichment notice:', err);
      });
    }, intervalMs);
    console.log(`[GeminiBatch] Periodic enrichment timer active (${Math.round(intervalMs / 60000)}m).`);
  }

  public static stopBackgroundBatchTimer() {
    if (this.timer) {
      clearInterval(this.timer);
      this.timer = null;
    }
  }
}
