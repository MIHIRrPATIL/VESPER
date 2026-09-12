import React from "react";
import { StyleSheet, View, Text, Image, ViewStyle } from "react-native";
import { theme } from "../styles/theme";

interface VesperLogoProps {
  size?: number;
  color?: string;
  showWordmark?: boolean;
  style?: ViewStyle;
}

/**
 * Official VESPER Brand Emblem & Wordmark.
 * Renders the custom geometric faceted aerospace "V" emblem
 * paired with the refined editorial italic wordmark.
 */
export const VesperLogo: React.FC<VesperLogoProps> = ({
  size = 24,
  color = theme.colors.textPrimary,
  showWordmark = true,
  style,
}) => {
  return (
    <View style={[styles.container, style]}>
      <Image
        source={require("../../assets/vesper-logo-transparent.png")}
        style={{ width: size, height: size }}
        resizeMode="contain"
      />
      {showWordmark && (
        <Text style={[styles.wordmark, { color }]}>vesper</Text>
      )}
    </View>
  );
};

const styles = StyleSheet.create({
  container: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
  },
  wordmark: {
    fontFamily: theme.fonts.serif,
    fontSize: 22,
    fontStyle: "italic",
    fontWeight: "400",
    letterSpacing: -0.5,
  },
});
