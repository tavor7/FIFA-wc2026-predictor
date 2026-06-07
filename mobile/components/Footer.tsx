import { StyleSheet, Text, View } from "react-native";
import { AUTHOR, DISCLAIMER_FULL, colors, spacing } from "@/constants/theme";

export function Footer() {
  return (
    <View style={styles.footer}>
      <Text style={styles.credit}>Designed by {AUTHOR}</Text>
      <Text style={styles.disclaimer}>{DISCLAIMER_FULL}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  footer: {
    marginTop: spacing.xl,
    paddingTop: spacing.lg,
    borderTopWidth: 1,
    borderTopColor: colors.border,
    alignItems: "center",
    paddingBottom: spacing.xl,
  },
  credit: {
    color: colors.textMuted,
    fontSize: 13,
    fontWeight: "600",
    marginBottom: spacing.sm,
  },
  disclaimer: {
    color: colors.textDim,
    fontSize: 11,
    lineHeight: 16,
    textAlign: "center",
    maxWidth: 320,
  },
});
