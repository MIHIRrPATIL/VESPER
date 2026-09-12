import React, { useEffect, useRef } from "react";
import {
  StyleSheet,
  Text,
  View,
  TouchableOpacity,
  Animated,
} from "react-native";
import { theme } from "../styles/theme";

export interface ProactiveAdvisory {
  id: string;
  title: string;
  severity: "CRITICAL" | "HIGH" | "ADVISORY" | "INFO";
  message: string;
  recommendation?: string;
  timestamp: number;
}

interface ProactiveAdvisoryModalProps {
  advisory: ProactiveAdvisory | null;
  onDismiss: (id: string) => void;
  onAcknowledge: (id: string) => void;
}

export const ProactiveAdvisoryModal: React.FC<ProactiveAdvisoryModalProps> = ({
  advisory,
  onDismiss,
  onAcknowledge,
}) => {
  const slideAnim = useRef(new Animated.Value(-120)).current;
  const opacityAnim = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    if (advisory) {
      Animated.parallel([
        Animated.spring(slideAnim, {
          toValue: 0,
          tension: 65,
          friction: 10,
          useNativeDriver: true,
        }),
        Animated.timing(opacityAnim, {
          toValue: 1,
          duration: 250,
          useNativeDriver: true,
        }),
      ]).start();
    } else {
      Animated.parallel([
        Animated.timing(slideAnim, {
          toValue: -120,
          duration: 200,
          useNativeDriver: true,
        }),
        Animated.timing(opacityAnim, {
          toValue: 0,
          duration: 180,
          useNativeDriver: true,
        }),
      ]).start();
    }
  }, [advisory]);

  if (!advisory) return null;

  const isCritical = advisory.severity === "CRITICAL" || advisory.severity === "HIGH";
  const badgeColor = isCritical ? theme.colors.accent : theme.colors.warning;

  return (
    <Animated.View
      style={[
        styles.container,
        {
          opacity: opacityAnim,
          transform: [{ translateY: slideAnim }],
        },
      ]}
    >
      <View style={[styles.card, { borderColor: badgeColor }]}>
        <View style={styles.topRow}>
          <View style={styles.badgeRow}>
            <View style={[styles.pulseDot, { backgroundColor: badgeColor }]} />
            <Text style={[styles.badgeText, { color: badgeColor }]}>
              PROACTIVE ADVISORY // {advisory.severity}
            </Text>
          </View>
          <TouchableOpacity onPress={() => onDismiss(advisory.id)}>
            <Text style={styles.dismissGlyph}>×</Text>
          </TouchableOpacity>
        </View>

        <Text style={styles.title}>{advisory.title}</Text>
        <Text style={styles.message}>{advisory.message}</Text>

        {advisory.recommendation && (
          <View style={styles.recBox}>
            <Text style={styles.recLabel}>RECOMMENDATION</Text>
            <Text style={styles.recText}>{advisory.recommendation}</Text>
          </View>
        )}

        <View style={styles.actionRow}>
          <TouchableOpacity
            style={styles.ackButton}
            onPress={() => onAcknowledge(advisory.id)}
          >
            <Text style={styles.ackButtonText}>ACKNOWLEDGE</Text>
          </TouchableOpacity>
          <TouchableOpacity
            style={styles.dismissButton}
            onPress={() => onDismiss(advisory.id)}
          >
            <Text style={styles.dismissButtonText}>DISMISS</Text>
          </TouchableOpacity>
        </View>
      </View>
    </Animated.View>
  );
};

const styles = StyleSheet.create({
  container: {
    position: "absolute",
    top: 10,
    left: 14,
    right: 14,
    zIndex: 9999,
  },
  card: {
    backgroundColor: theme.colors.cardElevated,
    borderRadius: theme.radii.md,
    borderWidth: 1,
    padding: theme.spacing.md,
    shadowColor: "#000000",
    shadowOffset: { width: 0, height: 8 },
    shadowOpacity: 0.6,
    shadowRadius: 16,
    elevation: 10,
  },
  topRow: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    marginBottom: theme.spacing.xs,
  },
  badgeRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: theme.spacing.xs,
  },
  pulseDot: {
    width: 6,
    height: 6,
    borderRadius: 3,
  },
  badgeText: {
    fontFamily: theme.fonts.mono,
    fontSize: 10,
    fontWeight: "700",
    letterSpacing: 1.2,
  },
  dismissGlyph: {
    fontFamily: theme.fonts.mono,
    fontSize: 18,
    color: theme.colors.textMuted,
    lineHeight: 18,
    paddingHorizontal: 4,
  },
  title: {
    fontFamily: theme.fonts.sans,
    fontSize: 14,
    fontWeight: "700",
    color: theme.colors.textPrimary,
    marginBottom: 4,
  },
  message: {
    fontFamily: theme.fonts.sans,
    fontSize: 12,
    lineHeight: 18,
    color: theme.colors.textSecondary,
  },
  recBox: {
    backgroundColor: theme.colors.cardSubtle,
    borderRadius: theme.radii.xs,
    padding: theme.spacing.sm,
    marginTop: theme.spacing.sm,
    borderLeftWidth: 2,
    borderLeftColor: theme.colors.warning,
  },
  recLabel: {
    fontFamily: theme.fonts.mono,
    fontSize: 9,
    letterSpacing: 1,
    color: theme.colors.textMuted,
    marginBottom: 2,
  },
  recText: {
    fontFamily: theme.fonts.sans,
    fontSize: 11,
    color: theme.colors.textPrimary,
    lineHeight: 16,
  },
  actionRow: {
    flexDirection: "row",
    justifyContent: "flex-end",
    gap: theme.spacing.sm,
    marginTop: theme.spacing.md,
  },
  ackButton: {
    backgroundColor: theme.colors.textPrimary,
    borderRadius: theme.radii.xs,
    paddingHorizontal: theme.spacing.md,
    paddingVertical: theme.spacing.xs,
  },
  ackButtonText: {
    fontFamily: theme.fonts.mono,
    fontSize: 10,
    fontWeight: "700",
    letterSpacing: 1,
    color: theme.colors.bg,
  },
  dismissButton: {
    backgroundColor: "transparent",
    borderWidth: 1,
    borderColor: theme.colors.border,
    borderRadius: theme.radii.xs,
    paddingHorizontal: theme.spacing.md,
    paddingVertical: theme.spacing.xs,
  },
  dismissButtonText: {
    fontFamily: theme.fonts.mono,
    fontSize: 10,
    letterSpacing: 1,
    color: theme.colors.textMuted,
  },
});
