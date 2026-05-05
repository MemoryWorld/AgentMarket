import "package:flutter/material.dart";

import "../models/listing.dart";
import "../services/api_client.dart";

class HomeScreen extends StatelessWidget {
  const HomeScreen({super.key, required this.apiClient});

  final ApiClient apiClient;

  @override
  Widget build(BuildContext context) {
    return FutureBuilder<List<ListingSummary>>(
      future: apiClient.fetchListings(),
      builder: (context, snapshot) {
        final items = snapshot.data ?? const <ListingSummary>[];
        return ListView(
          padding: const EdgeInsets.all(20),
          children: [
            const Text(
              "Public listings",
              style: TextStyle(fontSize: 28, fontWeight: FontWeight.w700),
            ),
            const SizedBox(height: 12),
            const Text(
              "This feed is intentionally crawlable on the web, while write actions stay authenticated.",
              style: TextStyle(height: 1.45),
            ),
            const SizedBox(height: 20),
            for (final item in items)
              Card(
                shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(24)),
                child: ListTile(
                  contentPadding: const EdgeInsets.all(18),
                  title: Text(item.title),
                  subtitle: Text("${item.citySlug} • ${item.currencyCode} ${(item.askingPriceCents / 100).toStringAsFixed(0)}"),
                ),
              ),
          ],
        );
      },
    );
  }
}
