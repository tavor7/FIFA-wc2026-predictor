import { StyleSheet, View } from "react-native";
import { colors, spacing } from "@/constants/theme";

export function SkeletonCard() {
  return (
    <View style={styles.card}>
      <View style={styles.lineShort} />
      <View style={styles.row}>
        <View style={styles.block} />
        <View style={styles.score} />
        <View style={styles.block} />
      </View>
      <View style={styles.lineFull} />
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: colors.surface,
    borderRadius: 14,
    borderWidth: 1,
    borderColor: colors.border,
    padding: spacing.md,
    marginBottom: spacing.sm,
    opacity: 0.7,
  },
  lineShort: {
    height: 10,
    width: "45%",
    backgroundColor: colors.border,
    borderRadius: 4,
    marginBottom: spacing.sm,
  },
  lineFull: {
    height: 8,
    width: "100%",
    backgroundColor: colors.border,
    borderRadius: 4,
    marginTop: spacing.sm,
  },
  row: { flexDirection: "row", alignItems: "center", gap: spacing.sm },
  block: { flex: 1, height: 40, backgroundColor: colors.border, borderRadius: 8 },
  score: { width: 48, height: 32, backgroundColor: colors.border, borderRadius: 6 },
});
