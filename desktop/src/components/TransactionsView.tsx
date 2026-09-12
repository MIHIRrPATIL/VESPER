import React, { useState, useEffect, useCallback } from 'react';
import {
  Wallet,
  Building2,
  Banknote,
  ArrowUpRight,
  ArrowDownLeft,
  ArrowLeftRight,
  Clock,
  Plus,
  Edit2,
  Trash2,
  CheckCircle2,
  Search,
  RefreshCw,
  Users,
  X,
  Star,
  Layers
} from 'lucide-react';
import { motion, AnimatePresence } from 'motion/react';
import {
  FinanceAccount,
  FinanceTransaction,
  FinanceDebt,
  RecurringTransaction,
  FinanceOverview,
} from '../types/vesper';
import { cn } from '../lib/utils';

const API_BASE = 'http://localhost:8000/api/finance';

interface TransactionsViewProps {
  onSendUserMessage?: (text: string) => void;
}

export const TransactionsView: React.FC<TransactionsViewProps> = ({ onSendUserMessage: _onSendUserMessage }) => {
  const [activeTab, setActiveTab] = useState<'overview' | 'ledger' | 'debts' | 'recurring'>('overview');
  const [overview, setOverview] = useState<FinanceOverview | null>(null);
  const [accounts, setAccounts] = useState<FinanceAccount[]>([]);
  const [transactions, setTransactions] = useState<FinanceTransaction[]>([]);
  const [debts, setDebts] = useState<FinanceDebt[]>([]);
  const [recurringRules, setRecurringRules] = useState<RecurringTransaction[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);

  // Filters for ledger
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedAccountFilter, setSelectedAccountFilter] = useState<string>('all');
  const [selectedTypeFilter, setSelectedTypeFilter] = useState<string>('all');

  // Modal states
  const [isAccountModalOpen, setIsAccountModalOpen] = useState(false);
  const [editingAccount, setEditingAccount] = useState<FinanceAccount | null>(null);
  const [accountForm, setAccountForm] = useState({ name: '', balance: 0, type: 'bank', is_default: false });

  const [isTxnModalOpen, setIsTxnModalOpen] = useState(false);
  const [editingTxn, setEditingTxn] = useState<FinanceTransaction | null>(null);
  const [txnForm, setTxnForm] = useState({
    type: 'expense',
    amount: '',
    category: 'General',
    description: '',
    account_id: '',
    to_account_id: '',
    date: new Date().toISOString().split('T')[0],
  });

  const [isDebtModalOpen, setIsDebtModalOpen] = useState(false);
  const [editingDebt, setEditingDebt] = useState<FinanceDebt | null>(null);
  const [debtForm, setDebtForm] = useState({
    person: '',
    amount: '',
    direction: 'owed',
    description: '',
  });

  const [settleModalDebt, setSettleModalDebt] = useState<FinanceDebt | null>(null);
  const [settleLogTxn, setSettleLogTxn] = useState(true);

  const [isRecurringModalOpen, setIsRecurringModalOpen] = useState(false);
  const [editingRecurring, setEditingRecurring] = useState<RecurringTransaction | null>(null);
  const [recurringForm, setRecurringForm] = useState({
    name: '',
    amount: '',
    type: 'expense',
    frequency: 'monthly',
    category: 'Subscription',
    account_id: '',
  });

  // ── Data Fetching ─────────────────────────────────────────────────────────

  const loadData = useCallback(async () => {
    try {
      const [overviewRes, accRes, txnRes, debtRes, recRes] = await Promise.all([
        fetch(`${API_BASE}/overview`).then((r) => (r.ok ? r.json() : null)),
        fetch(`${API_BASE}/accounts`).then((r) => (r.ok ? r.json() : [])),
        fetch(`${API_BASE}/transactions?limit=100`).then((r) => (r.ok ? r.json() : [])),
        fetch(`${API_BASE}/debts?include_settled=true`).then((r) => (r.ok ? r.json() : { debts: [] })),
        fetch(`${API_BASE}/recurring`).then((r) => (r.ok ? r.json() : [])),
      ]);

      if (overviewRes) setOverview(overviewRes);
      if (accRes) setAccounts(accRes);
      if (txnRes) setTransactions(txnRes);
      if (debtRes?.debts) setDebts(debtRes.debts);
      if (recRes) setRecurringRules(recRes);
    } catch (err) {
      console.error('Failed fetching finance data:', err);
    } finally {
      setIsLoading(false);
      setIsRefreshing(false);
    }
  }, []);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const handleRefresh = async () => {
    setIsRefreshing(true);
    await loadData();
  };

  // ── Account Handlers ──────────────────────────────────────────────────────

  const handleOpenAddAccount = () => {
    setEditingAccount(null);
    setAccountForm({ name: '', balance: 0, type: 'bank', is_default: false });
    setIsAccountModalOpen(true);
  };

  const handleOpenEditAccount = (acc: FinanceAccount) => {
    setEditingAccount(acc);
    setAccountForm({ name: acc.name, balance: acc.balance, type: acc.type, is_default: acc.is_default });
    setIsAccountModalOpen(true);
  };

  const handleSaveAccount = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      if (editingAccount) {
        await fetch(`${API_BASE}/accounts/${editingAccount.id}`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            name: accountForm.name,
            balance: parseFloat(String(accountForm.balance)),
            type: accountForm.type,
            is_default: accountForm.is_default,
          }),
        });
      } else {
        await fetch(`${API_BASE}/accounts`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            name: accountForm.name,
            balance: parseFloat(String(accountForm.balance)),
            type: accountForm.type,
            is_default: accountForm.is_default,
            currency: 'INR',
          }),
        });
      }
      setIsAccountModalOpen(false);
      await loadData();
    } catch (err) {
      console.error('Error saving account:', err);
    }
  };

  const handleSetDefaultAccount = async (accountId: string) => {
    try {
      await fetch(`${API_BASE}/accounts/${accountId}/set-default`, { method: 'POST' });
      await loadData();
    } catch (err) {
      console.error('Error setting default account:', err);
    }
  };

  const handleDeleteAccount = async (accountId: string) => {
    if (!confirm('Are you sure you want to delete this account?')) return;
    try {
      await fetch(`${API_BASE}/accounts/${accountId}`, { method: 'DELETE' });
      await loadData();
    } catch (err) {
      console.error('Error deleting account:', err);
    }
  };

  // ── Transaction Handlers ──────────────────────────────────────────────────

  const handleOpenAddTxn = (defaultAccId?: string) => {
    setEditingTxn(null);
    const defId = defaultAccId || overview?.default_account_id || accounts[0]?.id || '';
    setTxnForm({
      type: 'expense',
      amount: '',
      category: 'General',
      description: '',
      account_id: defId,
      to_account_id: '',
      date: new Date().toISOString().split('T')[0],
    });
    setIsTxnModalOpen(true);
  };

  const handleOpenEditTxn = (txn: FinanceTransaction) => {
    setEditingTxn(txn);
    setTxnForm({
      type: txn.type,
      amount: String(txn.amount),
      category: txn.category || '',
      description: txn.description || '',
      account_id: txn.account_id || '',
      to_account_id: txn.to_account_id || '',
      date: txn.date || new Date().toISOString().split('T')[0],
    });
    setIsTxnModalOpen(true);
  };

  const handleSaveTxn = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      const payload: Record<string, any> = {
        type: txnForm.type,
        amount: parseFloat(txnForm.amount),
        category: txnForm.category,
        description: txnForm.description,
        account_id: txnForm.account_id || null,
        date: txnForm.date,
      };
      if (txnForm.type === 'transfer' && txnForm.to_account_id) {
        payload.to_account_id = txnForm.to_account_id;
      }

      if (editingTxn) {
        await fetch(`${API_BASE}/transactions/${editingTxn.id}`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload),
        });
      } else {
        await fetch(`${API_BASE}/transactions`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload),
        });
      }
      setIsTxnModalOpen(false);
      await loadData();
    } catch (err) {
      console.error('Error saving transaction:', err);
    }
  };

  const handleDeleteTxn = async (txnId: string) => {
    if (!confirm('Delete this transaction and reverse its balance impact?')) return;
    try {
      await fetch(`${API_BASE}/transactions/${txnId}`, { method: 'DELETE' });
      await loadData();
    } catch (err) {
      console.error('Error deleting transaction:', err);
    }
  };

  // ── Debt Handlers ─────────────────────────────────────────────────────────

  const handleOpenAddDebt = (defaultPerson?: string) => {
    setEditingDebt(null);
    setDebtForm({
      person: defaultPerson || '',
      amount: '',
      direction: 'owed',
      description: '',
    });
    setIsDebtModalOpen(true);
  };

  const handleOpenEditDebt = (d: FinanceDebt) => {
    setEditingDebt(d);
    setDebtForm({
      person: d.person,
      amount: String(d.amount),
      direction: d.direction,
      description: d.description || '',
    });
    setIsDebtModalOpen(true);
  };

  const handleSaveDebt = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      const payload = {
        person: debtForm.person,
        amount: parseFloat(debtForm.amount),
        direction: debtForm.direction,
        description: debtForm.description,
      };
      if (editingDebt) {
        await fetch(`${API_BASE}/debts/${editingDebt.id}`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload),
        });
      } else {
        await fetch(`${API_BASE}/debts`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload),
        });
      }
      setIsDebtModalOpen(false);
      await loadData();
    } catch (err) {
      console.error('Error saving debt:', err);
    }
  };

  const handleConfirmSettle = async () => {
    if (!settleModalDebt) return;
    try {
      const defaultAcc = overview?.default_account_id || accounts[0]?.id;
      const url = `${API_BASE}/debts/${settleModalDebt.id}/settle?log_transaction=${settleLogTxn}${
        defaultAcc ? `&account_id=${defaultAcc}` : ''
      }`;
      await fetch(url, { method: 'POST' });
      setSettleModalDebt(null);
      await loadData();
    } catch (err) {
      console.error('Error settling debt:', err);
    }
  };

  const handleDeleteDebt = async (debtId: string) => {
    if (!confirm('Are you sure you want to delete this debt record?')) return;
    try {
      await fetch(`${API_BASE}/debts/${debtId}`, { method: 'DELETE' });
      await loadData();
    } catch (err) {
      console.error('Error deleting debt:', err);
    }
  };

  // ── Recurring Handlers ────────────────────────────────────────────────────

  const handleOpenAddRecurring = () => {
    setEditingRecurring(null);
    setRecurringForm({
      name: '',
      amount: '',
      type: 'expense',
      frequency: 'monthly',
      category: 'Subscription',
      account_id: overview?.default_account_id || accounts[0]?.id || '',
    });
    setIsRecurringModalOpen(true);
  };

  const handleSaveRecurring = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      const payload = {
        name: recurringForm.name,
        amount: parseFloat(recurringForm.amount),
        type: recurringForm.type,
        frequency: recurringForm.frequency,
        category: recurringForm.category,
        account_id: recurringForm.account_id || null,
      };
      if (editingRecurring) {
        await fetch(`${API_BASE}/recurring/${editingRecurring.id}`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload),
        });
      } else {
        await fetch(`${API_BASE}/recurring`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload),
        });
      }
      setIsRecurringModalOpen(false);
      await loadData();
    } catch (err) {
      console.error('Error saving recurring rule:', err);
    }
  };

  const handleTriggerRecurringNow = async (ruleId: string) => {
    try {
      await fetch(`${API_BASE}/recurring/${ruleId}/execute`, { method: 'POST' });
      await loadData();
    } catch (err) {
      console.error('Error executing recurring rule:', err);
    }
  };

  const handleDeleteRecurring = async (ruleId: string) => {
    if (!confirm('Delete this recurring schedule?')) return;
    try {
      await fetch(`${API_BASE}/recurring/${ruleId}`, { method: 'DELETE' });
      await loadData();
    } catch (err) {
      console.error('Error deleting recurring schedule:', err);
    }
  };

  // ── Computed Helpers ──────────────────────────────────────────────────────

  const accountMap = new Map<string, FinanceAccount>();
  accounts.forEach((a) => accountMap.set(a.id, a));

  const filteredTransactions = transactions.filter((t) => {
    if (selectedAccountFilter !== 'all') {
      if (t.account_id !== selectedAccountFilter && t.to_account_id !== selectedAccountFilter) {
        return false;
      }
    }
    if (selectedTypeFilter !== 'all' && t.type !== selectedTypeFilter) {
      return false;
    }
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase();
      const desc = (t.description || '').toLowerCase();
      const cat = (t.category || '').toLowerCase();
      if (!desc.includes(q) && !cat.includes(q)) return false;
    }
    return true;
  });

  const getAccountIcon = (type: string) => {
    switch (type) {
      case 'cash':
        return <Banknote size={16} className="text-[#E8E3DA]" />;
      case 'wallet':
        return <Wallet size={16} className="text-[#E8E3DA]" />;
      default:
        return <Building2 size={16} className="text-[#E8E3DA]" />;
    }
  };

  if (isLoading) {
    return (
      <div className="w-full max-w-5xl flex items-center justify-center py-24">
        <div className="flex items-center gap-3 font-mono text-sm text-[#8E8A83]">
          <RefreshCw size={18} className="animate-spin text-[#E8E3DA]" />
          <span>Synchronizing Financial Ledger...</span>
        </div>
      </div>
    );
  }

  return (
    <div className="w-full max-w-5xl flex flex-col items-start gap-8 py-4">
      {/* ── Page Header & Quick Stats ──────────────────────────────────────── */}
      <div className="flex flex-col gap-1.5 text-left w-full border-b border-white/[0.08] pb-6">
        <div className="flex items-center justify-between w-full">
          <div className="flex items-center gap-2 font-mono text-[11px] uppercase tracking-widest text-[#8E8A83]">
            <Layers size={14} className="text-[#E8E3DA]" />
            PERSONAL FINANCIAL LEDGER {'&'} ACCOUNTS
          </div>
          <button
            type="button"
            onClick={handleRefresh}
            disabled={isRefreshing}
            className="flex items-center gap-1.5 px-3 py-1 rounded-full bg-white/[0.04] hover:bg-white/[0.08] border border-white/[0.08] text-xs font-mono text-[#E8E3DA] transition-colors cursor-pointer"
          >
            <RefreshCw size={12} className={cn(isRefreshing && 'animate-spin')} />
            Sync
          </button>
        </div>

        <div className="flex flex-col md:flex-row items-start md:items-baseline justify-between gap-4 mt-2">
          <div>
            <h1 className="font-serif text-3xl font-medium text-[#E8E3DA]">
              Financial Reserves {'&'} Ledger
            </h1>
            <p className="font-sans text-sm text-[#8E8A83] mt-1">
              Double-entry account balances, peer debt tracking, and automated recurring schedules.
            </p>
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => handleOpenAddTxn()}
              className="flex items-center gap-1.5 px-4 py-2 rounded-xl bg-white text-black font-mono text-xs font-semibold hover:bg-[#E8E3DA] transition-all shadow-lg cursor-pointer"
            >
              <Plus size={14} />
              Log Transaction
            </button>
            <button
              type="button"
              onClick={() => handleOpenAddDebt()}
              className="flex items-center gap-1.5 px-3.5 py-2 rounded-xl bg-white/[0.06] hover:bg-white/[0.12] border border-white/10 text-xs font-mono text-[#E8E3DA] transition-all cursor-pointer"
            >
              <Users size={14} />
              Add Debt / Tab
            </button>
          </div>
        </div>

        {/* ── Executive Metric Tiles ────────────────────────────────────────── */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 w-full mt-6">
          <div className="p-4 rounded-xl bg-[#141414]/90 border border-white/[0.08] flex flex-col gap-1 text-left">
            <span className="font-mono text-[10px] uppercase text-[#8E8A83] tracking-wider">
              Total Net Worth
            </span>
            <span className="font-mono text-2xl font-bold text-[#E8E3DA] tabular-nums">
              ₹{(overview?.total_net_worth || 0).toLocaleString('en-IN', { minimumFractionDigits: 2 })}
            </span>
            <span className="font-mono text-[10px] text-[#8E8A83]">All Accounts Combined</span>
          </div>

          <div className="p-4 rounded-xl bg-[#141414]/90 border border-white/[0.08] flex flex-col gap-1 text-left">
            <span className="font-mono text-[10px] uppercase text-[#8E8A83] tracking-wider">
              Bank Balance
            </span>
            <span className="font-mono text-2xl font-bold text-[#E8E3DA] tabular-nums">
              ₹{(overview?.bank_balance || 0).toLocaleString('en-IN', { minimumFractionDigits: 2 })}
            </span>
            <span className="font-mono text-[10px] text-[#8E8A83]">Union Bank + SBI + Saraswat</span>
          </div>

          <div className="p-4 rounded-xl bg-[#141414]/90 border border-white/[0.08] flex flex-col gap-1 text-left">
            <span className="font-mono text-[10px] uppercase text-[#8E8A83] tracking-wider">
              Cash in Hand
            </span>
            <span className="font-mono text-2xl font-bold text-[#E8E3DA] tabular-nums">
              ₹{(overview?.cash_balance || 0).toLocaleString('en-IN', { minimumFractionDigits: 2 })}
            </span>
            <span className="font-mono text-[10px] text-[#8E8A83]">Physical Reserve</span>
          </div>

          <div className="p-4 rounded-xl bg-[#141414]/90 border border-white/[0.08] flex flex-col gap-1 text-left">
            <span className="font-mono text-[10px] uppercase text-[#8E8A83] tracking-wider">
              Net Peer Tabs
            </span>
            <span
              className={cn(
                'font-mono text-2xl font-bold tabular-nums',
                (overview?.debts?.net_debt_position || 0) >= 0 ? 'text-[#E8E3DA]' : 'text-amber-400'
              )}
            >
              ₹{(overview?.debts?.net_debt_position || 0).toLocaleString('en-IN', {
                minimumFractionDigits: 2,
              })}
            </span>
            <span className="font-mono text-[10px] text-[#8E8A83]">
              +₹{(overview?.debts?.total_owed_to_user || 0).toLocaleString('en-IN')} receivable
            </span>
          </div>
        </div>
      </div>

      {/* ── Section Tabs ───────────────────────────────────────────────────── */}
      <div className="flex items-center gap-1.5 p-1 rounded-xl bg-white/[0.03] border border-white/[0.08] w-full max-w-xl">
        <button
          type="button"
          onClick={() => setActiveTab('overview')}
          className={cn(
            'flex-1 py-1.5 px-3 rounded-lg text-xs font-mono transition-all cursor-pointer text-center',
            activeTab === 'overview'
              ? 'bg-white text-black font-semibold shadow'
              : 'text-[#8E8A83] hover:text-[#E8E3DA]'
          )}
        >
          ACCOUNTS ({accounts.length})
        </button>
        <button
          type="button"
          onClick={() => setActiveTab('debts')}
          className={cn(
            'flex-1 py-1.5 px-3 rounded-lg text-xs font-mono transition-all cursor-pointer text-center',
            activeTab === 'debts'
              ? 'bg-white text-black font-semibold shadow'
              : 'text-[#8E8A83] hover:text-[#E8E3DA]'
          )}
        >
          PEER TABS {'&'} DEBTS ({debts.filter((d) => !d.settled).length})
        </button>
        <button
          type="button"
          onClick={() => setActiveTab('recurring')}
          className={cn(
            'flex-1 py-1.5 px-3 rounded-lg text-xs font-mono transition-all cursor-pointer text-center',
            activeTab === 'recurring'
              ? 'bg-white text-black font-semibold shadow'
              : 'text-[#8E8A83] hover:text-[#E8E3DA]'
          )}
        >
          AUTOMATED ({recurringRules.length})
        </button>
        <button
          type="button"
          onClick={() => setActiveTab('ledger')}
          className={cn(
            'flex-1 py-1.5 px-3 rounded-lg text-xs font-mono transition-all cursor-pointer text-center',
            activeTab === 'ledger'
              ? 'bg-white text-black font-semibold shadow'
              : 'text-[#8E8A83] hover:text-[#E8E3DA]'
          )}
        >
          LEDGER ({transactions.length})
        </button>
      </div>

      {/* ── TAB 1: ACCOUNTS & OVERVIEW ──────────────────────────────────────── */}
      {activeTab === 'overview' && (
        <div className="w-full flex flex-col gap-6 text-left">
          <div className="flex items-center justify-between w-full">
            <span className="font-mono text-xs text-[#8E8A83] uppercase tracking-wider">
              Active Accounts {'&'} Physical Reserves
            </span>
            <button
              type="button"
              onClick={handleOpenAddAccount}
              className="flex items-center gap-1 text-xs font-mono text-[#E8E3DA] hover:text-white px-2.5 py-1 rounded bg-white/[0.04] hover:bg-white/[0.08] border border-white/[0.08] cursor-pointer"
            >
              <Plus size={12} /> Add Account
            </button>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 w-full">
            {accounts.map((acc) => (
              <div
                key={acc.id}
                className={cn(
                  'p-6 rounded-2xl bg-[#141414]/90 border transition-all flex flex-col justify-between text-left',
                  acc.is_default
                    ? 'border-white/25 shadow-[0_0_24px_rgba(255,255,255,0.04)]'
                    : 'border-white/[0.08] hover:border-white/15'
                )}
              >
                <div className="flex items-start justify-between w-full mb-3">
                  <div className="flex items-center gap-3">
                    <div className="p-3 rounded-xl bg-black/50 border border-white/[0.08]">
                      {getAccountIcon(acc.type)}
                    </div>
                    <div className="flex flex-col">
                      <div className="flex items-center gap-2">
                        <span className="font-sans text-base font-semibold text-[#E8E3DA]">
                          {acc.name}
                        </span>
                        {acc.is_default && (
                          <span className="flex items-center gap-1 font-mono text-[9px] uppercase px-2 py-0.5 rounded-full bg-white/[0.08] text-white border border-white/20 font-bold tracking-wider">
                            <Star size={9} fill="white" />
                            DEFAULT
                          </span>
                        )}
                      </div>
                      <span className="font-mono text-[11px] text-[#8E8A83] uppercase tracking-wider mt-0.5">
                        {acc.type} account
                      </span>
                    </div>
                  </div>

                  <div className="flex items-center gap-1">
                    <button
                      type="button"
                      title="Edit Account"
                      onClick={() => handleOpenEditAccount(acc)}
                      className="p-1.5 rounded-lg text-[#8E8A83] hover:text-[#E8E3DA] hover:bg-white/[0.06] transition-colors cursor-pointer"
                    >
                      <Edit2 size={13} />
                    </button>
                    {!acc.is_default && (
                      <button
                        type="button"
                        title="Delete Account"
                        onClick={() => handleDeleteAccount(acc.id)}
                        className="p-1.5 rounded-lg text-[#8E8A83] hover:text-red-400 hover:bg-red-500/10 transition-colors cursor-pointer"
                      >
                        <Trash2 size={13} />
                      </button>
                    )}
                  </div>
                </div>

                <div className="my-2">
                  <span className="font-mono text-2xl font-bold text-[#E8E3DA] tabular-nums">
                    ₹{acc.balance.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                  </span>
                </div>

                <div className="flex items-center justify-between pt-4 border-t border-white/[0.05] mt-3">
                  {!acc.is_default ? (
                    <button
                      type="button"
                      onClick={() => handleSetDefaultAccount(acc.id)}
                      className="text-[11px] font-mono text-[#8E8A83] hover:text-[#E8E3DA] transition-colors cursor-pointer"
                    >
                      Set as default
                    </button>
                  ) : (
                    <span className="text-[11px] font-mono text-[#8E8A83]">
                      Primary credit/debit target
                    </span>
                  )}
                  <button
                    type="button"
                    onClick={() => handleOpenAddTxn(acc.id)}
                    className="flex items-center gap-1 font-mono text-[11px] text-[#E8E3DA] hover:text-white px-2.5 py-1 rounded bg-white/[0.06] hover:bg-white/[0.12] border border-white/10 transition-colors cursor-pointer"
                  >
                    <Plus size={11} /> Transaction
                  </button>
                </div>
              </div>
            ))}
          </div>

          {/* Spending Distribution by Category */}
          {overview?.spending_by_category && Object.keys(overview.spending_by_category).length > 0 && (
            <div className="w-full p-6 rounded-2xl bg-[#141414]/90 border border-white/[0.08] flex flex-col gap-4 mt-2">
              <span className="font-mono text-xs text-[#8E8A83] uppercase tracking-wider">
                Category Spending Distribution
              </span>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                {Object.entries(overview.spending_by_category).map(([cat, amt]) => (
                  <div
                    key={cat}
                    className="p-3 rounded-xl bg-black/40 border border-white/[0.04] flex flex-col gap-1 text-left"
                  >
                    <span className="font-mono text-[10px] text-[#8E8A83] uppercase">{cat}</span>
                    <span className="font-mono text-base font-semibold text-[#E8E3DA] tabular-nums">
                      ₹{amt.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* ── TAB 2: PEER TABS & DEBTS ("Owed By" & "Owed To") ────────────────── */}
      {activeTab === 'debts' && (
        <div className="w-full flex flex-col gap-6 text-left">
          <div className="flex items-center justify-between w-full">
            <span className="font-mono text-xs text-[#8E8A83] uppercase tracking-wider">
              Peer Debts {'&'} Running Tabs
            </span>
            <button
              type="button"
              onClick={() => handleOpenAddDebt()}
              className="flex items-center gap-1 text-xs font-mono text-[#E8E3DA] hover:text-white px-3 py-1.5 rounded-xl bg-white/[0.06] hover:bg-white/[0.12] border border-white/10 cursor-pointer"
            >
              <Plus size={12} /> New Debt / Tab
            </button>
          </div>

          {/* Summary Stats Header */}
          {overview?.debts?.people && overview.debts.people.length > 0 && (() => {
            const peopleCount = overview.debts.people.length;
            const totalItems = overview.debts.people.reduce((acc, p) => acc + (p.debts?.length || 0), 0);
            const totalNet = overview.debts.people.reduce((acc, p) => acc + (p.net_amount || 0), 0);
            const isOverallReceivable = totalNet >= 0;

            return (
              <div className="flex flex-wrap items-center gap-3 p-3.5 rounded-xl bg-white/[0.03] border border-white/[0.08] text-xs font-mono">
                <div className="flex items-center gap-2">
                  <span className="text-[#8E8A83]">PEOPLE:</span>
                  <span className="text-[#E8E3DA] font-semibold">{peopleCount}</span>
                </div>
                <span className="text-white/20">•</span>
                <div className="flex items-center gap-2">
                  <span className="text-[#8E8A83]">ACTIVE ITEMS:</span>
                  <span className="text-[#E8E3DA] font-semibold">{totalItems}</span>
                </div>
                <span className="text-white/20">•</span>
                <div className="flex items-center gap-2">
                  <span className="text-[#8E8A83]">NET BALANCE:</span>
                  <span className={cn('font-semibold tabular-nums', isOverallReceivable ? 'text-[#E8E3DA]' : 'text-amber-400')}>
                    {isOverallReceivable ? '+' : '-'}₹{Math.abs(totalNet).toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                  </span>
                </div>
              </div>
            );
          })()}

          {/* Grouped by person with scrollable viewport */}
          {overview?.debts?.people && overview.debts.people.length > 0 ? (
            <div className="relative w-full">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4 w-full max-h-[calc(100vh-320px)] overflow-y-auto pr-1.5 scrollbar-thin">
                {overview.debts.people.map((p) => {
                  const isNetReceivable = p.net_amount >= 0;
                  return (
                    <div
                      key={p.person}
                      className="p-6 rounded-2xl bg-[#141414]/90 border border-white/[0.08] hover:border-white/15 transition-all flex flex-col justify-between text-left"
                    >
                      <div>
                        <div className="flex items-start justify-between w-full mb-3">
                          <div className="flex items-center gap-3">
                            <div className="w-10 h-10 rounded-full bg-white/[0.06] border border-white/10 flex items-center justify-center font-mono font-bold text-sm text-[#E8E3DA]">
                              {p.person.slice(0, 2).toUpperCase()}
                            </div>
                            <div className="flex flex-col">
                              <span className="font-sans text-base font-semibold text-[#E8E3DA]">
                                {p.person}
                              </span>
                              <span className="font-mono text-[11px] text-[#8E8A83]">
                                {p.debts.length} active item{p.debts.length > 1 ? 's' : ''}
                              </span>
                            </div>
                          </div>

                          <div className="text-right">
                            <div
                              className={cn(
                                'font-mono text-xl font-bold tabular-nums',
                                isNetReceivable ? 'text-[#E8E3DA]' : 'text-amber-400'
                              )}
                            >
                              {isNetReceivable ? '+' : '-'}₹
                              {Math.abs(p.net_amount).toLocaleString('en-IN', {
                                minimumFractionDigits: 2,
                              })}
                            </div>
                            <span className="font-mono text-[10px] text-[#8E8A83] uppercase">
                              {isNetReceivable ? 'Owes You' : 'You Owe'}
                            </span>
                          </div>
                        </div>

                        {/* Itemized tabs with per-card scroll limit */}
                        <div className="flex flex-col gap-2 my-4 max-h-[200px] overflow-y-auto pr-1 scrollbar-thin">
                          {p.debts.map((d) => (
                            <div
                              key={d.id}
                              className="p-3 rounded-xl bg-black/40 border border-white/[0.04] flex items-center justify-between"
                            >
                              <div className="flex flex-col pr-2">
                                <span className="font-sans text-xs text-[#E8E3DA]">
                                  {d.description || 'Running Tab'}
                                </span>
                                <span className="font-mono text-[10px] text-[#8E8A83] mt-0.5">
                                  {d.created_at ? new Date(d.created_at).toLocaleDateString() : 'Active'}
                                </span>
                              </div>
                              <div className="flex items-center gap-2">
                                <span className="font-mono text-xs font-semibold text-[#E8E3DA] tabular-nums">
                                  ₹{d.amount.toLocaleString('en-IN')}
                                </span>
                                <button
                                  type="button"
                                  title="Settle"
                                  onClick={() => setSettleModalDebt(d)}
                                  className="p-1 rounded bg-white/[0.06] hover:bg-white/[0.12] text-[#E8E3DA] hover:text-white transition-colors cursor-pointer"
                                >
                                  <CheckCircle2 size={13} />
                                </button>
                                <button
                                  type="button"
                                  title="Edit"
                                  onClick={() => handleOpenEditDebt(d)}
                                  className="p-1 rounded hover:bg-white/[0.06] text-[#8E8A83] hover:text-[#E8E3DA] transition-colors cursor-pointer"
                                >
                                  <Edit2 size={13} />
                                </button>
                                <button
                                  type="button"
                                  title="Delete"
                                  onClick={() => handleDeleteDebt(d.id)}
                                  className="p-1 rounded hover:bg-red-500/10 text-[#8E8A83] hover:text-red-400 transition-colors cursor-pointer"
                                >
                                  <Trash2 size={13} />
                                </button>
                              </div>
                            </div>
                          ))}
                        </div>
                      </div>

                      <div className="pt-2 border-t border-white/[0.04] flex items-center justify-between">
                        <button
                          type="button"
                          onClick={() => handleOpenAddDebt(p.person)}
                          className="text-[11px] font-mono text-[#8E8A83] hover:text-[#E8E3DA] cursor-pointer"
                        >
                          + Add item for {p.person}
                        </button>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          ) : (
            <div className="w-full p-12 rounded-2xl bg-[#141414]/90 border border-white/[0.08] flex flex-col items-center justify-center gap-2 text-center">
              <Users size={28} className="text-[#8E8A83]" />
              <span className="font-sans text-sm text-[#E8E3DA] font-medium">No Active Debts</span>
              <span className="font-sans text-xs text-[#8E8A83]">
                All peer accounts are settled up.
              </span>
            </div>
          )}

          {/* Settled History */}
          {debts.filter((d) => d.settled).length > 0 && (
            <div className="w-full flex flex-col gap-3 mt-4">
              <span className="font-mono text-xs text-[#8E8A83] uppercase tracking-wider">
                Settled History
              </span>
              <div className="w-full rounded-2xl bg-[#141414]/70 border border-white/[0.06] overflow-hidden">
                {debts
                  .filter((d) => d.settled)
                  .map((d) => (
                    <div
                      key={d.id}
                      className="p-4 border-b border-white/[0.04] flex items-center justify-between opacity-60 hover:opacity-100 transition-opacity"
                    >
                      <div className="flex items-center gap-3">
                        <CheckCircle2 size={15} className="text-[#8E8A83]" />
                        <div className="flex flex-col">
                          <span className="font-sans text-xs text-[#E8E3DA]">
                            {d.person} • {d.description || 'Settled Tab'}
                          </span>
                          <span className="font-mono text-[10px] text-[#8E8A83]">
                            Settled on{' '}
                            {d.settled_at ? new Date(d.settled_at).toLocaleDateString() : 'N/A'}
                          </span>
                        </div>
                      </div>
                      <div className="flex items-center gap-3">
                        <span className="font-mono text-xs line-through text-[#8E8A83]">
                          ₹{d.amount.toLocaleString('en-IN')}
                        </span>
                        <button
                          type="button"
                          onClick={() => handleDeleteDebt(d.id)}
                          className="p-1 rounded text-[#8E8A83] hover:text-red-400 cursor-pointer"
                        >
                          <Trash2 size={13} />
                        </button>
                      </div>
                    </div>
                  ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* ── TAB 3: AUTOMATED & RECURRING TRANSACTIONS ──────────────────────── */}
      {activeTab === 'recurring' && (
        <div className="w-full flex flex-col gap-6 text-left">
          <div className="flex items-center justify-between w-full">
            <span className="font-mono text-xs text-[#8E8A83] uppercase tracking-wider">
              Automated {'&'} Periodic Schedules (SIPs, Subscriptions, Rent)
            </span>
            <button
              type="button"
              onClick={handleOpenAddRecurring}
              className="flex items-center gap-1 text-xs font-mono text-[#E8E3DA] hover:text-white px-3 py-1.5 rounded-xl bg-white/[0.06] hover:bg-white/[0.12] border border-white/10 cursor-pointer"
            >
              <Plus size={12} /> Add Recurring Rule
            </button>
          </div>

          {recurringRules.length > 0 ? (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 w-full">
              {recurringRules.map((rule) => {
                const srcAcc = rule.account_id ? accountMap.get(rule.account_id) : null;
                return (
                  <div
                    key={rule.id}
                    className="p-6 rounded-2xl bg-[#141414]/90 border border-white/[0.08] hover:border-white/15 transition-all flex flex-col justify-between text-left"
                  >
                    <div>
                      <div className="flex items-start justify-between w-full mb-3">
                        <div className="flex items-center gap-3">
                          <div className="p-3 rounded-xl bg-black/50 border border-white/[0.08]">
                            <Clock size={16} className="text-[#E8E3DA]" />
                          </div>
                          <div className="flex flex-col">
                            <span className="font-sans text-base font-semibold text-[#E8E3DA]">
                              {rule.name}
                            </span>
                            <span className="font-mono text-[11px] text-[#8E8A83] uppercase">
                              {rule.frequency} • {rule.category || 'Subscription'}
                            </span>
                          </div>
                        </div>
                        <div className="flex items-center gap-1">
                          <button
                            type="button"
                            title="Trigger Now"
                            onClick={() => handleTriggerRecurringNow(rule.id)}
                            className="p-1.5 rounded-lg text-[#8E8A83] hover:text-[#E8E3DA] hover:bg-white/[0.06] transition-colors cursor-pointer"
                          >
                            <RefreshCw size={13} />
                          </button>
                          <button
                            type="button"
                            title="Delete"
                            onClick={() => handleDeleteRecurring(rule.id)}
                            className="p-1.5 rounded-lg text-[#8E8A83] hover:text-red-400 hover:bg-red-500/10 transition-colors cursor-pointer"
                          >
                            <Trash2 size={13} />
                          </button>
                        </div>
                      </div>

                      <div className="my-2">
                        <span className="font-mono text-2xl font-bold text-[#E8E3DA] tabular-nums">
                          ₹{rule.amount.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                        </span>
                      </div>

                      <div className="flex flex-col gap-1 text-[11px] font-mono text-[#8E8A83] mt-3">
                        <span>Debits From: {srcAcc?.name || 'Union Bank'}</span>
                        <span>
                          Next Due: {rule.next_due_date ? new Date(rule.next_due_date).toLocaleDateString() : 'Auto'}
                        </span>
                      </div>
                    </div>

                    <div className="pt-3 border-t border-white/[0.04] mt-4 flex items-center justify-between">
                      <span className="font-mono text-[10px] uppercase text-[#8E8A83]">
                        {rule.auto_execute ? 'Auto-Execute Enabled' : 'Manual Trigger'}
                      </span>
                      <button
                        type="button"
                        onClick={() => handleTriggerRecurringNow(rule.id)}
                        className="text-[11px] font-mono text-[#E8E3DA] hover:underline cursor-pointer"
                      >
                        Execute Now
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>
          ) : (
            <div className="w-full p-12 rounded-2xl bg-[#141414]/90 border border-white/[0.08] flex flex-col items-center justify-center gap-2 text-center">
              <Clock size={28} className="text-[#8E8A83]" />
              <span className="font-sans text-sm text-[#E8E3DA] font-medium">
                No Recurring Schedules
              </span>
              <span className="font-sans text-xs text-[#8E8A83]">
                Set up automated recurring transactions for SIPs, rent, or monthly subscriptions.
              </span>
            </div>
          )}
        </div>
      )}

      {/* ── TAB 4: TRANSACTIONS LEDGER ───────────────────────────────────────── */}
      {activeTab === 'ledger' && (
        <div className="w-full flex flex-col gap-4 text-left">
          {/* Filter Bar */}
          <div className="flex flex-col md:flex-row items-stretch md:items-center justify-between gap-3 w-full p-3 rounded-xl bg-[#141414]/90 border border-white/[0.08]">
            <div className="flex items-center gap-2 flex-1 px-3 py-1.5 rounded-lg bg-black/40 border border-white/[0.06]">
              <Search size={14} className="text-[#8E8A83]" />
              <input
                type="text"
                placeholder="Search transactions or categories..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="bg-transparent text-xs font-sans text-[#E8E3DA] focus:outline-none w-full placeholder-[#8E8A83]"
              />
            </div>

            <div className="flex items-center gap-2">
              <select
                value={selectedAccountFilter}
                onChange={(e) => setSelectedAccountFilter(e.target.value)}
                className="bg-black/40 border border-white/[0.06] text-xs font-mono text-[#E8E3DA] rounded-lg px-2.5 py-1.5 focus:outline-none cursor-pointer"
              >
                <option value="all">All Accounts</option>
                {accounts.map((a) => (
                  <option key={a.id} value={a.id}>
                    {a.name}
                  </option>
                ))}
              </select>

              <select
                value={selectedTypeFilter}
                onChange={(e) => setSelectedTypeFilter(e.target.value)}
                className="bg-black/40 border border-white/[0.06] text-xs font-mono text-[#E8E3DA] rounded-lg px-2.5 py-1.5 focus:outline-none cursor-pointer"
              >
                <option value="all">All Types</option>
                <option value="expense">Expense</option>
                <option value="income">Income</option>
                <option value="transfer">Transfer</option>
              </select>
            </div>
          </div>

          {/* Ledger Rows */}
          <div className="w-full rounded-2xl bg-[#141414]/90 border border-white/[0.08] overflow-hidden">
            {filteredTransactions.length > 0 ? (
              filteredTransactions.map((txn) => {
                const acc = txn.account_id ? accountMap.get(txn.account_id) : null;
                const toAcc = txn.to_account_id ? accountMap.get(txn.to_account_id) : null;
                const isExpense = txn.type === 'expense';
                const isIncome = txn.type === 'income';

                return (
                  <div
                    key={txn.id}
                    className="p-4 border-b border-white/[0.04] flex items-center justify-between hover:bg-white/[0.02] transition-colors"
                  >
                    <div className="flex items-center gap-3">
                      <div className="p-2.5 rounded-xl bg-black/40 border border-white/[0.06]">
                        {isExpense ? (
                          <ArrowDownLeft size={16} className="text-amber-400" />
                        ) : isIncome ? (
                          <ArrowUpRight size={16} className="text-[#E8E3DA]" />
                        ) : (
                          <ArrowLeftRight size={16} className="text-[#8E8A83]" />
                        )}
                      </div>
                      <div className="flex flex-col text-left">
                        <span className="font-sans text-sm font-medium text-[#E8E3DA]">
                          {txn.description || 'Transaction'}
                        </span>
                        <div className="flex items-center gap-2 font-mono text-[10px] text-[#8E8A83] mt-0.5">
                          <span>{txn.date}</span>
                          <span>•</span>
                          <span className="px-1.5 py-0.2 rounded bg-white/[0.04]">
                            {txn.category || 'General'}
                          </span>
                          <span>•</span>
                          <span>
                            {txn.type === 'transfer'
                              ? `${acc?.name || 'Account'} → ${toAcc?.name || 'Account'}`
                              : acc?.name || 'Union Bank'}
                          </span>
                        </div>
                      </div>
                    </div>

                    <div className="flex items-center gap-4">
                      <span
                        className={cn(
                          'font-mono text-sm font-bold tabular-nums',
                          isExpense ? 'text-[#E8E3DA]' : isIncome ? 'text-[#E8E3DA]' : 'text-[#8E8A83]'
                        )}
                      >
                        {isExpense ? '-' : isIncome ? '+' : ''}₹
                        {txn.amount.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                      </span>
                      <div className="flex items-center gap-1">
                        <button
                          type="button"
                          onClick={() => handleOpenEditTxn(txn)}
                          className="p-1.5 rounded hover:bg-white/[0.06] text-[#8E8A83] hover:text-[#E8E3DA] transition-colors cursor-pointer"
                        >
                          <Edit2 size={13} />
                        </button>
                        <button
                          type="button"
                          onClick={() => handleDeleteTxn(txn.id)}
                          className="p-1.5 rounded hover:bg-red-500/10 text-[#8E8A83] hover:text-red-400 transition-colors cursor-pointer"
                        >
                          <Trash2 size={13} />
                        </button>
                      </div>
                    </div>
                  </div>
                );
              })
            ) : (
              <div className="p-12 flex flex-col items-center justify-center gap-2 text-center text-[#8E8A83]">
                <Search size={24} />
                <span className="font-sans text-sm">No transactions match your search criteria.</span>
              </div>
            )}
          </div>
        </div>
      )}

      {/* ── MODALS & DRAWERS ───────────────────────────────────────────────── */}

      {/* 1. Account Modal */}
      <AnimatePresence>
        {isAccountModalOpen && (
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm">
            <motion.div
              initial={{ scale: 0.95, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              exit={{ scale: 0.95, opacity: 0 }}
              className="w-full max-w-md p-6 rounded-2xl bg-[#141414] border border-white/15 shadow-2xl flex flex-col gap-4 text-left"
            >
              <div className="flex items-center justify-between pb-3 border-b border-white/[0.08]">
                <h3 className="font-serif text-lg font-medium text-[#E8E3DA]">
                  {editingAccount ? 'Edit Account' : 'Add Financial Account'}
                </h3>
                <button
                  type="button"
                  onClick={() => setIsAccountModalOpen(false)}
                  className="p-1 text-[#8E8A83] hover:text-white"
                >
                  <X size={16} />
                </button>
              </div>

              <form onSubmit={handleSaveAccount} className="flex flex-col gap-3">
                <div className="flex flex-col gap-1">
                  <label className="font-mono text-[11px] text-[#8E8A83] uppercase">Account Name</label>
                  <input
                    type="text"
                    required
                    value={accountForm.name}
                    onChange={(e) => setAccountForm({ ...accountForm, name: e.target.value })}
                    placeholder="e.g. Union Bank, SBI, Cash"
                    className="p-2.5 rounded-xl bg-black/50 border border-white/10 text-xs font-sans text-[#E8E3DA] focus:outline-none focus:border-white/30"
                  />
                </div>

                <div className="flex flex-col gap-1">
                  <label className="font-mono text-[11px] text-[#8E8A83] uppercase">Current Balance (₹)</label>
                  <input
                    type="number"
                    step="any"
                    required
                    value={accountForm.balance}
                    onChange={(e) => setAccountForm({ ...accountForm, balance: parseFloat(e.target.value) || 0 })}
                    className="p-2.5 rounded-xl bg-black/50 border border-white/10 text-xs font-mono text-[#E8E3DA] focus:outline-none focus:border-white/30"
                  />
                </div>

                <div className="flex flex-col gap-1">
                  <label className="font-mono text-[11px] text-[#8E8A83] uppercase">Account Type</label>
                  <select
                    value={accountForm.type}
                    onChange={(e) => setAccountForm({ ...accountForm, type: e.target.value })}
                    className="p-2.5 rounded-xl bg-black/50 border border-white/10 text-xs font-mono text-[#E8E3DA] focus:outline-none focus:border-white/30"
                  >
                    <option value="bank">Bank</option>
                    <option value="cash">Cash</option>
                    <option value="wallet">Wallet</option>
                    <option value="credit">Credit Card</option>
                  </select>
                </div>

                <div className="flex items-center gap-2 mt-2">
                  <input
                    type="checkbox"
                    id="is_default_check"
                    checked={accountForm.is_default}
                    onChange={(e) => setAccountForm({ ...accountForm, is_default: e.target.checked })}
                    className="rounded border-white/20 bg-black cursor-pointer"
                  />
                  <label htmlFor="is_default_check" className="font-sans text-xs text-[#E8E3DA] cursor-pointer">
                    Set as default primary account for transactions
                  </label>
                </div>

                <div className="flex items-center justify-end gap-2 pt-4 mt-2 border-t border-white/[0.08]">
                  <button
                    type="button"
                    onClick={() => setIsAccountModalOpen(false)}
                    className="px-4 py-2 rounded-xl text-xs font-mono text-[#8E8A83] hover:text-white"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    className="px-4 py-2 rounded-xl bg-white text-black font-mono text-xs font-semibold hover:bg-[#E8E3DA]"
                  >
                    Save Account
                  </button>
                </div>
              </form>
            </motion.div>
          </div>
        )}
      </AnimatePresence>

      {/* 2. Transaction Modal */}
      <AnimatePresence>
        {isTxnModalOpen && (
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm">
            <motion.div
              initial={{ scale: 0.95, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              exit={{ scale: 0.95, opacity: 0 }}
              className="w-full max-w-md p-6 rounded-2xl bg-[#141414] border border-white/15 shadow-2xl flex flex-col gap-4 text-left"
            >
              <div className="flex items-center justify-between pb-3 border-b border-white/[0.08]">
                <h3 className="font-serif text-lg font-medium text-[#E8E3DA]">
                  {editingTxn ? 'Edit Transaction' : 'Log Transaction'}
                </h3>
                <button
                  type="button"
                  onClick={() => setIsTxnModalOpen(false)}
                  className="p-1 text-[#8E8A83] hover:text-white"
                >
                  <X size={16} />
                </button>
              </div>

              <form onSubmit={handleSaveTxn} className="flex flex-col gap-3">
                <div className="flex items-center gap-2 p-1 rounded-lg bg-black/40 border border-white/10">
                  {['expense', 'income', 'transfer'].map((t) => (
                    <button
                      key={t}
                      type="button"
                      onClick={() => setTxnForm({ ...txnForm, type: t })}
                      className={cn(
                        'flex-1 py-1 text-xs font-mono capitalize rounded-md transition-all cursor-pointer',
                        txnForm.type === t ? 'bg-white text-black font-bold' : 'text-[#8E8A83]'
                      )}
                    >
                      {t}
                    </button>
                  ))}
                </div>

                <div className="flex flex-col gap-1">
                  <label className="font-mono text-[11px] text-[#8E8A83] uppercase">Amount (₹)</label>
                  <input
                    type="number"
                    step="any"
                    required
                    placeholder="0.00"
                    value={txnForm.amount}
                    onChange={(e) => setTxnForm({ ...txnForm, amount: e.target.value })}
                    className="p-2.5 rounded-xl bg-black/50 border border-white/10 text-base font-mono font-bold text-[#E8E3DA] focus:outline-none focus:border-white/30"
                  />
                </div>

                <div className="flex flex-col gap-1">
                  <label className="font-mono text-[11px] text-[#8E8A83] uppercase">
                    {txnForm.type === 'transfer' ? 'From Account' : 'Account'}
                  </label>
                  <select
                    value={txnForm.account_id}
                    onChange={(e) => setTxnForm({ ...txnForm, account_id: e.target.value })}
                    className="p-2.5 rounded-xl bg-black/50 border border-white/10 text-xs font-mono text-[#E8E3DA] focus:outline-none"
                  >
                    {accounts.map((a) => (
                      <option key={a.id} value={a.id}>
                        {a.name} ({a.type}) • ₹{a.balance.toLocaleString('en-IN')}
                      </option>
                    ))}
                  </select>
                </div>

                {txnForm.type === 'transfer' && (
                  <div className="flex flex-col gap-1">
                    <label className="font-mono text-[11px] text-[#8E8A83] uppercase">To Account</label>
                    <select
                      value={txnForm.to_account_id}
                      onChange={(e) => setTxnForm({ ...txnForm, to_account_id: e.target.value })}
                      className="p-2.5 rounded-xl bg-black/50 border border-white/10 text-xs font-mono text-[#E8E3DA] focus:outline-none"
                    >
                      <option value="">Select Destination Account</option>
                      {accounts
                        .filter((a) => a.id !== txnForm.account_id)
                        .map((a) => (
                          <option key={a.id} value={a.id}>
                            {a.name} ({a.type}) • ₹{a.balance.toLocaleString('en-IN')}
                          </option>
                        ))}
                    </select>
                  </div>
                )}

                <div className="grid grid-cols-2 gap-2">
                  <div className="flex flex-col gap-1">
                    <label className="font-mono text-[11px] text-[#8E8A83] uppercase">Category</label>
                    <input
                      type="text"
                      value={txnForm.category}
                      onChange={(e) => setTxnForm({ ...txnForm, category: e.target.value })}
                      placeholder="e.g. Food, Tech, Fuel"
                      className="p-2.5 rounded-xl bg-black/50 border border-white/10 text-xs font-sans text-[#E8E3DA] focus:outline-none"
                    />
                  </div>
                  <div className="flex flex-col gap-1">
                    <label className="font-mono text-[11px] text-[#8E8A83] uppercase">Date</label>
                    <input
                      type="date"
                      value={txnForm.date}
                      onChange={(e) => setTxnForm({ ...txnForm, date: e.target.value })}
                      className="p-2.5 rounded-xl bg-black/50 border border-white/10 text-xs font-mono text-[#E8E3DA] focus:outline-none"
                    />
                  </div>
                </div>

                <div className="flex flex-col gap-1">
                  <label className="font-mono text-[11px] text-[#8E8A83] uppercase">Description</label>
                  <input
                    type="text"
                    value={txnForm.description}
                    onChange={(e) => setTxnForm({ ...txnForm, description: e.target.value })}
                    placeholder="Short description or note"
                    className="p-2.5 rounded-xl bg-black/50 border border-white/10 text-xs font-sans text-[#E8E3DA] focus:outline-none"
                  />
                </div>

                <div className="flex items-center justify-end gap-2 pt-4 mt-2 border-t border-white/[0.08]">
                  <button
                    type="button"
                    onClick={() => setIsTxnModalOpen(false)}
                    className="px-4 py-2 rounded-xl text-xs font-mono text-[#8E8A83] hover:text-white"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    className="px-4 py-2 rounded-xl bg-white text-black font-mono text-xs font-semibold hover:bg-[#E8E3DA]"
                  >
                    Save Transaction
                  </button>
                </div>
              </form>
            </motion.div>
          </div>
        )}
      </AnimatePresence>

      {/* 3. Debt Modal */}
      <AnimatePresence>
        {isDebtModalOpen && (
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm">
            <motion.div
              initial={{ scale: 0.95, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              exit={{ scale: 0.95, opacity: 0 }}
              className="w-full max-w-md p-6 rounded-2xl bg-[#141414] border border-white/15 shadow-2xl flex flex-col gap-4 text-left"
            >
              <div className="flex items-center justify-between pb-3 border-b border-white/[0.08]">
                <h3 className="font-serif text-lg font-medium text-[#E8E3DA]">
                  {editingDebt ? 'Edit Debt / Tab' : 'Record Peer Debt / Tab'}
                </h3>
                <button
                  type="button"
                  onClick={() => setIsDebtModalOpen(false)}
                  className="p-1 text-[#8E8A83] hover:text-white"
                >
                  <X size={16} />
                </button>
              </div>

              <form onSubmit={handleSaveDebt} className="flex flex-col gap-3">
                <div className="flex flex-col gap-1">
                  <label className="font-mono text-[11px] text-[#8E8A83] uppercase">Person Name</label>
                  <input
                    type="text"
                    required
                    value={debtForm.person}
                    onChange={(e) => setDebtForm({ ...debtForm, person: e.target.value })}
                    placeholder="e.g. Karan, Aman, Rohit"
                    className="p-2.5 rounded-xl bg-black/50 border border-white/10 text-xs font-sans text-[#E8E3DA] focus:outline-none"
                  />
                </div>

                <div className="flex flex-col gap-1">
                  <label className="font-mono text-[11px] text-[#8E8A83] uppercase">Amount (₹)</label>
                  <input
                    type="number"
                    step="any"
                    required
                    placeholder="0.00"
                    value={debtForm.amount}
                    onChange={(e) => setDebtForm({ ...debtForm, amount: e.target.value })}
                    className="p-2.5 rounded-xl bg-black/50 border border-white/10 text-base font-mono font-bold text-[#E8E3DA] focus:outline-none"
                  />
                </div>

                <div className="flex flex-col gap-1">
                  <label className="font-mono text-[11px] text-[#8E8A83] uppercase">Direction</label>
                  <div className="grid grid-cols-2 gap-2">
                    <button
                      type="button"
                      onClick={() => setDebtForm({ ...debtForm, direction: 'owed' })}
                      className={cn(
                        'py-2 px-3 rounded-xl border text-xs font-mono text-center cursor-pointer transition-all',
                        debtForm.direction === 'owed'
                          ? 'bg-white text-black font-bold border-white'
                          : 'border-white/10 text-[#8E8A83] hover:text-white'
                      )}
                    >
                      They Owe Me
                    </button>
                    <button
                      type="button"
                      onClick={() => setDebtForm({ ...debtForm, direction: 'owe' })}
                      className={cn(
                        'py-2 px-3 rounded-xl border text-xs font-mono text-center cursor-pointer transition-all',
                        debtForm.direction === 'owe'
                          ? 'bg-white text-black font-bold border-white'
                          : 'border-white/10 text-[#8E8A83] hover:text-white'
                      )}
                    >
                      I Owe Them
                    </button>
                  </div>
                </div>

                <div className="flex flex-col gap-1">
                  <label className="font-mono text-[11px] text-[#8E8A83] uppercase">Reason / Note</label>
                  <input
                    type="text"
                    value={debtForm.description}
                    onChange={(e) => setDebtForm({ ...debtForm, description: e.target.value })}
                    placeholder="e.g. Dinner, Movie tickets, Uber split"
                    className="p-2.5 rounded-xl bg-black/50 border border-white/10 text-xs font-sans text-[#E8E3DA] focus:outline-none"
                  />
                </div>

                <div className="flex items-center justify-end gap-2 pt-4 mt-2 border-t border-white/[0.08]">
                  <button
                    type="button"
                    onClick={() => setIsDebtModalOpen(false)}
                    className="px-4 py-2 rounded-xl text-xs font-mono text-[#8E8A83] hover:text-white"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    className="px-4 py-2 rounded-xl bg-white text-black font-mono text-xs font-semibold hover:bg-[#E8E3DA]"
                  >
                    Save Debt
                  </button>
                </div>
              </form>
            </motion.div>
          </div>
        )}
      </AnimatePresence>

      {/* 4. Settle Debt Modal */}
      <AnimatePresence>
        {settleModalDebt && (
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm">
            <motion.div
              initial={{ scale: 0.95, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              exit={{ scale: 0.95, opacity: 0 }}
              className="w-full max-w-sm p-6 rounded-2xl bg-[#141414] border border-white/15 shadow-2xl flex flex-col gap-4 text-left"
            >
              <div className="flex items-center justify-between pb-3 border-b border-white/[0.08]">
                <h3 className="font-serif text-lg font-medium text-[#E8E3DA]">Settle Debt</h3>
                <button
                  type="button"
                  onClick={() => setSettleModalDebt(null)}
                  className="p-1 text-[#8E8A83] hover:text-white"
                >
                  <X size={16} />
                </button>
              </div>

              <div className="flex flex-col gap-2">
                <span className="font-sans text-sm text-[#E8E3DA]">
                  Mark tab with <strong className="text-white">{settleModalDebt.person}</strong> of{' '}
                  <strong className="text-white">₹{settleModalDebt.amount.toLocaleString('en-IN')}</strong> as
                  settled?
                </span>
                <p className="font-sans text-xs text-[#8E8A83] mt-1">
                  Reason: {settleModalDebt.description || 'Running Tab'}
                </p>

                <div className="flex items-start gap-2.5 p-3 rounded-xl bg-black/40 border border-white/[0.06] mt-2">
                  <input
                    type="checkbox"
                    id="settle_log_txn"
                    checked={settleLogTxn}
                    onChange={(e) => setSettleLogTxn(e.target.checked)}
                    className="mt-0.5 rounded border-white/20 bg-black cursor-pointer"
                  />
                  <label htmlFor="settle_log_txn" className="font-sans text-xs text-[#E8E3DA] cursor-pointer">
                    Log cashflow transaction to <strong className="text-white">{overview?.default_account_name || 'Union Bank'}</strong>
                  </label>
                </div>
              </div>

              <div className="flex items-center justify-end gap-2 pt-4 border-t border-white/[0.08]">
                <button
                  type="button"
                  onClick={() => setSettleModalDebt(null)}
                  className="px-4 py-2 rounded-xl text-xs font-mono text-[#8E8A83] hover:text-white"
                >
                  Cancel
                </button>
                <button
                  type="button"
                  onClick={handleConfirmSettle}
                  className="px-4 py-2 rounded-xl bg-white text-black font-mono text-xs font-semibold hover:bg-[#E8E3DA]"
                >
                  Confirm Settlement
                </button>
              </div>
            </motion.div>
          </div>
        )}
      </AnimatePresence>

      {/* 5. Recurring Modal */}
      <AnimatePresence>
        {isRecurringModalOpen && (
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm">
            <motion.div
              initial={{ scale: 0.95, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              exit={{ scale: 0.95, opacity: 0 }}
              className="w-full max-w-md p-6 rounded-2xl bg-[#141414] border border-white/15 shadow-2xl flex flex-col gap-4 text-left"
            >
              <div className="flex items-center justify-between pb-3 border-b border-white/[0.08]">
                <h3 className="font-serif text-lg font-medium text-[#E8E3DA]">
                  {editingRecurring ? 'Edit Schedule' : 'New Recurring Schedule'}
                </h3>
                <button
                  type="button"
                  onClick={() => setIsRecurringModalOpen(false)}
                  className="p-1 text-[#8E8A83] hover:text-white"
                >
                  <X size={16} />
                </button>
              </div>

              <form onSubmit={handleSaveRecurring} className="flex flex-col gap-3">
                <div className="flex flex-col gap-1">
                  <label className="font-mono text-[11px] text-[#8E8A83] uppercase">Schedule Name</label>
                  <input
                    type="text"
                    required
                    value={recurringForm.name}
                    onChange={(e) => setRecurringForm({ ...recurringForm, name: e.target.value })}
                    placeholder="e.g. Netflix, Rent, Mutual Fund SIP"
                    className="p-2.5 rounded-xl bg-black/50 border border-white/10 text-xs font-sans text-[#E8E3DA] focus:outline-none"
                  />
                </div>

                <div className="grid grid-cols-2 gap-2">
                  <div className="flex flex-col gap-1">
                    <label className="font-mono text-[11px] text-[#8E8A83] uppercase">Amount (₹)</label>
                    <input
                      type="number"
                      step="any"
                      required
                      placeholder="0.00"
                      value={recurringForm.amount}
                      onChange={(e) => setRecurringForm({ ...recurringForm, amount: e.target.value })}
                      className="p-2.5 rounded-xl bg-black/50 border border-white/10 text-xs font-mono font-bold text-[#E8E3DA] focus:outline-none"
                    />
                  </div>
                  <div className="flex flex-col gap-1">
                    <label className="font-mono text-[11px] text-[#8E8A83] uppercase">Frequency</label>
                    <select
                      value={recurringForm.frequency}
                      onChange={(e) => setRecurringForm({ ...recurringForm, frequency: e.target.value })}
                      className="p-2.5 rounded-xl bg-black/50 border border-white/10 text-xs font-mono text-[#E8E3DA] focus:outline-none"
                    >
                      <option value="monthly">Monthly</option>
                      <option value="weekly">Weekly</option>
                      <option value="biweekly">Bi-weekly</option>
                      <option value="quarterly">Quarterly</option>
                      <option value="yearly">Yearly</option>
                      <option value="daily">Daily</option>
                    </select>
                  </div>
                </div>

                <div className="flex flex-col gap-1">
                  <label className="font-mono text-[11px] text-[#8E8A83] uppercase">Debit From Account</label>
                  <select
                    value={recurringForm.account_id}
                    onChange={(e) => setRecurringForm({ ...recurringForm, account_id: e.target.value })}
                    className="p-2.5 rounded-xl bg-black/50 border border-white/10 text-xs font-mono text-[#E8E3DA] focus:outline-none"
                  >
                    {accounts.map((a) => (
                      <option key={a.id} value={a.id}>
                        {a.name} ({a.type}) • ₹{a.balance.toLocaleString('en-IN')}
                      </option>
                    ))}
                  </select>
                </div>

                <div className="flex flex-col gap-1">
                  <label className="font-mono text-[11px] text-[#8E8A83] uppercase">Category</label>
                  <input
                    type="text"
                    value={recurringForm.category}
                    onChange={(e) => setRecurringForm({ ...recurringForm, category: e.target.value })}
                    placeholder="e.g. Subscription, Rent, Investment"
                    className="p-2.5 rounded-xl bg-black/50 border border-white/10 text-xs font-sans text-[#E8E3DA] focus:outline-none"
                  />
                </div>

                <div className="flex items-center justify-end gap-2 pt-4 mt-2 border-t border-white/[0.08]">
                  <button
                    type="button"
                    onClick={() => setIsRecurringModalOpen(false)}
                    className="px-4 py-2 rounded-xl text-xs font-mono text-[#8E8A83] hover:text-white"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    className="px-4 py-2 rounded-xl bg-white text-black font-mono text-xs font-semibold hover:bg-[#E8E3DA]"
                  >
                    Save Schedule
                  </button>
                </div>
              </form>
            </motion.div>
          </div>
        )}
      </AnimatePresence>
    </div>
  );
};
