import { Pressable, StyleSheet, Text, View } from "react-native";
import { useRouter } from "expo-router";
import { OutcomeBar } from "./OutcomeBar";
import { colors, spacing } from "@/constants/theme";
import { formatDate, isLive } from "@/services/api";
import type { Match } from "@/types";

interface Props {
  match: Match;
  onPress?: () => void;
}

export function MatchCard({ match, onPress }: Props) {
  const router = useRouter();
  const live = isLive(match.status);
  const pred = match.prediction;
  const top = pred?.top_scorelines?.[0];
  const pickHome = Math.round(pred?.predicted_home_goals ?? top?.home ?? 0);
  const pickAway = Math.round(pred?.predicted_away_goals ?? top?.away ?? 0);
  const pickPct = top?.probability ?? 0;
  const exactDiffers =
    top && (top.home !== pickHome || top.away !== pickAway);

  const hasScore = match.home_goals != null && match.away_goals != null;
  const center = hasScore
    ? `${match.home_goals}–${match.away_goals}`
    : `${pickHome}–${pickAway}`;

  const handlePress = () => {
    if (onPress) onPress();
    else router.push(`/match/${match.id}`);
  };

  return (
    <Pressable
      style={({ pressed }) => [styles.card, live && styles.live, pressed && styles.pressed]}
      onPress={handlePress}
    >
      <View style={styles.meta}>
        {live ? (
          <Text style={styles.liveBadge}>● LIVE</Text>
        ) : (
          <Text style={styles.upcomingBadge}>UPCOMING</Text>
        )}
        <Text style={styles.date}>{formatDate(match.date)}</Text>
      </View>

      <View style={styles.row}>
        <Text style={[styles.team, styles.left]} numberOfLines={2}>
          {match.home_team}
        </Text>
        <View style={styles.center}>
          <Text style={styles.score}>{center}</Text>
          <Text style={styles.pickLabel}>{hasScore ? "Score" : "Pick"}</Text>
          {!hasScore && exactDiffers && top && (
            <Text style={styles.conf}>
              Exact {top.home}–{top.away}: {(top.probability * 100).toFixed(0)}%
            </Text>
          )}
          {!hasScore && !exactDiffers && pickPct > 0 && (
            <Text style={styles.conf}>{(pickPct * 100).toFixed(0)}% likely</Text>
          )}
        </View>
        <Text style={[styles.team, styles.right]} numberOfLines={2}>
          {match.away_team}
        </Text>
      </View>

      {pred && (
        <OutcomeBar
          home={pred.home_win_prob}
          draw={pred.draw_prob}
          away={pred.away_win_prob}
        />
      )}
    </Pressable>
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: colors.surface,
    borderRadius: 16,
    borderWidth: 1,
    borderColor: colors.border,
    padding: spacing.md,
    marginBottom: spacing.sm + 4,
  },
  live: {
    borderColor: "rgba(239,68,68,0.35)",
  },
  pressed: {
    opacity: 0.85,
  },
  meta: {
    flexDirection: "row",
    justifyContent: "space-between",
    marginBottom: spacing.md,
  },
  liveBadge: {
    fontSize: 10,
    fontWeight: "700",
    color: colors.live,
    letterSpacing: 0.5,
  },
  upcomingBadge: {
    fontSize: 10,
    fontWeight: "600",
    color: colors.textMuted,
    letterSpacing: 0.5,
  },
  date: {
    fontSize: 11,
    color: colors.textMuted,
  },
  row: {
    flexDirection: "row",
    alignItems: "center",
  },
  team: {
    flex: 1,
    fontSize: 15,
    fontWeight: "600",
    color: colors.text,
    lineHeight: 20,
  },
  left: { textAlign: "right", paddingRight: spacing.sm },
  right: { textAlign: "left", paddingLeft: spacing.sm },
  center: { alignItems: "center", minWidth: 72 },
  score: {
    fontSize: 26,
    fontWeight: "700",
    color: colors.text,
    letterSpacing: -1,
  },
  pickLabel: {
    fontSize: 10,
    color: colors.textMuted,
    fontWeight: "600",
    letterSpacing: 1,
    marginTop: 2,
  },
  conf: {
    fontSize: 12,
    color: colors.textMuted,
    marginTop: 2,
  },
});
