import "package:flutter/material.dart";

import "screens/home_screen.dart";
import "screens/orders_screen.dart";
import "screens/sell_screen.dart";
import "services/api_client.dart";

void main() {
  runApp(const AgentMarketplaceApp());
}

class AgentMarketplaceApp extends StatefulWidget {
  const AgentMarketplaceApp({super.key});

  @override
  State<AgentMarketplaceApp> createState() => _AgentMarketplaceAppState();
}

class _AgentMarketplaceAppState extends State<AgentMarketplaceApp> {
  int index = 0;
  final apiClient = ApiClient();

  @override
  Widget build(BuildContext context) {
    final screens = [
      HomeScreen(apiClient: apiClient),
      SellScreen(apiClient: apiClient),
      const OrdersScreen(),
    ];

    return MaterialApp(
      title: "Agent Marketplace",
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        colorScheme: ColorScheme.fromSeed(
          seedColor: const Color(0xFF0F4C5C),
          brightness: Brightness.light,
        ),
        scaffoldBackgroundColor: const Color(0xFFF6F1E9),
        useMaterial3: true,
      ),
      home: Scaffold(
        appBar: AppBar(
          title: const Text("Agent Marketplace"),
          centerTitle: false,
        ),
        body: screens[index],
        bottomNavigationBar: NavigationBar(
          selectedIndex: index,
          onDestinationSelected: (value) => setState(() => index = value),
          destinations: const [
            NavigationDestination(icon: Icon(Icons.storefront_outlined), label: "Browse"),
            NavigationDestination(icon: Icon(Icons.auto_awesome_outlined), label: "Sell"),
            NavigationDestination(icon: Icon(Icons.receipt_long_outlined), label: "Orders"),
          ],
        ),
      ),
    );
  }
}
