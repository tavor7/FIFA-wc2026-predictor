import { useCallback, useEffect, useState } from "react";
import {
  ActivityIndicator,
  FlatList,
  RefreshControl,
  StyleSheet,
  Text,
  View,
} from "react-native";
import { DisclaimerBanner } from "@/components/DisclaimerBanner";
import { Footer } from "@/components/Footer";
import { api, formatDate } from "@/services/api";
import { colors, spacing } from "@/constants/theme";
import type { Match } from "@/types";

export default function ResultsScreen() {
  const [matches, setMatches] = useState<Match[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    try {
      setMatches(await api.recent());
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  if (loading) {
    return (
      <View style={styles.center}>
        <ActivityIndicator color={colors.text} />
      </View>
    );
  }

  return (
    <FlatList
      style={styles.list}
      contentContainerStyle={styles.content}
      data={matches}
      keyExtractor={(m) => String(m.id)}
      refreshControl={
        <RefreshControl refreshing={refreshing} onRefresh={() => { setRefreshing(true); load(); }} tintColor={colors.text} />
      }
      ListHeaderComponent={<DisclaimerBanner />}
      ListEmptyComponent={<Text style={styles.empty}>No results yet.</Text>}
      renderItem={({ item }) => (
        <View style={styles.row}>
          <View style={styles.info}>
            <Text style={styles.teams} numberOfLines={1}>
              {item.home_team} vs {item.away_team}
            </Text>
            <Text style={styles.date}>{formatDate(item.date)}</Text>
          </View>
          <Text style={styles.score}>
            {item.home_goals ?? "–"}–{item.away_goals ?? "–"}
          </Text>
        </View>
      )}
      ListFooterComponent={<Footer />}
    />
  );
}

const styles = StyleSheet.create({
  list: { flex: 1, backgroundColor: colors.bg },
  content: { padding: spacing.md },
  center: { flex: 1, justifyContent: "center", alignItems: "center", backgroundColor: colors.bg },
  row: {
    flexDirection: "row",
    alignItems: "center",
    backgroundColor: colors.surface,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: colors.border,
    padding: spacing.md,
    marginBottom: spacing.sm,
  },
  info: { flex: 1 },
  teams: { color: colors.text, fontSize: 14, fontWeight: "600" },
  date: { color: colors.textMuted, fontSize: 11, marginTop: 2 },
  score: { color: colors.text, fontSize: 16, fontWeight: "700" },
  empty: { color: colors.textMuted, textAlign: "center", padding: spacing.xl },
});
