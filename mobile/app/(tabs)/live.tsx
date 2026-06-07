import { useCallback, useEffect, useState } from "react";
import {
  FlatList,
  RefreshControl,
  StyleSheet,
  Text,
  View,
} from "react-native";
import { MatchCard } from "@/components/MatchCard";
import { SkeletonCard } from "@/components/SkeletonCard";
import { DisclaimerBanner } from "@/components/DisclaimerBanner";
import { Footer } from "@/components/Footer";
import { api } from "@/services/api";
import { colors, spacing } from "@/constants/theme";
import type { Match } from "@/types";

export default function LiveScreen() {
  const [matches, setMatches] = useState<Match[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    try {
      setMatches(await api.live());
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
      <View style={styles.content}>
        <DisclaimerBanner />
        <SkeletonCard />
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
        <RefreshControl
          refreshing={refreshing}
          onRefresh={() => {
            setRefreshing(true);
            load();
          }}
          tintColor={colors.text}
        />
      }
      ListHeaderComponent={<DisclaimerBanner />}
      ListEmptyComponent={
        <Text style={styles.empty}>No live matches right now.</Text>
      }
      renderItem={({ item }) => <MatchCard match={item} />}
      ListFooterComponent={<Footer />}
    />
  );
}

const styles = StyleSheet.create({
  list: { flex: 1, backgroundColor: colors.bg },
  content: { padding: spacing.md },
  empty: { color: colors.textMuted, textAlign: "center", padding: spacing.xl },
});
