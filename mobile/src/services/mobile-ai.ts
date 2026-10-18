/**
 * Standalone Mobile AI Assistant via Google Gemini 2.5 Flash.
 * Handles user directives and queries directly on the mobile device when disconnected from the central gateway.
 * Supports zero-latency local fast-paths for balances, tasks, and spending, plus direct cloud intelligence.
 */

import { offlineStore } from './offline-store';
import { GeminiBatchEnricher } from './gemini-batch';

const DEFAULT_GEMINI_MODEL = 'gemini-2.5-flash';

export class MobileAI {
  /**
   * Evaluates user prompt and dispatches to local fast-path or direct Gemini 2.5 Flash.
   */
  public static async query(prompt: string): Promise<string> {
    const clean = prompt.trim();
    if (!clean) return '';

    const lower = clean.toLowerCase();

    // ── Tier 1: Zero-Cloud Local Fast-Paths (0ms) ──────────────────────────

    // 1. Bank Balances & Accounts Query
    if (
      /\b(?:what(?:'s|\s+is)\s+my\s+(?:bank\s+)?balance|account\s+balances?|how\s+much\s+(?:money\s+)?(?:do\s+i\s+have|in\s+my\s+bank)|bank\s+balance)\b/i.test(lower)
    ) {
      try {
        const accounts = await offlineStore.getCachedAccounts();
        if (Array.isArray(accounts) && accounts.length > 0) {
          const total = accounts.reduce((acc, a) => acc + (Number(a.balance) || 0), 0);
          const breakdown = accounts
            .slice(0, 4)
            .map((a) => `${a.name || 'Account'}: ₹${Number(a.balance || 0).toLocaleString('en-IN')}`)
            .join(', ');
          return `Your total tracked balance across ${accounts.length} account(s) is ₹${total.toLocaleString('en-IN')}. (${breakdown})`;
        }
      } catch {
        // Fall through
      }
    }

    // 2. Tasks & Agenda Query
    if (
      /\b(?:what\s+are\s+my\s+tasks|show\s+(?:my\s+)?tasks|pending\s+tasks|today(?:'s)?\s+agenda|what(?:'s|\s+is)\s+on\s+my\s+schedule)\b/i.test(lower)
    ) {
      try {
        const tasks = await offlineStore.getCachedTasks();
        if (Array.isArray(tasks) && tasks.length > 0) {
          const pending = tasks.filter((t) => !(t.done ?? t.completed)).slice(0, 5);
          if (pending.length > 0) {
            const list = pending.map((t, idx) => `${idx + 1}. ${t.title || 'Task'}`).join('\n');
            return `You have ${pending.length} pending task(s) in your local agenda:\n${list}`;
          }
          return 'All your agenda tasks are currently marked as completed, sir.';
        }
      } catch {
        // Fall through
      }
    }

    // 3. Quick Local Task Creation
    const addTaskMatch = clean.match(/^(?:add\s+task|create\s+task|remind\s+me\s+to|new\s+task)\s+(.+)/i);
    if (addTaskMatch && addTaskMatch[1].trim()) {
      const taskTitle = addTaskMatch[1].trim();
      const payload = {
        title: taskTitle,
        priority: 'normal',
        done: false,
        created_at: new Date().toISOString(),
      };
      await offlineStore.enqueueOfflineTask('CREATE', payload);
      // Append optimistically to cache
      const cached = await offlineStore.getCachedTasks();
      cached.unshift({ id: `local_task_${Date.now()}`, ...payload });
      await offlineStore.saveCachedTasks(cached);
      return `Task '${taskTitle}' has been created locally and queued for synchronization.`;
    }

    // 4. Today's Spending Query
    if (
      /\b(?:how\s+much\s+did\s+i\s+spend\s+today|today(?:'s)?\s+expenses?|today(?:'s)?\s+spending|spent\s+today)\b/i.test(lower)
    ) {
      try {
        const txs = await offlineStore.getCachedTransactions();
        if (Array.isArray(txs)) {
          const todayStr = new Date().toISOString().split('T')[0];
          const todayExpenses = txs.filter((t: any) => {
            const dateStr = (t.date || t.created_at || '').split('T')[0];
            const isExpense = t.type === 'EXPENSE' || t.type === 'DEBIT' || Number(t.amount) < 0;
            return dateStr === todayStr && isExpense;
          });
          const totalSpent = todayExpenses.reduce((sum, t) => sum + Math.abs(Number(t.amount) || 0), 0);
          return `You have logged ₹${totalSpent.toLocaleString('en-IN')} across ${todayExpenses.length} transaction(s) today.`;
        }
      } catch {
        // Fall through
      }
    }

    // ── Tier 2: Direct Google Gemini 2.5 Flash Cloud Inference ─────────────
    const apiKey = await GeminiBatchEnricher.getApiKey();
    if (!apiKey) {
      return (
        'The mobile companion is currently operating in Standalone Mode while disconnected from the workstation gateway. ' +
        'To enable standalone intelligence, please configure your Gemini API Key in Settings or connect once to your desktop workstation to sync credentials automatically.'
      );
    }

    try {
      // Gather lightweight local situational context
      let contextSnippet = `Local Time: ${new Date().toLocaleString('en-IN')}.\n`;
      try {
        const accs = await offlineStore.getCachedAccounts();
        if (accs.length > 0) {
          const total = accs.reduce((sum, a) => sum + (Number(a.balance) || 0), 0);
          contextSnippet += `Current Tracked Balance: ₹${total.toLocaleString('en-IN')}.\n`;
        }
        const tasks = await offlineStore.getCachedTasks();
        const pendingCount = tasks.filter((t) => !(t.done ?? t.completed)).length;
        contextSnippet += `Pending Tasks: ${pendingCount}.\n`;
      } catch {
        // Ignore context gathering errors
      }

      const systemInstruction =
        'You are Alfred, the intelligent British butler and proactive executive assistant of the VESPER ecosystem. ' +
        'You are currently communicating with your user through the mobile companion app in Autonomous Standalone Mode (workstation gateway disconnected). ' +
        'Be extremely articulate, direct, concise, and helpful. Never use emojis. Address the user formally (as sir or by name).';

      const url = `https://generativelanguage.googleapis.com/v1beta/models/${DEFAULT_GEMINI_MODEL}:generateContent?key=${apiKey}`;

      const res = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          system_instruction: { parts: [{ text: systemInstruction }] },
          contents: [
            {
              parts: [
                {
                  text: `[System Context]\n${contextSnippet}\n\n[User Directive]\n${clean}`,
                },
              ],
            },
          ],
          generationConfig: {
            temperature: 0.3,
            maxOutputTokens: 600,
          },
        }),
      });

      if (!res.ok) {
        const errText = await res.text();
        console.warn(`[MobileAI] Gemini API error (${res.status}):`, errText);
        return `I encountered an issue contacting the Gemini intelligence service (HTTP ${res.status}). Please verify your network connection.`;
      }

      const data = await res.json();
      const reply = data?.candidates?.[0]?.content?.parts?.[0]?.text;
      if (reply) {
        return reply.trim();
      }
      return 'I received an empty response from the intelligence service, sir.';
    } catch (e: any) {
      console.warn('[MobileAI] Query execution failed:', e);
      return `Standalone query execution encountered a network exception: ${e?.message || e}`;
    }
  }
}
