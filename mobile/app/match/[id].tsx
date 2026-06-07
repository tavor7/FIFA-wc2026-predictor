import { useEffect, useState } from "react";
import {
  ActivityIndicator,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from "react-native";
import { useLocalSearchParams } from "expo-router";
import { MatchCard } from "@/components/MatchCard";
import { DisclaimerBanner } from "@/components/DisclaimerBanner";
import { Footer } from "@/components/Footer";
import { api } from "@/services/api";
import { DISCLAIMER_SHORT, colors, spacing } from "@/constants/theme";
import type { Match } from "@/types";

export default function MatchDetailScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const [match, setMatch] = useState<Match | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!id) return;
    api.detail(Number(id)).then(setMatch).finally(() => setLoading(false));
  }, [id]);

  if (loading) {
    return (
      <View style={styles.center}>
        <ActivityIndicator color={colors.text} />
      </View>
    );
  }

  if (!match) {
    return (
      <View style={styles.center}>
        <Text style={styles.empty}>Match not found</Text>
      </View>
    );
  }

  const pred = match.prediction;
  const alts = pred?.top_scorelines?.slice(1, 5) ?? [];

  return (
    <ScrollView style={styles.scroll} contentContainerStyle={styles.content}>
      <DisclaimerBanner />
      <MatchCard match={match} onPress={() => {}} />

      {pred?.explanation && (
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Why this score?</Text>
          <Text style={styles.explain}>{pred.explanation}</Text>
          {alts.length > 0 && (
            <>
              <Text style={styles.altTitle}>Other likely scores</Text>
              <View style={styles.altRow}>
                {alts.map((s, i) => (
                  <View key={i} style={styles.altChip}>
                    <Text style={styles.altText}>
                      {s.home}–{s.away} · {(s.probability * 100).toFixed(0)}%
                    </Text>
                  </View>
                ))}
              </View>
            </>
          )}
          <Text style={styles.pickDisclaimer}>{DISCLAIMER_SHORT}</Text>
        </View>
      )}

      {match.injuries && match.injuries.length > 0 && (
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Injuries</Text>
          {match.injuries.map((inj, i) => (
            <Text key={i} style={styles.line}>
              {inj.player_name} ({inj.team}) — {inj.reason || inj.injury_type || "Out"}
            </Text>
          ))}
        </View>
      )}

      {match.lineups && match.lineups.length > 0 && (
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Lineups</Text>
          {[...new Set(match.lineups.map((l) => l.team))].map((team) => {
            const starters = match.lineups!.filter((l) => l.team === team && l.is_starting);
            return (
              <View key={team} style={{ marginBottom: spacing.sm }}>
                <Text style={styles.teamName}>{team}</Text>
                <Text style={styles.line}>{starters.map((s) => s.player_name).join(", ")}</Text>
              </View>
            );
          })}
        </View>
      )}

      <Footer />
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  scroll: { flex: 1, backgroundColor: colors.bg },
  content: { padding: spacing.md },
  center: { flex: 1, justifyContent: "center", alignItems: "center", backgroundColor: colors.bg },
  empty: { color: colors.textMuted },
  section: {
    backgroundColor: colors.surface,
    borderRadius: 14,
    borderWidth: 1,
    borderColor: colors.border,
    padding: spacing.md,
    marginBottom: spacing.md,
  },
  sectionTitle: {
    color: colors.text,
    fontSize: 14,
    fontWeight: "700",
    marginBottom: spacing.sm,
  },
  explain: { color: colors.textMuted, fontSize: 13, lineHeight: 20 },
  altTitle: { color: colors.textDim, fontSize: 11, marginTop: spacing.md, marginBottom: spacing.sm },
  altRow: { flexDirection: "row", flexWrap: "wrap", gap: 6 },
  altChip: {
    backgroundColor: "rgba(255,255,255,0.04)",
    borderRadius: 6,
    paddingHorizontal: 8,
    paddingVertical: 4,
  },
  altText: { color: colors.textMuted, fontSize: 12 },
  pickDisclaimer: { color: colors.textDim, fontSize: 10, marginTop: spacing.md, lineHeight: 14 },
  line: { color: colors.textMuted, fontSize: 13, marginBottom: 4 },
  teamName: { color: colors.text, fontWeight: "600", fontSize: 13, marginBottom: 2 },
});
