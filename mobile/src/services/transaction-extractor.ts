/**
 * On-Device Financial Transaction Extractor.
 * Parses raw bank, SMS, and UPI notifications into structured StashedTransaction records.
 * Integrates with PromoFilter to eliminate marketing noise.
 */

import { PromoFilter } from './promo-filter';
import { StashedTransaction, TransactionStash } from './transaction-stash';
import { offlineStore } from './offline-store';

export class TransactionExtractor {
  /**
   * Evaluates notification and extracts a structured StashedTransaction if valid.
   * Returns null if notification is promotional or not a transaction.
   */
  public static async extract(
    packageName: string,
    title: string,
    text: string,
    postTimeMs?: number
  ): Promise<StashedTransaction | null> {
    const filterRes = PromoFilter.evaluate(packageName, title, text);
    if (!filterRes.isGenuineTransaction) {
      return null;
    }

    const pkg = (packageName || '').toLowerCase().trim();
    const t = (title || '').trim();
    const body = (text || '').trim();
    const combined = `${t} ${body}`;
    const lowerCombined = combined.toLowerCase();
    const timestamp = postTimeMs || Date.now();

    // 1. Extract Numeric Amount
    const amountMatch = combined.match(/(?:rs\.?|inr|₹|\$)\s*([\d,]+(?:\.\d{1,2})?)/i);
    if (!amountMatch) {
      return null;
    }
    const rawAmountStr = amountMatch[1].replace(/,/g, '');
    const amount = parseFloat(rawAmountStr);
    if (isNaN(amount) || amount <= 0) {
      return null;
    }

    // 2. Extract Transaction Type
    let type: 'EXPENSE' | 'INCOME' | 'TRANSFER' = 'EXPENSE';
    const isCredit = /\b(?:credited|received\s+from|refund\s+of|salary|deposit\s+of)\b/i.test(lowerCombined);
    const isTransfer = /\b(?:self\s+transfer|transferred\s+between|own\s+account)\b/i.test(lowerCombined);

    if (isTransfer) {
      type = 'TRANSFER';
    } else if (isCredit) {
      type = 'INCOME';
    } else {
      type = 'EXPENSE';
    }

    // 3. Extract Bank / Account Name & Last Digits
    let bankName = '';
    const bankMatches: Record<string, RegExp> = {
      'HDFC Bank': /\b(?:hdfc(?:\s+bank)?|hdfcbk)\b/i,
      'SBI': /\b(?:sbi|state\s+bank(?:\s+of\s+india)?)\b/i,
      'ICICI Bank': /\b(?:icici(?:\s+bank)?)\b/i,
      'Axis Bank': /\b(?:axis(?:\s+bank)?)\b/i,
      'Kotak Bank': /\b(?:kotak(?:\s+mahindra)?)\b/i,
      'Bank of Baroda': /\b(?:bob|bank\s+of\s+baroda)\b/i,
      'Punjab National Bank': /\b(?:pnb|punjab\s+national)\b/i,
      'IDFC FIRST Bank': /\b(?:idfc(?:\s+first)?)\b/i,
      'Paytm Payments Bank': /\bpaytm(?:\s+bank|\s+wallet)?\b/i,
      'Google Pay': /\b(?:gpay|google\s+pay)\b/i,
      'PhonePe': /\bphonepe\b/i,
      'CRED': /\bcred\b/i,
    };

    for (const [name, regex] of Object.entries(bankMatches)) {
      if (regex.test(lowerCombined) || regex.test(pkg)) {
        bankName = name;
        break;
      }
    }

    if (!bankName) {
      if (pkg.includes('paisa')) bankName = 'Google Pay';
      else if (pkg.includes('phonepe')) bankName = 'PhonePe';
      else if (pkg.includes('paytm')) bankName = 'Paytm';
      else if (pkg.includes('dreamplug')) bankName = 'CRED';
      else bankName = 'Primary Bank';
    }

    // Extract Account Digits (e.g., A/c XX4921 or Card ending in 1024)
    const digitsMatch = combined.match(/(?:a\/c|account|card)\s*(?:no\.?)?\s*(?:ending\s+with\s+|ending\s+in\s+|xx+|\*+)?(\d{3,6})/i);
    const accountDigits = digitsMatch ? digitsMatch[1] : '';
    const fullAccountName = accountDigits ? `${bankName} (..${accountDigits})` : bankName;

    // Cross-reference with cached user accounts
    let accountId: string | undefined = undefined;
    try {
      const cachedAccs = await offlineStore.getCachedAccounts();
      if (Array.isArray(cachedAccs) && cachedAccs.length > 0) {
        // Try matching by bank name and digits
        const found = cachedAccs.find((a: any) => {
          const aName = (a.name || '').toLowerCase();
          const matchesBank = bankName && aName.includes(bankName.toLowerCase());
          const matchesDigits = accountDigits && (aName.includes(accountDigits) || (a.account_number || '').includes(accountDigits));
          return matchesBank || matchesDigits;
        });
        if (found) {
          accountId = found.id;
        } else if (cachedAccs.length === 1) {
          accountId = cachedAccs[0].id;
        }
      }
    } catch {
      // Ignore cache lookup errors
    }

    // 4. Extract Merchant / Counterparty & Reference
    let merchant: string | undefined = undefined;
    const upiRefMatch = combined.match(/UPI(?:\s*Ref(?:\s*No\.?)?)?\s*[:\-]?\s*(\d{6,16})/i);
    const reference = upiRefMatch ? upiRefMatch[1] : undefined;

    // Regex heuristics for common transaction counterparty phrasing
    const toMatch = combined.match(/\bto\s+([A-Za-z0-9\s._&-]{2,30}?)(?:\s+on|\s+ref|\s+upi|\.|\,|$|\s+val)/i);
    const atMatch = combined.match(/\bat\s+([A-Za-z0-9\s._&-]{2,30}?)(?:\s+on|\s+ref|\s+upi|\.|\,|$|\s+val)/i);
    const vpaMatch = combined.match(/\bvpa\s+([a-zA-Z0-9.\-_@]+)/i);

    if (atMatch && atMatch[1].trim() && !atMatch[1].toLowerCase().includes('bank')) {
      merchant = atMatch[1].trim();
    } else if (toMatch && toMatch[1].trim() && !toMatch[1].toLowerCase().includes('bank')) {
      merchant = toMatch[1].trim();
    } else if (vpaMatch && vpaMatch[1].trim()) {
      merchant = vpaMatch[1].trim();
    }

    // 5. Initial Confidence & Description
    let confidence = 0.5;
    let description = '';
    let category = 'General';

    if (merchant) {
      confidence = 0.85;
      description = `Payment to ${merchant}`;
      // Basic rule heuristics for category
      const mLower = merchant.toLowerCase();
      if (/\b(swiggy|zomato|mcdonalds|starbucks|kfc|burger|restaurant|cafe|food)\b/i.test(mLower)) {
        category = 'Food & Dining';
      } else if (/\b(blinkit|zepto|instamart|bigbasket|supermarket|mart|grocery)\b/i.test(mLower)) {
        category = 'Groceries';
      } else if (/\b(uber|ola|rapido|metro|petrol|fuel|hpcl|bpcl|ioc|shell)\b/i.test(mLower)) {
        category = 'Transport & Fuel';
      } else if (/\b(amazon|flipkart|myntra|zara|h&m|shopping)\b/i.test(mLower)) {
        category = 'Shopping';
      } else if (/\b(netflix|spotify|prime|hotstar|pvr|inox|cinema)\b/i.test(mLower)) {
        category = 'Entertainment';
      }
    } else {
      description = `${bankName} Transaction`;
    }

    // 6. Generate Idempotent ID
    const id = TransactionStash.generateId(fullAccountName, amount, type, timestamp, reference);

    return {
      id,
      timestamp,
      raw_text: combined,
      package_name: packageName,
      amount,
      type,
      account_name: fullAccountName,
      account_id: accountId,
      merchant,
      category,
      description,
      confidence,
      status: 'STASHED',
      enrichment_source: 'REGEX',
    };
  }
}
