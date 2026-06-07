import { useCallback, useEffect, useState } from "react";
import {
  ActivityIndicator,
  FlatList,
  Pressable,
  RefreshControl,
  StyleSheet,
  Text,
  View,
} from "react-native";
import { MatchCard } from "@/components/MatchCard";
import { DisclaimerBanner } from "@/components/DisclaimerBanner";
import { Footer } from "@/components/Footer";
import { api } from "@/services/api";
import { colors, spacing } from "@/constants/theme";
import type { Match, Stats } from "@/types";

export default function MatchesScreen() {
  const [matches, setMatches] = useState<Match[]>([]);
  const [stats, setStats] = useState<Stats | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async (refresh = false) => {
    try {
      setError(null);
      if (refresh) setRefreshing(true);
      else setLoading(true);
      await api.bootstrap().catch(() => null);
      const [m, s] = await Promise.all([api.upcoming(), api.stats()]);
      setMatches(m);
      setStats(s);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load");
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const onRefresh = async () => {
    setRefreshing(true);
    try {
      await api.refresh();
      await load(true);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Refresh failed");
      setRefreshing(false);
    }
  };

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
        <RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={colors.text} />
      }
      ListHeaderComponent={
        <>
          <DisclaimerBanner />
          {stats && (
            <View style={styles.stats}>
              <Stat label="Upcoming" value={stats.upcoming} />
              <Stat label="Live" value={stats.live} />
              <Stat label="Picks" value={stats.predictions} />
            </View>
          )}
          {error && (
            <View style={styles.errorBox}>
              <Text style={styles.errorText}>{error}</Text>
              <Pressable onPress={() => load()}>
                <Text style={styles.retry}>Retry</Text>
              </Pressable>
            </View>
          )}
          {!matches.length && !error && (
            <Text style={styles.empty}>No matches. Pull down to refresh.</Text>
          )}
        </>
      }
      renderItem={({ item }) => <MatchCard match={item} />}
      ListFooterComponent={<Footer />}
    />
  );
}

function Stat({ label, value }: { label: string; value: number }) {
  return (
    <View style={styles.stat}>
      <Text style={styles.statVal}>{value}</Text>
      <Text style={styles.statLbl}>{label}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  list: { flex: 1, backgroundColor: colors.bg },
  content: { padding: spacing.md, paddingBottom: spacing.xl },
  center: { flex: 1, justifyContent: "center", alignItems: "center", backgroundColor: colors.bg },
  stats: {
    flexDirection: "row",
    gap: spacing.sm,
    marginBottom: spacing.md,
  },
  stat: {
    flex: 1,
    backgroundColor: colors.surface,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: colors.border,
    padding: spacing.sm + 4,
    alignItems: "center",
  },
  statVal: { fontSize: 20, fontWeight: "700", color: colors.text },
  statLbl: { fontSize: 10, color: colors.textMuted, marginTop: 2, fontWeight: "500" },
  errorBox: {
    backgroundColor: colors.surface,
    padding: spacing.md,
    borderRadius: 12,
    marginBottom: spacing.md,
  },
  errorText: { color: colors.live, fontSize: 13, marginBottom: spacing.sm },
  retry: { color: colors.text, fontWeight: "600" },
  empty: { color: colors.textMuted, textAlign: "center", padding: spacing.xl },
});
