import { StyleSheet, View, Text } from "react-native";
import { colors, spacing } from "@/constants/theme";

interface Props {
  home: number;
  draw: number;
  away: number;
}

export function OutcomeBar({ home, draw, away }: Props) {
  const total = home + draw + away || 1;
  const hp = (home / total) * 100;
  const dp = (draw / total) * 100;
  const ap = (away / total) * 100;

  return (
    <View style={styles.wrap}>
      <View style={styles.bar}>
        <View style={[styles.segment, styles.home, { flex: hp }]} />
        <View style={[styles.segment, styles.draw, { flex: dp }]} />
        <View style={[styles.segment, styles.away, { flex: ap }]} />
      </View>
      <View style={styles.labels}>
        <Text style={styles.label}>Home {(home * 100).toFixed(0)}%</Text>
        <Text style={styles.label}>Draw {(draw * 100).toFixed(0)}%</Text>
        <Text style={styles.label}>Away {(away * 100).toFixed(0)}%</Text>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { marginTop: spacing.sm },
  bar: {
    flexDirection: "row",
    height: 4,
    borderRadius: 99,
    overflow: "hidden",
    backgroundColor: "rgba(255,255,255,0.06)",
  },
  segment: { height: 4 },
  home: { backgroundColor: colors.barHome },
  draw: { backgroundColor: colors.barDraw },
  away: { backgroundColor: colors.barAway },
  labels: {
    flexDirection: "row",
    justifyContent: "space-between",
    marginTop: 6,
  },
  label: {
    fontSize: 11,
    color: colors.textMuted,
    fontWeight: "500",
  },
});
