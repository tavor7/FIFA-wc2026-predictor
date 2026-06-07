import { Tabs } from "expo-router";
import { Text, View, StyleSheet } from "react-native";
import { AUTHOR, colors } from "@/constants/theme";

export default function TabLayout() {
  return (
    <Tabs
      screenOptions={{
        headerStyle: { backgroundColor: colors.bg },
        headerTintColor: colors.text,
        tabBarStyle: {
          backgroundColor: colors.surface,
          borderTopColor: colors.border,
          height: 56,
          paddingBottom: 8,
        },
        tabBarActiveTintColor: colors.text,
        tabBarInactiveTintColor: colors.textMuted,
        tabBarLabelStyle: { fontSize: 11, fontWeight: "600" },
      }}
    >
      <Tabs.Screen
        name="index"
        options={{
          title: "World Cup 2026",
          headerTitle: () => (
            <View>
              <Text style={styles.title}>World Cup 2026</Text>
              <Text style={styles.sub}>Designed by {AUTHOR}</Text>
            </View>
          ),
          tabBarLabel: "Matches",
        }}
      />
      <Tabs.Screen name="live" options={{ title: "Live", tabBarLabel: "Live" }} />
      <Tabs.Screen name="results" options={{ title: "Results", tabBarLabel: "Results" }} />
    </Tabs>
  );
}

const styles = StyleSheet.create({
  title: { color: colors.text, fontSize: 17, fontWeight: "700" },
  sub: { color: colors.textDim, fontSize: 11, marginTop: 1 },
});
