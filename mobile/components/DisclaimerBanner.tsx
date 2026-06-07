import { StyleSheet, Text, View } from "react-native";
import { DISCLAIMER_SHORT, colors, spacing } from "@/constants/theme";

export function DisclaimerBanner() {
  return (
    <View style={styles.banner}>
      <Text style={styles.text}>
        <Text style={styles.bold}>Research only. </Text>
        {DISCLAIMER_SHORT}
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  banner: {
    backgroundColor: colors.surface,
    borderRadius: 10,
    borderWidth: 1,
    borderColor: colors.border,
    padding: spacing.sm + 2,
    marginBottom: spacing.md,
  },
  text: {
    color: colors.textMuted,
    fontSize: 11,
    lineHeight: 16,
  },
  bold: {
    color: colors.text,
    fontWeight: "600",
  },
});
