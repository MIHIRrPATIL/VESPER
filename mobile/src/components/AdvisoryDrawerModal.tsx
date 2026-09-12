import React, { useEffect, useRef } from "react";
import {
  StyleSheet,
  Text,
  View,
  TouchableOpacity,
  ScrollView,
  Animated,
  Dimensions,
  Modal,
  TouchableWithoutFeedback,
} from "react-native";
import { theme } from "../styles/theme";
import { ProactiveAlert } from "../types/vesper";

const { height: SCREEN_HEIGHT } = Dimensions.get("window");

interface AdvisoryDrawerModalProps {
  visible: boolean;
  advisories: ProactiveAlert[];
  onClose: () => void;
  onDismiss: (id: string) => void;
  onConfirm: (id: string) => void;
  onDismissAll: () => void;
}

function formatRelativeTime(ts: number): string {
  const diffSec = Math.max(0, Math.floor((Date.now() - ts) / 1000));
  if (diffSec < 60) return "JUST NOW";
  const diffMin = Math.floor(diffSec / 60);
  if (diffMin < 60) return `${diffMin}M AGO`;
  const diffHours = Math.floor(diffMin / 60);
  return `${diffHours}H AGO`;
}

export const AdvisoryDrawerModal: React.FC<AdvisoryDrawerModalProps> = ({
  visible,
  advisories,
  onClose,
  onDismiss,
  onConfirm,
  onDismissAll,
}) => {
  const slideAnim = useRef(new Animated.Value(SCREEN_HEIGHT)).current;
  const backdropAnim = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    if (visible) {
      Animated.parallel([
        Animated.spring(slideAnim, {
          toValue: 0,
          tension: 65,
          friction: 11,
          useNativeDriver: true,
        }),
        Animated.timing(backdropAnim, {
          toValue: 1,
          duration: 220,
          useNativeDriver: true,
        }),
      ]).start();
    } else {
      Animated.parallel([
        Animated.timing(slideAnim, {
          toValue: SCREEN_HEIGHT,
          duration: 200,
          useNativeDriver: true,
        }),
        Animated.timing(backdropAnim, {
          toValue: 0,
          duration: 180,
          useNativeDriver: true,
        }),
      ]).start();
    }
  }, [visible]);

  if (!visible && advisories.length === 0) {
    return null;
  }

  const activeCount = advisories.length;

  return (
    <Modal
      transparent
      visible={visible}
      animationType="none"
      onRequestClose={onClose}
    >
      <TouchableWithoutFeedback onPress={onClose}>
        <Animated.View
          style={[styles.backdrop, { opacity: backdropAnim }]}
        />
      </TouchableWithoutFeedback>

      <Animated.View
        style={[
          styles.sheetContainer,
          { transform: [{ translateY: slideAnim }] },
        ]}
      >
        {/* Handle Bar */}
        <View style={styles.handleBarWrapper}>
          <View style={styles.handleBar} />
        </View>

        {/* Header Strip */}
        <View style={styles.header}>
          <View style={styles.headerLeft}>
            <View style={styles.titleRow}>
              <Text style={styles.headerTitle}>CLUSTER ADVISORY SENTRY</Text>
              {activeCount > 0 && (
                <View style={styles.countBadge}>
                  <Text style={styles.countBadgeText}>{activeCount} ACTIVE</Text>
                </View>
              )}
            </View>
            <Text style={styles.headerSubtitle}>
              Proactive sentry recommendations and staging actions
            </Text>
          </View>

          <View style={styles.headerActions}>
            {activeCount > 0 && (
              <TouchableOpacity
                style={styles.dismissAllButton}
                onPress={onDismissAll}
                activeOpacity={0.7}
              >
                <Text style={styles.dismissAllText}>CLEAR ALL</Text>
              </TouchableOpacity>
            )}
            <TouchableOpacity
              style={styles.closeButton}
              onPress={onClose}
              activeOpacity={0.7}
            >
              <Text style={styles.closeGlyph}>✕</Text>
            </TouchableOpacity>
          </View>
        </View>

        {/* Scrollable Advisories List */}
        <ScrollView
          style={styles.advisoryList}
          contentContainerStyle={styles.advisoryListContent}
          showsVerticalScrollIndicator={false}
        >
          {activeCount === 0 ? (
            <View style={styles.emptyContainer}>
              <View style={styles.emptyIconCircle}>
                <View style={styles.radarDot} />
              </View>
              <Text style={styles.emptyLabel}>ALL SYSTEMS NOMINAL</Text>
              <Text style={styles.emptySubtitle}>
                Cluster proactive sentry is armed. No pending intervention requests or staged advisories.
              </Text>
            </View>
          ) : (
            advisories.map((advisory, idx) => {
              const urgencyKey = (advisory.urgency || "normal").toLowerCase();
              const isCritical = urgencyKey === "critical" || urgencyKey === "urgent";
              const isHigh = urgencyKey === "high";

              let badgeStyle = styles.badgeNormal;
              let badgeTextStyle = styles.badgeTextNormal;
              let dotColor = "#93C5FD";
              let urgencyLabel = "ADVISORY";

              if (isCritical) {
                badgeStyle = styles.badgeCritical;
                badgeTextStyle = styles.badgeTextCritical;
                dotColor = "#FCA5A5";
                urgencyLabel = "CRITICAL";
              } else if (isHigh) {
                badgeStyle = styles.badgeHigh;
                badgeTextStyle = styles.badgeTextHigh;
                dotColor = "#FCD34D";
                urgencyLabel = "HIGH PRIORITY";
              }

              const appOrigin = (advisory.appName || advisory.domain || "VESPER CLUSTER").toUpperCase();
              const hasStagedAction = Boolean(advisory.stagedActionId || advisory.actionRequired);

              return (
                <View
                  key={advisory.id || `adv_${idx}`}
                  style={[
                    styles.advisoryCard,
                    isCritical && styles.advisoryCardCritical,
                  ]}
                >
                  {/* Top Meta Strip */}
                  <View style={styles.cardHeaderRow}>
                    <View style={styles.metaLeft}>
                      <View style={[styles.urgencyBadge, badgeStyle]}>
                        <View style={[styles.urgencyDot, { backgroundColor: dotColor }]} />
                        <Text style={[styles.urgencyText, badgeTextStyle]}>
                          {urgencyLabel}
                        </Text>
                      </View>
                      <Text style={styles.originText}>{appOrigin}</Text>
                    </View>

                    <Text style={styles.timeText}>
                      {formatRelativeTime(advisory.timestamp)}
                    </Text>
                  </View>

                  {/* Title & Body */}
                  <View style={styles.contentBlock}>
                    <Text style={styles.cardTitle}>{advisory.title}</Text>
                    <Text style={styles.cardBody}>{advisory.body}</Text>
                  </View>

                  {/* Staged Action / Recommendation Well */}
                  {advisory.stagedAction && (
                    <View style={styles.recommendationWell}>
                      <View style={styles.recHeaderRow}>
                        <Text style={styles.recHeaderLabel}>STAGED EXECUTION</Text>
                        <Text style={styles.recActionDomain}>
                          {String(advisory.stagedAction.action || advisory.stagedAction.domain || "SYSTEM").toUpperCase()}
                        </Text>
                      </View>
                      <Text style={styles.recText}>
                        {typeof advisory.stagedAction === "object"
                          ? JSON.stringify(advisory.stagedAction.params || advisory.stagedAction, null, 2)
                          : String(advisory.stagedAction)}
                      </Text>
                    </View>
                  )}

                  {/* Action Buttons Bar */}
                  <View style={styles.cardActionsRow}>
                    <TouchableOpacity
                      style={styles.cancelBtn}
                      onPress={() => onDismiss(advisory.id)}
                      activeOpacity={0.7}
                    >
                      <Text style={styles.cancelBtnText}>DISMISS / CANCEL</Text>
                    </TouchableOpacity>

                    {hasStagedAction && (
                      <TouchableOpacity
                        style={styles.confirmBtn}
                        onPress={() => onConfirm(advisory.id)}
                        activeOpacity={0.7}
                      >
                        <Text style={styles.confirmBtnText}>AUTHORIZE ACTION ›</Text>
                      </TouchableOpacity>
                    )}
                  </View>
                </View>
              );
            })
          )}
        </ScrollView>
      </Animated.View>
    </Modal>
  );
};

const styles = StyleSheet.create({
  backdrop: {
    ...(StyleSheet.absoluteFill as any),
    backgroundColor: "rgba(0, 0, 0, 0.72)",
  },
  sheetContainer: {
    position: "absolute",
    bottom: 0,
    left: 0,
    right: 0,
    maxHeight: SCREEN_HEIGHT * 0.84,
    backgroundColor: "#111111",
    borderTopLeftRadius: 22,
    borderTopRightRadius: 22,
    borderTopWidth: 1,
    borderLeftWidth: 1,
    borderRightWidth: 1,
    borderColor: "rgba(255, 255, 255, 0.10)",
    paddingBottom: 28,
  },
  handleBarWrapper: {
    width: "100%",
    alignItems: "center",
    paddingTop: 10,
    paddingBottom: 6,
  },
  handleBar: {
    width: 38,
    height: 4,
    borderRadius: 2,
    backgroundColor: "rgba(255, 255, 255, 0.22)",
  },
  header: {
    flexDirection: "row",
    alignItems: "flex-start",
    justifyContent: "space-between",
    paddingHorizontal: 20,
    paddingVertical: 12,
    borderBottomWidth: 1,
    borderBottomColor: "rgba(255, 255, 255, 0.06)",
  },
  headerLeft: {
    flex: 1,
    marginRight: 12,
  },
  titleRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
  },
  headerTitle: {
    fontFamily: theme.fonts.sans,
    fontSize: 14,
    fontWeight: "700",
    color: theme.colors.boneWhite,
    letterSpacing: 1.1,
  },
  countBadge: {
    backgroundColor: "rgba(245, 158, 11, 0.15)",
    borderWidth: 1,
    borderColor: "rgba(245, 158, 11, 0.35)",
    paddingHorizontal: 6,
    paddingVertical: 2,
    borderRadius: 4,
  },
  countBadgeText: {
    fontFamily: theme.fonts.mono,
    fontSize: 9,
    color: theme.colors.amber,
    fontWeight: "700",
    letterSpacing: 0.5,
  },
  headerSubtitle: {
    fontFamily: theme.fonts.sans,
    fontSize: 11,
    color: theme.colors.textMuted,
    marginTop: 3,
  },
  headerActions: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
  },
  dismissAllButton: {
    paddingHorizontal: 9,
    paddingVertical: 5,
    borderRadius: 6,
    backgroundColor: "rgba(255, 255, 255, 0.05)",
    borderWidth: 1,
    borderColor: "rgba(255, 255, 255, 0.08)",
  },
  dismissAllText: {
    fontFamily: theme.fonts.mono,
    fontSize: 9,
    color: theme.colors.textMuted,
    fontWeight: "600",
    letterSpacing: 0.8,
  },
  closeButton: {
    width: 28,
    height: 28,
    borderRadius: 6,
    backgroundColor: "rgba(255, 255, 255, 0.05)",
    borderWidth: 1,
    borderColor: "rgba(255, 255, 255, 0.08)",
    alignItems: "center",
    justifyContent: "center",
  },
  closeGlyph: {
    fontFamily: theme.fonts.mono,
    fontSize: 12,
    color: theme.colors.boneWhite,
  },
  advisoryList: {
    maxHeight: SCREEN_HEIGHT * 0.70,
  },
  advisoryListContent: {
    padding: 16,
    gap: 12,
  },
  emptyContainer: {
    paddingVertical: 48,
    paddingHorizontal: 24,
    alignItems: "center",
    justifyContent: "center",
    borderRadius: 16,
    backgroundColor: "#161616",
    borderWidth: 1,
    borderColor: "rgba(255, 255, 255, 0.06)",
    marginVertical: 12,
  },
  emptyIconCircle: {
    width: 44,
    height: 44,
    borderRadius: 22,
    backgroundColor: "rgba(16, 185, 129, 0.10)",
    borderWidth: 1,
    borderColor: "rgba(16, 185, 129, 0.25)",
    alignItems: "center",
    justifyContent: "center",
    marginBottom: 14,
  },
  radarDot: {
    width: 10,
    height: 10,
    borderRadius: 5,
    backgroundColor: theme.colors.emerald,
  },
  emptyLabel: {
    fontFamily: theme.fonts.mono,
    fontSize: 12,
    fontWeight: "700",
    color: theme.colors.boneWhite,
    letterSpacing: 1.2,
    marginBottom: 6,
  },
  emptySubtitle: {
    fontFamily: theme.fonts.sans,
    fontSize: 12,
    color: theme.colors.textMuted,
    textAlign: "center",
    lineHeight: 18,
    maxWidth: 280,
  },
  advisoryCard: {
    backgroundColor: "#161616",
    borderRadius: 18,
    borderWidth: 1,
    borderColor: "rgba(255, 255, 255, 0.08)",
    padding: 16,
    gap: 12,
  },
  advisoryCardCritical: {
    borderColor: "rgba(239, 68, 68, 0.35)",
    backgroundColor: "#181414",
  },
  cardHeaderRow: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
  },
  metaLeft: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
  },
  urgencyBadge: {
    flexDirection: "row",
    alignItems: "center",
    paddingHorizontal: 7,
    paddingVertical: 3,
    borderRadius: 4,
    borderWidth: 1,
    gap: 5,
  },
  urgencyDot: {
    width: 5,
    height: 5,
    borderRadius: 2.5,
  },
  urgencyText: {
    fontFamily: theme.fonts.mono,
    fontSize: 9,
    fontWeight: "700",
    letterSpacing: 0.6,
  },
  badgeNormal: {
    backgroundColor: "rgba(96, 165, 250, 0.12)",
    borderColor: "rgba(96, 165, 250, 0.28)",
  },
  badgeTextNormal: {
    color: "#93C5FD",
  },
  badgeHigh: {
    backgroundColor: "rgba(245, 158, 11, 0.14)",
    borderColor: "rgba(245, 158, 11, 0.35)",
  },
  badgeTextHigh: {
    color: "#FCD34D",
  },
  badgeCritical: {
    backgroundColor: "rgba(239, 68, 68, 0.15)",
    borderColor: "rgba(239, 68, 68, 0.38)",
  },
  badgeTextCritical: {
    color: "#FCA5A5",
  },
  originText: {
    fontFamily: theme.fonts.mono,
    fontSize: 9,
    color: theme.colors.textMuted,
    letterSpacing: 0.6,
  },
  timeText: {
    fontFamily: theme.fonts.mono,
    fontSize: 9,
    color: theme.colors.textMuted,
  },
  contentBlock: {
    gap: 4,
  },
  cardTitle: {
    fontFamily: theme.fonts.sans,
    fontSize: 15,
    fontWeight: "700",
    color: theme.colors.boneWhite,
    letterSpacing: 0.2,
  },
  cardBody: {
    fontFamily: theme.fonts.sans,
    fontSize: 12.5,
    color: theme.colors.textSecondary,
    lineHeight: 18,
  },
  recommendationWell: {
    backgroundColor: "#1C1C1C",
    borderRadius: 12,
    borderWidth: 1,
    borderColor: "rgba(255, 255, 255, 0.05)",
    padding: 11,
    gap: 4,
  },
  recHeaderRow: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
  },
  recHeaderLabel: {
    fontFamily: theme.fonts.mono,
    fontSize: 9,
    color: theme.colors.textMuted,
    letterSpacing: 0.8,
  },
  recActionDomain: {
    fontFamily: theme.fonts.mono,
    fontSize: 8.5,
    color: theme.colors.amber,
    fontWeight: "700",
  },
  recText: {
    fontFamily: theme.fonts.mono,
    fontSize: 10.5,
    color: theme.colors.textSecondary,
    lineHeight: 15,
  },
  cardActionsRow: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "flex-end",
    gap: 8,
    paddingTop: 4,
    borderTopWidth: 1,
    borderTopColor: "rgba(255, 255, 255, 0.04)",
  },
  cancelBtn: {
    paddingHorizontal: 11,
    paddingVertical: 7,
    borderRadius: 7,
    backgroundColor: "rgba(255, 255, 255, 0.03)",
    borderWidth: 1,
    borderColor: "rgba(255, 255, 255, 0.09)",
  },
  cancelBtnText: {
    fontFamily: theme.fonts.mono,
    fontSize: 9.5,
    color: theme.colors.textMuted,
    fontWeight: "600",
    letterSpacing: 0.6,
  },
  confirmBtn: {
    paddingHorizontal: 13,
    paddingVertical: 7,
    borderRadius: 7,
    backgroundColor: "rgba(16, 185, 129, 0.16)",
    borderWidth: 1,
    borderColor: "rgba(16, 185, 129, 0.38)",
  },
  confirmBtnText: {
    fontFamily: theme.fonts.mono,
    fontSize: 9.5,
    color: "#A7F3D0",
    fontWeight: "700",
    letterSpacing: 0.6,
  },
});
