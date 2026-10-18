/**
 * Ultra-Strict Multi-Layered Financial Notification & Promo Filter.
 * Filters out marketing, loan pre-approvals, discount vouchers, and cash-back noise
 * from banking and payment apps before transaction parsing.
 */

export interface PromoFilterResult {
  isGenuineTransaction: boolean;
  rejectReason?: string;
}

const FINANCIAL_PACKAGE_KEYWORDS = [
  'paisa', // GPay
  'phonepe',
  'paytm',
  'dreamplug', // Cred
  'freecharge',
  'mobikwik',
  'bhim',
  'hdfc',
  'sbi',
  'icici',
  'axis',
  'kotak',
  'bob',
  'pnb',
  'canara',
  'idfc',
  'indusind',
  'rbl',
  'citi',
  'hsbc',
  'standardchartered',
  'federal',
  'bank',
];

const PROMO_TOKENS = [
  // Discounts, offers, and promotions
  /\bflat\s+\d+%\s*(?:off|discount|cashback)\b/i,
  /\b(?:save|earn)\s+extra\b/i,
  /\buse\s+(?:code|coupon)\b/i,
  /\b(?:promo|coupon|discount|voucher)\s*code\b/i,
  /\b(?:cashback|reward)\s+offer\b/i,
  /\b(?:win|earn)\s+(?:up\s+to|flat)\b/i,
  /\bchance\s+to\s+win\b/i,
  /\b(?:scratch\s*card|spin\s+and\s+win|spin\s*wheel)\b/i,
  /\brefer\s+(?:and\s+earn|a\s+friend)\b/i,
  /\bcongratulations(?:\s+you\s+won)?\b/i,
  /\bfree\s+(?:delivery|trial|membership)\b/i,
  /\blimited\s+(?:period|time)\s+offer\b/i,
  /\bhurry\s*[,!]?\s*(?:offer|deal)\b/i,

  // Loans, credit cards, and marketing invitations
  /\bpre-?approved\s+(?:loan|credit|card|offer|limit)\b/i,
  /\binstant\s+(?:personal\s+)?loan\b/i,
  /\bapply\s+now\s+for\b/i,
  /\bcredit\s+limit\s+(?:increased|enhanced|increase|upgrade)\b/i,
  /\bupgrade\s+your\s+(?:card|account|limit)\b/i,
  /\beligible\s+for\s+(?:a\s+)?(?:loan|credit|card)\b/i,
  /\binterest\s+rate\s+starting\b/i,
  /\bno\s+cost\s+emi\s+on\b/i,
  /\binvest\s+(?:now|today)\b/i,

  // Non-transactional alerts and bills
  /\brecharge\s+(?:due|now|reminder)\b/i,
  /\bbill\s+(?:generated|due|reminder)\b/i,
  /\bplan\s+(?:is\s+)?expiring\b/i,
  /\b(?:points|credits|coins)\s+will\s+expire\b/i,
  /\brenew\s+(?:now|your\s+subscription)\b/i,

  // Marketing link shorteners
  /\b(?:1kx\.in|bit\.ly|tinyurl|fkrt\.it|myntr\.it|zmt\.run|swiggy\.onelink)\b/i,
];

// Explicit settlement action verbs
const DEBIT_ACTION_VERBS = [
  /\bdebited\b/i,
  /\bspent\b/i,
  /\bpaid\s+(?:rs\.?|inr|₹|\$|to)\b/i,
  /\btransferred\s+(?:rs\.?|inr|₹|\$|to)\b/i,
  /\bwithdrawn\b/i,
  /\bpurchase\s+of\b/i,
  /\bauto-?debited\b/i,
  /\bauto-?debit\b/i,
  /\bpayment\s+of\s+(?:rs\.?|inr|₹|\$)/i,
  /\bsent\s+(?:rs\.?|inr|₹|\$)\b/i,
  /\btxn\s+(?:of\s+)?(?:rs\.?|inr|₹|\$)/i,
];

const CREDIT_ACTION_VERBS = [
  /\bcredited\b/i,
  /\breceived\s+(?:rs\.?|inr|₹|\$|from)\b/i,
  /\brefund\s+of\b/i,
  /\bsalary\b/i,
  /\bdeposit\s+of\b/i,
];

const CURRENCY_AMOUNT_PATTERN = /(?:rs\.?|inr|₹|\$)\s*[\d,]+(?:\.\d+)?/i;

export class PromoFilter {
  /**
   * Evaluates an incoming notification across 3 sequential gates.
   * Returns true only for verified financial transaction notifications.
   */
  public static evaluate(
    packageName: string,
    title: string,
    text: string
  ): PromoFilterResult {
    const pkg = (packageName || '').toLowerCase().trim();
    const t = (title || '').trim();
    const body = (text || '').trim();
    const combined = `${t} ${body}`.toLowerCase();

    // 0. Drop OTPs and 2FA verification notifications (handled separately by security listener)
    if (/\b(?:otp|verification\s*code|security\s*code|secret\s*code|auth\s*code|login\s*code)\b/i.test(combined)) {
      return { isGenuineTransaction: false, rejectReason: 'OTP / Verification Code' };
    }

    // 1. Gate 1: Check if sender is financial or telecommunication SMS header
    const isFinancialApp = FINANCIAL_PACKAGE_KEYWORDS.some((kw) => pkg.includes(kw));
    const isSmsApp =
      pkg.includes('messaging') ||
      pkg.includes('mms') ||
      pkg.includes('message') ||
      pkg === 'com.google.android.apps.messaging';

    // Drop generic ad-sender headers (e.g., AD-SWIGGY, DM-ZOMATO, TM-HDFCBK when purely promotional)
    const isCommercialHeader = /^(?:AD|DM|TM|QP|XY|BA|BW|BP|BZ|CP|VM)-/i.test(t);

    if (!isFinancialApp && !isSmsApp) {
      return { isGenuineTransaction: false, rejectReason: 'Non-financial package' };
    }

    // 2. Gate 2: Currency amount token requirement
    if (!CURRENCY_AMOUNT_PATTERN.test(combined)) {
      return { isGenuineTransaction: false, rejectReason: 'Missing currency amount token' };
    }

    // 3. Gate 3: Promotional token blacklist
    for (const pattern of PROMO_TOKENS) {
      if (pattern.test(combined)) {
        // Even if sent by a bank, if it matches loan marketing or promo codes, drop it
        // Exception: If message clearly says "Rs X debited for purchase at Swiggy using coupon", keep it
        const hasExplicitDebit = DEBIT_ACTION_VERBS.some((v) => v.test(combined));
        const hasExplicitCredit = CREDIT_ACTION_VERBS.some((v) => v.test(combined));
        if (!hasExplicitDebit && !hasExplicitCredit) {
          return { isGenuineTransaction: false, rejectReason: `Promo token match: ${pattern.source}` };
        }
      }
    }

    // 4. Gate 4: Mandatory Settlement Action Verb requirement
    const hasDebit = DEBIT_ACTION_VERBS.some((v) => v.test(combined));
    const hasCredit = CREDIT_ACTION_VERBS.some((v) => v.test(combined));

    if (!hasDebit && !hasCredit) {
      return {
        isGenuineTransaction: false,
        rejectReason: 'No settlement action verb (debited/credited/spent/paid)',
      };
    }

    // Passed all validation gates!
    return { isGenuineTransaction: true };
  }
}
