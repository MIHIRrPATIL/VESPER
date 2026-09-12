import React, { useState, useEffect, useCallback } from "react";
import {
  StyleSheet,
  Text,
  View,
  TouchableOpacity,
  TextInput,
  Modal,
  ActivityIndicator,
} from "react-native";
import { theme } from "../styles/theme";
import { gatewayClient } from "../services/gateway";
import { offlineStore } from "../services/offline-store";
import { CascadeView } from "./CascadeView";

export const LedgerTab: React.FC = () => {
  const [loading, setLoading] = useState<boolean>(true);
  const [isOffline, setIsOffline] = useState<boolean>(false);
  const [pendingCount, setPendingCount] = useState<number>(0);

  const [overview, setOverview] = useState<any | null>(null);
  const [accounts, setAccounts] = useState<any[]>([]);
  const [debts, setDebts] = useState<any[]>([]);
  const [transactions, setTransactions] = useState<any[]>([]);

  // Modal State for New Transaction
  const [isModalOpen, setIsModalOpen] = useState<boolean>(false);
  const [txDesc, setTxDesc] = useState<string>("");
  const [txAmount, setTxAmount] = useState<string>("");
  const [txType, setTxType] = useState<"EXPENSE" | "INCOME">("EXPENSE");
  const [txCategory, setTxCategory] = useState<string>("General");
  const [txAccountId, setTxAccountId] = useState<string>("");
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);

  // Modal State for New Peer Tab
  const [isDebtModalOpen, setIsDebtModalOpen] = useState<boolean>(false);
  const [debtPerson, setDebtPerson] = useState<string>("");
  const [debtAmount, setDebtAmount] = useState<string>("");
  const [debtDirection, setDebtDirection] = useState<"owed" | "owe">("owed");
  const [debtDesc, setDebtDesc] = useState<string>("");

  const loadLedgerData = useCallback(async () => {
    setLoading(true);

    // 1. Immediately hydrate from offline cache
    const [cOv, cAccs, cDbs, cTxs, pCount] = await Promise.all([
      offlineStore.getCachedFinanceOverview(),
      offlineStore.getCachedAccounts(),
      offlineStore.getCachedDebts(),
      offlineStore.getCachedTransactions(),
      offlineStore.getPendingCount(),
    ]);

    if (cOv) setOverview(cOv);
    if (cAccs && cAccs.length > 0) setAccounts(cAccs);
    if (cDbs) setDebts(cDbs);
    if (cTxs && cTxs.length > 0) setTransactions(cTxs);
    setPendingCount(pCount);

    // 2. Fetch live data if server reachable
    try {
      const [ov, accs, dbs, txs] = await Promise.all([
        gatewayClient.fetchFinanceOverview(),
        gatewayClient.fetchFinanceAccounts(),
        gatewayClient.fetchFinanceDebts(),
        gatewayClient.fetchFinanceTransactions(15),
      ]);

      let hadLiveSuccess = false;

      if (ov) {
        setOverview(ov);
        offlineStore.saveCachedFinanceOverview(ov);
        hadLiveSuccess = true;
      }
      if (accs && accs.length > 0) {
        setAccounts(accs);
        offlineStore.saveCachedAccounts(accs);
        hadLiveSuccess = true;
      }
      if (dbs) {
        setDebts(dbs);
        offlineStore.saveCachedDebts(dbs);
        hadLiveSuccess = true;
      }
      if (txs && txs.length > 0) {
        setTransactions(txs);
        offlineStore.saveCachedTransactions(txs);
        hadLiveSuccess = true;
      }

      setIsOffline(!hadLiveSuccess);
    } catch {
      setIsOffline(true);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadLedgerData();

    // Subscribe to sync queue updates
    const unsub = offlineStore.subscribeSync((_syncing, count) => {
      setPendingCount(count);
    });

    return () => unsub();
  }, [loadLedgerData]);

  const formatCurrency = (val: number | undefined | null) => {
    const num = Number(val || 0);
    return `₹${num.toLocaleString("en-IN", { maximumFractionDigits: 0 })}`;
  };

  const handleManualSync = async () => {
    setLoading(true);
    try {
      await offlineStore.syncPendingBacklog();
      await loadLedgerData();
    } finally {
      setLoading(false);
    }
  };

  const handleCreateTransaction = async () => {
    const amountNum = parseFloat(txAmount);
    if (!txDesc.trim() || isNaN(amountNum) || amountNum <= 0) return;

    setIsSubmitting(true);

    const newTxPayload = {
      type: txType,
      amount: amountNum,
      category: txCategory,
      description: txDesc.trim(),
      account_id: txAccountId || (accounts[0]?.id ?? undefined),
      date: new Date().toISOString(),
    };

    const optimisticTx = {
      id: `local_tx_${Date.now()}`,
      ...newTxPayload,
      account_name: accounts.find((a) => a.id === txAccountId)?.name || accounts[0]?.name || "Vault",
      isPendingSync: true,
    };

    // 1. Optimistic UI update
    const updatedTxs = [optimisticTx, ...transactions];
    setTransactions(updatedTxs);
    await offlineStore.saveCachedTransactions(updatedTxs);

    // 2. Try sending directly or enqueue to offline store
    try {
      const baseUrl = gatewayClient.getHttpUrl();
      const res = await fetch(`${baseUrl}/api/finance/transactions`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(newTxPayload),
      });

      if (!res.ok) {
        throw new Error(`HTTP ${res.status}`);
      }

      // Mark synced
      optimisticTx.isPendingSync = false;
      await offlineStore.saveCachedTransactions(updatedTxs);
    } catch {
      // Backend offline: enqueue for synchronization
      await offlineStore.enqueueOfflineTransaction(newTxPayload);
      setIsOffline(true);
    } finally {
      setIsSubmitting(false);
      setIsModalOpen(false);
      setTxDesc("");
      setTxAmount("");
      setTxCategory("General");
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
      loadLedgerData();
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
      loadLedgerData();
    } catch (e) {
      console.warn("Error settling debt:", e);
    }
  };

  const netWorth = overview?.total_net_worth ?? overview?.net_worth ?? 245000;
  const monthlyBurn = overview?.monthly_burn ?? 42500;
  const monthlySavings = overview?.monthly_net_savings ?? 85000;

  const displayAccounts =
    accounts.length > 0
      ? accounts
      : [
          { name: "Saraswat Bank", balance: 145000, type: "CHECKING", is_default: true },
          { name: "SBI Operating", balance: 65000, type: "SAVINGS", is_default: false },
          { name: "HDFC Reserve", balance: 25000, type: "SAVINGS", is_default: false },
          { name: "Petty Cash", balance: 10000, type: "CASH", is_default: false },
        ];

  // Pure real user debts - no mock peers
  const displayDebts = debts;

  const debtsOwedToUser = displayDebts
    .filter((d: any) => d.direction === "OWES_ME" || d.direction === "owed")
    .reduce((acc: number, d: any) => acc + (d.amount || 0), 0);
  const debtsUserOwes = displayDebts
    .filter((d: any) => d.direction === "I_OWE" || d.direction === "owe")
    .reduce((acc: number, d: any) => acc + (d.amount || 0), 0);
  const netPeerBalance = debtsOwedToUser - debtsUserOwes;

  return (
    <View style={styles.container}>
      {/* ── Offline & Pending Sync Banner ── */}
      {(isOffline || pendingCount > 0) && (
        <CascadeView delay={0}>
          <View style={styles.syncOuterBezel}>
            <View style={styles.syncInnerCore}>
              <View style={styles.syncBannerLeft}>
                <View
                  style={[
                    styles.syncDot,
                    {
                      backgroundColor:
                        pendingCount > 0 ? theme.colors.amber : theme.colors.emerald,
                    },
                  ]}
                />
                <Text style={styles.syncBannerText}>
                  {isOffline ? "OFFLINE CACHE ACTIVE" : "SYNCHRONIZED"} //{" "}
                  {pendingCount > 0
                    ? `${pendingCount} ENTRY(S) QUEUED FOR DISPATCH`
                    : "PREVIOUS CAPITAL SNAPSHOT PERSISTED"}
                </Text>
              </View>
              {pendingCount > 0 && (
                <TouchableOpacity
                  style={styles.syncActionBtn}
                  onPress={handleManualSync}
                  activeOpacity={0.8}
                >
                  <Text style={styles.syncActionText}>SYNC NOW</Text>
                </TouchableOpacity>
              )}
            </View>
          </View>
        </CascadeView>
      )}

      {/* ── 1. Net Worth & Capital Summary (Double-Bezel Hero) ── */}
      <CascadeView delay={40}>
        <View style={styles.heroOuterBezel}>
          <View style={styles.heroInnerCore}>
            <View style={styles.bentoHeaderRow}>
              <View style={styles.bentoTagWrap}>
                <View style={styles.pulseDot} />
                <Text style={styles.bentoEyebrow}>CAPITAL VAULT NOMINAL</Text>
              </View>
              <View style={styles.bentoActionsRow}>
                <TouchableOpacity
                  style={styles.quickActionPill}
                  onPress={() => setIsModalOpen(true)}
                  activeOpacity={0.8}
                >
                  <Text style={styles.quickActionPillText}>+ LOG ENTRY</Text>
                </TouchableOpacity>
                <TouchableOpacity
                  style={styles.refreshPill}
                  onPress={loadLedgerData}
                  disabled={loading}
                >
                  {loading ? (
                    <ActivityIndicator size="small" color={theme.colors.textMuted} />
                  ) : (
                    <Text style={styles.refreshPillText}>REFRESH</Text>
                  )}
                </TouchableOpacity>
              </View>
            </View>

            <View style={styles.netCapitalHeroRow}>
              <Text style={styles.netCapitalLabel}>NET LIQUID CAPITAL</Text>
              <Text style={styles.netCapitalValue} numberOfLines={1} adjustsFontSizeToFit>
                {formatCurrency(netWorth)}
              </Text>
            </View>

            <View style={styles.gaugesContainerRow}>
              <View style={styles.gaugeBox}>
                <View style={styles.gaugeHeader}>
                  <Text style={styles.gaugeLabel}>MONTHLY BURN</Text>
                  <Text style={[styles.gaugeAmount, { color: theme.colors.coral }]}>
                    {formatCurrency(monthlyBurn)}
                  </Text>
                </View>
                <View style={styles.gaugeTrack}>
                  <View style={[styles.gaugeFill, styles.gaugeFillCoral]} />
                </View>
              </View>

              <View style={styles.gaugeBox}>
                <View style={styles.gaugeHeader}>
                  <Text style={styles.gaugeLabel}>NET SAVINGS</Text>
                  <Text style={[styles.gaugeAmount, { color: theme.colors.emerald }]}>
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
      </CascadeView>

      {/* ── 2. Bank Accounts Bento Grid (Zero Overflows) ── */}
      <CascadeView delay={80}>
        <View style={styles.heroOuterBezel}>
          <View style={styles.heroInnerCore}>
            <View style={styles.bentoHeaderRow}>
              <View style={styles.bentoTagWrap}>
                <View style={styles.bentoDot} />
                <Text style={styles.bentoEyebrow}>OPERATING VAULTS &amp; ACCOUNTS</Text>
              </View>
              <View style={styles.bentoLinkCapsule}>
                <Text style={styles.bentoLinkText}>{displayAccounts.length} VAULTS</Text>
              </View>
            </View>

            <View style={styles.vaultsGrid}>
              {displayAccounts.map((acc, idx) => (
                <View key={acc.id || `acc_${idx}`} style={styles.vaultPod}>
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
                      {acc.type || "CHECKING"}
                    </Text>
                    <Text style={styles.vaultCurrencyTag}>INR</Text>
                  </View>
                </View>
              ))}
            </View>
          </View>
        </View>
      </CascadeView>

      {/* ── 3. Peer Debts Flight Deck (Zero Overflows, Authentic Empty State) ── */}
      <CascadeView delay={120}>
        <View style={styles.heroOuterBezel}>
          <View style={styles.heroInnerCore}>
            <View style={styles.bentoHeaderRow}>
              <View style={styles.bentoTagWrap}>
                <View
                  style={[
                    styles.bentoAmberDot,
                    displayDebts.length === 0 && { backgroundColor: theme.colors.emerald },
                  ]}
                />
                <Text style={styles.bentoEyebrow}>PEER TABS &amp; SHARED LEDGER</Text>
              </View>
              <TouchableOpacity
                onPress={() => setIsDebtModalOpen(true)}
                activeOpacity={0.8}
                style={styles.bentoLinkCapsule}
              >
                <Text style={styles.bentoLinkText}>+ NEW TAB</Text>
              </TouchableOpacity>
            </View>

            {/* 3-Capsule Telemetry Summary Row */}
            <View style={styles.peerTelemetryRow}>
              <View style={styles.peerTelemetryPill}>
                <Text style={styles.peerTelemetryLabel}>RECEIVABLES</Text>
                <Text
                  style={[styles.peerTelemetryValue, { color: theme.colors.emerald }]}
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

            {/* Peer Tabs Roster or Clean Empty State */}
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
                <>
                  <Text style={styles.peerRosterLabel}>ACTIVE PEER BALANCES</Text>
                  {displayDebts.map((d: any, idx: number) => {
                    const owesMe = d.direction === "OWES_ME" || d.direction === "owed";
                    return (
                      <View key={d.id || `debt_${idx}`} style={styles.peerCardRow}>
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
                                owesMe
                                  ? styles.debtPillReceivable
                                  : styles.debtPillPayable,
                              ]}
                            >
                              <Text
                                style={[
                                  styles.debtPillText,
                                  owesMe
                                    ? { color: theme.colors.emerald }
                                    : { color: theme.colors.coral },
                                ]}
                              >
                                {owesMe ? "+ RECEIVABLE" : "- PAYABLE"}
                              </Text>
                            </View>
                          </View>
                          <Text
                            style={styles.peerDescText}
                            numberOfLines={1}
                            ellipsizeMode="tail"
                          >
                            {d.purpose || d.description || "Shared Tab Split"}
                          </Text>
                        </View>

                        <View style={styles.peerAmountCol}>
                          <Text
                            style={[
                              styles.peerCardAmount,
                              owesMe
                                ? { color: theme.colors.emerald }
                                : { color: theme.colors.coral },
                            ]}
                            numberOfLines={1}
                          >
                            {owesMe ? "+" : "-"}
                            {formatCurrency(d.amount)}
                          </Text>
                          {d.id && (
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
                  })}
                </>
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
      </CascadeView>

      {/* ── 4. Recent Transactions ── */}
      <CascadeView delay={160}>
        <View style={styles.heroOuterBezel}>
          <View style={styles.heroInnerCore}>
            <View style={styles.bentoHeaderRow}>
              <View style={styles.bentoTagWrap}>
                <View style={styles.bentoDot} />
                <Text style={styles.bentoEyebrow}>TRANSACTION JOURNAL STREAM</Text>
              </View>
              <Text style={styles.cardArrow}>LIVE STREAM &gt;</Text>
            </View>

            {transactions.length === 0 ? (
              <Text style={styles.emptyText}>No recent transactions recorded.</Text>
            ) : (
              transactions.map((tx, idx) => {
                const isExpense =
                  tx.type === "EXPENSE" || tx.type === "expense" || tx.type === "DEBIT" || (tx.amount && tx.amount < 0);
                const absAmount = Math.abs(tx.amount || 0);

                return (
                  <View key={tx.id || `tx_${idx}`} style={styles.txnPodOuter}>
                    <View style={styles.txnPodInner}>
                      <View style={styles.txnTypeIconWrap}>
                        <Text
                          style={[
                            styles.txnTypeGlyph,
                            { color: isExpense ? theme.colors.coral : theme.colors.emerald },
                          ]}
                        >
                          {isExpense ? "-" : "+"}
                        </Text>
                      </View>

                      <View style={styles.txnBodyCol}>
                        <Text style={styles.txnDescText} numberOfLines={1}>
                          {tx.description || tx.merchant || "Transaction"}
                        </Text>
                        <View style={styles.txnMetaRow}>
                          <Text style={styles.txnMetaCategory}>
                            {tx.category || "General"}
                          </Text>
                          <Text style={styles.txnMetaDot}>•</Text>
                          <Text style={styles.txnMetaCategory}>
                            {tx.account_name || "Vault"}
                          </Text>
                          {tx.isPendingSync && (
                            <View style={styles.offlineSyncTag}>
                              <Text style={styles.offlineSyncTagText}>PENDING SYNC</Text>
                            </View>
                          )}
                        </View>
                      </View>

                      <Text
                        style={[
                          styles.txnAmountText,
                          { color: isExpense ? theme.colors.boneWhite : theme.colors.emerald },
                        ]}
                      >
                        {isExpense ? "-" : "+"}
                        {formatCurrency(absAmount)}
                      </Text>
                    </View>
                  </View>
                );
              })
            )}
          </View>
        </View>
      </CascadeView>

      {/* ── Add Transaction Modal (Double-Bezel) ── */}
      <Modal
        visible={isModalOpen}
        transparent
        animationType="fade"
        onRequestClose={() => setIsModalOpen(false)}
      >
        <View style={styles.modalBackdrop}>
          <View style={styles.modalOuterBezel}>
            <View style={styles.modalInnerCore}>
              <View style={styles.bentoHeaderRow}>
                <View style={styles.bentoTagWrap}>
                  <View style={styles.bentoDot} />
                  <Text style={styles.modalTitle}>NEW LEDGER ENTRY</Text>
                </View>
                <TouchableOpacity
                  onPress={() => setIsModalOpen(false)}
                  style={styles.modalCloseX}
                >
                  <Text style={styles.modalCloseXText}>x</Text>
                </TouchableOpacity>
              </View>

              {/* Type selector */}
              <View style={styles.txnTypeSwitchRow}>
                <TouchableOpacity
                  style={[
                    styles.typePillBtn,
                    txType === "EXPENSE" && styles.typePillBtnActive,
                  ]}
                  onPress={() => setTxType("EXPENSE")}
                  activeOpacity={0.8}
                >
                  <Text
                    style={[
                      styles.typePillText,
                      txType === "EXPENSE" && styles.typePillTextActive,
                    ]}
                  >
                    EXPENSE
                  </Text>
                </TouchableOpacity>
                <TouchableOpacity
                  style={[
                    styles.typePillBtn,
                    txType === "INCOME" && styles.typePillBtnActive,
                  ]}
                  onPress={() => setTxType("INCOME")}
                  activeOpacity={0.8}
                >
                  <Text
                    style={[
                      styles.typePillText,
                      txType === "INCOME" && styles.typePillTextActive,
                    ]}
                  >
                    INCOME
                  </Text>
                </TouchableOpacity>
              </View>

              {/* Inputs */}
              <Text style={styles.inputFieldLabel}>DESCRIPTION</Text>
              <TextInput
                style={styles.aerospaceInput}
                placeholder="e.g. Flight tickets, Groceries"
                placeholderTextColor="#A39E93"
                value={txDesc}
                onChangeText={setTxDesc}
              />

              <Text style={styles.inputFieldLabel}>AMOUNT (INR)</Text>
              <TextInput
                style={styles.aerospaceInput}
                placeholder="0.00"
                placeholderTextColor="#A39E93"
                keyboardType="numeric"
                value={txAmount}
                onChangeText={setTxAmount}
              />

              <Text style={styles.inputFieldLabel}>CATEGORY</Text>
              <TextInput
                style={styles.aerospaceInput}
                placeholder="General, Travel, Infrastructure"
                placeholderTextColor="#A39E93"
                value={txCategory}
                onChangeText={setTxCategory}
              />

              {/* Action buttons */}
              <View style={styles.modalActionsRow}>
                <TouchableOpacity
                  style={styles.cancelActionBtn}
                  onPress={() => setIsModalOpen(false)}
                >
                  <Text style={styles.cancelActionText}>CANCEL</Text>
                </TouchableOpacity>
                <TouchableOpacity
                  style={[
                    styles.commitActionBtn,
                    isSubmitting && styles.btnDisabled,
                  ]}
                  onPress={handleCreateTransaction}
                  disabled={isSubmitting}
                >
                  {isSubmitting ? (
                    <ActivityIndicator size="small" color="#121212" />
                  ) : (
                    <Text style={styles.commitActionText}>
                      {isOffline ? "SAVE LOCALLY" : "RECORD"}
                    </Text>
                  )}
                </TouchableOpacity>
              </View>
            </View>
          </View>
        </View>
      </Modal>

      {/* ── Add Peer Tab Modal ── */}
      <Modal
        visible={isDebtModalOpen}
        transparent
        animationType="fade"
        onRequestClose={() => setIsDebtModalOpen(false)}
      >
        <View style={styles.modalBackdrop}>
          <View style={styles.modalOuterBezel}>
            <View style={styles.modalInnerCore}>
              <View style={styles.bentoHeaderRow}>
                <View style={styles.bentoTagWrap}>
                  <View style={styles.bentoAmberDot} />
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
    </View>
  );
};

const styles = StyleSheet.create({
  container: {
    gap: 12,
  },
  syncOuterBezel: {
    backgroundColor: "#161616",
    borderRadius: 14,
    borderWidth: 1,
    borderColor: "rgba(255, 255, 255, 0.08)",
    padding: 2,
  },
  syncInnerCore: {
    backgroundColor: "#1C1C1C",
    borderRadius: 12,
    paddingHorizontal: 12,
    paddingVertical: 8,
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
  },
  syncBannerLeft: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
    flex: 1,
  },
  syncDot: {
    width: 6,
    height: 6,
    borderRadius: 3,
  },
  syncBannerText: {
    fontFamily: theme.fonts.mono,
    fontSize: 9,
    letterSpacing: 0.8,
    color: theme.colors.textSecondary,
  },
  syncActionBtn: {
    paddingHorizontal: 8,
    paddingVertical: 4,
    backgroundColor: "#141414",
    borderRadius: 6,
    borderWidth: 1,
    borderColor: "rgba(255, 255, 255, 0.1)",
  },
  syncActionText: {
    fontFamily: theme.fonts.mono,
    fontSize: 8.5,
    fontWeight: "700",
    color: theme.colors.amber,
    letterSpacing: 0.8,
  },

  // ── Hero Bento Double Bezel ──
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
  pulseDot: {
    width: 6,
    height: 6,
    borderRadius: 3,
    backgroundColor: theme.colors.emerald,
  },
  bentoDot: {
    width: 6,
    height: 6,
    borderRadius: 3,
    backgroundColor: theme.colors.emerald,
  },
  bentoAmberDot: {
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
  bentoActionsRow: {
    flexDirection: "row",
    gap: 6,
  },
  quickActionPill: {
    backgroundColor: "rgba(255, 255, 255, 0.08)",
    borderWidth: 1,
    borderColor: "rgba(255, 255, 255, 0.15)",
    paddingHorizontal: 8,
    paddingVertical: 3,
    borderRadius: 6,
  },
  quickActionPillText: {
    fontFamily: theme.fonts.mono,
    fontSize: 8.5,
    color: theme.colors.boneWhite,
    fontWeight: "700",
    letterSpacing: 0.5,
  },
  refreshPill: {
    backgroundColor: "#141414",
    borderWidth: 1,
    borderColor: "rgba(255, 255, 255, 0.06)",
    paddingHorizontal: 8,
    paddingVertical: 3,
    borderRadius: 6,
  },
  refreshPillText: {
    fontFamily: theme.fonts.mono,
    fontSize: 8.5,
    color: theme.colors.textMuted,
    letterSpacing: 0.5,
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
    fontSize: 9,
    color: theme.colors.textMuted,
    letterSpacing: 0.8,
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
    fontSize: 30,
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

  // ── Operating Vaults 2x2 Grid (No Text Overflows) ──
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

  // ── Peer Tabs Deck ──
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

  peerRosterSection: {
    gap: 6,
    paddingTop: 10,
    borderTopWidth: 1,
    borderTopColor: "rgba(255, 255, 255, 0.04)",
  },
  peerRosterLabel: {
    fontFamily: theme.fonts.mono,
    fontSize: 9,
    fontWeight: "700",
    color: theme.colors.textMuted,
    letterSpacing: 0.8,
    marginBottom: 4,
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

  // ── Transaction Pods ──
  txnPodOuter: {
    backgroundColor: "#151515",
    borderRadius: 10,
    borderWidth: 1,
    borderColor: "rgba(255, 255, 255, 0.05)",
    padding: 10,
    marginBottom: 6,
  },
  txnPodInner: {
    flexDirection: "row",
    alignItems: "center",
    gap: 10,
  },
  txnTypeIconWrap: {
    width: 26,
    height: 26,
    borderRadius: 13,
    backgroundColor: "#141414",
    borderWidth: 1,
    borderColor: "rgba(255, 255, 255, 0.08)",
    alignItems: "center",
    justifyContent: "center",
  },
  txnTypeGlyph: {
    fontFamily: theme.fonts.mono,
    fontSize: 13,
    fontWeight: "700",
  },
  txnBodyCol: {
    flex: 1,
    gap: 2,
  },
  txnDescText: {
    fontFamily: theme.fonts.sans,
    fontSize: 12.5,
    fontWeight: "600",
    color: theme.colors.boneWhite,
  },
  txnMetaRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: 5,
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
    fontSize: 12.5,
    fontWeight: "700",
  },
  emptyText: {
    fontFamily: theme.fonts.mono,
    fontSize: 10,
    color: theme.colors.textMuted,
    textAlign: "center",
    paddingVertical: 12,
  },

  // Modal
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
  btnDisabled: {
    opacity: 0.5,
  },
});
