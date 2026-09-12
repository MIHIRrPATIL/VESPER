import React, { useState, useEffect, useCallback } from "react";
import {
  StyleSheet,
  Text,
  View,
  TouchableOpacity,
  ScrollView,
  TextInput,
  Modal,
  ActivityIndicator,
} from "react-native";
import { theme } from "../styles/theme";
import { gatewayClient } from "../services/gateway";
import { offlineStore } from "../services/offline-store";
import { workstationStore } from "../services/workstation-store";
import {
  FinanceOverview,
  FinanceAccount,
  FinanceTransaction,
  FinanceDebt,
  RecurringTransaction,
} from "../types/vesper";

type LedgerSubTab = "overview" | "transactions" | "debts" | "recurring";
type DebtFilter = "all" | "receivable" | "payable";

export const LedgerView: React.FC = () => {
  const [activeTab, setActiveTab] = useState<LedgerSubTab>("overview");
  const [loading, setLoading] = useState(true);
  const [isOffline, setIsOffline] = useState(false);
  const [pendingCount, setPendingCount] = useState(0);

  const [overview, setOverview] = useState<FinanceOverview | null>(null);
  const [accounts, setAccounts] = useState<FinanceAccount[]>([]);
  const [transactions, setTransactions] = useState<FinanceTransaction[]>([]);
  const [debts, setDebts] = useState<FinanceDebt[]>([]);
  const [recurring, setRecurring] = useState<RecurringTransaction[]>([]);

  // Peer Tabs Filter on dedicated tab
  const [debtFilter, setDebtFilter] = useState<DebtFilter>("all");

  // Directive Command Input
  const [directiveInput, setDirectiveInput] = useState("");

  // Modals
  const [isTxnModalOpen, setIsTxnModalOpen] = useState(false);
  const [txnType, setTxnType] = useState<"expense" | "income" | "transfer">("expense");
  const [txnAmount, setTxnAmount] = useState("");
  const [txnCategory, setTxnCategory] = useState("General");
  const [txnDesc, setTxnDesc] = useState("");

  const [isDebtModalOpen, setIsDebtModalOpen] = useState(false);
  const [debtPerson, setDebtPerson] = useState("");
  const [debtAmount, setDebtAmount] = useState("");
  const [debtDirection, setDebtDirection] = useState<"owe" | "owed">("owed");
  const [debtDesc, setDebtDesc] = useState("");

  const loadData = useCallback(async () => {
    setLoading(true);

    // 1. Immediately hydrate from offline cache
    const [cOv, cAccs, cTxs, cDebts, pCount] = await Promise.all([
      offlineStore.getCachedFinanceOverview(),
      offlineStore.getCachedAccounts(),
      offlineStore.getCachedTransactions(),
      offlineStore.getCachedDebts(),
      offlineStore.getPendingCount(),
    ]);

    if (cOv) setOverview(cOv);
    if (cAccs && cAccs.length > 0) setAccounts(cAccs);
    if (cTxs && cTxs.length > 0) setTransactions(cTxs);
    if (cDebts) setDebts(cDebts);
    setPendingCount(pCount);

    // 2. Fetch live data
    try {
      const baseUrl = gatewayClient.getHttpUrl();
      const [ovRes, accRes, txnRes, debtRes, recRes] = await Promise.all([
        fetch(`${baseUrl}/api/finance/overview`).then((r) => (r.ok ? r.json() : null)),
        fetch(`${baseUrl}/api/finance/accounts`).then((r) => (r.ok ? r.json() : [])),
        fetch(`${baseUrl}/api/finance/transactions?limit=50`).then((r) => (r.ok ? r.json() : [])),
        fetch(`${baseUrl}/api/finance/debts?include_settled=true`).then((r) => (r.ok ? r.json() : { debts: [] })),
        fetch(`${baseUrl}/api/finance/recurring`).then((r) => (r.ok ? r.json() : [])),
      ]);

      let hasLive = false;
      if (ovRes) {
        setOverview(ovRes);
        offlineStore.saveCachedFinanceOverview(ovRes);
        hasLive = true;
      }
      if (accRes && Array.isArray(accRes) && accRes.length > 0) {
        setAccounts(accRes);
        offlineStore.saveCachedAccounts(accRes);
        hasLive = true;
      }
      if (txnRes && Array.isArray(txnRes) && txnRes.length > 0) {
        setTransactions(txnRes);
        offlineStore.saveCachedTransactions(txnRes);
        hasLive = true;
      }
      if (debtRes?.debts) {
        setDebts(debtRes.debts);
        offlineStore.saveCachedDebts(debtRes.debts);
        hasLive = true;
      }
      if (recRes && Array.isArray(recRes)) setRecurring(recRes);

      setIsOffline(!hasLive);
    } catch (e) {
      console.warn("[LedgerView] Load error, using offline cache:", e);
      setIsOffline(true);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData();

    const unsub = offlineStore.subscribeSync((_syncing, count) => {
      setPendingCount(count);
    });

    return () => unsub();
  }, [loadData]);

  const formatCurrency = (val: number | undefined | null) => {
    const num = Number(val || 0);
    return `₹${num.toLocaleString("en-IN", { maximumFractionDigits: 0 })}`;
  };

  const handleDirectiveSubmit = () => {
    if (!directiveInput.trim()) return;
    const input = directiveInput.trim();
    setDirectiveInput("");

    // Quick parse if user enters numbers or expenses directly
    const match = input.match(/^([+-]?\d+)\s*(.*)$/);
    if (match) {
      const amt = Math.abs(parseFloat(match[1]));
      const desc = match[2] || "Direct Expense";
      setTxnAmount(String(amt));
      setTxnDesc(desc);
      setTxnType(match[1].startsWith("+") ? "income" : "expense");
      setIsTxnModalOpen(true);
    } else {
      // Dispatch as natural language command to Alfred
      workstationStore.sendUserMessage(input);
    }
  };

  const handleCreateTxn = async () => {
    const amt = parseFloat(txnAmount);
    if (isNaN(amt) || amt <= 0) return;

    const payload = {
      type: txnType.toUpperCase() as "EXPENSE" | "INCOME" | "TRANSFER",
      amount: amt,
      category: txnCategory,
      description: txnDesc,
      date: new Date().toISOString().split("T")[0],
    };

    const optimisticTx: FinanceTransaction = {
      id: `local_tx_${Date.now()}`,
      account_id: accounts[0]?.id || "primary",
      account_name: accounts[0]?.name || "Vault",
      type: txnType,
      amount: amt,
      category: txnCategory,
      description: txnDesc,
      date: new Date().toISOString().split("T")[0],
      created_at: new Date().toISOString(),
      tags: ["pending_sync"],
    };

    const updated = [optimisticTx, ...transactions];
    setTransactions(updated);
    await offlineStore.saveCachedTransactions(updated);

    try {
      const baseUrl = gatewayClient.getHttpUrl();
      const res = await fetch(`${baseUrl}/api/finance/transactions`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (res.ok) {
        const created = await res.json();
        optimisticTx.id = created.id || optimisticTx.id;
        await offlineStore.saveCachedTransactions(updated);
      } else {
        throw new Error(`HTTP ${res.status}`);
      }
    } catch {
      await offlineStore.enqueueOfflineTransaction(payload);
      setIsOffline(true);
    } finally {
      setIsTxnModalOpen(false);
      setTxnAmount("");
      setTxnDesc("");
    }
  };

  const handleCreateDebt = async () => {
    const amt = parseFloat(debtAmount);
    if (!debtPerson.trim() || isNaN(amt) || amt <= 0) return;

    try {
      const baseUrl = gatewayClient.getHttpUrl();
      await fetch(`${baseUrl}/api/finance/debts`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          person: debtPerson.trim(),
          amount: amt,
          direction: debtDirection,
          description: debtDesc,
        }),
      });
      setIsDebtModalOpen(false);
      setDebtPerson("");
      setDebtAmount("");
      setDebtDesc("");
      loadData();
    } catch (e) {
      console.warn("Error creating debt:", e);
    }
  };

  const handleSettleDebt = async (debtId: string) => {
    try {
      const baseUrl = gatewayClient.getHttpUrl();
      await fetch(`${baseUrl}/api/finance/debts/${debtId}/settle`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ log_transaction: true }),
      });
      loadData();
    } catch (e) {
      console.warn("Error settling debt:", e);
    }
  };

  const netWorth = overview?.total_net_worth ?? 245000;
  const monthlyBurn = overview?.monthly_burn ?? 42500;
  const monthlySavings = overview?.monthly_net_savings ?? 85000;
  const savingsRate =
    monthlyBurn + monthlySavings > 0
      ? Math.round((monthlySavings / (monthlyBurn + monthlySavings)) * 100)
      : 66;

  const displayAccounts =
    accounts.length > 0
      ? accounts
      : [
          { id: "1", name: "Saraswat Bank", balance: 145000, type: "bank" as const, is_default: true, currency: "INR" },
          { id: "2", name: "SBI Operating", balance: 65000, type: "bank" as const, is_default: false, currency: "INR" },
          { id: "3", name: "HDFC Reserve", balance: 25000, type: "bank" as const, is_default: false, currency: "INR" },
          { id: "4", name: "Petty Cash", balance: 10000, type: "cash" as const, is_default: false, currency: "INR" },
        ];

  // Pure real user debts - no mock peers
  const displayDebts: FinanceDebt[] = debts;

  // Computations for Debts
  const debtsOwedToUser = displayDebts
    .filter((d) => !d.settled && d.direction === "owed")
    .reduce((acc, d) => acc + (d.amount || 0), 0);
  const debtsUserOwes = displayDebts
    .filter((d) => !d.settled && d.direction === "owe")
    .reduce((acc, d) => acc + (d.amount || 0), 0);
  const netPeerBalance = debtsOwedToUser - debtsUserOwes;

  const filteredDebts = displayDebts.filter((d) => {
    if (debtFilter === "receivable") return d.direction === "owed";
    if (debtFilter === "payable") return d.direction === "owe";
    return true;
  });

  return (
    <ScrollView
      style={styles.container}
      contentContainerStyle={styles.contentContainer}
      showsVerticalScrollIndicator={false}
    >
      {/* ── Section 1: Aerospace Header & Capital Telemetry Deck ── */}
      <View style={styles.headerOuterBezel}>
        <View style={styles.headerInnerCore}>
          <View style={styles.greetingBlock}>
            <View style={styles.systemTagRow}>
              <View style={[styles.pulseDot, isOffline && styles.pulseDotOffline]} />
              <Text style={styles.systemTagText}>
                {isOffline ? "OFFLINE CACHE ARMED" : "CAPITAL VAULT NOMINAL"}
              </Text>
              <Text style={styles.systemSeparator}>•</Text>
              <Text style={styles.systemNodeText}>
                {pendingCount > 0 ? `SYNC (${pendingCount})` : "VAULT-01"}
              </Text>
            </View>
            <Text style={styles.greetingTitle}>Financial Flight Deck</Text>
            <Text style={styles.greetingSub}>
              Double-entry balance sheet &amp; liquid reserve telemetry.
            </Text>
          </View>

          {/* Precision Aerospace Metric Capsule */}
          <View style={styles.chronoCapsule}>
            <View style={styles.chronoTopRow}>
              <Text style={styles.chronoDigits} numberOfLines={1} adjustsFontSizeToFit>
                {formatCurrency(netWorth)}
              </Text>
            </View>
            <Text style={styles.chronoDate}>
              {savingsRate}% SAVINGS • {isOffline ? "CACHED" : "LIVE"}
            </Text>
          </View>
        </View>
      </View>

      {/* ── Section 2: Directives Capsule Bar ── */}
      <View style={styles.directiveOuterBezel}>
        <View style={styles.directiveInnerCore}>
          <View style={styles.directiveInputRow}>
            <Text style={styles.directivePrefix}>ledger &gt;</Text>
            <TextInput
              style={styles.directiveInput}
              value={directiveInput}
              onChangeText={setDirectiveInput}
              placeholder="Log expense or prompt Alfred..."
              placeholderTextColor="#8E887E"
              onSubmitEditing={handleDirectiveSubmit}
              returnKeyType="send"
              autoCapitalize="none"
              autoCorrect={false}
            />
            <TouchableOpacity
              style={[
                styles.directiveRunBtn,
                !directiveInput.trim() && styles.directiveRunBtnDisabled,
              ]}
              onPress={handleDirectiveSubmit}
              disabled={!directiveInput.trim()}
              activeOpacity={0.8}
            >
              <Text
                style={[
                  styles.directiveRunText,
                  !directiveInput.trim() && styles.directiveRunTextDisabled,
                ]}
              >
                POST
              </Text>
            </TouchableOpacity>
          </View>

          {/* Action Chips */}
          <View style={styles.chipsRow}>
            <TouchableOpacity
              style={styles.chipPill}
              onPress={() => {
                setTxnType("expense");
                setIsTxnModalOpen(true);
              }}
              activeOpacity={0.7}
            >
              <Text style={styles.chipPillText}>+ EXPENSE</Text>
            </TouchableOpacity>

            <TouchableOpacity
              style={styles.chipPill}
              onPress={() => {
                setTxnType("income");
                setIsTxnModalOpen(true);
              }}
              activeOpacity={0.7}
            >
              <Text style={styles.chipPillText}>+ INCOME</Text>
            </TouchableOpacity>

            <TouchableOpacity
              style={styles.chipPill}
              onPress={() => setIsDebtModalOpen(true)}
              activeOpacity={0.7}
            >
              <Text style={styles.chipPillText}>+ PEER TAB</Text>
            </TouchableOpacity>

            <TouchableOpacity
              style={styles.chipPill}
              onPress={loadData}
              activeOpacity={0.7}
            >
              <Text style={styles.chipPillText}>REFRESH</Text>
            </TouchableOpacity>
          </View>
        </View>
      </View>

      {/* ── Section 3: Segmented Aerospace Subtabs Switcher ── */}
      <View style={styles.subTabsOuter}>
        <View style={styles.subTabsInner}>
          {(["overview", "transactions", "debts", "recurring"] as LedgerSubTab[]).map(
            (tab) => {
              const active = activeTab === tab;
              const labelMap: Record<LedgerSubTab, string> = {
                overview: "OVERVIEW",
                transactions: "TRANSACTIONS",
                debts: "PEER TABS",
                recurring: "RECURRING",
              };
              return (
                <TouchableOpacity
                  key={tab}
                  style={[styles.subTabPill, active && styles.subTabPillActive]}
                  onPress={() => setActiveTab(tab)}
                  activeOpacity={0.8}
                >
                  <Text
                    style={[
                      styles.subTabPillText,
                      active && styles.subTabPillTextActive,
                    ]}
                  >
                    {labelMap[tab]}
                  </Text>
                </TouchableOpacity>
              );
            }
          )}
        </View>
      </View>

      {/* ── Section 4: Subtab Content ── */}

      {/* 4A: OVERVIEW TAB (MAIN DASHBOARD) */}
      {activeTab === "overview" && (
        <View style={styles.tabContentCol}>
          {/* Hero Bento Card: Net Liquid Capital & Reserves */}
          <View style={styles.heroOuterBezel}>
            <View style={styles.heroInnerCore}>
              <View style={styles.bentoHeaderRow}>
                <View style={styles.bentoTagWrap}>
                  <View style={styles.bentoAmberDot} />
                  <Text style={styles.bentoEyebrow}>CAPITAL VAULT STATUS</Text>
                </View>
                <View style={styles.bentoLinkCapsule}>
                  <Text style={styles.bentoLinkText}>RESERVES NOMINAL</Text>
                </View>
              </View>

              {/* Net Capital Value */}
              <View style={styles.netCapitalHeroRow}>
                <Text style={styles.netCapitalLabel}>NET LIQUID CAPITAL</Text>
                <Text style={styles.netCapitalValue} numberOfLines={1} adjustsFontSizeToFit>
                  {formatCurrency(netWorth)}
                </Text>
              </View>

              {/* Telemetry Burn & Savings Gauges */}
              <View style={styles.gaugesContainerRow}>
                {/* Burn Gauge */}
                <View style={styles.gaugeBox}>
                  <View style={styles.gaugeHeader}>
                    <Text style={styles.gaugeLabel} numberOfLines={1}>MONTHLY BURN</Text>
                    <Text style={[styles.gaugeAmount, { color: theme.colors.coral }]} numberOfLines={1}>
                      {formatCurrency(monthlyBurn)}
                    </Text>
                  </View>
                  <View style={styles.gaugeTrack}>
                    <View style={[styles.gaugeFill, styles.gaugeFillCoral]} />
                  </View>
                </View>

                {/* Savings Gauge */}
                <View style={styles.gaugeBox}>
                  <View style={styles.gaugeHeader}>
                    <Text style={styles.gaugeLabel} numberOfLines={1}>NET SAVINGS</Text>
                    <Text style={[styles.gaugeAmount, { color: theme.colors.emerald }]} numberOfLines={1}>
                      {formatCurrency(monthlySavings)}
                    </Text>
                  </View>
                  <View style={styles.gaugeTrack}>
                    <View style={[styles.gaugeFill, styles.gaugeFillEmerald]} />
                  </View>
                </View>
              </View>
            </View>
          </View>

          {/* ── OPERATING VAULTS: Dedicated Full-Width Bento Grid ── */}
          <View style={styles.heroOuterBezel}>
            <View style={styles.heroInnerCore}>
              <View style={styles.bentoHeaderRow}>
                <View style={styles.bentoTagWrap}>
                  <View style={styles.bentoAmberDot} />
                  <Text style={styles.bentoEyebrow}>OPERATING VAULTS &amp; RESERVES</Text>
                </View>
                <View style={styles.bentoLinkCapsule}>
                  <Text style={styles.bentoLinkText}>{displayAccounts.length} VAULTS</Text>
                </View>
              </View>

              {/* 2x2 Grid of Operating Accounts without any text overflow */}
              <View style={styles.vaultsGrid}>
                {displayAccounts.map((acc, idx) => (
                  <View key={idx} style={styles.vaultPod}>
                    <View style={styles.vaultPodTop}>
                      <View style={styles.vaultNameWrap}>
                        <View style={styles.accountActiveDot} />
                        <Text
                          style={styles.vaultNameText}
                          numberOfLines={1}
                          ellipsizeMode="tail"
                        >
                          {acc.name}
                        </Text>
                      </View>
                      {acc.is_default && (
                        <View style={styles.defaultBadgeBox}>
                          <Text style={styles.defaultBadgeText}>PRIMARY</Text>
                        </View>
                      )}
                    </View>

                    <Text
                      style={styles.vaultBalanceText}
                      numberOfLines={1}
                      adjustsFontSizeToFit
                    >
                      {formatCurrency(acc.balance)}
                    </Text>

                    <View style={styles.vaultSubRow}>
                      <Text style={styles.vaultTypeText}>
                        {acc.type === "cash" ? "PETTY CASH" : "LIQUID VAULT"}
                      </Text>
                      <Text style={styles.vaultCurrencyTag}>{acc.currency || "INR"}</Text>
                    </View>
                  </View>
                ))}
              </View>
            </View>
          </View>

          {/* ── PEER TABS ON MAIN PAGE: Dedicated Full-Width Flight Deck Card ── */}
          <View style={styles.heroOuterBezel}>
            <View style={styles.heroInnerCore}>
              <View style={styles.bentoHeaderRow}>
                <View style={styles.bentoTagWrap}>
                  <View
                    style={[
                      styles.peerAmberDot,
                      displayDebts.length === 0 && { backgroundColor: theme.colors.emerald },
                    ]}
                  />
                  <Text style={styles.bentoEyebrow}>PEER TABS &amp; SHARED LEDGER</Text>
                </View>
                <TouchableOpacity
                  onPress={() => setActiveTab("debts")}
                  activeOpacity={0.7}
                  style={styles.bentoLinkCapsule}
                >
                  <Text style={styles.bentoLinkText}>
                    MANAGE ({displayDebts.length}) &gt;
                  </Text>
                </TouchableOpacity>
              </View>

              {/* 3-Capsule Telemetry Summary Row */}
              <View style={styles.peerTelemetryRow}>
                <View style={styles.peerTelemetryPill}>
                  <Text style={styles.peerTelemetryLabel}>RECEIVABLES</Text>
                  <Text
                    style={[
                      styles.peerTelemetryValue,
                      { color: theme.colors.emerald },
                    ]}
                    numberOfLines={1}
                    adjustsFontSizeToFit
                  >
                    +{formatCurrency(debtsOwedToUser)}
                  </Text>
                  <Text style={styles.peerTelemetrySub}>Owed to you</Text>
                </View>

                <View style={styles.peerTelemetryPill}>
                  <Text style={styles.peerTelemetryLabel}>PAYABLES</Text>
                  <Text
                    style={[styles.peerTelemetryValue, { color: theme.colors.coral }]}
                    numberOfLines={1}
                    adjustsFontSizeToFit
                  >
                    -{formatCurrency(debtsUserOwes)}
                  </Text>
                  <Text style={styles.peerTelemetrySub}>You owe</Text>
                </View>

                <View style={styles.peerTelemetryPillHighlight}>
                  <Text style={styles.peerTelemetryLabel}>NET POSITION</Text>
                  <Text
                    style={[
                      styles.peerTelemetryValue,
                      {
                        color:
                          netPeerBalance >= 0
                            ? theme.colors.emerald
                            : theme.colors.coral,
                      },
                    ]}
                    numberOfLines={1}
                    adjustsFontSizeToFit
                  >
                    {netPeerBalance >= 0 ? "+" : "-"}
                    {formatCurrency(Math.abs(netPeerBalance))}
                  </Text>
                  <Text style={styles.peerTelemetrySub}>
                    {displayDebts.length === 0
                      ? "All Balanced"
                      : netPeerBalance >= 0
                      ? "Net Positive"
                      : "Net Deficit"}
                  </Text>
                </View>
              </View>

              {/* Active Peer Tabs Roster or Clean Empty State */}
              <View style={styles.peerRosterSection}>
                {displayDebts.length === 0 ? (
                  <View style={styles.peerEmptyPod}>
                    <Text style={styles.peerEmptyTitle}>
                      You owe no one, and no one owes you.
                    </Text>
                    <Text style={styles.peerEmptySubtitle}>
                      All peer accounts balanced. Zero outstanding shared tabs.
                    </Text>
                  </View>
                ) : (
                  displayDebts.slice(0, 3).map((d) => {
                    const isOwed = d.direction === "owed";
                    return (
                      <View key={d.id} style={styles.peerCardRow}>
                        <View style={styles.peerAvatarCircle}>
                          <Text style={styles.peerAvatarInitial}>
                            {d.person?.charAt(0).toUpperCase() || "P"}
                          </Text>
                        </View>

                        <View style={styles.peerCardMainCol}>
                          <View style={styles.peerCardTopRow}>
                            <Text
                              style={styles.peerNameText}
                              numberOfLines={1}
                              ellipsizeMode="tail"
                            >
                              {d.person}
                            </Text>
                            <View
                              style={[
                                styles.debtPillBadge,
                                isOwed
                                  ? styles.debtPillReceivable
                                  : styles.debtPillPayable,
                              ]}
                            >
                              <Text
                                style={[
                                  styles.debtPillText,
                                  isOwed
                                    ? { color: theme.colors.emerald }
                                    : { color: theme.colors.coral },
                                ]}
                              >
                                {isOwed ? "+ RECEIVABLE" : "- PAYABLE"}
                              </Text>
                            </View>
                          </View>
                          <Text
                            style={styles.peerDescText}
                            numberOfLines={1}
                            ellipsizeMode="tail"
                          >
                            {d.description || "Shared Tab Split"}
                          </Text>
                        </View>

                        <View style={styles.peerAmountCol}>
                          <Text
                            style={[
                              styles.peerCardAmount,
                              isOwed
                                ? { color: theme.colors.emerald }
                                : { color: theme.colors.coral },
                            ]}
                            numberOfLines={1}
                          >
                            {isOwed ? "+" : "-"}
                            {formatCurrency(d.amount)}
                          </Text>
                          {!d.settled && (
                            <TouchableOpacity
                              style={styles.peerSettleBtn}
                              onPress={() => handleSettleDebt(d.id)}
                              activeOpacity={0.8}
                            >
                              <Text style={styles.peerSettleBtnText}>SETTLE</Text>
                            </TouchableOpacity>
                          )}
                        </View>
                      </View>
                    );
                  })
                )}

                <TouchableOpacity
                  style={styles.addPeerTabBtn}
                  onPress={() => setIsDebtModalOpen(true)}
                  activeOpacity={0.8}
                >
                  <Text style={styles.addPeerTabText}>+ RECORD NEW PEER TAB</Text>
                </TouchableOpacity>
              </View>
            </View>
          </View>

          {/* Recent Transaction Stream Preview */}
          <View style={styles.heroOuterBezel}>
            <View style={styles.heroInnerCore}>
              <View style={styles.bentoHeaderRow}>
                <View style={styles.bentoTagWrap}>
                  <View style={styles.bentoAmberDot} />
                  <Text style={styles.bentoEyebrow}>LATEST TRANSACTION STREAM</Text>
                </View>
                <TouchableOpacity
                  onPress={() => setActiveTab("transactions")}
                  activeOpacity={0.7}
                >
                  <Text style={styles.cardArrow}>FULL STREAM &gt;</Text>
                </TouchableOpacity>
              </View>

              {transactions.slice(0, 4).map((tx) => (
                <View key={tx.id} style={styles.txnPodOuter}>
                  <View style={styles.txnPodInner}>
                    <View style={styles.txnTypeIconWrap}>
                      <Text
                        style={[
                          styles.txnTypeGlyph,
                          {
                            color:
                              tx.type === "income"
                                ? theme.colors.emerald
                                : theme.colors.coral,
                          },
                        ]}
                      >
                        {tx.type === "income" ? "+" : "-"}
                      </Text>
                    </View>

                    <View style={styles.txnBodyCol}>
                      <Text style={styles.txnDescText} numberOfLines={1}>
                        {tx.description || tx.category || "Transaction"}
                      </Text>
                      <View style={styles.txnMetaRow}>
                        <Text style={styles.txnMetaDate}>{tx.date}</Text>
                        <Text style={styles.txnMetaDot}>•</Text>
                        <Text style={styles.txnMetaCategory}>
                          {tx.category || "General"}
                        </Text>
                        {tx.tags?.includes("pending_sync") && (
                          <View style={styles.offlineSyncTag}>
                            <Text style={styles.offlineSyncTagText}>QUEUE</Text>
                          </View>
                        )}
                      </View>
                    </View>

                    <Text
                      style={[
                        styles.txnAmountText,
                        {
                          color:
                            tx.type === "income"
                              ? theme.colors.emerald
                              : theme.colors.boneWhite,
                        },
                      ]}
                      numberOfLines={1}
                    >
                      {tx.type === "income" ? "+" : "-"}
                      {formatCurrency(tx.amount)}
                    </Text>
                  </View>
                </View>
              ))}
            </View>
          </View>
        </View>
      )}

      {/* 4B: TRANSACTIONS TAB */}
      {activeTab === "transactions" && (
        <View style={styles.tabContentCol}>
          {/* Peer Tabs Quick Link Strip on Transactions Page */}
          <TouchableOpacity
            style={styles.peerQuickStripOuter}
            onPress={() => setActiveTab("debts")}
            activeOpacity={0.8}
          >
            <View style={styles.peerQuickStripInner}>
              <View style={styles.peerQuickLeft}>
                <View
                  style={[
                    styles.peerAmberDot,
                    displayDebts.length === 0 && { backgroundColor: theme.colors.emerald },
                  ]}
                />
                <Text style={styles.peerQuickText}>
                  {displayDebts.length === 0
                    ? "PEER TABS: ALL BALANCED // YOU OWE NO ONE"
                    : `PEER TABS: ${netPeerBalance >= 0 ? "+" : "-"}${formatCurrency(Math.abs(netPeerBalance))} NET (${displayDebts.length} TABS)`}
                </Text>
              </View>
              <Text style={styles.peerQuickLinkText}>
                {displayDebts.length === 0 ? "+ NEW TAB >" : "VIEW ALL >"}
              </Text>
            </View>
          </TouchableOpacity>

          <View style={styles.filterStripOuter}>
            <View style={styles.filterStripInner}>
              <Text style={styles.filterMonoText}>
                {transactions.length} JOURNAL ENTRIES RECORDED
              </Text>
              <TouchableOpacity
                style={styles.quickAddTxnBtn}
                onPress={() => {
                  setTxnType("expense");
                  setIsTxnModalOpen(true);
                }}
                activeOpacity={0.8}
              >
                <Text style={styles.quickAddTxnText}>+ RECORD ENTRY</Text>
              </TouchableOpacity>
            </View>
          </View>

          {transactions.length === 0 ? (
            <View style={styles.emptyOuterBezel}>
              <View style={styles.emptyInnerCore}>
                <Text style={styles.emptyTitle}>No Transactions Recorded</Text>
                <Text style={styles.emptySubtitle}>
                  Execute directives or click + RECORD ENTRY to log cashflow.
                </Text>
              </View>
            </View>
          ) : (
            transactions.map((tx) => (
              <View key={tx.id} style={styles.txnPodOuter}>
                <View style={styles.txnPodInner}>
                  <View style={styles.txnTypeIconWrap}>
                    <Text
                      style={[
                        styles.txnTypeGlyph,
                        {
                          color:
                            tx.type === "income"
                              ? theme.colors.emerald
                              : theme.colors.coral,
                        },
                      ]}
                    >
                      {tx.type === "income" ? "+" : "-"}
                    </Text>
                  </View>

                  <View style={styles.txnBodyCol}>
                    <Text style={styles.txnDescText} numberOfLines={1}>
                      {tx.description || tx.category || "Transaction"}
                    </Text>
                    <View style={styles.txnMetaRow}>
                      <Text style={styles.txnMetaDate}>{tx.date}</Text>
                      <Text style={styles.txnMetaDot}>•</Text>
                      <Text style={styles.txnMetaCategory}>
                        {tx.category || "General"}
                      </Text>
                      {tx.account_name && (
                        <>
                          <Text style={styles.txnMetaDot}>•</Text>
                          <Text style={styles.txnMetaCategory}>{tx.account_name}</Text>
                        </>
                      )}
                      {tx.tags?.includes("pending_sync") && (
                        <View style={styles.offlineSyncTag}>
                          <Text style={styles.offlineSyncTagText}>PENDING SYNC</Text>
                        </View>
                      )}
                    </View>
                  </View>

                  <Text
                    style={[
                      styles.txnAmountText,
                      {
                        color:
                          tx.type === "income"
                            ? theme.colors.emerald
                            : theme.colors.boneWhite,
                      },
                    ]}
                    numberOfLines={1}
                  >
                    {tx.type === "income" ? "+" : "-"}
                    {formatCurrency(tx.amount)}
                  </Text>
                </View>
              </View>
            ))
          )}
        </View>
      )}

      {/* 4C: DEDICATED PEER TABS SUBTAB */}
      {activeTab === "debts" && (
        <View style={styles.tabContentCol}>
          {/* Peer Ledger Hero Deck */}
          <View style={styles.heroOuterBezel}>
            <View style={styles.heroInnerCore}>
              <View style={styles.bentoHeaderRow}>
                <View style={styles.bentoTagWrap}>
                  <View
                    style={[
                      styles.peerAmberDot,
                      displayDebts.length === 0 && { backgroundColor: theme.colors.emerald },
                    ]}
                  />
                  <Text style={styles.bentoEyebrow}>PEER LEDGER DECK</Text>
                </View>
                <TouchableOpacity
                  style={styles.quickAddTxnBtn}
                  onPress={() => setIsDebtModalOpen(true)}
                  activeOpacity={0.8}
                >
                  <Text style={styles.quickAddTxnText}>+ NEW PEER TAB</Text>
                </TouchableOpacity>
              </View>

              {/* Split Balance Summary */}
              <View style={styles.peerTelemetryRow}>
                <View style={styles.peerTelemetryPill}>
                  <Text style={styles.peerTelemetryLabel}>TOTAL TO RECEIVE</Text>
                  <Text
                    style={[
                      styles.peerTelemetryValue,
                      { color: theme.colors.emerald },
                    ]}
                    numberOfLines={1}
                    adjustsFontSizeToFit
                  >
                    +{formatCurrency(debtsOwedToUser)}
                  </Text>
                  <Text style={styles.peerTelemetrySub}>Receivable from peers</Text>
                </View>

                <View style={styles.peerTelemetryPill}>
                  <Text style={styles.peerTelemetryLabel}>TOTAL TO SETTLE</Text>
                  <Text
                    style={[styles.peerTelemetryValue, { color: theme.colors.coral }]}
                    numberOfLines={1}
                    adjustsFontSizeToFit
                  >
                    -{formatCurrency(debtsUserOwes)}
                  </Text>
                  <Text style={styles.peerTelemetrySub}>Payable to peers</Text>
                </View>

                <View style={styles.peerTelemetryPillHighlight}>
                  <Text style={styles.peerTelemetryLabel}>NET OUTSTANDING</Text>
                  <Text
                    style={[
                      styles.peerTelemetryValue,
                      {
                        color:
                          netPeerBalance >= 0
                            ? theme.colors.emerald
                            : theme.colors.coral,
                      },
                    ]}
                    numberOfLines={1}
                    adjustsFontSizeToFit
                  >
                    {netPeerBalance >= 0 ? "+" : "-"}
                    {formatCurrency(Math.abs(netPeerBalance))}
                  </Text>
                  <Text style={styles.peerTelemetrySub}>
                    {displayDebts.length === 0 ? "All Balanced" : "Net liquidation"}
                  </Text>
                </View>
              </View>
            </View>
          </View>

          {/* Filter Pills for Debts */}
          {displayDebts.length > 0 && (
            <View style={styles.subTabsOuter}>
              <View style={styles.subTabsInner}>
                {(
                  [
                    { key: "all", label: `ALL (${displayDebts.length})` },
                    {
                      key: "receivable",
                      label: `RECEIVABLE (${displayDebts.filter((d) => d.direction === "owed").length})`,
                    },
                    {
                      key: "payable",
                      label: `PAYABLE (${displayDebts.filter((d) => d.direction === "owe").length})`,
                    },
                  ] as const
                ).map((f) => {
                  const active = debtFilter === f.key;
                  return (
                    <TouchableOpacity
                      key={f.key}
                      style={[styles.subTabPill, active && styles.subTabPillActive]}
                      onPress={() => setDebtFilter(f.key)}
                      activeOpacity={0.8}
                    >
                      <Text
                        style={[
                          styles.subTabPillText,
                          active && styles.subTabPillTextActive,
                        ]}
                        numberOfLines={1}
                      >
                        {f.label}
                      </Text>
                    </TouchableOpacity>
                  );
                })}
              </View>
            </View>
          )}

          {/* Peer Debts List or Authentic Empty State */}
          {filteredDebts.length === 0 ? (
            <View style={styles.emptyOuterBezel}>
              <View style={styles.emptyInnerCore}>
                <Text style={styles.emptyTitle}>
                  {displayDebts.length === 0
                    ? "You owe no one, and no one owes you"
                    : "Zero Balances in this View"}
                </Text>
                <Text style={styles.emptySubtitle}>
                  {displayDebts.length === 0
                    ? "All peer accounts balanced. Zero outstanding split expense obligations."
                    : "No outstanding peer tab records matching the current filter."}
                </Text>
                <TouchableOpacity
                  style={[styles.addPeerTabBtn, { width: "100%", marginTop: 8 }]}
                  onPress={() => setIsDebtModalOpen(true)}
                  activeOpacity={0.8}
                >
                  <Text style={styles.addPeerTabText}>+ RECORD NEW PEER TAB</Text>
                </TouchableOpacity>
              </View>
            </View>
          ) : (
            filteredDebts.map((debt) => {
              const isOwed = debt.direction === "owed";
              return (
                <View key={debt.id} style={styles.peerCardRowBezel}>
                  <View style={styles.peerCardRowInner}>
                    {/* Upper Row: Avatar + Name + Pill + Amount */}
                    <View style={styles.peerDeckTopRow}>
                      <View style={styles.peerDeckIdentity}>
                        <View style={styles.peerAvatarCircle}>
                          <Text style={styles.peerAvatarInitial}>
                            {debt.person?.charAt(0).toUpperCase() || "P"}
                          </Text>
                        </View>
                        <View style={styles.peerDeckNames}>
                          <Text
                            style={styles.peerNameText}
                            numberOfLines={1}
                            ellipsizeMode="tail"
                          >
                            {debt.person}
                          </Text>
                          <View
                            style={[
                              styles.debtPillBadge,
                              isOwed
                                ? styles.debtPillReceivable
                                : styles.debtPillPayable,
                            ]}
                          >
                            <Text
                              style={[
                                styles.debtPillText,
                                isOwed
                                  ? { color: theme.colors.emerald }
                                  : { color: theme.colors.coral },
                              ]}
                            >
                              {isOwed ? "+ RECEIVABLE" : "- PAYABLE"}
                            </Text>
                          </View>
                        </View>
                      </View>

                      <Text
                        style={[
                          styles.peerCardAmountLarge,
                          isOwed
                            ? { color: theme.colors.emerald }
                            : { color: theme.colors.coral },
                        ]}
                        numberOfLines={1}
                      >
                        {isOwed ? "+" : "-"}
                        {formatCurrency(debt.amount)}
                      </Text>
                    </View>

                    {/* Lower Row: Note + Settle Action */}
                    <View style={styles.peerDeckBottomRow}>
                      <Text
                        style={styles.peerNoteText}
                        numberOfLines={1}
                        ellipsizeMode="tail"
                      >
                        {debt.description || "Shared Expense Tab"}
                      </Text>

                      {!debt.settled ? (
                        <TouchableOpacity
                          style={styles.peerSettleBtnLarge}
                          onPress={() => handleSettleDebt(debt.id)}
                          activeOpacity={0.8}
                        >
                          <Text style={styles.peerSettleBtnLargeText}>SETTLE TAB</Text>
                        </TouchableOpacity>
                      ) : (
                        <View style={styles.settledBadgeBox}>
                          <Text style={styles.settledBadgeText}>SETTLED</Text>
                        </View>
                      )}
                    </View>
                  </View>
                </View>
              );
            })
          )}
        </View>
      )}

      {/* 4D: RECURRING TAB */}
      {activeTab === "recurring" && (
        <View style={styles.tabContentCol}>
          <View style={styles.filterStripOuter}>
            <View style={styles.filterStripInner}>
              <Text style={styles.filterMonoText}>
                {recurring.length} SCHEDULED RECURRING CHARGES
              </Text>
            </View>
          </View>

          {recurring.length === 0 ? (
            <View style={styles.emptyOuterBezel}>
              <View style={styles.emptyInnerCore}>
                <Text style={styles.emptyTitle}>No Recurring Rules Active</Text>
                <Text style={styles.emptySubtitle}>
                  Subscriptions, cloud instances, and periodic bills will appear here.
                </Text>
              </View>
            </View>
          ) : (
            recurring.map((rec) => (
              <View key={rec.id} style={styles.txnPodOuter}>
                <View style={styles.txnPodInner}>
                  <View style={styles.txnTypeIconWrap}>
                    <Text style={styles.txnTypeGlyph}>//</Text>
                  </View>

                  <View style={styles.txnBodyCol}>
                    <Text style={styles.txnDescText}>{rec.name}</Text>
                    <Text style={styles.txnMetaDate}>
                      {rec.frequency.toUpperCase()} • NEXT DUE:{" "}
                      {rec.next_due_date || "Monthly Cycle"}
                    </Text>
                  </View>

                  <Text style={styles.txnAmountText}>
                    {formatCurrency(rec.amount)}
                  </Text>
                </View>
              </View>
            ))
          )}
        </View>
      )}

      <View style={{ height: 120 }} />

      {/* ── Section 5: Aerospace Modals ── */}

      {/* Record Transaction Modal */}
      <Modal
        visible={isTxnModalOpen}
        transparent
        animationType="fade"
        onRequestClose={() => setIsTxnModalOpen(false)}
      >
        <View style={styles.modalBackdrop}>
          <View style={styles.modalOuterBezel}>
            <View style={styles.modalInnerCore}>
              <View style={styles.modalHeaderRow}>
                <View style={styles.bentoTagWrap}>
                  <View style={styles.bentoAmberDot} />
                  <Text style={styles.modalTitle}>RECORD NEW ENTRY</Text>
                </View>
                <TouchableOpacity
                  onPress={() => setIsTxnModalOpen(false)}
                  style={styles.modalCloseX}
                >
                  <Text style={styles.modalCloseXText}>x</Text>
                </TouchableOpacity>
              </View>

              {/* Type Switcher */}
              <View style={styles.txnTypeSwitchRow}>
                {(["expense", "income", "transfer"] as const).map((t) => {
                  const active = txnType === t;
                  return (
                    <TouchableOpacity
                      key={t}
                      style={[styles.typePillBtn, active && styles.typePillBtnActive]}
                      onPress={() => setTxnType(t)}
                      activeOpacity={0.8}
                    >
                      <Text
                        style={[
                          styles.typePillText,
                          active && styles.typePillTextActive,
                        ]}
                      >
                        {t.toUpperCase()}
                      </Text>
                    </TouchableOpacity>
                  );
                })}
              </View>

              <Text style={styles.inputFieldLabel}>AMOUNT (INR)</Text>
              <TextInput
                style={styles.aerospaceInput}
                value={txnAmount}
                onChangeText={setTxnAmount}
                placeholder="e.g. 1250"
                keyboardType="numeric"
                placeholderTextColor="#A39E93"
              />

              <Text style={styles.inputFieldLabel}>CATEGORY</Text>
              <TextInput
                style={styles.aerospaceInput}
                value={txnCategory}
                onChangeText={setTxnCategory}
                placeholder="e.g. Dining, Cloud, Hardware"
                placeholderTextColor="#A39E93"
              />

              <Text style={styles.inputFieldLabel}>DESCRIPTION</Text>
              <TextInput
                style={styles.aerospaceInput}
                value={txnDesc}
                onChangeText={setTxnDesc}
                placeholder="e.g. AWS Production Bill or Coffee"
                placeholderTextColor="#A39E93"
              />

              <View style={styles.modalActionsRow}>
                <TouchableOpacity
                  style={styles.cancelActionBtn}
                  onPress={() => setIsTxnModalOpen(false)}
                >
                  <Text style={styles.cancelActionText}>CANCEL</Text>
                </TouchableOpacity>
                <TouchableOpacity
                  style={styles.commitActionBtn}
                  onPress={handleCreateTxn}
                >
                  <Text style={styles.commitActionText}>COMMIT ENTRY</Text>
                </TouchableOpacity>
              </View>
            </View>
          </View>
        </View>
      </Modal>

      {/* Record Debt Modal */}
      <Modal
        visible={isDebtModalOpen}
        transparent
        animationType="fade"
        onRequestClose={() => setIsDebtModalOpen(false)}
      >
        <View style={styles.modalBackdrop}>
          <View style={styles.modalOuterBezel}>
            <View style={styles.modalInnerCore}>
              <View style={styles.modalHeaderRow}>
                <View style={styles.bentoTagWrap}>
                  <View style={styles.peerAmberDot} />
                  <Text style={styles.modalTitle}>RECORD PEER TAB</Text>
                </View>
                <TouchableOpacity
                  onPress={() => setIsDebtModalOpen(false)}
                  style={styles.modalCloseX}
                >
                  <Text style={styles.modalCloseXText}>x</Text>
                </TouchableOpacity>
              </View>

              <Text style={styles.inputFieldLabel}>PERSON / RECIPIENT</Text>
              <TextInput
                style={styles.aerospaceInput}
                value={debtPerson}
                onChangeText={setDebtPerson}
                placeholder="e.g. Alex"
                placeholderTextColor="#A39E93"
              />

              <View style={styles.txnTypeSwitchRow}>
                <TouchableOpacity
                  style={[
                    styles.typePillBtn,
                    debtDirection === "owed" && styles.typePillBtnActive,
                  ]}
                  onPress={() => setDebtDirection("owed")}
                  activeOpacity={0.8}
                >
                  <Text
                    style={[
                      styles.typePillText,
                      debtDirection === "owed" && styles.typePillTextActive,
                    ]}
                  >
                    THEY OWE YOU
                  </Text>
                </TouchableOpacity>

                <TouchableOpacity
                  style={[
                    styles.typePillBtn,
                    debtDirection === "owe" && styles.typePillBtnActive,
                  ]}
                  onPress={() => setDebtDirection("owe")}
                  activeOpacity={0.8}
                >
                  <Text
                    style={[
                      styles.typePillText,
                      debtDirection === "owe" && styles.typePillTextActive,
                    ]}
                  >
                    YOU OWE THEM
                  </Text>
                </TouchableOpacity>
              </View>

              <Text style={styles.inputFieldLabel}>AMOUNT (INR)</Text>
              <TextInput
                style={styles.aerospaceInput}
                value={debtAmount}
                onChangeText={setDebtAmount}
                placeholder="e.g. 800"
                keyboardType="numeric"
                placeholderTextColor="#A39E93"
              />

              <Text style={styles.inputFieldLabel}>REASON / NOTE</Text>
              <TextInput
                style={styles.aerospaceInput}
                value={debtDesc}
                onChangeText={setDebtDesc}
                placeholder="e.g. Dinner split, Uber ride"
                placeholderTextColor="#A39E93"
              />

              <View style={styles.modalActionsRow}>
                <TouchableOpacity
                  style={styles.cancelActionBtn}
                  onPress={() => setIsDebtModalOpen(false)}
                >
                  <Text style={styles.cancelActionText}>CANCEL</Text>
                </TouchableOpacity>
                <TouchableOpacity
                  style={styles.commitActionBtn}
                  onPress={handleCreateDebt}
                >
                  <Text style={styles.commitActionText}>SAVE TAB</Text>
                </TouchableOpacity>
              </View>
            </View>
          </View>
        </View>
      </Modal>
    </ScrollView>
  );
};

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: theme.colors.background,
  },
  contentContainer: {
    paddingHorizontal: 16,
    paddingTop: 12,
    paddingBottom: 40,
  },

  // ── Header Outer Bezel & Inner Core (Cockpit Style) ──
  headerOuterBezel: {
    backgroundColor: "#141414",
    borderRadius: 20,
    borderWidth: 1,
    borderColor: "rgba(255, 255, 255, 0.08)",
    padding: 3,
    marginBottom: 12,
  },
  headerInnerCore: {
    backgroundColor: "#1A1A1A",
    borderRadius: 17,
    paddingHorizontal: 16,
    paddingVertical: 14,
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    borderWidth: 1,
    borderColor: "rgba(255, 255, 255, 0.04)",
  },
  greetingBlock: {
    flex: 1,
    marginRight: 12,
  },
  systemTagRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
    marginBottom: 4,
  },
  pulseDot: {
    width: 7,
    height: 7,
    borderRadius: 3.5,
    backgroundColor: theme.colors.emerald,
  },
  pulseDotOffline: {
    backgroundColor: theme.colors.amber,
  },
  systemTagText: {
    fontFamily: theme.fonts.mono,
    fontSize: 9,
    color: theme.colors.textMuted,
    letterSpacing: 1.2,
    fontWeight: "700",
  },
  systemSeparator: {
    color: "rgba(255, 255, 255, 0.2)",
    fontSize: 8,
  },
  systemNodeText: {
    fontFamily: theme.fonts.mono,
    fontSize: 9,
    color: theme.colors.emerald,
    letterSpacing: 0.8,
  },
  greetingTitle: {
    fontFamily: theme.fonts.serif,
    fontSize: 20,
    fontWeight: "700",
    color: theme.colors.boneWhite,
    letterSpacing: -0.3,
  },
  greetingSub: {
    fontFamily: theme.fonts.sans,
    fontSize: 11,
    color: theme.colors.textSecondary,
    marginTop: 2,
    lineHeight: 15,
  },

  // Chronometer / Metric Capsule
  chronoCapsule: {
    backgroundColor: "#121212",
    borderRadius: 12,
    paddingHorizontal: 12,
    paddingVertical: 8,
    alignItems: "flex-end",
    borderWidth: 1,
    borderColor: "rgba(255, 255, 255, 0.06)",
    minWidth: 100,
  },
  chronoTopRow: {
    flexDirection: "row",
    alignItems: "baseline",
  },
  chronoDigits: {
    fontFamily: theme.fonts.mono,
    fontSize: 16,
    fontWeight: "700",
    color: theme.colors.boneWhite,
    letterSpacing: 0.5,
  },
  chronoDate: {
    fontFamily: theme.fonts.mono,
    fontSize: 8.5,
    color: theme.colors.textMuted,
    letterSpacing: 0.8,
    marginTop: 2,
  },

  // ── Directive Command Deck ──
  directiveOuterBezel: {
    backgroundColor: "#161616",
    borderRadius: 18,
    borderWidth: 1,
    borderColor: "rgba(255, 255, 255, 0.07)",
    padding: 3,
    marginBottom: 12,
  },
  directiveInnerCore: {
    backgroundColor: "#1C1C1C",
    borderRadius: 15,
    padding: 10,
    borderWidth: 1,
    borderColor: "rgba(255, 255, 255, 0.04)",
  },
  directiveInputRow: {
    flexDirection: "row",
    alignItems: "center",
    backgroundColor: "#131313",
    borderRadius: 12,
    borderWidth: 1,
    borderColor: "rgba(255, 255, 255, 0.06)",
    paddingHorizontal: 10,
    paddingVertical: 4,
  },
  directivePrefix: {
    fontFamily: theme.fonts.mono,
    fontSize: 11,
    color: theme.colors.textMuted,
    marginRight: 6,
  },
  directiveInput: {
    flex: 1,
    color: theme.colors.boneWhite,
    fontFamily: theme.fonts.sans,
    fontSize: 13,
    paddingVertical: 6,
  },
  directiveRunBtn: {
    backgroundColor: theme.colors.boneWhite,
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderRadius: 8,
  },
  directiveRunBtnDisabled: {
    backgroundColor: "rgba(255, 255, 255, 0.08)",
    borderWidth: 1,
    borderColor: "rgba(255, 255, 255, 0.16)",
  },
  directiveRunText: {
    fontFamily: theme.fonts.mono,
    fontSize: 10,
    color: "#121212",
    fontWeight: "700",
    letterSpacing: 0.8,
  },
  directiveRunTextDisabled: {
    color: "#D1CCC2",
    fontWeight: "600",
  },
  chipsRow: {
    flexDirection: "row",
    gap: 6,
    marginTop: 8,
    paddingTop: 6,
    borderTopWidth: 1,
    borderTopColor: "rgba(255, 255, 255, 0.04)",
  },
  chipPill: {
    backgroundColor: "rgba(255, 255, 255, 0.04)",
    paddingHorizontal: 9,
    paddingVertical: 4,
    borderRadius: 8,
    borderWidth: 1,
    borderColor: "rgba(255, 255, 255, 0.06)",
  },
  chipPillText: {
    fontFamily: theme.fonts.mono,
    fontSize: 9,
    color: "#A39E93",
    letterSpacing: 0.5,
  },

  // ── Subtabs Segmented Switcher ──
  subTabsOuter: {
    backgroundColor: "#161616",
    borderRadius: 14,
    borderWidth: 1,
    borderColor: "rgba(255, 255, 255, 0.06)",
    padding: 3,
    marginBottom: 12,
  },
  subTabsInner: {
    flexDirection: "row",
    gap: 4,
  },
  subTabPill: {
    flex: 1,
    paddingVertical: 8,
    alignItems: "center",
    borderRadius: 10,
  },
  subTabPillActive: {
    backgroundColor: "#222222",
    borderWidth: 1,
    borderColor: "rgba(255, 255, 255, 0.14)",
  },
  subTabPillText: {
    fontFamily: theme.fonts.mono,
    fontSize: 9,
    color: theme.colors.textMuted,
    letterSpacing: 0.8,
  },
  subTabPillTextActive: {
    color: theme.colors.boneWhite,
    fontWeight: "700",
  },

  tabContentCol: {
    gap: 12,
  },

  // ── Hero Bento Card ──
  heroOuterBezel: {
    backgroundColor: "#161616",
    borderRadius: 18,
    borderWidth: 1,
    borderColor: "rgba(255, 255, 255, 0.07)",
    padding: 3,
  },
  heroInnerCore: {
    backgroundColor: "#1C1C1C",
    borderRadius: 15,
    padding: 14,
    borderWidth: 1,
    borderColor: "rgba(255, 255, 255, 0.04)",
  },
  bentoHeaderRow: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    marginBottom: 10,
  },
  bentoTagWrap: {
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
    flex: 1,
  },
  bentoAmberDot: {
    width: 6,
    height: 6,
    borderRadius: 3,
    backgroundColor: theme.colors.emerald,
  },
  peerAmberDot: {
    width: 6,
    height: 6,
    borderRadius: 3,
    backgroundColor: theme.colors.amber,
  },
  bentoEyebrow: {
    fontFamily: theme.fonts.mono,
    fontSize: 9,
    color: theme.colors.textMuted,
    letterSpacing: 1.3,
    fontWeight: "700",
  },
  bentoLinkCapsule: {
    backgroundColor: "rgba(16, 185, 129, 0.10)",
    borderWidth: 1,
    borderColor: "rgba(16, 185, 129, 0.25)",
    paddingHorizontal: 8,
    paddingVertical: 3,
    borderRadius: 5,
  },
  bentoLinkText: {
    fontFamily: theme.fonts.mono,
    fontSize: 8.5,
    color: theme.colors.emerald,
    letterSpacing: 0.8,
    fontWeight: "700",
  },
  cardArrow: {
    fontFamily: theme.fonts.mono,
    fontSize: 9.5,
    color: theme.colors.textMuted,
    letterSpacing: 0.6,
  },

  netCapitalHeroRow: {
    gap: 4,
    marginBottom: 12,
  },
  netCapitalLabel: {
    fontFamily: theme.fonts.mono,
    fontSize: 9,
    color: theme.colors.textMuted,
    letterSpacing: 1.2,
  },
  netCapitalValue: {
    fontFamily: theme.fonts.mono,
    fontSize: 32,
    fontWeight: "700",
    color: theme.colors.boneWhite,
    letterSpacing: 0.5,
  },

  gaugesContainerRow: {
    flexDirection: "row",
    gap: 10,
    paddingTop: 10,
    borderTopWidth: 1,
    borderTopColor: "rgba(255, 255, 255, 0.04)",
  },
  gaugeBox: {
    flex: 1,
    backgroundColor: "#151515",
    borderRadius: 10,
    padding: 10,
    borderWidth: 1,
    borderColor: "rgba(255, 255, 255, 0.05)",
    gap: 6,
  },
  gaugeHeader: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
  },
  gaugeLabel: {
    fontFamily: theme.fonts.mono,
    fontSize: 8.5,
    color: theme.colors.textMuted,
    letterSpacing: 0.8,
  },
  gaugeAmount: {
    fontFamily: theme.fonts.mono,
    fontSize: 12,
    fontWeight: "700",
  },
  gaugeTrack: {
    height: 4,
    borderRadius: 2,
    backgroundColor: "rgba(255, 255, 255, 0.08)",
    overflow: "hidden",
  },
  gaugeFill: {
    height: "100%",
    borderRadius: 2,
  },
  gaugeFillCoral: {
    width: "42%",
    backgroundColor: theme.colors.coral,
  },
  gaugeFillEmerald: {
    width: "68%",
    backgroundColor: theme.colors.emerald,
  },

  // ── Operating Vaults 2x2 Bento Grid ──
  vaultsGrid: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 8,
  },
  vaultPod: {
    width: "48.5%",
    backgroundColor: "#141414",
    borderRadius: 10,
    borderWidth: 1,
    borderColor: "rgba(255, 255, 255, 0.06)",
    padding: 10,
    minHeight: 80,
    justifyContent: "space-between",
  },
  vaultPodTop: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    gap: 4,
  },
  vaultNameWrap: {
    flexDirection: "row",
    alignItems: "center",
    gap: 5,
    flex: 1,
  },
  accountActiveDot: {
    width: 5,
    height: 5,
    borderRadius: 2.5,
    backgroundColor: theme.colors.emerald,
  },
  vaultNameText: {
    fontFamily: theme.fonts.sans,
    fontSize: 11.5,
    fontWeight: "600",
    color: theme.colors.boneWhite,
  },
  defaultBadgeBox: {
    backgroundColor: "rgba(16, 185, 129, 0.12)",
    borderWidth: 1,
    borderColor: "rgba(16, 185, 129, 0.25)",
    paddingHorizontal: 4,
    paddingVertical: 1,
    borderRadius: 3,
  },
  defaultBadgeText: {
    fontFamily: theme.fonts.mono,
    fontSize: 7,
    color: theme.colors.emerald,
    fontWeight: "700",
  },
  vaultBalanceText: {
    fontFamily: theme.fonts.mono,
    fontSize: 14.5,
    fontWeight: "700",
    color: theme.colors.boneWhite,
    marginVertical: 4,
  },
  vaultSubRow: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
  },
  vaultTypeText: {
    fontFamily: theme.fonts.mono,
    fontSize: 8,
    color: theme.colors.textMuted,
    letterSpacing: 0.5,
  },
  vaultCurrencyTag: {
    fontFamily: theme.fonts.mono,
    fontSize: 8,
    color: "rgba(255, 255, 255, 0.3)",
  },

  // ── Peer Tabs Deck (Main & Subtab) ──
  peerTelemetryRow: {
    flexDirection: "row",
    gap: 8,
    marginBottom: 12,
  },
  peerTelemetryPill: {
    flex: 1,
    backgroundColor: "#141414",
    borderRadius: 10,
    borderWidth: 1,
    borderColor: "rgba(255, 255, 255, 0.05)",
    padding: 8,
    alignItems: "center",
    gap: 2,
  },
  peerTelemetryPillHighlight: {
    flex: 1,
    backgroundColor: "#171F1A",
    borderRadius: 10,
    borderWidth: 1,
    borderColor: "rgba(16, 185, 129, 0.20)",
    padding: 8,
    alignItems: "center",
    gap: 2,
  },
  peerTelemetryLabel: {
    fontFamily: theme.fonts.mono,
    fontSize: 8,
    color: theme.colors.textMuted,
    letterSpacing: 0.8,
    fontWeight: "700",
  },
  peerTelemetryValue: {
    fontFamily: theme.fonts.mono,
    fontSize: 13.5,
    fontWeight: "700",
    marginTop: 2,
  },
  peerTelemetrySub: {
    fontFamily: theme.fonts.mono,
    fontSize: 7.5,
    color: "rgba(255, 255, 255, 0.4)",
  },

  // Peer Roster Preview on Main Overview
  peerRosterSection: {
    gap: 6,
    paddingTop: 10,
    borderTopWidth: 1,
    borderTopColor: "rgba(255, 255, 255, 0.04)",
  },
  peerEmptyPod: {
    backgroundColor: "#141414",
    borderRadius: 10,
    borderWidth: 1,
    borderColor: "rgba(255, 255, 255, 0.05)",
    padding: 14,
    alignItems: "center",
    gap: 4,
  },
  peerEmptyTitle: {
    fontFamily: theme.fonts.sans,
    fontSize: 12.5,
    fontWeight: "600",
    color: theme.colors.boneWhite,
  },
  peerEmptySubtitle: {
    fontFamily: theme.fonts.mono,
    fontSize: 8.5,
    color: theme.colors.textMuted,
    textAlign: "center",
  },
  peerCardRow: {
    backgroundColor: "#141414",
    borderRadius: 10,
    borderWidth: 1,
    borderColor: "rgba(255, 255, 255, 0.05)",
    padding: 10,
    flexDirection: "row",
    alignItems: "center",
    gap: 10,
  },
  peerAvatarCircle: {
    width: 32,
    height: 32,
    borderRadius: 16,
    backgroundColor: "#1B1B1B",
    borderWidth: 1,
    borderColor: "rgba(255, 255, 255, 0.10)",
    alignItems: "center",
    justifyContent: "center",
  },
  peerAvatarInitial: {
    fontFamily: theme.fonts.mono,
    fontSize: 12,
    fontWeight: "700",
    color: theme.colors.boneWhite,
  },
  peerCardMainCol: {
    flex: 1,
    gap: 3,
  },
  peerCardTopRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
  },
  peerNameText: {
    fontFamily: theme.fonts.sans,
    fontSize: 13,
    fontWeight: "700",
    color: theme.colors.boneWhite,
    maxWidth: 120,
  },
  debtPillBadge: {
    paddingHorizontal: 6,
    paddingVertical: 1.5,
    borderRadius: 4,
    borderWidth: 1,
  },
  debtPillReceivable: {
    backgroundColor: "rgba(16, 185, 129, 0.12)",
    borderColor: "rgba(16, 185, 129, 0.30)",
  },
  debtPillPayable: {
    backgroundColor: "rgba(239, 68, 68, 0.12)",
    borderColor: "rgba(239, 68, 68, 0.30)",
  },
  debtPillText: {
    fontFamily: theme.fonts.mono,
    fontSize: 7.5,
    fontWeight: "700",
    letterSpacing: 0.5,
  },
  peerDescText: {
    fontFamily: theme.fonts.sans,
    fontSize: 10.5,
    color: theme.colors.textMuted,
  },
  peerAmountCol: {
    alignItems: "flex-end",
    gap: 4,
  },
  peerCardAmount: {
    fontFamily: theme.fonts.mono,
    fontSize: 13,
    fontWeight: "700",
  },
  peerSettleBtn: {
    backgroundColor: "rgba(16, 185, 129, 0.12)",
    borderWidth: 1,
    borderColor: "rgba(16, 185, 129, 0.35)",
    paddingHorizontal: 8,
    paddingVertical: 3,
    borderRadius: 5,
  },
  peerSettleBtnText: {
    fontFamily: theme.fonts.mono,
    fontSize: 8,
    color: theme.colors.emerald,
    fontWeight: "700",
    letterSpacing: 0.8,
  },
  addPeerTabBtn: {
    backgroundColor: "rgba(255, 255, 255, 0.04)",
    borderWidth: 1,
    borderColor: "rgba(255, 255, 255, 0.08)",
    borderRadius: 8,
    paddingVertical: 8,
    alignItems: "center",
    marginTop: 4,
  },
  addPeerTabText: {
    fontFamily: theme.fonts.mono,
    fontSize: 9,
    color: theme.colors.boneWhite,
    fontWeight: "700",
    letterSpacing: 0.8,
  },

  // Peer Quick Strip on Transactions Tab
  peerQuickStripOuter: {
    backgroundColor: "#161616",
    borderRadius: 12,
    borderWidth: 1,
    borderColor: "rgba(245, 158, 11, 0.25)",
    padding: 2,
    marginBottom: 4,
  },
  peerQuickStripInner: {
    backgroundColor: "#1C1C1C",
    borderRadius: 10,
    paddingHorizontal: 12,
    paddingVertical: 8,
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
  },
  peerQuickLeft: {
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
    flex: 1,
  },
  peerQuickText: {
    fontFamily: theme.fonts.mono,
    fontSize: 9,
    color: theme.colors.boneWhite,
    fontWeight: "600",
    letterSpacing: 0.5,
  },
  peerQuickLinkText: {
    fontFamily: theme.fonts.mono,
    fontSize: 8.5,
    color: theme.colors.amber,
    fontWeight: "700",
    letterSpacing: 0.8,
  },

  // Dedicated Debts Tab Card Bezel
  peerCardRowBezel: {
    backgroundColor: "#161616",
    borderRadius: 14,
    borderWidth: 1,
    borderColor: "rgba(255, 255, 255, 0.06)",
    padding: 2,
    marginBottom: 8,
  },
  peerCardRowInner: {
    backgroundColor: "#1C1C1C",
    borderRadius: 12,
    padding: 12,
    gap: 8,
  },
  peerDeckTopRow: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
  },
  peerDeckIdentity: {
    flexDirection: "row",
    alignItems: "center",
    gap: 10,
    flex: 1,
  },
  peerDeckNames: {
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
    flex: 1,
  },
  peerCardAmountLarge: {
    fontFamily: theme.fonts.mono,
    fontSize: 16,
    fontWeight: "700",
    letterSpacing: 0.3,
  },
  peerDeckBottomRow: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    paddingTop: 6,
    borderTopWidth: 1,
    borderTopColor: "rgba(255, 255, 255, 0.04)",
  },
  peerNoteText: {
    fontFamily: theme.fonts.mono,
    fontSize: 9.5,
    color: theme.colors.textMuted,
    flex: 1,
    marginRight: 10,
  },
  peerSettleBtnLarge: {
    backgroundColor: "rgba(16, 185, 129, 0.12)",
    borderWidth: 1,
    borderColor: "rgba(16, 185, 129, 0.35)",
    paddingHorizontal: 10,
    paddingVertical: 4,
    borderRadius: 6,
  },
  peerSettleBtnLargeText: {
    fontFamily: theme.fonts.mono,
    fontSize: 8.5,
    color: theme.colors.emerald,
    fontWeight: "700",
    letterSpacing: 0.8,
  },
  settledBadgeBox: {
    backgroundColor: "rgba(255, 255, 255, 0.05)",
    paddingHorizontal: 8,
    paddingVertical: 3,
    borderRadius: 4,
  },
  settledBadgeText: {
    fontFamily: theme.fonts.mono,
    fontSize: 8,
    color: theme.colors.textMuted,
    fontWeight: "700",
  },

  // ── Transaction Pods ──
  txnPodOuter: {
    backgroundColor: "#161616",
    borderRadius: 14,
    borderWidth: 1,
    borderColor: "rgba(255, 255, 255, 0.06)",
    padding: 2,
    marginBottom: 6,
  },
  txnPodInner: {
    backgroundColor: "#1C1C1C",
    borderRadius: 12,
    padding: 10,
    flexDirection: "row",
    alignItems: "center",
    gap: 10,
  },
  txnTypeIconWrap: {
    width: 28,
    height: 28,
    borderRadius: 14,
    backgroundColor: "#141414",
    borderWidth: 1,
    borderColor: "rgba(255, 255, 255, 0.08)",
    alignItems: "center",
    justifyContent: "center",
  },
  txnTypeGlyph: {
    fontFamily: theme.fonts.mono,
    fontSize: 14,
    fontWeight: "700",
  },
  txnBodyCol: {
    flex: 1,
    gap: 2,
  },
  txnDescText: {
    fontFamily: theme.fonts.sans,
    fontSize: 13,
    fontWeight: "600",
    color: theme.colors.boneWhite,
  },
  txnMetaRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: 5,
  },
  txnMetaDate: {
    fontFamily: theme.fonts.mono,
    fontSize: 9,
    color: theme.colors.textMuted,
  },
  txnMetaDot: {
    fontFamily: theme.fonts.mono,
    fontSize: 9,
    color: theme.colors.textMuted,
  },
  txnMetaCategory: {
    fontFamily: theme.fonts.mono,
    fontSize: 9,
    color: theme.colors.textSecondary,
  },
  offlineSyncTag: {
    backgroundColor: "rgba(245, 158, 11, 0.15)",
    borderWidth: 1,
    borderColor: "rgba(245, 158, 11, 0.3)",
    paddingHorizontal: 4,
    paddingVertical: 1,
    borderRadius: 3,
  },
  offlineSyncTagText: {
    fontFamily: theme.fonts.mono,
    fontSize: 7,
    color: theme.colors.amber,
    fontWeight: "700",
  },
  txnAmountText: {
    fontFamily: theme.fonts.mono,
    fontSize: 13,
    fontWeight: "700",
  },

  // Filter Strip
  filterStripOuter: {
    backgroundColor: "#161616",
    borderRadius: 12,
    borderWidth: 1,
    borderColor: "rgba(255, 255, 255, 0.06)",
    padding: 2,
    marginBottom: 4,
  },
  filterStripInner: {
    backgroundColor: "#1A1A1A",
    borderRadius: 10,
    paddingHorizontal: 12,
    paddingVertical: 8,
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
  },
  filterMonoText: {
    fontFamily: theme.fonts.mono,
    fontSize: 9,
    color: theme.colors.textMuted,
    letterSpacing: 1,
  },
  quickAddTxnBtn: {
    backgroundColor: "rgba(255, 255, 255, 0.08)",
    paddingHorizontal: 8,
    paddingVertical: 4,
    borderRadius: 6,
    borderWidth: 1,
    borderColor: "rgba(255, 255, 255, 0.12)",
  },
  quickAddTxnText: {
    fontFamily: theme.fonts.mono,
    fontSize: 8.5,
    color: theme.colors.boneWhite,
    fontWeight: "700",
  },

  // Empty States
  emptyOuterBezel: {
    backgroundColor: "#161616",
    borderRadius: 16,
    borderWidth: 1,
    borderColor: "rgba(255, 255, 255, 0.06)",
    padding: 3,
  },
  emptyInnerCore: {
    backgroundColor: "#1C1C1C",
    borderRadius: 13,
    padding: 24,
    alignItems: "center",
    gap: 6,
  },
  emptyTitle: {
    fontFamily: theme.fonts.serif,
    fontSize: 16,
    color: theme.colors.boneWhite,
    textAlign: "center",
  },
  emptySubtitle: {
    fontFamily: theme.fonts.sans,
    fontSize: 12,
    color: theme.colors.textMuted,
    textAlign: "center",
  },

  // ── Modals (Aerospace Double Bezel) ──
  modalBackdrop: {
    flex: 1,
    backgroundColor: "rgba(0, 0, 0, 0.78)",
    justifyContent: "center",
    paddingHorizontal: 20,
  },
  modalOuterBezel: {
    backgroundColor: "#161616",
    borderRadius: 22,
    borderWidth: 1,
    borderColor: "rgba(255, 255, 255, 0.12)",
    padding: 3,
  },
  modalInnerCore: {
    backgroundColor: "#1C1C1C",
    borderRadius: 19,
    padding: 18,
    borderWidth: 1,
    borderColor: "rgba(255, 255, 255, 0.05)",
  },
  modalHeaderRow: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    marginBottom: 14,
  },
  modalTitle: {
    fontFamily: theme.fonts.mono,
    fontSize: 11,
    fontWeight: "700",
    color: theme.colors.boneWhite,
    letterSpacing: 1,
  },
  modalCloseX: {
    padding: 4,
  },
  modalCloseXText: {
    fontFamily: theme.fonts.mono,
    fontSize: 14,
    color: theme.colors.textMuted,
  },
  txnTypeSwitchRow: {
    flexDirection: "row",
    gap: 6,
    marginBottom: 12,
  },
  typePillBtn: {
    flex: 1,
    paddingVertical: 6,
    borderRadius: 8,
    alignItems: "center",
    backgroundColor: "#141414",
    borderWidth: 1,
    borderColor: "rgba(255, 255, 255, 0.06)",
  },
  typePillBtnActive: {
    backgroundColor: "rgba(255, 255, 255, 0.12)",
    borderColor: theme.colors.boneWhite,
  },
  typePillText: {
    fontFamily: theme.fonts.mono,
    fontSize: 9,
    color: theme.colors.textMuted,
    letterSpacing: 0.8,
  },
  typePillTextActive: {
    color: theme.colors.boneWhite,
    fontWeight: "700",
  },
  inputFieldLabel: {
    fontFamily: theme.fonts.mono,
    fontSize: 8.5,
    color: theme.colors.textMuted,
    letterSpacing: 1,
    marginTop: 8,
    marginBottom: 4,
  },
  aerospaceInput: {
    backgroundColor: "#141414",
    borderWidth: 1,
    borderColor: "rgba(255, 255, 255, 0.08)",
    borderRadius: 8,
    color: theme.colors.boneWhite,
    fontFamily: theme.fonts.mono,
    fontSize: 13,
    paddingHorizontal: 12,
    paddingVertical: 8,
  },
  modalActionsRow: {
    flexDirection: "row",
    gap: 10,
    marginTop: 16,
  },
  cancelActionBtn: {
    flex: 1,
    paddingVertical: 10,
    borderRadius: 8,
    backgroundColor: "#141414",
    borderWidth: 1,
    borderColor: "rgba(255, 255, 255, 0.1)",
    alignItems: "center",
  },
  cancelActionText: {
    fontFamily: theme.fonts.mono,
    fontSize: 10,
    color: theme.colors.textMuted,
    fontWeight: "700",
    letterSpacing: 0.8,
  },
  commitActionBtn: {
    flex: 1,
    paddingVertical: 10,
    borderRadius: 8,
    backgroundColor: theme.colors.boneWhite,
    alignItems: "center",
  },
  commitActionText: {
    fontFamily: theme.fonts.mono,
    fontSize: 10,
    color: "#121212",
    fontWeight: "700",
    letterSpacing: 0.8,
  },
});
