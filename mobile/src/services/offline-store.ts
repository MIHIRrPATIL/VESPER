import AsyncStorage from "@react-native-async-storage/async-storage";
import { gatewayClient } from "./gateway";

export interface OfflineTaskAction {
  id: string; // Action ID or local task ID
  action: "CREATE" | "TOGGLE" | "DELETE";
  payload: any;
  timestamp: number;
  retries?: number;
}

export interface OfflineTransactionAction {
  id: string;
  payload: {
    type: "EXPENSE" | "INCOME" | "TRANSFER";
    amount: number;
    category?: string;
    description?: string;
    account_id?: string;
    date?: string;
  };
  timestamp: number;
  retries?: number;
}

export type OfflineSyncListener = (isSyncing: boolean, pendingCount: number) => void;

class OfflineStore {
  private syncListeners: Set<OfflineSyncListener> = new Set();
  private isSyncing = false;

  constructor() {
    // Automatically trigger sync when the gateway reconnects
    gatewayClient.onStatus((status) => {
      if (status === "connected") {
        this.syncPendingBacklog().catch((err) => {
          console.warn("[OfflineStore] Auto-sync notice:", err);
        });
      }
    });
  }

  public subscribeSync(listener: OfflineSyncListener): () => void {
    this.syncListeners.add(listener);
    this.notifySync(this.isSyncing);
    return () => this.syncListeners.delete(listener);
  }

  private async notifySync(syncing: boolean) {
    this.isSyncing = syncing;
    const count = await this.getPendingCount();
    this.syncListeners.forEach((l) => {
      try {
        l(syncing, count);
      } catch (e) {
        console.error("[OfflineStore] Listener error:", e);
      }
    });
  }

  // ── 1. Cache Storage Helpers ─────────────────────────────────────────────

  public async getCachedTasks(): Promise<any[]> {
    try {
      const raw = await AsyncStorage.getItem("vesper_cached_tasks");
      return raw ? JSON.parse(raw) : [];
    } catch {
      return [];
    }
  }

  public async saveCachedTasks(tasks: any[]): Promise<void> {
    try {
      await AsyncStorage.setItem("vesper_cached_tasks", JSON.stringify(tasks));
    } catch (e) {
      console.warn("[OfflineStore] saveCachedTasks failed:", e);
    }
  }

  public async getCachedCalendarEvents(): Promise<any[]> {
    try {
      const raw = await AsyncStorage.getItem("vesper_cached_calendar_events");
      return raw ? JSON.parse(raw) : [];
    } catch {
      return [];
    }
  }

  public async saveCachedCalendarEvents(events: any[]): Promise<void> {
    try {
      await AsyncStorage.setItem("vesper_cached_calendar_events", JSON.stringify(events));
    } catch (e) {
      console.warn("[OfflineStore] saveCachedCalendarEvents failed:", e);
    }
  }

  public async getCachedFinanceOverview(): Promise<any | null> {
    try {
      const raw = await AsyncStorage.getItem("vesper_cached_finance_overview");
      return raw ? JSON.parse(raw) : null;
    } catch {
      return null;
    }
  }

  public async saveCachedFinanceOverview(overview: any): Promise<void> {
    try {
      await AsyncStorage.setItem("vesper_cached_finance_overview", JSON.stringify(overview));
    } catch (e) {
      console.warn("[OfflineStore] saveCachedFinanceOverview failed:", e);
    }
  }

  public async getCachedAccounts(): Promise<any[]> {
    try {
      const raw = await AsyncStorage.getItem("vesper_cached_accounts");
      return raw ? JSON.parse(raw) : [];
    } catch {
      return [];
    }
  }

  public async saveCachedAccounts(accounts: any[]): Promise<void> {
    try {
      await AsyncStorage.setItem("vesper_cached_accounts", JSON.stringify(accounts));
    } catch (e) {
      console.warn("[OfflineStore] saveCachedAccounts failed:", e);
    }
  }

  public async getCachedDebts(): Promise<any[]> {
    try {
      const raw = await AsyncStorage.getItem("vesper_cached_debts");
      return raw ? JSON.parse(raw) : [];
    } catch {
      return [];
    }
  }

  public async saveCachedDebts(debts: any[]): Promise<void> {
    try {
      await AsyncStorage.setItem("vesper_cached_debts", JSON.stringify(debts));
    } catch (e) {
      console.warn("[OfflineStore] saveCachedDebts failed:", e);
    }
  }

  public async getCachedTransactions(): Promise<any[]> {
    try {
      const raw = await AsyncStorage.getItem("vesper_cached_transactions");
      return raw ? JSON.parse(raw) : [];
    } catch {
      return [];
    }
  }

  public async saveCachedTransactions(txs: any[]): Promise<void> {
    try {
      await AsyncStorage.setItem("vesper_cached_transactions", JSON.stringify(txs));
    } catch (e) {
      console.warn("[OfflineStore] saveCachedTransactions failed:", e);
    }
  }

  // ── 2. Offline Action Queues ─────────────────────────────────────────────

  public async getPendingTaskQueue(): Promise<OfflineTaskAction[]> {
    try {
      const raw = await AsyncStorage.getItem("vesper_offline_task_queue");
      return raw ? JSON.parse(raw) : [];
    } catch {
      return [];
    }
  }

  public async enqueueOfflineTask(
    action: "CREATE" | "TOGGLE" | "DELETE",
    payload: any
  ): Promise<void> {
    const queue = await this.getPendingTaskQueue();
    const item: OfflineTaskAction = {
      id: `task_action_${Date.now()}_${Math.random().toString(36).substring(2, 6)}`,
      action,
      payload,
      timestamp: Date.now(),
    };
    queue.push(item);
    await AsyncStorage.setItem("vesper_offline_task_queue", JSON.stringify(queue));
    await this.notifySync(this.isSyncing);
  }

  public async getPendingTransactionQueue(): Promise<OfflineTransactionAction[]> {
    try {
      const raw = await AsyncStorage.getItem("vesper_offline_transaction_queue");
      return raw ? JSON.parse(raw) : [];
    } catch {
      return [];
    }
  }

  public async enqueueOfflineTransaction(
    payload: OfflineTransactionAction["payload"]
  ): Promise<void> {
    const queue = await this.getPendingTransactionQueue();
    const item: OfflineTransactionAction = {
      id: `tx_action_${Date.now()}_${Math.random().toString(36).substring(2, 6)}`,
      payload,
      timestamp: Date.now(),
    };
    queue.push(item);
    await AsyncStorage.setItem("vesper_offline_transaction_queue", JSON.stringify(queue));
    await this.notifySync(this.isSyncing);
  }

  public async getPendingCount(): Promise<number> {
    const [tasks, txs] = await Promise.all([
      this.getPendingTaskQueue(),
      this.getPendingTransactionQueue(),
    ]);
    return tasks.length + txs.length;
  }

  // ── 3. Synchronization Engine ────────────────────────────────────────────

  public async clearPendingBacklog(): Promise<void> {
    try {
      await AsyncStorage.removeItem("vesper_offline_task_queue");
      await AsyncStorage.removeItem("vesper_offline_transaction_queue");
      console.log("[OfflineStore] Manually purged offline queues.");
    } catch (e) {
      console.warn("[OfflineStore] clearPendingBacklog failed:", e);
    }
    await this.notifySync(false);
  }

  public async syncPendingBacklog(): Promise<{ tasksSynced: number; txsSynced: number }> {
    if (this.isSyncing) return { tasksSynced: 0, txsSynced: 0 };
    await this.notifySync(true);

    let tasksSynced = 0;
    let txsSynced = 0;

    const baseUrl = gatewayClient.getHttpUrl();

    try {
      // 1. Flush Task Actions
      const taskQueue = await this.getPendingTaskQueue();
      const remainingTasks: OfflineTaskAction[] = [];

      for (const item of taskQueue) {
        const retries = (item.retries || 0) + 1;
        item.retries = retries;
        try {
          let res: Response | null = null;
          if (item.action === "CREATE") {
            res = await fetch(`${baseUrl}/api/tasks`, {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify(item.payload),
            });
          } else if (item.action === "TOGGLE") {
            const taskId = item.payload?.id || item.payload;
            res = await fetch(`${baseUrl}/api/tasks/${taskId}/toggle`, {
              method: "PATCH",
            });
          } else if (item.action === "DELETE") {
            const taskId = item.payload?.id || item.payload;
            res = await fetch(`${baseUrl}/api/tasks/${taskId}`, {
              method: "DELETE",
            });
          }

          if (res) {
            if (res.ok) {
              tasksSynced++;
            } else if (res.status === 404 && (item.action === "TOGGLE" || item.action === "DELETE")) {
              // Target task already gone/reconciled on gateway; consider completed
              tasksSynced++;
            } else if (res.status >= 400 && res.status < 500 && res.status !== 429) {
              // Poison-pill client error (bad payload/missing resource); drop permanently
              console.warn(`[OfflineStore] Dropping poison task mutation ${item.id}: HTTP ${res.status}`);
            } else if (retries < 3) {
              remainingTasks.push(item);
            } else {
              console.warn(`[OfflineStore] Dropping task mutation ${item.id} after ${retries} attempts: HTTP ${res.status}`);
            }
          }
        } catch (e) {
          if (retries < 3) {
            remainingTasks.push(item);
          } else {
            console.warn(`[OfflineStore] Dropping task mutation ${item.id} after ${retries} network failures:`, e);
          }
        }
      }

      await AsyncStorage.setItem("vesper_offline_task_queue", JSON.stringify(remainingTasks));

      // 2. Flush Transaction Actions
      const txQueue = await this.getPendingTransactionQueue();
      const remainingTxs: OfflineTransactionAction[] = [];

      for (const item of txQueue) {
        const retries = (item.retries || 0) + 1;
        item.retries = retries;
        try {
          const res = await fetch(`${baseUrl}/api/finance/transactions`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(item.payload),
          });
          if (res.ok) {
            txsSynced++;
          } else if (res.status >= 400 && res.status < 500 && res.status !== 429) {
            // Unrecoverable validation error; drop
            console.warn(`[OfflineStore] Dropping poison tx mutation ${item.id}: HTTP ${res.status}`);
          } else if (retries < 3) {
            remainingTxs.push(item);
          } else {
            console.warn(`[OfflineStore] Dropping tx mutation ${item.id} after ${retries} attempts: HTTP ${res.status}`);
          }
        } catch (e) {
          if (retries < 3) {
            remainingTxs.push(item);
          } else {
            console.warn(`[OfflineStore] Dropping tx mutation ${item.id} after ${retries} network failures:`, e);
          }
        }
      }

      await AsyncStorage.setItem("vesper_offline_transaction_queue", JSON.stringify(remainingTxs));
    } finally {
      await this.notifySync(false);
    }

    return { tasksSynced, txsSynced };
  }
}

export const offlineStore = new OfflineStore();
